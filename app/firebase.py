import json
import os
from typing import Any, Dict

from dotenv import load_dotenv


load_dotenv()


def _load_service_account_info() -> Dict[str, Any]:
    raw_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    file_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_FILE")

    if raw_json:
        try:
            return json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON") from exc

    if file_path:
        if not os.path.exists(file_path):
            raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_FILE path does not exist")
        with open(file_path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    raise RuntimeError(
        "Missing Firebase credentials: set FIREBASE_SERVICE_ACCOUNT_JSON or FIREBASE_SERVICE_ACCOUNT_FILE"
    )


def initialize_firebase() -> bool:
    try:
        import firebase_admin
        from firebase_admin import credentials
    except ModuleNotFoundError as exc:
        raise RuntimeError("firebase-admin is not installed. Run: pip install firebase-admin") from exc

    if firebase_admin._apps:
        return True

    service_account_info = _load_service_account_info()
    cred = credentials.Certificate(service_account_info)
    firebase_admin.initialize_app(cred)
    return True
