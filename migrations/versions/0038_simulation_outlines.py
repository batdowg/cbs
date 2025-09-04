"""add simulation outlines table"""

from alembic import op
import sqlalchemy as sa


revision = '0038_simulation_outlines'
down_revision = '0037_preferred_view'
branch_labels = None
depends_on = None


SKILLS = (
    'Systematic Troubleshooting',
    'Frontline',
    'Risk',
    'PSDMxp',
    'Refresher',
    'Custom',
)
LEVELS = ('Novice', 'Competent', 'Advanced')


def upgrade() -> None:
    op.create_table(
        'simulation_outlines',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('number', sa.String(length=6), nullable=False),
        sa.Column('skill', sa.Enum(*SKILLS, name='simulation_skill'), nullable=False),
        sa.Column('descriptor', sa.String(length=160), nullable=False),
        sa.Column('level', sa.Enum(*LEVELS, name='simulation_level'), nullable=False),
        sa.UniqueConstraint('number', name='uq_simulation_outlines_number'),
    )
    op.add_column('sessions', sa.Column('simulation_outline_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_sessions_simulation_outline',
        'sessions',
        'simulation_outlines',
        ['simulation_outline_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_sessions_simulation_outline', 'sessions', type_='foreignkey')
    op.drop_column('sessions', 'simulation_outline_id')
    op.drop_table('simulation_outlines')
