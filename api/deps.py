"""
FastAPI dependency providers.
"""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from config.settings import Settings

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


async def get_current_user(
    token: Annotated[str, Depends(_oauth2_scheme)],
    settings: Settings = Depends(get_settings),
) -> dict:
    from api.auth import decode_access_token
    from api.services import user_service

    payload = decode_access_token(token, settings)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username: str = payload.get("sub", "")
    user = user_service.get_user_by_username(username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
