"""初始表、索引和搜索向量。

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-10

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()
TSVECTOR = postgresql.TSVECTOR()


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(1024), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="author"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint("role IN ('author', 'reviewer')", name="ck_users_role"),
    )
    op.create_table(
        "access_tokens",
        sa.Column("token", sa.String(64), primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_access_tokens_user_id", "access_tokens", ["user_id"])
    op.create_index("ix_access_tokens_created_at", "access_tokens", ["created_at"])

    op.create_table(
        "subjects",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("slug", sa.String(160), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("primary_channel", sa.String(32), nullable=False),
        sa.Column("condition_axes", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("geo_text", sa.Text(), nullable=True),
        sa.Column("safety_notes", sa.Text(), nullable=True),
        sa.Column("cover_media_id", UUID, nullable=True),
        sa.Column("guide_summary", sa.Text(), nullable=True),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("search_vector", TSVECTOR, nullable=True),
        sa.UniqueConstraint("slug", name="uq_subjects_slug"),
        sa.CheckConstraint("type IN ('location', 'scene', 'theme')", name="ck_subjects_type"),
        sa.CheckConstraint(
            "primary_channel IN ('landscape', 'culture', 'portrait')",
            name="ck_subjects_primary_channel",
        ),
    )
    op.create_index("ix_subjects_primary_channel_type", "subjects", ["primary_channel", "type"])

    op.create_table(
        "notes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("author_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("subject_id", UUID, sa.ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("fields", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("portrait_auth_accepted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("search_vector", TSVECTOR, nullable=True),
        sa.CheckConstraint(
            "type IN ('finished', 'spot', 'pre', 'post', 'lighting', 'posing')",
            name="ck_notes_type",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'pending_review', 'approved', 'rejected')",
            name="ck_notes_status",
        ),
    )
    op.create_index("ix_notes_subject_id_type_status", "notes", ["subject_id", "type", "status"])
    op.create_index(
        "ix_notes_approved",
        "notes",
        ["subject_id", "type", "published_at"],
        postgresql_where=sa.text("status = 'approved'"),
    )

    op.create_table(
        "media",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("mime", sa.String(100), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("role", sa.String(32), nullable=False, server_default="photo"),
        sa.Column("alt", sa.Text(), nullable=True),
        sa.Column("note_id", UUID, sa.ForeignKey("notes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("subject_id", UUID, sa.ForeignKey("subjects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("storage_key", name="uq_media_storage_key"),
        sa.CheckConstraint("role IN ('cover', 'annotation', 'photo')", name="ck_media_role"),
    )
    op.create_foreign_key(
        "fk_subjects_cover_media_id",
        "subjects",
        "media",
        ["cover_media_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "review_tickets",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("note_id", UUID, sa.ForeignKey("notes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("submitter_id", UUID, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("reviewer_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="ck_review_tickets_status"),
    )
    op.create_index("ix_review_tickets_status_submitted_at", "review_tickets", ["status", "submitted_at"])

    op.create_table(
        "tags",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("facet", sa.String(32), nullable=False),
        sa.UniqueConstraint("slug", name="uq_tags_slug"),
        sa.CheckConstraint(
            "facet IN ('environment', 'style', 'season', 'time_of_day', 'weather', 'light')",
            name="ck_tags_facet",
        ),
    )
    op.create_index("ix_tags_facet", "tags", ["facet"])

    op.create_table(
        "subject_tags",
        sa.Column("subject_id", UUID, sa.ForeignKey("subjects.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", UUID, sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "note_tags",
        sa.Column("note_id", UUID, sa.ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", UUID, sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_index(
        "ix_subjects_search_vector",
        "subjects",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_notes_search_vector",
        "notes",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )
    for statement in _SEARCH_SQL:
        op.execute(statement)


def downgrade() -> None:
    for statement in (
        "DROP TRIGGER IF EXISTS trg_tags_search ON tags",
        "DROP TRIGGER IF EXISTS trg_note_tags_search ON note_tags",
        "DROP TRIGGER IF EXISTS trg_subject_tags_search ON subject_tags",
        "DROP TRIGGER IF EXISTS trg_notes_search_vector ON notes",
        "DROP TRIGGER IF EXISTS trg_subjects_search_vector ON subjects",
        "DROP FUNCTION IF EXISTS skytrace_tags_refresh_search()",
        "DROP FUNCTION IF EXISTS skytrace_touch_note_search()",
        "DROP FUNCTION IF EXISTS skytrace_touch_subject_search()",
        "DROP FUNCTION IF EXISTS skytrace_notes_search_trigger()",
        "DROP FUNCTION IF EXISTS skytrace_subjects_search_trigger()",
        "DROP FUNCTION IF EXISTS skytrace_note_search_vector(notes)",
        "DROP FUNCTION IF EXISTS skytrace_subject_search_vector(subjects)",
    ):
        op.execute(statement)
    op.drop_index("ix_notes_search_vector", table_name="notes")
    op.drop_index("ix_subjects_search_vector", table_name="subjects")
    op.drop_table("note_tags")
    op.drop_table("subject_tags")
    op.drop_index("ix_tags_facet", table_name="tags")
    op.drop_table("tags")
    op.drop_index("ix_review_tickets_status_submitted_at", table_name="review_tickets")
    op.drop_table("review_tickets")
    op.drop_constraint("fk_subjects_cover_media_id", "subjects", type_="foreignkey")
    op.drop_table("media")
    op.drop_index("ix_notes_approved", table_name="notes")
    op.drop_index("ix_notes_subject_id_type_status", table_name="notes")
    op.drop_table("notes")
    op.drop_index("ix_subjects_primary_channel_type", table_name="subjects")
    op.drop_table("subjects")
    op.drop_index("ix_access_tokens_created_at", table_name="access_tokens")
    op.drop_index("ix_access_tokens_user_id", table_name="access_tokens")
    op.drop_table("access_tokens")
    op.drop_table("users")


_SEARCH_SQL = (
    """
    CREATE FUNCTION skytrace_subject_search_vector(subject_row subjects)
    RETURNS tsvector
    LANGUAGE sql
    STABLE
    AS $$
      SELECT
        setweight(to_tsvector('simple', coalesce(subject_row.name, '')), 'A')
        || setweight(to_tsvector('simple', coalesce((
          SELECT string_agg(t.name, ' ')
          FROM subject_tags st
          JOIN tags t ON t.id = st.tag_id
          WHERE st.subject_id = subject_row.id
        ), '')), 'A');
    $$
    """,
    """
    CREATE FUNCTION skytrace_note_search_vector(note_row notes)
    RETURNS tsvector
    LANGUAGE sql
    STABLE
    AS $$
      SELECT
        setweight(to_tsvector('simple', coalesce(note_row.title, '')), 'A')
        || setweight(to_tsvector('simple', coalesce(note_row.body, '')), 'B')
        || setweight(to_tsvector('simple', coalesce((
          SELECT string_agg(t.name, ' ')
          FROM note_tags nt
          JOIN tags t ON t.id = nt.tag_id
          WHERE nt.note_id = note_row.id
        ), '')), 'A');
    $$
    """,
    """
    CREATE FUNCTION skytrace_subjects_search_trigger()
    RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    BEGIN
      NEW.search_vector := skytrace_subject_search_vector(NEW);
      RETURN NEW;
    END;
    $$
    """,
    """
    CREATE FUNCTION skytrace_notes_search_trigger()
    RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    BEGIN
      NEW.search_vector := skytrace_note_search_vector(NEW);
      RETURN NEW;
    END;
    $$
    """,
    """
    CREATE TRIGGER trg_subjects_search_vector
    BEFORE INSERT OR UPDATE ON subjects
    FOR EACH ROW
    EXECUTE FUNCTION skytrace_subjects_search_trigger()
    """,
    """
    CREATE TRIGGER trg_notes_search_vector
    BEFORE INSERT OR UPDATE ON notes
    FOR EACH ROW
    EXECUTE FUNCTION skytrace_notes_search_trigger()
    """,
    """
    CREATE FUNCTION skytrace_touch_subject_search()
    RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    DECLARE
      sid uuid;
    BEGIN
      sid := COALESCE(NEW.subject_id, OLD.subject_id);
      UPDATE subjects SET slug = slug WHERE id = sid;
      RETURN NULL;
    END;
    $$
    """,
    """
    CREATE FUNCTION skytrace_touch_note_search()
    RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    DECLARE
      nid uuid;
    BEGIN
      nid := COALESCE(NEW.note_id, OLD.note_id);
      UPDATE notes SET title = title WHERE id = nid;
      RETURN NULL;
    END;
    $$
    """,
    """
    CREATE TRIGGER trg_subject_tags_search
    AFTER INSERT OR UPDATE OR DELETE ON subject_tags
    FOR EACH ROW
    EXECUTE FUNCTION skytrace_touch_subject_search()
    """,
    """
    CREATE TRIGGER trg_note_tags_search
    AFTER INSERT OR UPDATE OR DELETE ON note_tags
    FOR EACH ROW
    EXECUTE FUNCTION skytrace_touch_note_search()
    """,
    """
    CREATE FUNCTION skytrace_tags_refresh_search()
    RETURNS trigger
    LANGUAGE plpgsql
    AS $$
    BEGIN
      UPDATE subjects SET slug = slug
      WHERE id IN (SELECT subject_id FROM subject_tags WHERE tag_id = NEW.id);
      UPDATE notes SET title = title
      WHERE id IN (SELECT note_id FROM note_tags WHERE tag_id = NEW.id);
      RETURN NEW;
    END;
    $$
    """,
    """
    CREATE TRIGGER trg_tags_search
    AFTER UPDATE OF name ON tags
    FOR EACH ROW
    EXECUTE FUNCTION skytrace_tags_refresh_search()
    """,
)
