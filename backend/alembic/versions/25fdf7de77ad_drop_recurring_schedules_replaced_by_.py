"""drop recurring_schedules, replaced by shared reminder config

Revision ID: 25fdf7de77ad
Revises: 3b75c057dcec
Create Date: 2026-11-17 17:05:41.511650

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '25fdf7de77ad'
down_revision: Union[str, None] = '3b75c057dcec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


recurrence_type_enum = postgresql.ENUM(
    "DAILY", "WEEKLY", "CUSTOM_WEEKDAYS", "CUSTOM_DATES", name="recurrence_type"
)


def upgrade() -> None:
    op.drop_table('recurring_schedules')
    recurrence_type_enum.drop(op.get_bind())


def downgrade() -> None:
    # The type is created once here; the column below must not create it again
    # (create_type=False) or the rollback fails with "type already exists".
    recurrence_type_enum.create(op.get_bind())
    op.create_table('recurring_schedules',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('task_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('recurrence_type', postgresql.ENUM('DAILY', 'WEEKLY', 'CUSTOM_WEEKDAYS', 'CUSTOM_DATES', name='recurrence_type', create_type=False), autoincrement=False, nullable=False),
    sa.Column('start_date', sa.DATE(), autoincrement=False, nullable=False),
    sa.Column('end_date', sa.DATE(), autoincrement=False, nullable=True),
    sa.Column('weekdays', postgresql.ARRAY(sa.SMALLINT()), autoincrement=False, nullable=True),
    sa.Column('custom_dates', postgresql.ARRAY(sa.DATE()), autoincrement=False, nullable=True),
    sa.Column('scheduled_time', postgresql.TIME(), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], name='recurring_schedules_task_id_fkey', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name='recurring_schedules_pkey'),
    sa.UniqueConstraint('task_id', name='recurring_schedules_task_id_key')
    )
    # ### end Alembic commands ###
