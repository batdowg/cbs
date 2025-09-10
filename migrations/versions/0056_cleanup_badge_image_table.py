"""cleanup leftover badge_images usage"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = '0056_cleanup_badge_image_table'
down_revision = '0055_remove_workshop_type_badge'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # ensure badge_filename column exists
    columns = [c['name'] for c in insp.get_columns('certificate_templates')]
    if 'badge_filename' not in columns:
        op.add_column('certificate_templates', sa.Column('badge_filename', sa.String(length=255), nullable=True))

    if 'badge_image_id' in columns:
        tables = insp.get_table_names()
        if 'badge_images' in tables:
            op.execute(
                text(
                    """
                    UPDATE certificate_templates ct
                    SET badge_filename = bi.filename
                    FROM badge_images bi
                    WHERE ct.badge_image_id = bi.id
                    """
                )
            )
        fk_names = [fk['name'] for fk in insp.get_foreign_keys('certificate_templates')]
        if 'fk_cert_templates_badge_image' in fk_names:
            op.drop_constraint('fk_cert_templates_badge_image', 'certificate_templates', type_='foreignkey')
        op.drop_column('certificate_templates', 'badge_image_id')

    if 'badge_images' in insp.get_table_names():
        op.drop_table('badge_images')


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()

    if 'badge_images' not in tables:
        op.create_table(
            'badge_images',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('name', sa.String(length=255), nullable=False),
            sa.Column('language', sa.String(length=8), nullable=False),
            sa.Column('filename', sa.String(length=255), nullable=False),
        )
    columns = [c['name'] for c in insp.get_columns('certificate_templates')]
    if 'badge_image_id' not in columns:
        op.add_column('certificate_templates', sa.Column('badge_image_id', sa.Integer, nullable=True))
        op.create_foreign_key(
            'fk_cert_templates_badge_image',
            'certificate_templates',
            'badge_images',
            ['badge_image_id'],
            ['id'],
        )
    if 'badge_filename' in columns:
        op.execute(
            text(
                """
                INSERT INTO badge_images (name, language, filename)
                SELECT DISTINCT badge_filename, 'en', badge_filename
                FROM certificate_templates
                WHERE badge_filename IS NOT NULL
                """
            )
        )
        op.execute(
            text(
                """
                UPDATE certificate_templates ct
                SET badge_image_id = bi.id
                FROM badge_images bi
                WHERE ct.badge_filename = bi.filename
                """
            )
        )
        op.drop_column('certificate_templates', 'badge_filename')
