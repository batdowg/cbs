"""add participant company client linkage"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0078_participant_company_client"
down_revision: Union[str, None] = "0077_split_names_first_last"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = "session_participants"
    if table_name not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns(table_name)}
    if "company_client_id" not in columns:
        op.add_column(
            table_name,
            sa.Column("company_client_id", sa.Integer(), nullable=True),
        )

    fk_names = {fk["name"] for fk in inspector.get_foreign_keys(table_name)}
    fk_name = "fk_session_participants_company_client"
    if fk_name not in fk_names:
        op.create_foreign_key(
            fk_name,
            table_name,
            "clients",
            ["company_client_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.execute(
        sa.text(
            """
            UPDATE session_participants AS sp
            SET company_client_id = s.client_id
            FROM sessions AS s
            WHERE sp.session_id = s.id
              AND s.client_id IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = "session_participants"
    if table_name not in inspector.get_table_names():
        return

    fk_names = {fk["name"] for fk in inspector.get_foreign_keys(table_name)}
    fk_name = "fk_session_participants_company_client"
    if fk_name in fk_names:
        op.drop_constraint(fk_name, table_name, type_="foreignkey")

    columns = {col["name"] for col in inspector.get_columns(table_name)}
    if "company_client_id" in columns:
        op.drop_column(table_name, "company_client_id")
