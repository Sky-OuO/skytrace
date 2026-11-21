"""题材字段、地点示例，以及笔记上的示例外键。

Revision ID: 0002_topics
Revises: 0001_initial
Create Date: 2026-11-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_topics"
down_revision: Union[str, Sequence[str], None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()


def upgrade() -> None:
    op.add_column("subjects", sa.Column("tagline", sa.Text(), nullable=True))
    op.add_column(
        "subjects",
        sa.Column("aliases", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column("subjects", sa.Column("guide", JSONB, nullable=True))
    op.drop_constraint("ck_subjects_primary_channel", "subjects", type_="check")
    op.create_check_constraint(
        "ck_subjects_primary_channel",
        "subjects",
        "primary_channel IN ('landscape', 'portrait')",
    )
    op.create_table(
        "subject_examples",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("subject_id", UUID, sa.ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("geo_text", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("verify_status", sa.String(32), nullable=False, server_default="pending"),
        sa.CheckConstraint(
            "verify_status IN ('verified', 'pending')",
            name="ck_subject_examples_verify_status",
        ),
    )
    op.create_index("ix_subject_examples_subject_sort", "subject_examples", ["subject_id", "sort_order"])
    op.add_column(
        "notes",
        sa.Column("example_id", UUID, sa.ForeignKey("subject_examples.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_notes_example_id", "notes", ["example_id"])


def downgrade() -> None:
    op.drop_index("ix_notes_example_id", table_name="notes")
    op.drop_column("notes", "example_id")
    op.drop_index("ix_subject_examples_subject_sort", table_name="subject_examples")
    op.drop_table("subject_examples")
    op.drop_constraint("ck_subjects_primary_channel", "subjects", type_="check")
    op.create_check_constraint(
        "ck_subjects_primary_channel",
        "subjects",
        "primary_channel IN ('landscape', 'culture', 'portrait')",
    )
    op.drop_column("subjects", "guide")
    op.drop_column("subjects", "aliases")
    op.drop_column("subjects", "tagline")
