"""client shipping and workshop locations"""

from alembic import op
import sqlalchemy as sa

revision = '0029_client_locations'
down_revision = '0028_languages_bridge'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'client_shipping_locations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id', ondelete='CASCADE'), nullable=False),
        sa.Column('contact_name', sa.String(length=255)),
        sa.Column('contact_phone', sa.String(length=50)),
        sa.Column('contact_email', sa.String(length=255)),
        sa.Column('address_line1', sa.String(length=255)),
        sa.Column('address_line2', sa.String(length=255)),
        sa.Column('city', sa.String(length=255)),
        sa.Column('state', sa.String(length=255)),
        sa.Column('postal_code', sa.String(length=50)),
        sa.Column('country', sa.String(length=100)),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
    )
    op.create_index(
        'ix_client_shipping_locations_client_active',
        'client_shipping_locations',
        ['client_id', 'is_active'],
    )
    op.create_table(
        'client_workshop_locations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id', ondelete='CASCADE'), nullable=False),
        sa.Column('label', sa.String(length=255), nullable=False),
        sa.Column('is_virtual', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('platform', sa.String(length=100)),
        sa.Column('address_line1', sa.String(length=255)),
        sa.Column('address_line2', sa.String(length=255)),
        sa.Column('city', sa.String(length=255)),
        sa.Column('state', sa.String(length=255)),
        sa.Column('postal_code', sa.String(length=50)),
        sa.Column('country', sa.String(length=100)),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
    )
    op.create_index(
        'ix_client_workshop_locations_client_active',
        'client_workshop_locations',
        ['client_id', 'is_active'],
    )
    op.add_column('sessions', sa.Column('workshop_location_id', sa.Integer(), sa.ForeignKey('client_workshop_locations.id', ondelete='SET NULL')))
    op.add_column('sessions', sa.Column('shipping_location_id', sa.Integer(), sa.ForeignKey('client_shipping_locations.id', ondelete='SET NULL')))
    op.add_column('session_shipping', sa.Column('client_shipping_location_id', sa.Integer(), sa.ForeignKey('client_shipping_locations.id', ondelete='SET NULL')))

    bind = op.get_bind()
    # backfill shipping locations
    rows = bind.execute(sa.text(
        """
        SELECT ss.id as ss_id, s.id as session_id, s.client_id, ss.contact_name, ss.contact_phone, ss.contact_email,
               ss.address_line1, ss.address_line2, ss.city, ss.state, ss.postal_code, ss.country
        FROM session_shipping ss JOIN sessions s ON ss.session_id = s.id
        WHERE s.client_id IS NOT NULL AND ss.address_line1 IS NOT NULL
        """
    )).fetchall()
    for r in rows:
        existing = bind.execute(sa.text(
            """SELECT id FROM client_shipping_locations WHERE client_id=:cid AND address_line1=:a1 AND city=:city AND postal_code=:pc AND country=:country"""),
            {"cid": r.client_id, "a1": r.address_line1, "city": r.city, "pc": r.postal_code, "country": r.country},
        ).fetchone()
        if existing:
            loc_id = existing.id
        else:
            loc_id = bind.execute(sa.text(
                """INSERT INTO client_shipping_locations (client_id, contact_name, contact_phone, contact_email, address_line1, address_line2, city, state, postal_code, country) VALUES (:cid,:cn,:cp,:ce,:a1,:a2,:city,:state,:pc,:country) RETURNING id"""
            ), {
                "cid": r.client_id,
                "cn": r.contact_name,
                "cp": r.contact_phone,
                "ce": r.contact_email,
                "a1": r.address_line1,
                "a2": r.address_line2,
                "city": r.city,
                "state": r.state,
                "pc": r.postal_code,
                "country": r.country,
            }).scalar()
        bind.execute(sa.text("UPDATE sessions SET shipping_location_id=:lid WHERE id=:sid"), {"lid": loc_id, "sid": r.session_id})
        bind.execute(sa.text("UPDATE session_shipping SET client_shipping_location_id=:lid WHERE id=:ssid"), {"lid": loc_id, "ssid": r.ss_id})

    # seed virtual workshop locations
    clients = bind.execute(sa.text("SELECT id FROM clients")).fetchall()
    defaults = [
        ("Virtual - MS Teams", "MS Teams"),
        ("Virtual - Zoom", "Zoom"),
        ("Virtual - Google Meets", "Google Meets"),
        ("Virtual - Webex", "Webex"),
        ("Virtual - Other", "Other"),
    ]
    for c in clients:
        for label, platform in defaults:
            existing = bind.execute(sa.text(
                "SELECT id FROM client_workshop_locations WHERE client_id=:cid AND label=:label"),
                {"cid": c.id, "label": label},
            ).fetchone()
            if not existing:
                bind.execute(sa.text(
                    "INSERT INTO client_workshop_locations (client_id, label, is_virtual, platform) VALUES (:cid,:label,true,:platform)"
                ), {"cid": c.id, "label": label, "platform": platform})


def downgrade() -> None:
    op.drop_column('session_shipping', 'client_shipping_location_id')
    op.drop_column('sessions', 'shipping_location_id')
    op.drop_column('sessions', 'workshop_location_id')
    op.drop_table('client_workshop_locations')
    op.drop_table('client_shipping_locations')
