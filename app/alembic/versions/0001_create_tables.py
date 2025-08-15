"""create workshop, company, session tables

Revision ID: 0001_create_tables
Revises: 
Create Date: 2024-01-01 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0001_create_tables'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'workshop_type',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('short_name', sa.String(), nullable=False),
        sa.Column('full_name', sa.String(), nullable=False),
        sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ux_workshop_type_short_name', 'workshop_type', ['short_name'], unique=True)
    op.create_index('ux_workshop_type_full_name', 'workshop_type', ['full_name'], unique=True)

    op.create_table(
        'company',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('normalized_name', sa.String(), nullable=False),
        sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ux_company_name', 'company', ['name'], unique=True)

    op.create_table(
        'session',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('session_id', sa.String(), nullable=False),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('company.id'), nullable=False),
        sa.Column('workshop_type_id', sa.Integer(), sa.ForeignKey('workshop_type.id'), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('client_manager_name', sa.String(), nullable=True),
        sa.Column('client_manager_email', sa.String(), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), sa.ForeignKey('user_account.user_account_id'), nullable=True),
        sa.Column('shipping_json', postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ux_session_session_id', 'session', ['session_id'], unique=True)
    op.create_index('ix_session_client_manager_email_lower', 'session', [sa.text('lower(client_manager_email)')])


def downgrade() -> None:
    op.drop_index('ix_session_client_manager_email_lower', table_name='session')
    op.drop_index('ux_session_session_id', table_name='session')
    op.drop_table('session')
    op.drop_index('ux_company_name', table_name='company')
    op.drop_table('company')
    op.drop_index('ux_workshop_type_full_name', table_name='workshop_type')
    op.drop_index('ux_workshop_type_short_name', table_name='workshop_type')
    op.drop_table('workshop_type')
