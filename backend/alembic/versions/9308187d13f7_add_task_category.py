"""add task category

Revision ID: 9308187d13f7
Revises: c035ae306983
Create Date: 2026-11-17 15:06:50.106717

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9308187d13f7'
down_revision: Union[str, None] = 'c035ae306983'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


task_category_enum = sa.Enum('RECURRING', 'ONE_TIME', name='task_category')


def upgrade() -> None:
    task_category_enum.create(op.get_bind())
    op.add_column('tasks', sa.Column('category', task_category_enum, nullable=False))


def downgrade() -> None:
    op.drop_column('tasks', 'category')
    task_category_enum.drop(op.get_bind())
