from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api._common import iso, ok
from db.models import DesignRunRow, SessionRow
from db.session import get_session
from domain.api import SessionCreated, SessionCreateRequest, SessionSummary

router = APIRouter(prefix="/api")


@router.post("/sessions")
def create_session(req: SessionCreateRequest, session: Session = Depends(get_session)) -> dict:
    row = SessionRow(title=(req.title or "").strip())
    session.add(row)
    session.flush()
    return ok(
        SessionCreated(
            session_id=row.id, title=row.title, created_at=iso(row.created_at)
        ).model_dump()
    )


@router.get("/sessions")
def list_sessions(session: Session = Depends(get_session)) -> dict:
    stmt = (
        select(
            SessionRow,
            func.count(DesignRunRow.id),
            func.coalesce(func.sum(DesignRunRow.prompt_tokens), 0),
            func.coalesce(func.sum(DesignRunRow.completion_tokens), 0),
            func.coalesce(func.sum(DesignRunRow.cost_usd), 0.0),
        )
        .outerjoin(DesignRunRow, DesignRunRow.session_id == SessionRow.id)
        .group_by(SessionRow.id)
        .order_by(SessionRow.created_at.desc())
    )
    sessions = [
        SessionSummary(
            session_id=row.id,
            title=row.title,
            created_at=iso(row.created_at),
            run_count=run_count,
            total_prompt_tokens=prompt_tokens,
            total_completion_tokens=completion_tokens,
            total_cost_usd=cost_usd,
        ).model_dump()
        for row, run_count, prompt_tokens, completion_tokens, cost_usd in session.execute(stmt)
    ]
    return ok({"sessions": sessions})
