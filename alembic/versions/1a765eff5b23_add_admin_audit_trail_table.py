"""Add admin_audit_trail table

Revision ID: 1a765eff5b23
Revises: 3f2b5081e575
Create Date: 2026-04-13 00:00:00.000000

Design: append-only — no UPDATE/DELETE permitted by application logic.
Rows are immutable once inserted; the created_at column is DB-stamped.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '1a765eff5b23'
down_revision: Union[str, None] = '3f2b5081e575'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'admin_audit_trail',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(64), nullable=False),
        sa.Column('entity_type', sa.String(64), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=True),
        sa.Column('entity_name', sa.String(255), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('user_email', sa.String(320), nullable=False),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'],
            name='fk_admin_audit_trail_user_id',
            ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_admin_audit_trail_id'), 'admin_audit_trail', ['id'], unique=False)
    op.create_index('ix_admin_audit_trail_action', 'admin_audit_trail', ['action'], unique=False)
    op.create_index('ix_admin_audit_trail_entity_type', 'admin_audit_trail', ['entity_type'], unique=False)
    op.create_index('ix_admin_audit_trail_user_id', 'admin_audit_trail', ['user_id'], unique=False)
    op.create_index('ix_admin_audit_trail_created_at', 'admin_audit_trail', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_admin_audit_trail_created_at', table_name='admin_audit_trail')
    op.drop_index('ix_admin_audit_trail_user_id', table_name='admin_audit_trail')
    op.drop_index('ix_admin_audit_trail_entity_type', table_name='admin_audit_trail')
    op.drop_index('ix_admin_audit_trail_action', table_name='admin_audit_trail')
    op.drop_index(op.f('ix_admin_audit_trail_id'), table_name='admin_audit_trail')
    op.drop_table('admin_audit_trail')
