"""PR-11 add missing columns and views from manual fixes

Revision ID: a1b2c3d4e5f6
Revises: f69170dd22cf
Create Date: 2026-03-21 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f69170dd22cf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column("assessment_responses", sa.Column("answer_value", sa.Integer(), nullable=True))
    op.add_column("student_skill_scores", sa.Column("skill_id", sa.Integer(), nullable=True))
    op.add_column("student_skill_scores", sa.Column("student_id", sa.Integer(), nullable=True))
    op.add_column("student_skill_scores", sa.Column("raw_score", sa.Numeric(), nullable=True))
    op.add_column("student_skill_scores", sa.Column("avg_raw", sa.Numeric(), nullable=True))
    op.add_column("student_skill_scores", sa.Column("normalized_score", sa.Numeric(), nullable=True))
    op.add_column("student_skill_scores", sa.Column("question_count", sa.Integer(), nullable=True))
    op.add_column("student_skill_scores", sa.Column("created_at", sa.TIMESTAMP(), nullable=True))
    op.add_column("student_skill_scores", sa.Column("updated_at", sa.TIMESTAMP(), nullable=True))
    op.add_column("student_skill_scores", sa.Column("raw_total", sa.Float(), nullable=True))
    op.add_column("student_skill_scores", sa.Column("scaled_0_100", sa.Float(), nullable=True))
    op.add_column("student_skill_scores", sa.Column("computed_at", sa.TIMESTAMP(), nullable=True))
    op.add_column("student_skill_scores", sa.Column("norm_weight_sum", sa.Float(), nullable=True))
    op.add_column("student_keyskill_map", sa.Column("score", sa.Float(), nullable=True))
    op.add_column("careers", sa.Column("career_code", sa.String(), nullable=True))
    op.execute("UPDATE careers SET career_code = CONCAT('C', LPAD(id::text, 4, '0')) WHERE career_code IS NULL")
    op.execute("""
        CREATE TABLE IF NOT EXISTS assessment_answer_scale (
            id SERIAL PRIMARY KEY,
            assessment_version VARCHAR NOT NULL,
            min_value INTEGER NOT NULL,
            max_value INTEGER NOT NULL,
            is_active BOOLEAN DEFAULT TRUE
        )
    """)
    op.execute("""
        INSERT INTO assessment_answer_scale (assessment_version, min_value, max_value, is_active)
        SELECT 'v1', 1, 5, TRUE
        WHERE NOT EXISTS (SELECT 1 FROM assessment_answer_scale WHERE assessment_version = 'v1')
    """)
    op.execute("""
        CREATE OR REPLACE VIEW career_keyskill_weights_effective_int_v AS
        SELECT
            c.id AS career_id,
            CONCAT('C', LPAD(c.id::text, 4, '0')) AS career_code,
            k.id AS keyskill_id,
            CONCAT('KS', LPAD(k.id::text, 4, '0')) AS keyskill_code,
            k.name AS keyskill_name,
            COALESCE(cka.weight_percentage, 0)::int AS effective_weight_int
        FROM career_keyskill_association cka
        JOIN careers c ON c.id = cka.career_id
        JOIN keyskills k ON k.id = cka.keyskill_id
    """)

def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS career_keyskill_weights_effective_int_v")
    op.drop_column("careers", "career_code")
    op.drop_column("student_keyskill_map", "score")
    op.drop_column("assessment_responses", "answer_value")
    for col in ["norm_weight_sum","computed_at","scaled_0_100","raw_total","updated_at","created_at","question_count","normalized_score","avg_raw","raw_score","student_id","skill_id"]:
        op.drop_column("student_skill_scores", col)
