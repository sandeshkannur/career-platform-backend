"""Add cps_factor_config table with seed data

Revision ID: 3f2b5081e575
Revises: 15d04200d9f1
Create Date: 2026-04-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3f2b5081e575'
down_revision: Union[str, None] = '15d04200d9f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cps_factor_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('factor_key', sa.String(64), nullable=False),
        sa.Column('label', sa.String(200), nullable=False),
        sa.Column('weight', sa.Float(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('factor_key', name='uq_cps_factor_config_factor_key'),
    )
    op.create_index(op.f('ix_cps_factor_config_id'), 'cps_factor_config', ['id'], unique=False)
    op.create_index(op.f('ix_cps_factor_config_factor_key'), 'cps_factor_config', ['factor_key'], unique=True)

    # Seed with current hardcoded weights — these mirror compute_cps_v1 exactly.
    # Weights sum to 1.0: 0.35 + 0.25 + 0.25 + 0.15 = 1.00
    op.execute("""
        INSERT INTO cps_factor_config (factor_key, label, weight, sort_order)
        VALUES
            ('ses_band',        'Socio-Economic Status', 0.35, 1),
            ('education_board', 'Education Board',       0.25, 2),
            ('support_level',   'Support Level',         0.25, 3),
            ('resource_access', 'Resource Access',       0.15, 4)
    """)


def downgrade() -> None:
    op.drop_index(op.f('ix_cps_factor_config_factor_key'), table_name='cps_factor_config')
    op.drop_index(op.f('ix_cps_factor_config_id'), table_name='cps_factor_config')
    op.drop_table('cps_factor_config')
