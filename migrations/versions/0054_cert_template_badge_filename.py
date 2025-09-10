"""store badge filename on certificate templates"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0054_cert_template_badge_filename'
down_revision = '0053_cert_template_badge_image'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('certificate_templates', sa.Column('badge_filename', sa.String(length=255), nullable=True))
    op.execute(
        """
        UPDATE certificate_templates ct
        SET badge_filename = bi.filename
        FROM badge_images bi
        WHERE ct.badge_image_id = bi.id
        """
    )
    op.drop_constraint('fk_cert_templates_badge_image', 'certificate_templates', type_='foreignkey')
    op.drop_column('certificate_templates', 'badge_image_id')
    op.drop_table('badge_images')


def downgrade() -> None:
    op.create_table(
        'badge_images',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('language', sa.String(length=8), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
    )
    op.add_column('certificate_templates', sa.Column('badge_image_id', sa.Integer, nullable=True))
    op.create_foreign_key(
        'fk_cert_templates_badge_image',
        'certificate_templates',
        'badge_images',
        ['badge_image_id'],
        ['id'],
    )
    op.execute(
        """
        INSERT INTO badge_images (name, language, filename)
        SELECT DISTINCT badge_filename, 'en', badge_filename
        FROM certificate_templates
        WHERE badge_filename IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE certificate_templates ct
        SET badge_image_id = bi.id
        FROM badge_images bi
        WHERE ct.badge_filename = bi.filename
        """
    )
    op.drop_column('certificate_templates', 'badge_filename')
