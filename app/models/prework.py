from __future__ import annotations

from datetime import datetime

from ..app import db


class PreworkInvite(db.Model):
    __tablename__ = "prework_invites"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer, db.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    participant_id = db.Column(
        db.Integer, db.ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    sender_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL")
    )
    sent_at = db.Column(
        db.DateTime(timezone=True), nullable=False, server_default=db.func.now()
    )


class PreworkTemplate(db.Model):
    __tablename__ = "prework_templates"

    id = db.Column(db.Integer, primary_key=True)
    workshop_type_id = db.Column(
        db.Integer, db.ForeignKey("workshop_types.id", ondelete="CASCADE")
    )
    language = db.Column(db.String(16), nullable=False, default="en")
    workshop_type = db.relationship("WorkshopType")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    require_completion = db.Column(db.Boolean, nullable=False, default=True)
    info_html = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    __table_args__ = (
        db.UniqueConstraint(
            "workshop_type_id",
            "language",
            name="uq_prework_template_workshop_language",
        ),
    )

    questions = db.relationship(
        "PreworkQuestion", backref="template", cascade="all, delete-orphan"
    )
    resources = db.relationship(
        "PreworkTemplateResource", backref="template", cascade="all, delete-orphan"
    )


class PreworkQuestion(db.Model):
    __tablename__ = "prework_questions"

    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(
        db.Integer, db.ForeignKey("prework_templates.id", ondelete="CASCADE")
    )
    position = db.Column(db.Integer, nullable=False)
    text = db.Column(db.Text, nullable=False)
    required = db.Column(db.Boolean, nullable=False, default=True)
    kind = db.Column(
        db.Enum("TEXT", "LIST", name="prework_question_kind"),
        nullable=False,
        server_default="TEXT",
    )
    min_items = db.Column(db.Integer)
    max_items = db.Column(db.Integer)
    __table_args__ = (
        db.UniqueConstraint("template_id", "position", name="uq_prework_question_position"),
    )


class PreworkTemplateResource(db.Model):
    __tablename__ = "prework_template_resources"

    template_id = db.Column(
        db.Integer, db.ForeignKey("prework_templates.id", ondelete="CASCADE"), primary_key=True
    )
    resource_id = db.Column(
        db.Integer, db.ForeignKey("resources.id", ondelete="CASCADE"), primary_key=True
    )


class PreworkAssignment(db.Model):
    __tablename__ = "prework_assignments"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id", ondelete="CASCADE"))
    participant_account_id = db.Column(
        db.Integer, db.ForeignKey("participant_accounts.id", ondelete="CASCADE")
    )
    template_id = db.Column(
        db.Integer, db.ForeignKey("prework_templates.id", ondelete="SET NULL")
    )
    status = db.Column(db.String(16), nullable=False, default="PENDING")
    due_at = db.Column(db.DateTime(timezone=True))
    sent_at = db.Column(db.DateTime(timezone=True))
    completed_at = db.Column(db.DateTime(timezone=True))
    snapshot_json = db.Column(db.JSON, nullable=False)
    magic_token_hash = db.Column(db.String(128))
    magic_token_expires = db.Column(db.DateTime(timezone=True))
    account_sent_at = db.Column(db.DateTime(timezone=True))
    __table_args__ = (
        db.UniqueConstraint(
            "session_id", "participant_account_id", name="uq_prework_assignment_unique"
        ),
    )

    session = db.relationship("Session")
    participant_account = db.relationship("ParticipantAccount")
    template = db.relationship("PreworkTemplate")
    answers = db.relationship(
        "PreworkAnswer", backref="assignment", cascade="all, delete-orphan"
    )
    emails = db.relationship(
        "PreworkEmailLog", backref="assignment", cascade="all, delete-orphan"
    )

    def update_completion(self) -> None:
        if not (self.template and self.template.require_completion):
            return
        qs = {q["index"]: q for q in self.snapshot_json.get("questions", [])}
        for idx, q in qs.items():
            if not q.get("required"):
                continue
            if q.get("kind") == "LIST":
                min_items = q.get("min_items") or 1
                count = sum(
                    1
                    for a in self.answers
                    if a.question_index == idx and a.answer_text and a.answer_text.strip()
                )
                if count < min_items:
                    break
            else:
                found = any(
                    a.answer_text and a.answer_text.strip()
                    for a in self.answers
                    if a.question_index == idx
                )
                if not found:
                    break
        else:
            if self.status != "COMPLETED":
                self.status = "COMPLETED"
                self.completed_at = datetime.utcnow()
            return
        if self.status == "COMPLETED":
            self.status = "SENT"
            self.completed_at = None


class PreworkAnswer(db.Model):
    __tablename__ = "prework_answers"

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(
        db.Integer, db.ForeignKey("prework_assignments.id", ondelete="CASCADE")
    )
    question_index = db.Column(db.Integer, nullable=False)
    item_index = db.Column(db.Integer, nullable=False, default=0)
    answer_text = db.Column(db.Text, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.now(),
        onupdate=db.func.now(),
    )
    __table_args__ = (
        db.UniqueConstraint(
            "assignment_id",
            "question_index",
            "item_index",
            name="uq_prework_answer_unique",
        ),
    )


class PreworkEmailLog(db.Model):
    __tablename__ = "prework_email_log"

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(
        db.Integer, db.ForeignKey("prework_assignments.id", ondelete="CASCADE")
    )
    to_email = db.Column(db.String(320))
    subject = db.Column(db.String(255))
    sent_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
