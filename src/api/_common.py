from datetime import datetime
from typing import Any

from fastapi import HTTPException


def ok(data: Any) -> dict:
    return {"data": data, "error": None}


def api_error(code: str, message: str, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
