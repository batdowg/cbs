from __future__ import annotations

import os

from sqlalchemy import event
from sqlalchemy.orm import validates

from ..app import db
from ..shared.storage_resources import remove_resource_dir, remove_resource_file

resource_workshop_types = db.Table(
    "resource_workshop_types",
    db.Column(
        "resource_id",
        db.Integer,
        db.ForeignKey("resources.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "workshop_type_id",
        db.Integer,
        db.ForeignKey("workshop_types.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.UniqueConstraint("resource_id", "workshop_type_id", name="uix_resource_workshop_type"),
)


class Resource(db.Model):
    __tablename__ = "resources"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    resource_value = db.Column(db.String(2048))
    description_html = db.Column(db.Text)
    active = db.Column(db.Boolean, nullable=False, default=True)
    language = db.Column(
        db.String(8), nullable=False, default="en", server_default="en"
    )
    audience = db.Column(
        db.Enum(
            "Participant",
            "Facilitator",
            "Both",
            name="resource_audience",
        ),
        nullable=False,
        default="Participant",
        server_default="Participant",
    )
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    workshop_types = db.relationship(
        "WorkshopType",
        secondary=resource_workshop_types,
        back_populates="resources",
    )

    TYPE_CHOICES = ("LINK", "DOCUMENT", "APP")
    AUDIENCE_CHOICES = ("Participant", "Facilitator", "Both")

    @property
    def public_url(self) -> str | None:
        if self.type == "DOCUMENT":
            value = (self.resource_value or "").strip()
            if not value:
                return None
            if value.startswith(("http://", "https://")):
                return value
            if value.startswith("/"):
                return value
            return f"/resources/{value}"
        return self.resource_value

    @property
    def document_filename(self) -> str | None:
        if self.type != "DOCUMENT" or not self.resource_value:
            return None
        value = self.resource_value.strip()
        if not value:
            return None
        return os.path.basename(value)

    @validates("type")
    def _normalize_type(self, key, value):
        value = (value or "").upper()
        if value not in self.TYPE_CHOICES:
            raise ValueError("invalid resource type")
        return value

    @validates("audience")
    def _normalize_audience(self, key, value):
        mapping = {
            "participant": "Participant",
            "facilitator": "Facilitator",
            "both": "Both",
        }
        normalized = mapping.get((value or "").strip().lower())
        if not normalized:
            raise ValueError("invalid resource audience")
        return normalized

    @validates("language")
    def _normalize_language(self, key, value):
        language_code = (value or "en").strip().lower()
        if not language_code:
            language_code = "en"
        from ..shared.languages import LANG_CODE_NAMES

        if language_code not in LANG_CODE_NAMES:
            raise ValueError("invalid resource language")
        return language_code

    def validate(self) -> None:
        if self.type in {"LINK", "APP"}:
            if not self.resource_value or not self.resource_value.startswith(("http://", "https://")):
                raise ValueError("URL required")
        elif self.type == "DOCUMENT":
            if not self.resource_value:
                raise ValueError("filename required")
        else:
            raise ValueError("invalid resource type")


@event.listens_for(Resource, "after_delete")
def _cleanup_resource_files(mapper, connection, target):
    remove_resource_file(target.id, getattr(target, "resource_value", None))
    remove_resource_dir(target.id)
