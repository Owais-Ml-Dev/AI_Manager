"""add paused task status and automatic history event types

Revision ID: 4187cbe11e04
Revises: 524dcf696aa4
Create Date: 2026-11-19 16:00:00.050799

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4187cbe11e04'
down_revision: Union[str, None] = '524dcf696aa4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NEW_HISTORY_TYPES = ("BECAME_OVERDUE", "OCCURRENCE_MISSED", "PAUSED", "RESUMED")
_OLD_TASK_STATUSES = ("PENDING", "COMPLETED", "OVERDUE", "CANCELLED")
_OLD_HISTORY_TYPES = ("CREATED", "FIELD_UPDATED", "PRIORITY_CHANGED", "STATUS_CHANGED",
                      "REOPENED", "SCHEDULE_CHANGED")


def upgrade() -> None:
    # Postgres 12+ allows ADD VALUE inside the migration's transaction (the
    # new values just can't be used until it commits, and nothing here does).
    op.execute("ALTER TYPE task_status ADD VALUE IF NOT EXISTS 'PAUSED'")
    for value in _NEW_HISTORY_TYPES:
        op.execute(f"ALTER TYPE history_event_type ADD VALUE IF NOT EXISTS '{value}'")


def _recreate_enum(type_name: str, values: tuple, table: str, column: str, default: str | None) -> None:
    """Postgres can't remove a value from an enum type: rebuild it without
    the new values (rows using them must already be gone/converted)."""
    labels = ", ".join(f"'{v}'" for v in values)
    op.execute(f"ALTER TYPE {type_name} RENAME TO {type_name}_old")
    op.execute(f"CREATE TYPE {type_name} AS ENUM ({labels})")
    if default:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")
    op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {type_name} "
               f"USING {column}::text::{type_name}")
    if default:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT '{default}'")
    op.execute(f"DROP TYPE {type_name}_old")


def downgrade() -> None:
    # Data that only exists with the new values: paused tasks go back to
    # pending; the automatic history events are removed.
    op.execute("UPDATE tasks SET status = 'PENDING' WHERE status = 'PAUSED'")
    new = ", ".join(f"'{v}'" for v in _NEW_HISTORY_TYPES)
    op.execute(f"DELETE FROM task_history_events WHERE event_type::text IN ({new})")
    _recreate_enum("task_status", _OLD_TASK_STATUSES, "tasks", "status", "PENDING")
    _recreate_enum("history_event_type", _OLD_HISTORY_TYPES, "task_history_events", "event_type", None)
