"""Sprint1: scoring rebuild — career_student_skill, aq_student_skill_weight,
careers.cluster, skills.student_skill_name

Revision ID: a2b3c4d5e6f7
Revises: 16094f5085d0
Create Date: 2026-04-03 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "16094f5085d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Short skill name → full Student Skill name (17 skills currently in DB)
_SKILL_NAME_MAP = {
    "Adaptability":              "Adaptability & Flexibility",
    "Collaboration":             "Collaboration & Teamwork",
    "Communication":             "Communication Skills",
    "Confidence / Self-Efficacy":"Initiative",
    "Creative Expression":       "Creativity & Innovation",
    "Critical Thinking":         "Critical Thinking & Problem Solving",
    "Curiosity & Inquiry":       "Curiosity",
    "Digital Literacy":          "Digital Literacy",
    "Emotional Regulation":      "Coping with Stress & Resilience",
    "Empathy":                   "Social & Cross-Cultural Skills",
    "Ethical Judgment":          "Ethical Reasoning",
    "Grit & Perseverance":       "Grit & Self-Direction",
    "Information Literacy":      "Information Literacy",
    "Numerical Comfort":         "Financial Literacy",
    "Self-Discipline":           "Productivity",
    "Systems Thinking":          "Decision-Making",
    "Time Management":           "Time Management",
}


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1) Add careers.cluster (text label, separate from cluster_id FK)
    # ------------------------------------------------------------------
    op.execute("ALTER TABLE careers ADD COLUMN IF NOT EXISTS cluster VARCHAR(64)")

    # ------------------------------------------------------------------
    # 2) Add skills.student_skill_name (full canonical name)
    # ------------------------------------------------------------------
    op.execute("ALTER TABLE skills ADD COLUMN IF NOT EXISTS student_skill_name VARCHAR(128)")

    # Populate from known short-name → full-name mapping
    for short, full in _SKILL_NAME_MAP.items():
        op.execute(
            sa.text(
                "UPDATE skills SET student_skill_name = :full WHERE name = :short AND student_skill_name IS NULL"
            ).bindparams(full=full, short=short)
        )

    # ------------------------------------------------------------------
    # 3) Create career_student_skill table
    # ------------------------------------------------------------------
    op.create_table(
        "career_student_skill",
        sa.Column("career_id",     sa.Integer(),      nullable=False),
        sa.Column("student_skill", sa.String(128),    nullable=False),
        sa.Column("weight",        sa.Numeric(6, 2),  nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["career_id"], ["careers.id"], name="fk_css_career_id"),
        sa.PrimaryKeyConstraint("career_id", "student_skill", name="pk_career_student_skill"),
    )
    op.create_index("ix_career_student_skill_career", "career_student_skill", ["career_id"])
    op.create_index("ix_career_student_skill_skill",  "career_student_skill", ["student_skill"])

    # ------------------------------------------------------------------
    # 4) Create aq_student_skill_weight table
    # ------------------------------------------------------------------
    op.create_table(
        "aq_student_skill_weight",
        sa.Column("aq_code",      sa.String(8),      nullable=False),
        sa.Column("student_skill", sa.String(128),   nullable=False),
        sa.Column("weight",        sa.Numeric(8, 6), nullable=False),
        sa.PrimaryKeyConstraint("aq_code", "student_skill", name="pk_aq_student_skill_weight"),
    )
    op.create_index("ix_aq_student_skill_weight_aq", "aq_student_skill_weight", ["aq_code"])


def downgrade() -> None:
    op.drop_index("ix_aq_student_skill_weight_aq",   table_name="aq_student_skill_weight")
    op.drop_table("aq_student_skill_weight")

    op.drop_index("ix_career_student_skill_skill",   table_name="career_student_skill")
    op.drop_index("ix_career_student_skill_career",  table_name="career_student_skill")
    op.drop_table("career_student_skill")

    op.execute("ALTER TABLE skills DROP COLUMN IF EXISTS student_skill_name")
    op.execute("ALTER TABLE careers DROP COLUMN IF EXISTS cluster")
