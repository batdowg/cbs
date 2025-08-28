"""prework list questions and item index"""

revision = '0032_prework_list_questions'
down_revision = '0031_prework'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.add_column('prework_questions', sa.Column('kind', sa.Enum('TEXT','LIST', name='prework_question_kind'), nullable=False, server_default='TEXT'))
    op.add_column('prework_questions', sa.Column('min_items', sa.Integer(), nullable=True))
    op.add_column('prework_questions', sa.Column('max_items', sa.Integer(), nullable=True))

    op.add_column('prework_answers', sa.Column('item_index', sa.Integer(), nullable=False, server_default='0'))
    op.execute('UPDATE prework_answers SET item_index=0')
    op.drop_constraint('uq_prework_answer_unique', 'prework_answers', type_='unique')
    op.create_unique_constraint('uq_prework_answer_unique', 'prework_answers', ['assignment_id','question_index','item_index'])
    op.alter_column('prework_answers', 'item_index', server_default=None)


def downgrade() -> None:
    op.drop_constraint('uq_prework_answer_unique', 'prework_answers', type_='unique')
    op.create_unique_constraint('uq_prework_answer_unique', 'prework_answers', ['assignment_id','question_index'])
    op.drop_column('prework_answers', 'item_index')

    op.drop_column('prework_questions', 'max_items')
    op.drop_column('prework_questions', 'min_items')
    op.drop_column('prework_questions', 'kind')
    op.execute("DROP TYPE prework_question_kind")
