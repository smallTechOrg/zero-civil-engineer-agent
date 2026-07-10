"""DB persistence for design runs — the graph's only write path to the audit trail.

`db.models` is imported lazily inside every function: the graph must compile and
unit-test without the DB layer (spec/data.md is normative for the schema).
"""

import json
from datetime import datetime, timezone

MESSAGE_TURN_LIMIT = 20  # context guard per spec/agent.md — sessions are short


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_run_row(session_id: str, prompt: str) -> str:
    """Insert the run row (status "running", started_at now) and return its id."""
    from db.models import DesignRunRow
    from db.session import create_db_session

    with create_db_session() as session:
        row = DesignRunRow(session_id=session_id, prompt=prompt, status="running")
        session.add(row)
        session.flush()
        return row.id


def load_messages(session_id: str, *, exclude_run_id: str | None = None) -> list[dict]:
    """Rebuild the session conversation: last ≤20 turns, prompt + outcome per turn."""
    from db.models import DesignRunRow
    from db.session import create_db_session

    with create_db_session() as session:
        rows = (
            session.query(DesignRunRow)
            .filter(DesignRunRow.session_id == session_id)
            .order_by(DesignRunRow.started_at.asc())
            .all()
        )
        turns = [row for row in rows if row.id != exclude_run_id][-MESSAGE_TURN_LIMIT:]
        messages: list[dict] = []
        for row in turns:
            messages.append({"role": "user", "content": row.prompt})
            reply = _assistant_reply(row)
            if reply:
                messages.append({"role": "assistant", "content": reply})
        return messages


def _assistant_reply(row) -> str | None:
    if row.status == "completed":
        parts = [f"[completed] {row.plan_text or 'Design completed.'}"]
        if row.params_json:
            parts.append(f"Adopted parameters: {row.params_json}")
        return "\n".join(parts)
    if row.status == "needs_input":
        return f"[needs_input] Asked the user: {row.clarification_question}"
    if row.status == "out_of_scope":
        return f"[out_of_scope] {row.scope_message or 'The request was out of scope.'}"
    if row.status == "failed":
        return f"[failed] {row.error_message or 'The run failed.'}"
    return None  # still running — no outcome yet


def load_prior_params(session_id: str, *, exclude_run_id: str | None = None) -> dict | None:
    """params_json of the session's most recent COMPLETED run, if any."""
    from db.models import DesignRunRow
    from db.session import create_db_session

    with create_db_session() as session:
        rows = (
            session.query(DesignRunRow)
            .filter(
                DesignRunRow.session_id == session_id,
                DesignRunRow.status == "completed",
            )
            .order_by(DesignRunRow.started_at.desc())
            .all()
        )
        for row in rows:
            if row.id != exclude_run_id and row.params_json:
                return json.loads(row.params_json)
        return None


def load_preset_values(preset_id: str | None) -> dict:
    """Values of the named preset, else the default preset, else {}."""
    from db.models import PresetRow
    from db.session import create_db_session

    with create_db_session() as session:
        if preset_id:
            row = session.get(PresetRow, preset_id)
        else:
            row = (
                session.query(PresetRow)
                .filter(PresetRow.is_default.is_(True))
                .first()
            )
        if row is None or not row.values_json:
            return {}
        return json.loads(row.values_json)


def record_artifact(run_id: str, kind: str, filename: str, mime: str, size_bytes: int) -> None:
    from db.models import ArtifactRow
    from db.session import create_db_session

    with create_db_session() as session:
        session.add(
            ArtifactRow(
                run_id=run_id, kind=kind, filename=filename, mime=mime, size_bytes=size_bytes
            )
        )


def session_cost_sum(session_id: str) -> float:
    """SUM(cost_usd) over the session's persisted runs — session totals are derived."""
    from sqlalchemy import func, select

    from db.models import DesignRunRow
    from db.session import create_db_session

    with create_db_session() as session:
        total = session.execute(
            select(func.coalesce(func.sum(DesignRunRow.cost_usd), 0.0)).where(
                DesignRunRow.session_id == session_id
            )
        ).scalar_one()
        return float(total)


def finish_run(
    run_id: str,
    *,
    status: str,
    component_type: str | None = None,
    error_message: str | None = None,
    clarification_question: str | None = None,
    plan_text: str | None = None,
    scope_message: str | None = None,
    params: dict | None = None,
    assumptions: list[dict] | None = None,
    warnings: list[str] | None = None,
    steps: list[dict] | None = None,
    checks: list[dict] | None = None,
    checklist: list[dict] | None = None,
    verdict: str | None = None,
    type_summary: dict | None = None,
    suggestions: list[str] | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cost_usd: float = 0.0,
    duration_ms: int | None = None,
) -> None:
    """Persist a run's terminal record (completed / out_of_scope / needs_input / failed)."""
    from db.models import DesignRunRow
    from db.session import create_db_session

    with create_db_session() as session:
        row = session.get(DesignRunRow, run_id)
        if row is None:
            raise RuntimeError(f"design run {run_id} not found while persisting {status}")
        row.status = status
        if component_type is not None:
            row.component_type = component_type
        row.error_message = error_message
        row.clarification_question = clarification_question
        row.plan_text = plan_text
        row.scope_message = scope_message
        row.params_json = json.dumps(params) if params is not None else None
        row.assumptions_json = json.dumps(assumptions) if assumptions is not None else None
        row.warnings_json = json.dumps(warnings) if warnings is not None else None
        row.steps_json = json.dumps(steps) if steps is not None else None
        row.checks_json = json.dumps(checks) if checks is not None else None
        row.checklist_json = json.dumps(checklist) if checklist is not None else None
        row.verdict = verdict
        row.type_summary_json = (
            json.dumps(type_summary) if type_summary is not None else None
        )
        # Completed runs persist their (possibly empty) suggestions honestly;
        # non-completed terminals stay NULL → the snapshot serves [].
        row.suggestions_json = json.dumps(suggestions) if suggestions is not None else None
        row.prompt_tokens = prompt_tokens
        row.completion_tokens = completion_tokens
        row.cost_usd = cost_usd
        row.completed_at = _now()
        row.duration_ms = duration_ms
