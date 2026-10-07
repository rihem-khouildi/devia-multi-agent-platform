"""
User management service — supports DB and in-memory fallback.
"""

from typing import Optional, Dict, Any
from api.db import session_scope, is_database_ready
from api.db_models import UserModel
from api.auth import hash_password, verify_password
from utils.logger import get_logger

logger = get_logger(__name__)

# In-memory fallback: username -> record
_users_mem: Dict[str, Dict[str, Any]] = {}
_users_by_email: Dict[str, str] = {}  # email -> username


def create_user(username: str, email: str, plain_password: str) -> Dict[str, Any]:
    hashed = hash_password(plain_password)

    if is_database_ready():
        with session_scope() as session:
            if session is None:
                raise RuntimeError("Database session unavailable")
            user = UserModel(username=username, email=email, hashed_password=hashed)
            session.add(user)
            session.flush()
            return {"id": user.id, "username": user.username, "email": user.email}

    # In-memory fallback
    record = {"id": len(_users_mem) + 1, "username": username, "email": email, "hashed_password": hashed, "is_active": True}
    _users_mem[username] = record
    _users_by_email[email] = username
    return {"id": record["id"], "username": username, "email": email}


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    if is_database_ready():
        with session_scope() as session:
            if session is None:
                return None
            user = session.query(UserModel).filter_by(username=username).first()
            if not user:
                return None
            return {"id": user.id, "username": user.username, "email": user.email, "hashed_password": user.hashed_password, "is_active": user.is_active}

    return _users_mem.get(username)


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    if is_database_ready():
        with session_scope() as session:
            if session is None:
                return None
            user = session.query(UserModel).filter_by(email=email).first()
            if not user:
                return None
            return {"id": user.id, "username": user.username, "email": user.email, "hashed_password": user.hashed_password, "is_active": user.is_active}

    username = _users_by_email.get(email)
    return _users_mem.get(username) if username else None


def authenticate_user(username: str, plain_password: str) -> Optional[Dict[str, Any]]:
    user = get_user_by_username(username)
    if not user:
        return None
    if not verify_password(plain_password, user["hashed_password"]):
        return None
    return user
