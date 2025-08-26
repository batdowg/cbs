"""add languages table and materials_option_languages bridge"""

from alembic import op
import sqlalchemy as sa

revision = '0028_languages_bridge'
down_revision = '0027_materials_options'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'languages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=120), nullable=False, unique=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('sort_order', sa.SmallInteger(), nullable=False, server_default='100'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )
    op.create_table(
        'materials_option_languages',
        sa.Column('materials_option_id', sa.Integer(), nullable=False),
        sa.Column('language_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['materials_option_id'], ['materials_options.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['language_id'], ['languages.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('materials_option_id', 'language_id', name='pk_materials_option_languages'),
    )
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'materials_options' in insp.get_table_names():
        cols = [c['name'] for c in insp.get_columns('materials_options')]
        if 'languages' in cols:
            op.drop_column('materials_options', 'languages')
    names = sorted([
        'Chinese',
        'Dutch',
        'English',
        'French',
        'German',
        'Japanese',
        'Spanish',
    ])
    for n in names:
        op.execute(
            sa.text(
                "INSERT INTO languages (name) VALUES (:name) ON CONFLICT (name) DO NOTHING"
            ),
            {"name": n},
        )


def downgrade() -> None:
    op.add_column(
        'materials_options',
        sa.Column('languages', sa.JSON(), nullable=False, server_default='[]'),
    )
    op.drop_table('materials_option_languages')
    op.drop_table('languages')
