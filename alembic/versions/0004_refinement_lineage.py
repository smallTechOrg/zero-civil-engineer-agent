"""refinement lineage — add root_run_id to design_runs

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-11 00:00:00.000000

Refinement lineage: a "design record" groups an original design and all its
refinements. `root_run_id` is a nullable self-referential FK on `design_runs`;
NULL means the run is its own record root (an original / new design), while a
refinement stores the root run_id of the record it belongs to. Grouping a
record's versions is then an O(1) lookup by root; version order is derived by
ordering a root-group on `started_at` (no parent/version columns). The column is
nullable TEXT, so a single add/drop needs no server_default; existing rows stay
NULL and remain their own record roots.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("design_runs") as batch:
        batch.add_column(sa.Column("root_run_id", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("design_runs") as batch:
        batch.drop_column("root_run_id")
