from __future__ import annotations

from sqlalchemy.orm import validates

from ..app import db

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
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    workshop_types = db.relationship(
        "WorkshopType",
        secondary=resource_workshop_types,
        back_populates="resources",
    )

    TYPE_CHOICES = ("LINK", "DOCUMENT", "APP")

    @property
    def public_url(self) -> str | None:
        if self.type == "DOCUMENT" and self.resource_value:
            return f"/resources/{self.resource_value}"
        return self.resource_value

    @validates("type")
    def _normalize_type(self, key, value):
        value = (value or "").upper()
        if value not in self.TYPE_CHOICES:
            raise ValueError("invalid resource type")
        return value

    def validate(self) -> None:
        if self.type in {"LINK", "APP"}:
            if not self.resource_value or not self.resource_value.startswith(("http://", "https://")):
                raise ValueError("URL required")
        elif self.type == "DOCUMENT":
            if not self.resource_value:
                raise ValueError("filename required")
        else:
            raise ValueError("invalid resource type")
