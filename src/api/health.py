from fastapi import APIRouter

from api._common import ok

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return ok({"status": "ok"})
