"""ensure users table with roles and lower email unique"""

from alembic import op


revision = "0011_user_roles_and_unique_email"
down_revision = "0010_full_db_from_excel"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            email VARCHAR(255) NOT NULL,
            password_hash VARCHAR(255),
            full_name VARCHAR(255),
            is_app_admin BOOLEAN DEFAULT FALSE,
            is_admin BOOLEAN DEFAULT FALSE,
            is_kcrm BOOLEAN DEFAULT FALSE,
            is_kt_delivery BOOLEAN DEFAULT FALSE,
            is_kt_contractor BOOLEAN DEFAULT FALSE,
            is_kt_staff BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        "ALTER TABLE users RENAME COLUMN IF EXISTS name TO full_name"
    )
    op.execute(
        "ALTER TABLE users RENAME COLUMN IF EXISTS is_kt_admin TO is_admin"
    )
    op.execute(
        "ALTER TABLE users RENAME COLUMN IF EXISTS is_kt_crm TO is_kcrm"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(255)"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_app_admin BOOLEAN DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_kcrm BOOLEAN DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_kt_delivery BOOLEAN DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_kt_contractor BOOLEAN DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_kt_staff BOOLEAN DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    )
    op.execute("DROP INDEX IF EXISTS ix_users_email")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email_lower ON users (lower(email))"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_users_email_lower")
    op.execute("DROP TABLE IF EXISTS users")

