"""component platform — add component_type + type_summary_json to design_runs

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-11 00:00:00.000000

Expansion Phase 1 (multi-domain component platform): the shared-core pipeline
now dispatches every engineering step to a selected Component Module. Each run
records which component type it designed and (for completed runs) the module's
type-specific summary. No table is dropped; the schema stays component-agnostic
(params/geometry remain component-specific JSON, artefact `kind` is the shared
fixed set). Existing rows backfill `component_type` to `box_culvert`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite can't add a NOT NULL column without a default; add nullable with a
    # server_default, backfill, then drop the default via batch alter so the
    # ORM's NOT NULL/default contract holds going forward.
    with op.batch_alter_table("design_runs") as batch:
        batch.add_column(
            sa.Column(
                "component_type",
                sa.Text(),
                nullable=False,
                server_default="box_culvert",
            )
        )
        batch.add_column(sa.Column("type_summary_json", sa.Text(), nullable=True))

    # Backfill is covered by the server_default for existing rows; make the
    # default application-managed (matches the ORM model) going forward.
    with op.batch_alter_table("design_runs") as batch:
        batch.alter_column("component_type", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("design_runs") as batch:
        batch.drop_column("type_summary_json")
        batch.drop_column("component_type")
