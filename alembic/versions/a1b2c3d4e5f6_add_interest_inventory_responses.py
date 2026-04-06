"""add interest_inventory_responses table

Revision ID: a1b2c3d4e5f6
Revises: e7cf6ce8be79
Create Date: 2026-04-07 09:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'e7cf6ce8be79'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'interest_inventory_responses',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),

        # Student link — who answered
        sa.Column(
            'student_id',
            sa.Integer(),
            sa.ForeignKey('students.id', ondelete='CASCADE'),
            nullable=False,
            index=True,
        ),

        # Versioning — allows future question set changes without breaking old data
        sa.Column(
            'inventory_version',
            sa.String(length=20),
            nullable=False,
            server_default='v1',
        ),

        # The 10 answers stored as JSON: {"q1": "a", "q2": "c", ...}
        # Storing as JSON keeps it flexible — adding Q11, Q12 later needs no schema change
        sa.Column(
            'answers',
            JSONB(),
            nullable=False,
        ),

        # Derived cluster boost scores — stored at submit time for fast reads
        # Format: {"Business": 0.15, "STEM": 0.30, "Health Sci": 0.15, ...}
        # Values are additive boost percentages (0.0 to 1.0)
        sa.Column(
            'cluster_boosts',
            JSONB(),
            nullable=True,
        ),

        # Lang used when questions were shown (en or kn)
        sa.Column(
            'lang',
            sa.String(length=10),
            nullable=False,
            server_default='en',
        ),

        # Audit
        sa.Column(
            'submitted_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
            onupdate=sa.text('now()'),
        ),
    )

    # One active response per student per version
    # (student can retake — old row is updated, not duplicated)
    op.create_unique_constraint(
        'uq_interest_student_version',
        'interest_inventory_responses',
        ['student_id', 'inventory_version'],
    )

    # Fast lookup by student
    op.create_index(
        'ix_interest_inventory_responses_student_id',
        'interest_inventory_responses',
        ['student_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_interest_inventory_responses_student_id',
                  table_name='interest_inventory_responses')
    op.drop_constraint('uq_interest_student_version',
                       'interest_inventory_responses')
    op.drop_table('interest_inventory_responses')
