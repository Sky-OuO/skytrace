"""题材须知和待核实条目。

Revision ID: 0003_subject_notices
Revises: 0002_topics
Create Date: 2026-11-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_subject_notices"
down_revision: Union[str, Sequence[str], None] = "0002_topics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONB = postgresql.JSONB()


def upgrade() -> None:
    op.add_column("subjects", sa.Column("notices", JSONB, nullable=True))
    op.add_column("subjects", sa.Column("pending_verify", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("subjects", "pending_verify")
    op.drop_column("subjects", "notices")
