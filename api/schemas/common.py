from pydantic import BaseModel
from typing import Any, Optional


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None


class OkResponse(BaseModel):
    ok: bool = True
    message: Optional[str] = None
