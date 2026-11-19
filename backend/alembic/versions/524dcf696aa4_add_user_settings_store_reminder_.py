"""add user_settings; store reminder delivery times in UTC

Revision ID: 524dcf696aa4
Revises: bda9ebf29c28
Create Date: 2026-11-19 15:47:30.794404

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '524dcf696aa4'
down_revision: Union[str, None] = 'bda9ebf29c28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Existing reminder_deliveries.scheduled_for values are naive local times
# written by a server running in India; they are converted as Asia/Kolkata
# (the default zone for every existing user). No other zone was ever used.
_LEGACY_ZONE = "Asia/Kolkata"


def upgrade() -> None:
    op.create_table(
        'user_settings',
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('timezone', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['auth.users.id'], name='user_settings_user_id_fkey',
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', name='user_settings_pkey'),
    )
    # Reminder deliveries become absolute instants (timestamptz, UTC).
    op.alter_column(
        'reminder_deliveries', 'scheduled_for',
        type_=sa.DateTime(timezone=True),
        existing_type=sa.DateTime(timezone=False),
        existing_nullable=False,
        postgresql_using=f"scheduled_for AT TIME ZONE '{_LEGACY_ZONE}'",
    )


def downgrade() -> None:
    op.alter_column(
        'reminder_deliveries', 'scheduled_for',
        type_=sa.DateTime(timezone=False),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        postgresql_using=f"scheduled_for AT TIME ZONE '{_LEGACY_ZONE}'",
    )
    op.drop_table('user_settings')
