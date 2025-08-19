from __future__ import annotations

import base64
from flask import current_app
from sqlalchemy.orm import validates

from .app import db


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


class Session(db.Model):
    __tablename__ = "sessions"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255))
    description = db.Column(db.Text)
    client_owner = db.Column(db.String(255))
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    location = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, server_default=db.func.now())


class Participant(db.Model):
    __tablename__ = "participants"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(255))
    organization = db.Column(db.String(255))
    job_title = db.Column(db.String(255))
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
