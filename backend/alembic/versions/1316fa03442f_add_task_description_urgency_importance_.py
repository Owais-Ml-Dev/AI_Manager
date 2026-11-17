"""add task description, urgency, importance, status

Revision ID: 1316fa03442f
Revises: 9308187d13f7
Create Date: 2026-11-17 15:29:57.625794

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1316fa03442f'
down_revision: Union[str, None] = '9308187d13f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


task_status_enum = sa.Enum('PENDING', 'COMPLETED', 'OVERDUE', 'CANCELLED', name='task_status')


def upgrade() -> None:
    task_status_enum.create(op.get_bind())
    op.add_column('tasks', sa.Column('description', sa.String(length=2000), nullable=True))
    op.add_column('tasks', sa.Column('urgent', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('tasks', sa.Column('important', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('tasks', sa.Column('status', task_status_enum, server_default='PENDING', nullable=False))


def downgrade() -> None:
    op.drop_column('tasks', 'status')
    op.drop_column('tasks', 'important')
    op.drop_column('tasks', 'urgent')
    op.drop_column('tasks', 'description')
    task_status_enum.drop(op.get_bind())
