"""add user_id to students

Revision ID: 6d561fe21dcd
Revises: 65c24201a283
Create Date: 2025-12-24 00:29:30.351259

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6d561fe21dcd'
down_revision: Union[str, None] = '65c24201a283'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column(
        "students",
        sa.Column("user_id", sa.Integer(), nullable=True)
    )

    op.create_index(
        "ix_students_user_id",
        "students",
        ["user_id"]
    )

    op.create_unique_constraint(
        "uq_students_user_id",
        "students",
        ["user_id"]
    )

    op.create_foreign_key(
        "fk_students_user_id_users",
        "students",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL"
    )



def downgrade():
    op.drop_constraint(
        "fk_students_user_id_users",
        "students",
        type_="foreignkey"
    )

    op.drop_constraint(
        "uq_students_user_id",
        "students",
        type_="unique"
    )

    op.drop_index(
        "ix_students_user_id",
        table_name="students"
    )

    op.drop_column(
        "students",
        "user_id"
    )

