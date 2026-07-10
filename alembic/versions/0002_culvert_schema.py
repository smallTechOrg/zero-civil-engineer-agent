"""culvert schema — sessions/design_runs/artifacts/presets, drop legacy runs, seed default preset

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-10 00:00:00.000000

"""
import json
from datetime import datetime, timezone
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The engine's non-critical defaults per spec/data.md — the seeded "IR standard defaults" preset.
_DEFAULT_PRESET_VALUES = {
    "concrete_grade": "M30",
    "steel_grade": "Fe500",
    "clear_cover_mm": 50,
    "soil_unit_weight_kn_m3": 18.0,
    "angle_of_friction_deg": 30.0,
    "formation_width_m": 6.85,
    "side_slope_h_per_v": 2.0,
    "haunch_mm": 150,
}


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "design_runs",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("plan_text", sa.Text(), nullable=True),
        sa.Column("scope_message", sa.Text(), nullable=True),
        sa.Column("clarification_question", sa.Text(), nullable=True),
        sa.Column("params_json", sa.Text(), nullable=True),
        sa.Column("assumptions_json", sa.Text(), nullable=True),
        sa.Column("warnings_json", sa.Text(), nullable=True),
        sa.Column("steps_json", sa.Text(), nullable=True),
        sa.Column("checks_json", sa.Text(), nullable=True),
        sa.Column("checklist_json", sa.Text(), nullable=True),
        sa.Column("verdict", sa.Text(), nullable=True),
        sa.Column("suggestions_json", sa.Text(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "artifacts",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("mime", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["design_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "presets",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("values_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # The transform_text capability the legacy skeleton table served is replaced.
    op.drop_table("runs")

    now = datetime.now(timezone.utc)
    presets = sa.table(
        "presets",
        sa.column("id", sa.Text()),
        sa.column("name", sa.Text()),
        sa.column("is_default", sa.Boolean()),
        sa.column("values_json", sa.Text()),
        sa.column("created_at", sa.TIMESTAMP(timezone=True)),
        sa.column("updated_at", sa.TIMESTAMP(timezone=True)),
    )
    op.bulk_insert(
        presets,
        [
            {
                "id": str(uuid4()),
                "name": "IR standard defaults",
                "is_default": True,
                "values_json": json.dumps(_DEFAULT_PRESET_VALUES),
                "created_at": now,
                "updated_at": now,
            }
        ],
    )


def downgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("input_text", sa.Text(), nullable=True),
        sa.Column("output_text", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.drop_table("artifacts")
    op.drop_table("design_runs")
    op.drop_table("sessions")
    op.drop_table("presets")
