"""add missing assessment and versioned knowledge pack tables

Revision ID: ec55ebc40479
Revises: 5c50f1279676
Create Date: 2026-03-14 21:49:23.751597

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ec55ebc40479'
down_revision: Union[str, None] = '5c50f1279676'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------------------------------------------------
    # 1) assessment_questions
    # ---------------------------------------------------------
    op.create_table(
        "assessment_questions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("assessment_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("assessment_version", sa.String(length=32), nullable=False),
        sa.Column("question_code", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assessment_questions_id", "assessment_questions", ["id"], unique=False)
    op.create_index("ix_assessment_questions_assessment_id", "assessment_questions", ["assessment_id"], unique=False)
    op.create_index("ix_assessment_questions_assessment_version", "assessment_questions", ["assessment_version"], unique=False)

    # ---------------------------------------------------------
    # 2) associated_qualities_v
    # ---------------------------------------------------------
    op.create_table(
        "associated_qualities_v",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("assessment_version", sa.String(length=32), nullable=False),
        sa.Column("aq_code", sa.String(length=120), nullable=False),
        sa.Column("name_en", sa.Text(), nullable=False),
        sa.Column("name_hi", sa.Text(), nullable=True),
        sa.Column("name_ta", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assessment_version", "aq_code", name="uq_associated_qualities_v_version_code"),
    )
    op.create_index("ix_associated_qualities_v_id", "associated_qualities_v", ["id"], unique=False)
    op.create_index("ix_associated_qualities_v_assessment_version", "associated_qualities_v", ["assessment_version"], unique=False)
    op.create_index("ix_associated_qualities_v_aq_code", "associated_qualities_v", ["aq_code"], unique=False)

    # ---------------------------------------------------------
    # 3) aq_facets_v
    # ---------------------------------------------------------
    op.create_table(
        "aq_facets_v",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("assessment_version", sa.String(length=32), nullable=False),
        sa.Column("facet_code", sa.String(length=120), nullable=False),
        sa.Column("aq_code", sa.String(length=120), nullable=False),
        sa.Column("name_en", sa.Text(), nullable=False),
        sa.Column("name_hi", sa.Text(), nullable=True),
        sa.Column("name_ta", sa.Text(), nullable=True),
        sa.Column("description_en", sa.Text(), nullable=True),
        sa.Column("description_hi", sa.Text(), nullable=True),
        sa.Column("description_ta", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assessment_version", "facet_code", name="uq_aq_facets_v_version_facet"),
        sa.ForeignKeyConstraint(
            ["assessment_version", "aq_code"],
            ["associated_qualities_v.assessment_version", "associated_qualities_v.aq_code"],
            name="fk_aq_facets_v_version_aq",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_aq_facets_v_id", "aq_facets_v", ["id"], unique=False)
    op.create_index("ix_aq_facets_v_assessment_version", "aq_facets_v", ["assessment_version"], unique=False)
    op.create_index("ix_aq_facets_v_facet_code", "aq_facets_v", ["facet_code"], unique=False)
    op.create_index("ix_aq_facets_v_aq_code", "aq_facets_v", ["aq_code"], unique=False)

    # ---------------------------------------------------------
    # 4) question_facet_tags_v
    # ---------------------------------------------------------
    op.create_table(
        "question_facet_tags_v",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("assessment_version", sa.String(length=32), nullable=False),
        sa.Column("question_code", sa.String(length=100), nullable=False),
        sa.Column("facet_code", sa.String(length=120), nullable=False),
        sa.Column("tag_weight", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "assessment_version",
            "question_code",
            "facet_code",
            name="uq_question_facet_tags_v_version_question_facet",
        ),
        sa.ForeignKeyConstraint(
            ["assessment_version", "facet_code"],
            ["aq_facets_v.assessment_version", "aq_facets_v.facet_code"],
            name="fk_question_facet_tags_v_version_facet",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_question_facet_tags_v_id", "question_facet_tags_v", ["id"], unique=False)
    op.create_index("ix_question_facet_tags_v_assessment_version", "question_facet_tags_v", ["assessment_version"], unique=False)
    op.create_index("ix_question_facet_tags_v_question_code", "question_facet_tags_v", ["question_code"], unique=False)
    op.create_index("ix_question_facet_tags_v_facet_code", "question_facet_tags_v", ["facet_code"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_question_facet_tags_v_facet_code", table_name="question_facet_tags_v")
    op.drop_index("ix_question_facet_tags_v_question_code", table_name="question_facet_tags_v")
    op.drop_index("ix_question_facet_tags_v_assessment_version", table_name="question_facet_tags_v")
    op.drop_index("ix_question_facet_tags_v_id", table_name="question_facet_tags_v")
    op.drop_table("question_facet_tags_v")

    op.drop_index("ix_aq_facets_v_aq_code", table_name="aq_facets_v")
    op.drop_index("ix_aq_facets_v_facet_code", table_name="aq_facets_v")
    op.drop_index("ix_aq_facets_v_assessment_version", table_name="aq_facets_v")
    op.drop_index("ix_aq_facets_v_id", table_name="aq_facets_v")
    op.drop_table("aq_facets_v")

    op.drop_index("ix_associated_qualities_v_aq_code", table_name="associated_qualities_v")
    op.drop_index("ix_associated_qualities_v_assessment_version", table_name="associated_qualities_v")
    op.drop_index("ix_associated_qualities_v_id", table_name="associated_qualities_v")
    op.drop_table("associated_qualities_v")

    op.drop_index("ix_assessment_questions_assessment_version", table_name="assessment_questions")
    op.drop_index("ix_assessment_questions_assessment_id", table_name="assessment_questions")
    op.drop_index("ix_assessment_questions_id", table_name="assessment_questions")
    op.drop_table("assessment_questions")
    