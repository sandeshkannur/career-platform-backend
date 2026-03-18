"""pr09_add_missing_scoring_support_tables

Revision ID: 11ec2ee927be
Revises: ec55ebc40479
Create Date: 2026-03-17 23:46:15.960580

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '11ec2ee927be'
down_revision: Union[str, None] = 'ec55ebc40479'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "question_student_skill_weights",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Numeric(6, 4), nullable=False),
        sa.Column("source", sa.String(length=200), nullable=True),
        sa.Column("facet_id", sa.String(length=50), nullable=True),
        sa.Column("aq_id", sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["skills.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "question_id",
            "skill_id",
            name="question_student_skill_weights_question_id_skill_id_key",
        ),
    )
    op.create_index(
        op.f("ix_question_student_skill_weights_id"),
        "question_student_skill_weights",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_question_student_skill_weights_question_id"),
        "question_student_skill_weights",
        ["question_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_question_student_skill_weights_skill_id"),
        "question_student_skill_weights",
        ["skill_id"],
        unique=False,
    )

    op.create_table(
        "skill_keyskill_map",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column("keyskill_id", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["skills.id"],
        ),
        sa.ForeignKeyConstraint(
            ["keyskill_id"],
            ["keyskills.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "skill_id",
            "keyskill_id",
            name="uq_skill_keyskill",
        ),
    )
    op.create_index(
        op.f("ix_skill_keyskill_map_id"),
        "skill_keyskill_map",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_skill_keyskill_map_skill_id",
        "skill_keyskill_map",
        ["skill_id"],
        unique=False,
    )
    op.create_index(
        "ix_skill_keyskill_map_keyskill_id",
        "skill_keyskill_map",
        ["keyskill_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index("ix_skill_keyskill_map_keyskill_id", table_name="skill_keyskill_map")
    op.drop_index("ix_skill_keyskill_map_skill_id", table_name="skill_keyskill_map")
    op.drop_index(op.f("ix_skill_keyskill_map_id"), table_name="skill_keyskill_map")
    op.drop_table("skill_keyskill_map")

    op.drop_index(
        op.f("ix_question_student_skill_weights_skill_id"),
        table_name="question_student_skill_weights",
    )
    op.drop_index(
        op.f("ix_question_student_skill_weights_question_id"),
        table_name="question_student_skill_weights",
    )
    op.drop_index(
        op.f("ix_question_student_skill_weights_id"),
        table_name="question_student_skill_weights",
    )
    op.drop_table("question_student_skill_weights")

    
