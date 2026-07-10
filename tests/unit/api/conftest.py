"""Shared helpers for API contract tests — synthetic rows, SSE frame parsing."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session


@pytest.fixture
def make_session_row(_isolated_db):
    def _make(title: str = "", created_at: datetime | None = None) -> str:
        from db.models import SessionRow

        with Session(_isolated_db) as s:
            row = SessionRow(title=title)
            if created_at is not None:
                row.created_at = created_at
                row.updated_at = created_at
            s.add(row)
            s.commit()
            return row.id

    return _make


@pytest.fixture
def make_run_row(_isolated_db):
    def _make(session_id: str, **overrides) -> str:
        from db.models import DesignRunRow

        with Session(_isolated_db) as s:
            row = DesignRunRow(
                session_id=session_id,
                prompt=overrides.pop("prompt", "single box culvert, 4 m span"),
                status=overrides.pop("status", "completed"),
            )
            for key, value in overrides.items():
                setattr(row, key, value)
            s.add(row)
            s.commit()
            return row.id

    return _make


@pytest.fixture
def make_preset_row(_isolated_db):
    def _make(
        name: str = "IR standard defaults",
        is_default: bool = True,
        values: dict | None = None,
        updated_at: datetime | None = None,
    ) -> str:
        from db.models import PresetRow

        with Session(_isolated_db) as s:
            row = PresetRow(
                name=name,
                is_default=is_default,
                values_json=json.dumps(values if values is not None else {"clear_cover_mm": 50}),
            )
            if updated_at is not None:
                row.created_at = updated_at
                row.updated_at = updated_at
            s.add(row)
            s.commit()
            return row.id

    return _make


@pytest.fixture
def make_artifact_row(_isolated_db):
    def _make(run_id: str, kind: str, filename: str, mime: str, size_bytes: int = 100) -> str:
        from db.models import ArtifactRow

        with Session(_isolated_db) as s:
            row = ArtifactRow(
                run_id=run_id, kind=kind, filename=filename, mime=mime, size_bytes=size_bytes
            )
            s.add(row)
            s.commit()
            return row.id

    return _make


def _utc(offset_seconds: int = 0) -> datetime:
    return datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc) + timedelta(
        seconds=offset_seconds
    )


@pytest.fixture
def utc():
    """Deterministic timestamp factory: utc(offset_seconds) -> aware datetime."""
    return _utc


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    frames = []
    for block in text.strip().split("\n\n"):
        event = None
        data_lines = []
        for line in block.split("\n"):
            if line.startswith("event: "):
                event = line[len("event: "):]
            elif line.startswith("data: "):
                data_lines.append(line[len("data: "):])
        frames.append((event, json.loads("\n".join(data_lines))))
    return frames


@pytest.fixture
def parse_sse():
    """Parse an SSE body into (event, data) tuples."""
    return _parse_sse
