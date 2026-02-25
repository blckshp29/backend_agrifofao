import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import random
from jose import JWTError, jwt
from passlib.context import CryptContext
from typing import Optional

from ..database import get_db
from ..models import User, OtpCode
from ..schemas import UserCreate, User as UserSchema, Token, UserLogin, OtpRequest, OtpVerify, OtpResponse

router = APIRouter()

# Security
SECRET_KEY = "your-secret-key-here"  # Change in production!
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/token")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    # bcrypt.checkpw expects bytes
    return bcrypt.checkpw(
        plain_password.encode('utf-8'), 
        hashed_password.encode('utf-8')
    )

def get_password_hash(password: str) -> str:
    # Generate salt and hash the password
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def authenticate_user(db: Session, identifier: str, password: str):
    user = db.query(User).filter(
        (User.username == identifier) | (User.email == identifier) | (User.mobile_number == identifier)
    ).first()
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        print(f"DEBUG: Username from token: {username}")
        if username is None:
            print("DEBUG: Sub key is missing!")
            raise credentials_exception
    except JWTError as error:
        print(f"DEBUG: JWT Decode failed: {error}")
        raise credentials_exception
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user

@router.post("/register", response_model=UserSchema)
def register(user: UserCreate, db: Session = Depends(get_db)):
    print("DEBUG: Register endpoint hit!") # <--- Add this
    # Check if user exists
    db_user = db.query(User).filter(User.username == user.username).first()
    print(f"DEBUG: Found user: {db_user}") # <--- Add this
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    # Check if email exists
    db_email = db.query(User).filter(User.email == user.email).first()
    if db_email:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Check if mobile number exists
    if user.mobile_number:
        db_mobile = db.query(User).filter(User.mobile_number == user.mobile_number).first()
        if db_mobile:
            raise HTTPException(status_code=400, detail="Mobile number already registered")
    
    # Create new user
    hashed_password = get_password_hash(user.password)
    db_user = User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password,
        full_name=user.full_name,
        farm_name=user.farm_name,
        sex=user.sex,
        location=user.location,
        province=user.province,
        city_municipality=user.city_municipality,
        barangay=user.barangay,
        mobile_number=user.mobile_number,
        birthdate=user.birthdate
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return db_user

@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user.last_login_at = datetime.utcnow()
    db.commit()
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/users/me", response_model=UserSchema)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

# --- DEV-ONLY OTP FLOW ---
@router.post("/otp/request", response_model=OtpResponse)
def request_otp(payload: OtpRequest, db: Session = Depends(get_db)):
    code = f"{random.randint(0, 999999):06d}"
    expires_at = datetime.utcnow() + timedelta(minutes=10)

    otp = OtpCode(
        channel=payload.channel.value,
        destination=payload.destination,
        code=code,
        expires_at=expires_at
    )
    db.add(otp)
    db.commit()

    # DEV-ONLY: return the code so frontend can display or test
    return {"success": True, "message": f"OTP generated: {code}"}

@router.post("/otp/verify", response_model=OtpResponse)
def verify_otp(payload: OtpVerify, db: Session = Depends(get_db)):
    otp = db.query(OtpCode).filter(
        OtpCode.channel == payload.channel.value,
        OtpCode.destination == payload.destination,
        OtpCode.code == payload.code,
        OtpCode.verified_at.is_(None)
    ).order_by(OtpCode.created_at.desc()).first()

    if not otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    if otp.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="OTP expired")

    otp.verified_at = datetime.utcnow()

    # Mark user verified if exists
    user = None
    if payload.channel.value == "email":
        user = db.query(User).filter(User.email == payload.destination).first()
        if user:
            user.email_verified = True
    elif payload.channel.value == "sms":
        user = db.query(User).filter(User.mobile_number == payload.destination).first()
        if user:
            user.phone_verified = True

    db.commit()
    return {"success": True, "message": "OTP verified"}
