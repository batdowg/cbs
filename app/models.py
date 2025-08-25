from __future__ import annotations

import base64
from flask import current_app
from sqlalchemy.orm import validates

from .app import db
from .utils.passwords import hash_password, check_password

# Language choices stored as human labels for now
LANG_CHOICES = [
    ("Chinese", "zh"),
    ("Dutch", "nl"),
    ("English", "en"),
    ("French", "fr"),
    ("German", "de"),
    ("Japanese", "ja"),
    ("Spanish", "es"),
]


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False)
    password_hash = db.Column(db.String(255))
    full_name = db.Column(db.String(255))
    is_app_admin = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_kcrm = db.Column(db.Boolean, default=False)
    is_kt_delivery = db.Column(db.Boolean, default=False)
    is_kt_contractor = db.Column(db.Boolean, default=False)
    is_kt_staff = db.Column(db.Boolean, default=False)
    region = db.Column(db.String(8))
    created_at = db.Column(db.DateTime, server_default=db.func.now())
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


class ParticipantAccount(db.Model):
    __tablename__ = "participant_accounts"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False)
    password_hash = db.Column(db.String(255))
    full_name = db.Column(db.String(200), nullable=False)
    certificate_name = db.Column(db.String(200), default="")
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


class WorkshopType(db.Model):
    __tablename__ = "workshop_types"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(16), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(16), default="active")
    description = db.Column(db.Text)
    badge = db.Column(db.String(50), nullable=True)  # one of allowed set; NULL means none
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    __table_args__ = (
        db.Index("uix_workshop_types_code_upper", db.func.upper(code), unique=True),
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


class Session(db.Model):
    __tablename__ = "sessions"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255))
    code = db.Column(db.String(64))
    description = db.Column(db.Text)
    client_owner = db.Column(db.String(255))
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    daily_start_time = db.Column(
        db.Time, server_default="08:00:00"
    )
    daily_end_time = db.Column(
        db.Time, server_default="17:00:00"
    )
    timezone = db.Column(db.String(64))
    location = db.Column(db.String(255))
    delivery_type = db.Column(db.String(32))
    region = db.Column(db.String(8))
    language = db.Column(db.String(16))
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
    simulation_outline = db.Column(db.Text)
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
    csa_account_id = db.Column(
        db.Integer, db.ForeignKey("participant_accounts.id", ondelete="SET NULL")
    )
    csa_account = db.relationship("ParticipantAccount")

    @validates("workshop_type")
    def _sync_code(self, key, wt):  # pragma: no cover - simple setter
        if wt:
            self.code = wt.code
        return wt

    @property
    def computed_status(self) -> str:
        if self.cancelled:
            return "Cancelled"
        if self.finalized:
            return "Closed"
        if self.delivered:
            return "Delivered"
        if self.ready_for_delivery:
            return "Ready for Delivery"
        if self.materials_ordered or self.info_sent or self.on_hold:
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
    session_id = db.Column(
        db.Integer, db.ForeignKey("sessions.id", ondelete="CASCADE")
    )
    participant_id = db.Column(
        db.Integer, db.ForeignKey("participants.id", ondelete="CASCADE")
    )
    completion_date = db.Column(db.Date)
    __table_args__ = (
        db.UniqueConstraint("session_id", "participant_id", name="uix_session_participant"),
    )


class Certificate(db.Model):
    __tablename__ = "certificates"

    id = db.Column(db.Integer, primary_key=True)
    participant_id = db.Column(
        db.Integer, db.ForeignKey("participants.id", ondelete="CASCADE")
    )
    session_id = db.Column(
        db.Integer, db.ForeignKey("sessions.id", ondelete="CASCADE")
    )
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
    session_id = db.Column(
        db.Integer, db.ForeignKey("sessions.id", ondelete="CASCADE")
    )
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


class SessionShipping(db.Model):
    __tablename__ = "session_shipping"
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id", ondelete="CASCADE"))
    created_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
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
    ship_date = db.Column(db.Date)
    special_instructions = db.Column(db.Text)
    created_at = db.Column(db.DateTime, server_default=db.func.now())


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
