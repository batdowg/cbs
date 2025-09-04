from __future__ import annotations

from ..app import db


class SimulationOutline(db.Model):
    __tablename__ = "simulation_outlines"

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(6), unique=True, nullable=False)
    skill = db.Column(
        db.Enum(
            "Systematic Troubleshooting",
            "Frontline",
            "Risk",
            "PSDMxp",
            "Refresher",
            "Custom",
            name="simulation_skill",
        ),
        nullable=False,
    )
    descriptor = db.Column(db.String(160), nullable=False)
    level = db.Column(
        db.Enum("Novice", "Competent", "Advanced", name="simulation_level"),
        nullable=False,
    )

    def __str__(self) -> str:  # pragma: no cover - simple repr
        return f"{self.number} – {self.skill} – {self.descriptor}"

    @property
    def label(self) -> str:
        return str(self)
