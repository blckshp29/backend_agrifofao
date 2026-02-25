from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta

from .. import models, schemas
from ..database import get_db
from ..models import FinancialRecord, User, Field as FieldModel, CropProject
from ..schemas import (
    FinancialRecordCreate,
    FinancialRecord as FinancialRecordSchema,
    CropProjectCreate,
    CropProjectUpdate,
    CropProject as CropProjectSchema,
)
from ..financial.partial_budgeting import PartialBudgeting
from ..schemas import PartialBudgetingInput, PartialBudgetingResponse
from .auth import get_current_user

router = APIRouter()
partial_budgeting = PartialBudgeting()

@router.post("/financial/records", response_model=FinancialRecordSchema)
def create_financial_record(
    record: FinancialRecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    record_data = record.model_dump()
    db_record = FinancialRecord(**record_data, owner_id=current_user.id, user_id=current_user.id)
    
    # Update project budget and totals if linked
    if record.project_id:
        project = db.query(CropProject).filter(
            CropProject.id == record.project_id,
            CropProject.owner_id == current_user.id
        ).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        db_record.budget_snapshot = project.budget_remaining if project.budget_remaining is not None else project.budget_total
        
        transaction_type = record.transaction_type.value if hasattr(record.transaction_type, "value") else record.transaction_type
        if transaction_type == "expense":
            if project.budget_remaining is None:
                project.budget_remaining = project.budget_total or 0
            if record.amount > (project.budget_remaining or 0):
                if not record.over_budget_approved:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "message": "Expense exceeds remaining budget. Confirm to proceed.",
                            "budget_remaining": project.budget_remaining or 0,
                            "expense_amount": record.amount
                        }
                    )
                db_record.is_over_budget = True
                db_record.over_budget_approved = True
            project.expense_total = (project.expense_total or 0) + record.amount
            project.budget_remaining = (project.budget_remaining or 0) - record.amount
        elif transaction_type == "income":
            project.income_total = (project.income_total or 0) + record.amount

    db.add(db_record)
    db.commit()
    db.refresh(db_record)
    return db_record

@router.post("/financial/records/confirm-over-budget", response_model=FinancialRecordSchema)
def confirm_over_budget_record(
    record: FinancialRecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not record.project_id:
        raise HTTPException(status_code=400, detail="project_id is required for over-budget confirmation")
    record.over_budget_approved = True
    return create_financial_record(record, db, current_user)

@router.get("/financial/insights/summary", response_model=schemas.InsightSummary)
def get_financial_insight_summary(
    project_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if project_id:
        project = db.query(CropProject).filter(
            CropProject.id == project_id,
            CropProject.owner_id == current_user.id
        ).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        budget_total = project.budget_total or 0
        expenses_total = project.expense_total or 0
        income_total = project.income_total or 0
    else:
        budget_total = db.query(CropProject).filter(
            CropProject.owner_id == current_user.id
        ).with_entities(CropProject.budget_total).all()
        budget_total = sum(b[0] or 0 for b in budget_total)
        expenses_total = db.query(FinancialRecord).filter(
            FinancialRecord.owner_id == current_user.id,
            FinancialRecord.transaction_type == "expense"
        ).with_entities(FinancialRecord.amount).all()
        expenses_total = sum(e[0] or 0 for e in expenses_total)
        income_total = db.query(FinancialRecord).filter(
            FinancialRecord.owner_id == current_user.id,
            FinancialRecord.transaction_type == "income"
        ).with_entities(FinancialRecord.amount).all()
        income_total = sum(i[0] or 0 for i in income_total)

    net_profit = income_total - expenses_total
    max_value = max(budget_total, expenses_total, income_total, 1)

    def bar(label: str, value: float):
        return {"label": label, "percent": (value / max_value) * 100, "value": value}

    return {
        "budget_total": budget_total,
        "expenses_total": expenses_total,
        "income_total": income_total,
        "net_profit": net_profit,
        "is_over_budget": expenses_total > budget_total,
        "budget_bar": bar("Budget", budget_total),
        "expenses_bar": bar("Expenses", expenses_total),
        "income_bar": bar("Income", income_total),
    }

@router.get("/financial/insights/compare", response_model=schemas.InsightComparison)
def compare_financial_insights(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    projects = db.query(CropProject).filter(
        CropProject.owner_id == current_user.id
    ).order_by(CropProject.start_date.desc().nullslast(), CropProject.created_at.desc()).limit(2).all()

    if len(projects) < 2:
        raise HTTPException(status_code=400, detail="Not enough projects to compare")

    current = projects[0]
    previous = projects[1]

    def to_percent(expenses: float, net_profit: float):
        base = max(expenses + max(net_profit, 0), 1)
        expenses_percent = (expenses / base) * 100
        netprofit_percent = (max(net_profit, 0) / base) * 100
        return expenses_percent, netprofit_percent

    prev_exp_p, prev_np_p = to_percent(previous.expense_total or 0, (previous.income_total or 0) - (previous.expense_total or 0))
    cur_exp_p, cur_np_p = to_percent(current.expense_total or 0, (current.income_total or 0) - (current.expense_total or 0))

    return {
        "previous_label": previous.name,
        "current_label": current.name,
        "previous_expenses_percent": prev_exp_p,
        "current_expenses_percent": cur_exp_p,
        "previous_netprofit_percent": prev_np_p,
        "current_netprofit_percent": cur_np_p
    }

@router.get("/financial/records", response_model=List[FinancialRecordSchema])
def get_financial_records(
    start_date: datetime = None,
    end_date: datetime = None,
    category: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(FinancialRecord).filter(FinancialRecord.owner_id == current_user.id)
    
    if start_date:
        query = query.filter(FinancialRecord.date >= start_date)
    if end_date:
        query = query.filter(FinancialRecord.date <= end_date)
    if category:
        query = query.filter(FinancialRecord.category == category)
    
    records = query.order_by(FinancialRecord.date.desc()).all()
    return records

@router.get("/financial/summary")
def get_financial_summary(
    start_date: datetime = None,
    end_date: datetime = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not start_date:
        start_date = datetime.now() - timedelta(days=30)
    if not end_date:
        end_date = datetime.now()
    
    records = db.query(FinancialRecord).filter(
        FinancialRecord.owner_id == current_user.id,
        FinancialRecord.date >= start_date,
        FinancialRecord.date <= end_date
    ).all()

    # DEBUG PRINT: Check your terminal! 
    # This will tell us if the query found anything at all.
    print(f"DEBUG: Found {len(records)} records for user {current_user.id} in this date range.")

    total_income = 0
    total_expenses = 0
    categories = {}

    for r in records:
        # Normalize to UPPERCASE to avoid "income" vs "INCOME" errors
        t_type = r.transaction_type.upper() if r.transaction_type else ""
        
        if t_type == "INCOME":
            total_income += r.amount
        elif t_type == "EXPENSE":
            total_expenses += r.amount

        # Category logic
        if r.category not in categories:
            categories[r.category] = {"INCOME": 0, "EXPENSE": 0}
        categories[r.category][t_type if t_type in ["INCOME", "EXPENSE"] else "EXPENSE"] += r.amount
    
    net_profit = total_income - total_expenses
    
    return {
        "period": {"start_date": start_date, "end_date": end_date},
        "total_income": total_income,
        "total_expenses": total_expenses,
        "net_profit": net_profit,
        "profit_margin": (net_profit / total_income * 100) if total_income > 0 else 0,
        "category_breakdown": categories
    }

@router.post("/financial/partial-budgeting", response_model=PartialBudgetingResponse)
def calculate_partial_budgeting(
    input_data: PartialBudgetingInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return partial_budgeting.calculate_net_benefit(input_data)

@router.get("/financial/net-financial-return/{field_id}")
def calculate_net_financial_return(
    field_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from ..decision_tree.engine import DecisionTreeEngine
    
    decision_tree = DecisionTreeEngine()
    
    # Get field
    field = db.query(FieldModel).filter(
        FieldModel.id == field_id,
        FieldModel.owner_id == current_user.id
    ).first()
    
    if not field:
        raise HTTPException(status_code=404, detail="Field not found")
    
    # Get financial records for this field
    financial_records = db.query(FinancialRecord).filter(
        FinancialRecord.field_id == field_id,
        FinancialRecord.owner_id == current_user.id
    ).all()
    
    total_costs = sum(r.amount for r in financial_records if r.transaction_type == "expense")
    
    # Estimate yield value (simplified)
    base_yields = {
        "coconut": 50000,
        "corn": 30000,
        "rice": 40000  
    }
    
    base_yield = base_yields.get(field.crop_type.value, 20000)
    predicted_yield_value = base_yield * field.area_hectares
    
    net_financial_return = decision_tree.calculate_net_financial_return(
        predicted_yield_value, total_costs
    )
    
    return {
        "field_id": field_id,
        "crop_type": field.crop_type.value,
        "area_hectares": field.area_hectares,
        "predicted_yield_value": predicted_yield_value,
        "total_costs": total_costs,
        "net_financial_return": net_financial_return,
        "roi": (net_financial_return / total_costs * 100) if total_costs > 0 else 0
    }

# Use .put for full updates or .patch for partial updates
@router.put("/financial/records/{record_id}", response_model=schemas.FinancialRecord)
def update_record(
    record_id: int, 
    updated_data: schemas.FinancialRecordCreate, # The new data from Postman
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # 1. Find the record
    query = db.query(models.FinancialRecord).filter(models.FinancialRecord.id == record_id)
    db_record = query.first()

    # 2. Check if it exists
    if not db_record:
        raise HTTPException(status_code=404, detail="Record not found")

    # 3. Security Check: Does this record belong to the logged-in user?
    if db_record.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this record")

    # 4. Update the fields
    query.update(updated_data.model_dump(), synchronize_session=False)
    db.commit()
    
    return query.first()

@router.delete("/financial/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_record(
    record_id: int, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    query = db.query(models.FinancialRecord).filter(models.FinancialRecord.id == record_id)
    db_record = query.first()

    if not db_record:
        raise HTTPException(status_code=404, detail="Record not found")
        
    if db_record.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    query.delete(synchronize_session=False)
    db.commit()
    return None # 204 No Content doesn't return a body

# --- Crop Projects ---
@router.post("/financial/projects", response_model=CropProjectSchema)
def create_project(
    project: CropProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    data = project.model_dump()
    budget_total = data.get("budget_total") or 0
    db_project = CropProject(
        **data,
        owner_id=current_user.id,
        budget_remaining=budget_total
    )
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project

@router.get("/financial/projects", response_model=List[CropProjectSchema])
def list_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return db.query(CropProject).filter(CropProject.owner_id == current_user.id).all()

@router.get("/financial/projects/{project_id}", response_model=CropProjectSchema)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    project = db.query(CropProject).filter(
        CropProject.id == project_id,
        CropProject.owner_id == current_user.id
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@router.patch("/financial/projects/{project_id}", response_model=CropProjectSchema)
def update_project(
    project_id: int,
    payload: CropProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(CropProject).filter(
        CropProject.id == project_id,
        CropProject.owner_id == current_user.id
    )
    project = query.first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    query.update(payload.model_dump(exclude_unset=True), synchronize_session=False)
    db.commit()
    return query.first()

@router.delete("/financial/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(CropProject).filter(
        CropProject.id == project_id,
        CropProject.owner_id == current_user.id
    )
    if not query.first():
        raise HTTPException(status_code=404, detail="Project not found")
    query.delete(synchronize_session=False)
    db.commit()
    return None
