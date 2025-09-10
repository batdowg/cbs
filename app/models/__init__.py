from __future__ import annotations

import base64
from flask import current_app
from sqlalchemy.orm import validates

from ..app import db
from ..shared.passwords import hash_password, check_password
from ..shared.constants import ROLE_ATTRS

from .simulation import SimulationOutline  # noqa: E402,F401


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False)
    password_hash = db.Column(db.String(255))
    full_name = db.Column(db.String(255))
    title = db.Column(db.String(255))
    is_app_admin = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_kcrm = db.Column(db.Boolean, default=False)
    is_kt_delivery = db.Column(db.Boolean, default=False)
    is_kt_contractor = db.Column(db.Boolean, default=False)
    is_kt_staff = db.Column(db.Boolean, default=False)
    region = db.Column(db.String(8))
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    preferred_language = db.Column(
        db.String(10), nullable=False, default="en", server_default="en"
    )
    preferred_view = db.Column(
        db.String(20), nullable=True, default="ADMIN", server_default="ADMIN"
    )
    __table_args__ = (
        db.Index("ix_users_email_lower", db.func.lower(email), unique=True),
    )

    @validates("email")
    def lower_email(self, key, value):  # pragma: no cover - simple normalizer
        return value.lower()

    def set_password(self, plain: str) -> None:
        self.password_hash = hash_password(plain)

    def check_password(self, plain: str) -> bool:
        if not self.password_hash:
            return False
        return check_password(plain, self.password_hash)

    def has_role(self, role: str) -> bool:
        attr = ROLE_ATTRS.get(role)
        return bool(attr and getattr(self, attr, False))


class ParticipantAccount(db.Model):
    __tablename__ = "participant_accounts"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False)
    password_hash = db.Column(db.String(255))
    must_change_password = db.Column(db.Boolean, nullable=False, default=False)
    full_name = db.Column(db.String(200), nullable=False)
    certificate_name = db.Column(db.String(200), default="")
    login_magic_hash = db.Column(db.String(128))
    login_magic_expires = db.Column(db.DateTime(timezone=True))
    preferred_language = db.Column(
        db.String(10), nullable=False, default="en", server_default="en"
    )
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    __table_args__ = (
        db.Index(
            "ix_participant_accounts_email_lower",
            db.func.lower(email),
            unique=True,
        ),
    )

    @validates("email")
    def lower_email(self, key, value):  # pragma: no cover - simple normalizer
        return value.lower()

    def set_password(self, plain: str) -> None:
        self.password_hash = hash_password(plain)

    def check_password(self, plain: str) -> bool:
        if not self.password_hash:
            return False
        return check_password(plain, self.password_hash)


class Settings(db.Model):
    __tablename__ = "settings"
    id = db.Column(db.Integer, primary_key=True, default=1)
    smtp_host = db.Column(db.String(255))
    smtp_port = db.Column(db.Integer)
    smtp_user = db.Column(db.String(255))
    smtp_from_default = db.Column(db.String(255))
    smtp_from_name = db.Column(db.String(255))
    smtp_pass_enc = db.Column(db.Text)
    use_tls = db.Column(db.Boolean, default=True)
    use_ssl = db.Column(db.Boolean, default=False)
    updated_at = db.Column(
        db.DateTime, server_default=db.func.now(), onupdate=db.func.now()
    )

    # always enforce singleton row id=1
    @staticmethod
    def get() -> "Settings | None":
        return db.session.get(Settings, 1)

    def set_smtp_pass(self, plain: str) -> None:
        if not plain:
            self.smtp_pass_enc = None
            return
        key = current_app.config.get("SECRET_KEY", "").encode()
        data = plain.encode()
        xored = bytes([b ^ key[i % len(key)] for i, b in enumerate(data)])
        self.smtp_pass_enc = base64.b64encode(xored).decode()

    def get_smtp_pass(self) -> str | None:
        if not self.smtp_pass_enc:
            return None
        try:
            key = current_app.config.get("SECRET_KEY", "").encode()
            raw = base64.b64decode(self.smtp_pass_enc.encode())
            data = bytes([b ^ key[i % len(key)] for i, b in enumerate(raw)])
            return data.decode()
        except Exception:
            return None


class Language(db.Model):
    __tablename__ = "languages"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    sort_order = db.Column(db.SmallInteger, nullable=False, default=100)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)


class WorkshopType(db.Model):
    __tablename__ = "workshop_types"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(16), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(16), default="active")
    description = db.Column(db.Text)
    badge = db.Column(
        db.String(50), nullable=True
    )  # one of allowed set; NULL means none
    simulation_based = db.Column(
        db.Boolean, nullable=False, default=False, server_default=db.text("false")
    )
    default_materials_option_id = db.Column(
        db.Integer,
        db.ForeignKey("materials_options.id", ondelete="SET NULL"),
    )
    default_materials_option = db.relationship("MaterialsOption")
    supported_languages = db.Column(db.JSON, nullable=False, default=lambda: ["en"])
    cert_series = db.Column(db.String(16), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    __table_args__ = (
        db.Index("uix_workshop_types_code_upper", db.func.upper(code), unique=True),
    )

    resources = db.relationship(
        "Resource",
        secondary="resource_workshop_types",
        back_populates="workshop_types",
    )

    @validates("code")
    def upper_code(self, key, value):  # pragma: no cover - simple normalizer
        return (value or "").upper()


class Client(db.Model):
    __tablename__ = "clients"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    sfc_link = db.Column(db.String(512))
    crm_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    crm = db.relationship("User")
    data_region = db.Column(db.String(8))
    status = db.Column(db.String(16), nullable=False, default="active")
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    __table_args__ = (
        db.Index("uix_clients_name_lower", db.func.lower(name), unique=True),
    )


class ClientShippingLocation(db.Model):
    __tablename__ = "client_shipping_locations"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(
        db.Integer, db.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    client = db.relationship("Client", backref="shipping_locations")
    contact_name = db.Column(db.String(255))
    contact_phone = db.Column(db.String(50))
    contact_email = db.Column(db.String(255))
    address_line1 = db.Column(db.String(255))
    address_line2 = db.Column(db.String(255))
    city = db.Column(db.String(255))
    state = db.Column(db.String(255))
    postal_code = db.Column(db.String(50))
    country = db.Column(db.String(100))
    notes = db.Column(db.String(255))
    is_active = db.Column(
        db.Boolean, nullable=False, default=True, server_default=db.text("true")
    )
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    __table_args__ = (
        db.Index(
            "ix_client_shipping_locations_client_active",
            "client_id",
            "is_active",
        ),
    )

    def display_name(self) -> str:  # pragma: no cover - simple helper
        parts = [
            self.contact_name,
            self.address_line1,
            self.city,
            self.country,
        ]
        return " / ".join([p for p in parts if p])


class ClientWorkshopLocation(db.Model):
    __tablename__ = "client_workshop_locations"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(
        db.Integer, db.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    client = db.relationship("Client", backref="workshop_locations")
    label = db.Column(db.String(255), nullable=False)
    is_virtual = db.Column(
        db.Boolean, nullable=False, default=False, server_default=db.text("false")
    )
    platform = db.Column(db.String(100))
    access_notes = db.Column(db.String(255))
    address_line1 = db.Column(db.String(255))
    address_line2 = db.Column(db.String(255))
    city = db.Column(db.String(255))
    state = db.Column(db.String(255))
    postal_code = db.Column(db.String(50))
    country = db.Column(db.String(100))
    is_active = db.Column(
        db.Boolean, nullable=False, default=True, server_default=db.text("true")
    )
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    __table_args__ = (
        db.Index(
            "ix_client_workshop_locations_client_active",
            "client_id",
            "is_active",
        ),
    )


class Session(db.Model):
    __tablename__ = "sessions"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255))
    code = db.Column(db.String(64))
    description = db.Column(db.Text)
    client_owner = db.Column(db.String(255))
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    daily_start_time = db.Column(db.Time, server_default="08:00:00")
    daily_end_time = db.Column(db.Time, server_default="17:00:00")
    timezone = db.Column(db.String(64))
    location = db.Column(db.String(255))
    delivery_type = db.Column(db.String(32))
    region = db.Column(db.String(8))
    language = db.Column(db.String(16))
    paper_size = db.Column(
        db.Enum("A4", "LETTER", name="paper_size"),
        nullable=False,
        default="A4",
        server_default="A4",
    )
    workshop_language = db.Column(
        db.Enum("en", "es", "fr", "ja", "de", "nl", "zh", name="workshop_language"),
        nullable=False,
        default="en",
        server_default="en",
    )
    capacity = db.Column(db.Integer)
    status = db.Column(
        db.String(16), nullable=False, default="New", server_default="New"
    )
    confirmed_ready = db.Column(
        db.Boolean, nullable=False, default=False, server_default=db.text("false")
    )
    delivered = db.Column(
        db.Boolean, nullable=False, default=False, server_default=db.text("false")
    )
    materials_ordered = db.Column(
        db.Boolean, nullable=False, default=False, server_default=db.text("false")
    )
    ready_for_delivery = db.Column(
        db.Boolean, nullable=False, default=False, server_default=db.text("false")
    )
    info_sent = db.Column(
        db.Boolean, nullable=False, default=False, server_default=db.text("false")
    )
    finalized = db.Column(
        db.Boolean, nullable=False, default=False, server_default=db.text("false")
    )
    on_hold = db.Column(
        db.Boolean, nullable=False, default=False, server_default=db.text("false")
    )
    no_material_order = db.Column(
        db.Boolean, nullable=False, default=False, server_default=db.text("false")
    )
    materials_only = db.Column(
        db.Boolean, nullable=False, default=False, server_default=db.text("false")
    )
    no_prework = db.Column(
        db.Boolean, nullable=False, default=False, server_default=db.text("false")
    )
    cancelled = db.Column(
        db.Boolean, nullable=False, default=False, server_default=db.text("false")
    )
    materials_ordered_at = db.Column(db.DateTime)
    ready_at = db.Column(db.DateTime)
    info_sent_at = db.Column(db.DateTime)
    delivered_at = db.Column(db.DateTime)
    finalized_at = db.Column(db.DateTime)
    cancelled_at = db.Column(db.DateTime)
    on_hold_at = db.Column(db.DateTime)
    sponsor = db.Column(db.String(255))
    notes = db.Column(db.Text)
    simulation_outline_text = db.Column("simulation_outline", db.Text)
    simulation_outline_id = db.Column(
        db.Integer,
        db.ForeignKey("simulation_outlines.id", ondelete="SET NULL"),
        nullable=True,
    )
    simulation_outline = db.relationship("SimulationOutline")
    workshop_type_id = db.Column(
        db.Integer, db.ForeignKey("workshop_types.id", ondelete="SET NULL")
    )
    workshop_type = db.relationship("WorkshopType")
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    lead_facilitator_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL")
    )
    lead_facilitator = db.relationship(
        "User", foreign_keys=[lead_facilitator_id], backref="lead_sessions"
    )
    facilitators = db.relationship(
        "User",
        secondary="session_facilitators",
        backref="facilitated_sessions",
    )
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id", ondelete="SET NULL"))
    client = db.relationship("Client")
    workshop_location_id = db.Column(
        db.Integer,
        db.ForeignKey("client_workshop_locations.id", ondelete="SET NULL"),
    )
    workshop_location = db.relationship("ClientWorkshopLocation")
    shipping_location_id = db.Column(
        db.Integer,
        db.ForeignKey("client_shipping_locations.id", ondelete="SET NULL"),
    )
    shipping_location = db.relationship("ClientShippingLocation")
    csa_account_id = db.Column(
        db.Integer, db.ForeignKey("participant_accounts.id", ondelete="SET NULL")
    )
    csa_account = db.relationship("ParticipantAccount", foreign_keys=[csa_account_id])
    csa_notified_account_id = db.Column(
        db.Integer, db.ForeignKey("participant_accounts.id", ondelete="SET NULL")
    )
    csa_notified_at = db.Column(db.DateTime)

    @validates("workshop_type")
    def _sync_code(self, key, wt):  # pragma: no cover - simple setter
        if wt:
            self.code = wt.code
        return wt

    @property
    def computed_status(self) -> str:
        if self.cancelled:
            return "Cancelled"
        if self.on_hold:
            return "On Hold"
        if self.finalized:
            return "Finalized"
        if self.delivered:
            return "Delivered"
        if self.ready_for_delivery:
            return "Ready for Delivery"
        if self.materials_ordered or self.info_sent:
            return "In Progress"
        return "New"

    def participants_locked(self) -> bool:
        return self.on_hold or self.finalized or self.cancelled


class Participant(db.Model):
    __tablename__ = "participants"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(255))
    organization = db.Column(db.String(255))
    job_title = db.Column(db.String(255))
    title = db.Column(db.String(255))
    account_id = db.Column(
        db.Integer, db.ForeignKey("participant_accounts.id", ondelete="SET NULL")
    )
    account = db.relationship("ParticipantAccount")
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    __table_args__ = (
        db.Index("ix_participants_email_lower", db.func.lower(email), unique=True),
    )

    @validates("email")
    def lower_email(self, key, value):  # pragma: no cover - simple normalizer
        return value.lower()


class SessionParticipant(db.Model):
    __tablename__ = "session_participants"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id", ondelete="CASCADE"))
    participant_id = db.Column(
        db.Integer, db.ForeignKey("participants.id", ondelete="CASCADE")
    )
    completion_date = db.Column(db.Date)
    __table_args__ = (
        db.UniqueConstraint(
            "session_id", "participant_id", name="uix_session_participant"
        ),
    )


class CertificateTemplateSeries(db.Model):
    __tablename__ = "certificate_template_series"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(16), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class CertificateTemplate(db.Model):
    __tablename__ = "certificate_templates"

    id = db.Column(db.Integer, primary_key=True)
    series_id = db.Column(
        db.Integer,
        db.ForeignKey("certificate_template_series.id", ondelete="CASCADE"),
        nullable=False,
    )
    language = db.Column(db.String(8), nullable=False)
    size = db.Column(db.String(10), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    badge_filename = db.Column(db.String(255))
    __table_args__ = (
        db.UniqueConstraint(
            "series_id", "language", "size", name="uix_cert_template_series_lang_size"
        ),
    )
    series = db.relationship("CertificateTemplateSeries", backref="templates")


class Certificate(db.Model):
    __tablename__ = "certificates"

    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(
        db.Integer, db.ForeignKey("participants.id", ondelete="CASCADE")
    )
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id", ondelete="CASCADE"))
    certificate_name = db.Column(db.String(255))
    workshop_name = db.Column(db.String(255))
    workshop_date = db.Column(db.Date)
    pdf_path = db.Column(db.String(255))
    issued_at = db.Column(db.DateTime, server_default=db.func.now())
    __table_args__ = (
        db.UniqueConstraint(
            "session_id",
            "participant_id",
            name="uix_certificate_session_participant",
        ),
    )
    session = db.relationship("Session")


class SessionFacilitator(db.Model):
    __tablename__ = "session_facilitators"
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id", ondelete="CASCADE"))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"))
    created_at = db.Column(db.DateTime, server_default=db.func.now())


class MaterialType(db.Model):
    __tablename__ = "material_types"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)


class Material(db.Model):
    __tablename__ = "materials"
    id = db.Column(db.Integer, primary_key=True)
    material_type_id = db.Column(
        db.Integer, db.ForeignKey("material_types.id", ondelete="SET NULL")
    )
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)


materials_option_languages = db.Table(
    "materials_option_languages",
    db.Column(
        "materials_option_id",
        db.Integer,
        db.ForeignKey("materials_options.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "language_id",
        db.Integer,
        db.ForeignKey("languages.id", ondelete="RESTRICT"),
        primary_key=True,
    ),
)

session_shipping_materials_options = db.Table(
    "session_shipping_materials_options",
    db.Column(
        "session_shipping_id",
        db.Integer,
        db.ForeignKey("session_shipping.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "materials_option_id",
        db.Integer,
        db.ForeignKey("materials_options.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class MaterialsOption(db.Model):
    __tablename__ = "materials_options"
    __table_args__ = (
        db.UniqueConstraint(
            "order_type",
            "title",
            name="uq_materials_options_order_type_title",
        ),
        db.CheckConstraint(
            "order_type IN ('KT-Run Standard materials','KT-Run Modular materials','KT-Run LDI materials','Client-run Bulk order','Simulation')",
            name="ck_materials_options_order_type",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    order_type = db.Column(db.Text, nullable=False)
    title = db.Column(db.String(160), nullable=False)
    formats = db.Column(db.JSON, nullable=False, default=list)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now(), nullable=False)
    languages = db.relationship("Language", secondary="materials_option_languages")


class SessionShipping(db.Model):
    __tablename__ = "session_shipping"
    __table_args__ = (
        db.UniqueConstraint("session_id", name="uq_session_shipping_session_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id", ondelete="CASCADE"))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    name = db.Column(db.String(120), nullable=False, default="Main Shipment")
    materials_option_id = db.Column(
        db.Integer,
        db.ForeignKey("materials_options.id", ondelete="SET NULL"),
        nullable=True,
    )
    materials_option = db.relationship("MaterialsOption")
    materials_options = db.relationship(
        "MaterialsOption", secondary="session_shipping_materials_options"
    )
    client_shipping_location_id = db.Column(
        db.Integer,
        db.ForeignKey("client_shipping_locations.id", ondelete="SET NULL"),
    )
    client_shipping_location = db.relationship("ClientShippingLocation")
    contact_name = db.Column(db.String(255))
    contact_phone = db.Column(db.String(50))
    contact_email = db.Column(db.String(255))
    address_line1 = db.Column(db.String(255))
    address_line2 = db.Column(db.String(255))
    city = db.Column(db.String(255))
    state = db.Column(db.String(255))
    postal_code = db.Column(db.String(50))
    country = db.Column(db.String(100))
    courier = db.Column(db.String(255))
    tracking = db.Column(db.String(255))
    order_date = db.Column(db.Date)
    ship_date = db.Column(db.Date)
    special_instructions = db.Column(db.Text)
    arrival_date = db.Column(db.Date)
    order_type = db.Column(db.Text)
    status = db.Column(
        db.String(16), nullable=False, default="New", server_default="New"
    )
    material_sets = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    credits = db.Column(db.Integer, nullable=False, default=2, server_default="2")
    materials_format = db.Column(
        db.Enum(
            "ALL_PHYSICAL",
            "MIXED",
            "ALL_DIGITAL",
            "SIM_ONLY",
            name="materials_format",
        ),
        nullable=True,
    )
    materials_components = db.Column(db.JSON)
    materials_po_number = db.Column(db.String(64))
    submitted_at = db.Column(db.DateTime)
    delivered_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    items = db.relationship(
        "SessionShippingItem", backref="shipment", cascade="all, delete-orphan"
    )

    # Compatibility alias for materials_components
    @property
    def physical_components(self):
        return self.materials_components

    @physical_components.setter
    def physical_components(self, value):
        self.materials_components = value


class SessionShippingItem(db.Model):
    __tablename__ = "session_shipping_items"
    id = db.Column(db.Integer, primary_key=True)
    session_shipping_id = db.Column(
        db.Integer, db.ForeignKey("session_shipping.id", ondelete="CASCADE")
    )
    material_id = db.Column(
        db.Integer, db.ForeignKey("materials.id", ondelete="SET NULL")
    )
    quantity = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text)


class Badge(db.Model):
    __tablename__ = "badges"
    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(
        db.Integer, db.ForeignKey("participants.id", ondelete="CASCADE")
    )
    name = db.Column(db.String(255), nullable=False)
    issued_at = db.Column(db.DateTime, server_default=db.func.now())


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    session_id = db.Column(
        db.Integer, db.ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True
    )
    participant_id = db.Column(
        db.Integer, db.ForeignKey("participants.id", ondelete="SET NULL"), nullable=True
    )
    action = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, server_default=db.func.now())


class UserAuditLog(db.Model):
    __tablename__ = "user_audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    actor_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    target_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    field = db.Column(db.String(64), nullable=False)
    old_value = db.Column(db.String(255))
    new_value = db.Column(db.String(255))
    changed_at = db.Column(db.DateTime, server_default=db.func.now())


VIRTUAL_WORKSHOP_DEFAULTS = [
    ("Virtual - MS Teams", "MS Teams"),
    ("Virtual - Zoom", "Zoom"),
    ("Virtual - Google Meets", "Google Meets"),
    ("Virtual - Webex", "Webex"),
    ("Virtual - Other", "Other"),
]


def ensure_virtual_workshop_locations(client_id: int) -> None:
    for label, platform in VIRTUAL_WORKSHOP_DEFAULTS:
        exists = (
            db.session.query(ClientWorkshopLocation)
            .filter_by(client_id=client_id, label=label)
            .first()
        )
        if not exists:
            db.session.add(
                ClientWorkshopLocation(
                    client_id=client_id,
                    label=label,
                    is_virtual=True,
                    platform=platform,
                )
            )
    db.session.commit()


def seed_virtual_workshop_locations() -> None:
    for client in Client.query.all():
        ensure_virtual_workshop_locations(client.id)


from .resource import Resource, resource_workshop_types  # noqa: E402,F401
from .prework import (
    PreworkTemplate,
    PreworkQuestion,
    PreworkTemplateResource,
    PreworkAssignment,
    PreworkAnswer,
    PreworkEmailLog,
)  # noqa: E402,F401

__all__ = [
    "User",
    "ParticipantAccount",
    "Settings",
    "Language",
    "WorkshopType",
    "Client",
    "ClientShippingLocation",
    "ClientWorkshopLocation",
    "SimulationOutline",
    "Session",
    "Participant",
    "SessionParticipant",
    "Certificate",
    "SessionFacilitator",
    "MaterialType",
    "Material",
    "MaterialsOption",
    "SessionShipping",
    "SessionShippingItem",
    "Badge",
    "AuditLog",
    "UserAuditLog",
    "Resource",
    "resource_workshop_types",
    "PreworkTemplate",
    "PreworkQuestion",
    "PreworkTemplateResource",
    "PreworkAssignment",
    "PreworkAnswer",
    "PreworkEmailLog",
]
