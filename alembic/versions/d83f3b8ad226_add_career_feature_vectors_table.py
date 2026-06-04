"""Add career_feature_vectors table

Revision ID: d83f3b8ad226
Revises: 1a765eff5b23
Create Date: 2026-04-13 00:00:00.000000

Stores per-career feature vectors used for similarity search and
career intelligence. Computed offline by the vector service and cached
here — never written by user-facing endpoints.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'd83f3b8ad226'
down_revision: Union[str, None] = '1a765eff5b23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'career_feature_vectors',
        sa.Column('career_id', sa.Integer(), nullable=False),
        sa.Column('keyskill_vec',  postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('market_vec',    postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('tfidf_vec',     postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('aq_vec',        postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('student_vec',   postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('archetype_id',    sa.Integer(), nullable=True),
        sa.Column('archetype_label', sa.String(100), nullable=True),
        sa.Column('centrality_score', sa.Float(), nullable=True),
        sa.Column(
            'computed_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['career_id'], ['careers.id'],
            name='fk_career_feature_vectors_career_id',
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('career_id'),
    )
    op.create_index(
        'ix_career_feature_vectors_archetype_id',
        'career_feature_vectors', ['archetype_id'], unique=False,
    )
    op.create_index(
        'ix_career_feature_vectors_computed_at',
        'career_feature_vectors', ['computed_at'], unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_career_feature_vectors_computed_at', table_name='career_feature_vectors')
    op.drop_index('ix_career_feature_vectors_archetype_id', table_name='career_feature_vectors')
    op.drop_table('career_feature_vectors')
