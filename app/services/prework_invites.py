from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable, Sequence

from flask import current_app, render_template, url_for
from sqlalchemy.orm import joinedload

from .. import emailer
from ..app import db
from ..models import (
    Participant,
    ParticipantAccount,
    PreworkAssignment,
    PreworkEmailLog,
    PreworkInvite,
    PreworkTemplate,
    Session,
    SessionParticipant,
)
from ..shared.accounts import ensure_participant_account
from ..shared.constants import MAGIC_LINK_TTL_DAYS
from ..shared.prework_status import ParticipantPreworkStatus, get_participant_prework_status
from ..shared.time import now_utc
from ..shared.names import greeting_name


class PreworkSendError(Exception):
    """Raised when prework invites cannot be sent."""


@dataclass
class PreworkSendResult:
    sent_count: int
    skipped_count: int
    failure_count: int
    statuses: dict[int, ParticipantPreworkStatus] = field(default_factory=dict)

    @property
    def any_failure(self) -> bool:
        return self.failure_count > 0


def _snapshot_for_template(template: PreworkTemplate) -> dict:
    questions = sorted(template.questions, key=lambda q: q.position)
    return {
        "questions": [
            {
                "index": index,
                "text": q.text,
                "required": q.required,
                "kind": q.kind,
                "min_items": q.min_items,
                "max_items": q.max_items,
            }
            for index, q in enumerate(questions, start=1)
        ],
        "resources": [r.resource_id for r in template.resources],
    }


def _ensure_assignment(
    session: Session,
    account: ParticipantAccount,
    template: PreworkTemplate,
    existing: dict[int, PreworkAssignment],
) -> PreworkAssignment:
    assignment = existing.get(account.id)
    if assignment:
        return assignment

    snapshot = _snapshot_for_template(template)
    due_at: datetime | None = None
    if session.start_date and session.daily_start_time:
        due_at = datetime.combine(session.start_date, session.daily_start_time) - timedelta(days=3)

    assignment = PreworkAssignment(
        session_id=session.id,
        participant_account_id=account.id,
        template_id=template.id,
        status="PENDING",
        due_at=due_at,
        snapshot_json=snapshot,
    )
    db.session.add(assignment)
    existing[account.id] = assignment
    return assignment


def _send_prework_email(
    session: Session,
    assignment: PreworkAssignment,
    account: ParticipantAccount,
    temp_password: str | None,
    participant: Participant | None = None,
) -> bool:
    token = secrets.token_urlsafe(16)
    assignment.magic_token_hash = hashlib.sha256(
        (token + current_app.secret_key).encode()
    ).hexdigest()
    assignment.magic_token_expires = now_utc() + timedelta(days=MAGIC_LINK_TTL_DAYS)
    db.session.flush()

    link = url_for(
        "auth.prework_magic",
        assignment_id=assignment.id,
        token=token,
        _external=True,
        _scheme="https",
    )
    recipient_name = greeting_name(participant=participant, account=account)
    subject = f"Prework for Workshop: {session.title}"
    body = render_template(
        "email/prework.txt",
        session=session,
        assignment=assignment,
        link=link,
        account=account,
        temp_password=temp_password,
        greeting_name=recipient_name,
    )
    html_body = render_template(
        "email/prework.html",
        session=session,
        assignment=assignment,
        link=link,
        account=account,
        temp_password=temp_password,
        greeting_name=recipient_name,
    )
    try:
        res = emailer.send(account.email, subject, body, html=html_body)
    except Exception as exc:  # pragma: no cover - defensive logging
        res = {"ok": False, "detail": str(exc)}

    if res.get("ok"):
        assignment.status = "SENT"
        assignment.sent_at = now_utc()
        db.session.add(
            PreworkEmailLog(
                assignment_id=assignment.id,
                to_email=account.email,
                subject=subject,
            )
        )
        current_app.logger.info(
            f'[MAIL-OUT] prework session={session.id} pa={account.id} to={account.email} subject="{subject}"'
        )
        return True

    current_app.logger.info(
        f"[MAIL-FAIL] prework session={session.id} pa={account.id} to={account.email} error=\"{res.get('detail')}\""
    )
    return False


def _eligible_participant_ids(
    statuses: dict[int, ParticipantPreworkStatus],
    explicit_ids: Sequence[int] | None,
    allow_completed_resend: bool,
) -> tuple[set[int], int]:
    skipped = 0
    if explicit_ids is not None:
        target_ids = set(explicit_ids)
    else:
        target_ids = set(statuses.keys())

    eligible: set[int] = set()
    for participant_id in target_ids:
        status = statuses.get(participant_id)
        if status is None:
            continue
        if status.status == "WAIVED":
            skipped += 1
            continue
        if status.is_submitted and not allow_completed_resend:
            skipped += 1
            continue
        eligible.add(participant_id)
    return eligible, skipped


def send_prework_invites(
    session: Session,
    participant_ids: Sequence[int] | None = None,
    *,
    allow_completed_resend: bool = False,
    sender_id: int | None = None,
) -> PreworkSendResult:
    """Send prework invites to session participants."""

    if session.no_prework or getattr(session, "prework_disabled", False):
        raise PreworkSendError("Prework disabled for this workshop")

    if not session.workshop_type_id:
        raise PreworkSendError("No workshop type configured")

    session_language = session.workshop_language or "en"
    template = PreworkTemplate.query.filter_by(
        workshop_type_id=session.workshop_type_id,
        language=session_language,
        is_active=True,
    ).first()
    if not template:
        raise PreworkSendError("No active prework template")

    statuses = get_participant_prework_status(session.id)
    eligible_ids, skipped_count = _eligible_participant_ids(
        statuses, participant_ids, allow_completed_resend
    )

    if not eligible_ids:
        return PreworkSendResult(
            sent_count=0,
            skipped_count=skipped_count,
            failure_count=0,
            statuses=statuses,
        )

    participants_query = (
        db.session.query(Participant)
        .join(SessionParticipant, SessionParticipant.participant_id == Participant.id)
        .filter(SessionParticipant.session_id == session.id)
        .filter(SessionParticipant.participant_id.in_(eligible_ids))
        .options(joinedload(Participant.account))
    )
    participants: Iterable[Participant] = participants_query.all()

    assignments = {
        a.participant_account_id: a
        for a in PreworkAssignment.query.filter_by(session_id=session.id).all()
    }

    sent_count = 0
    failure_count = 0
    account_cache: dict[str, ParticipantAccount] = {}

    for participant in participants:
        try:
            account, temp_password = ensure_participant_account(participant, account_cache)
        except ValueError:
            skipped_count += 1
            continue

        assignment = _ensure_assignment(session, account, template, assignments)
        if assignment.status == "WAIVED":
            skipped_count += 1
            continue

        if not allow_completed_resend and assignment.completed_at:
            skipped_count += 1
            continue

        if _send_prework_email(
            session, assignment, account, temp_password, participant
        ):
            sent_count += 1
            db.session.add(
                PreworkInvite(
                    session_id=session.id,
                    participant_id=participant.id,
                    sender_id=sender_id,
                    sent_at=assignment.sent_at or now_utc(),
                )
            )
        else:
            failure_count += 1

    if sent_count > 0 and not session.info_sent:
        session.info_sent = True
        if not session.info_sent_at:
            session.info_sent_at = now_utc()

    db.session.commit()
    updated_statuses = get_participant_prework_status(session.id)
    return PreworkSendResult(
        sent_count=sent_count,
        skipped_count=skipped_count,
        failure_count=failure_count,
        statuses=updated_statuses,
    )

