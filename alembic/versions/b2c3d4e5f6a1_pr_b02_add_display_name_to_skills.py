"""pr_b02_add_display_name_to_skills

Revision ID: b2c3d4e5f6a1
Revises: a1b2c3d4e5f6
Create Date: 2026-03-28 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'b2c3d4e5f6a1'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('skills', sa.Column('display_name', sa.String(200), nullable=True))

    op.execute("UPDATE skills SET display_name = 'Critical Thinking & Problem Solving' WHERE name = 'Critical Thinking'")
    op.execute("UPDATE skills SET display_name = 'Collaboration & Teamwork' WHERE name = 'Collaboration'")
    op.execute("UPDATE skills SET display_name = 'Analytical Reasoning' WHERE name = 'Analytical Reasoning'")
    op.execute("UPDATE skills SET display_name = 'Practical Problem Solving' WHERE name = 'Practical Problem Solving'")
    op.execute("UPDATE skills SET display_name = 'Learning Agility' WHERE name = 'Learning Agility'")
    op.execute("UPDATE skills SET display_name = 'Creativity & Innovation' WHERE name = 'Creative Expression'")
    op.execute("UPDATE skills SET display_name = 'Communication Skills' WHERE name = 'Communication'")
    op.execute("UPDATE skills SET display_name = 'Information Literacy' WHERE name = 'Information Literacy'")
    op.execute("UPDATE skills SET display_name = 'Adaptability & Flexibility' WHERE name = 'Adaptability'")
    op.execute("UPDATE skills SET display_name = 'Digital Literacy' WHERE name = 'Digital Literacy'")
    op.execute("UPDATE skills SET display_name = 'Self-Discipline & Focus' WHERE name = 'Self-Discipline'")
    op.execute("UPDATE skills SET display_name = 'Goal Orientation' WHERE name = 'Goal Orientation'")
    op.execute("UPDATE skills SET display_name = 'Grit & Perseverance' WHERE name = 'Grit & Perseverance'")
    op.execute("UPDATE skills SET display_name = 'Confidence & Self-Belief' WHERE name = 'Confidence / Self-Efficacy'")
    op.execute("UPDATE skills SET display_name = 'Emotional Regulation' WHERE name = 'Emotional Regulation'")
    op.execute("UPDATE skills SET display_name = 'Empathy & Perspective-Taking' WHERE name = 'Empathy'")
    op.execute("UPDATE skills SET display_name = 'Curiosity & Inquiry' WHERE name = 'Curiosity & Inquiry'")
    op.execute("UPDATE skills SET display_name = 'Numerical Comfort' WHERE name = 'Numerical Comfort'")
    op.execute("UPDATE skills SET display_name = 'Logical Reasoning' WHERE name = 'Logical Reasoning'")
    op.execute("UPDATE skills SET display_name = 'Systems Thinking' WHERE name = 'Systems Thinking'")
    op.execute("UPDATE skills SET display_name = 'Abstract Thinking' WHERE name = 'Abstract Thinking'")
    op.execute("UPDATE skills SET display_name = 'Focus & Attention Control' WHERE name = 'Focus & Attention Control'")
    op.execute("UPDATE skills SET display_name = 'Time Management' WHERE name = 'Time Management'")
    op.execute("UPDATE skills SET display_name = 'Ethical Judgment' WHERE name = 'Ethical Judgment'")


def downgrade():
    op.drop_column('skills', 'display_name')
