"""Add sme_profiles and sme_submissions tables

Revision ID: 06086df126bb
Revises: a1b2c3d4e5f6
Create Date: 2026-04-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '06086df126bb'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # sme_profiles: minimal table; sme_id FK in sme_submissions references this
    op.create_table(
        'sme_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(320), nullable=False),
        sa.Column('full_name', sa.String(255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email', name='uq_sme_profiles_email'),
    )
    op.create_index(op.f('ix_sme_profiles_id'), 'sme_profiles', ['id'], unique=False)
    op.create_index(op.f('ix_sme_profiles_email'), 'sme_profiles', ['email'], unique=True)

    op.create_table(
        'sme_submissions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sme_id', sa.Integer(), nullable=True),
        sa.Column('sme_email', sa.String(320), nullable=False),
        sa.Column('career_id', sa.Integer(), nullable=False),
        sa.Column('submission_data', sa.JSON(), nullable=False),
        sa.Column('idempotency_key', sa.String(255), nullable=False),
        sa.Column('status', sa.String(32), nullable=False, server_default='received'),
        sa.Column('submitted_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reviewed_by', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['sme_id'], ['sme_profiles.id'], name='fk_sme_submissions_sme_id', ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['career_id'], ['careers.id'], name='fk_sme_submissions_career_id', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], name='fk_sme_submissions_reviewed_by', ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key', name='uq_sme_submissions_idempotency_key'),
    )
    op.create_index(op.f('ix_sme_submissions_id'), 'sme_submissions', ['id'], unique=False)
    op.create_index(op.f('ix_sme_submissions_sme_email'), 'sme_submissions', ['sme_email'], unique=False)
    op.create_index(op.f('ix_sme_submissions_career_id'), 'sme_submissions', ['career_id'], unique=False)
    op.create_index(op.f('ix_sme_submissions_status'), 'sme_submissions', ['status'], unique=False)
    op.create_index(op.f('ix_sme_submissions_idempotency_key'), 'sme_submissions', ['idempotency_key'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_sme_submissions_idempotency_key'), table_name='sme_submissions')
    op.drop_index(op.f('ix_sme_submissions_status'), table_name='sme_submissions')
    op.drop_index(op.f('ix_sme_submissions_career_id'), table_name='sme_submissions')
    op.drop_index(op.f('ix_sme_submissions_sme_email'), table_name='sme_submissions')
    op.drop_index(op.f('ix_sme_submissions_id'), table_name='sme_submissions')
    op.drop_table('sme_submissions')

    op.drop_index(op.f('ix_sme_profiles_email'), table_name='sme_profiles')
    op.drop_index(op.f('ix_sme_profiles_id'), table_name='sme_profiles')
    op.drop_table('sme_profiles')
