from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict

from sqlalchemy import func
from sqlalchemy.orm import Query

from ..app import db
from ..models import (
    Participant,
    ParticipantAccount,
    PreworkAssignment,
    PreworkInvite,
    SessionParticipant,
)


@dataclass
class ParticipantPreworkStatus:
    """Lightweight view of a participant's prework state for a session."""

    participant_id: int
    account_id: int | None
    assignment_id: int | None
    status: str | None
    sent_at: datetime | None
    invite_count: int
    last_invite_sent_at: datetime | None
    completed_at: datetime | None

    @property
    def is_submitted(self) -> bool:
        return bool(self.completed_at)


def get_participant_prework_status(session_id: int) -> Dict[int, ParticipantPreworkStatus]:
    """Return a mapping of participant id → prework status for the session."""

    invite_subquery = (
        db.session.query(
            PreworkInvite.participant_id.label("participant_id"),
            func.count(PreworkInvite.id).label("invite_count"),
            func.max(PreworkInvite.sent_at).label("last_invite_sent_at"),
        )
        .filter(PreworkInvite.session_id == session_id)
        .group_by(PreworkInvite.participant_id)
        .subquery()
    )

    query: Query = (
        db.session.query(
            SessionParticipant.participant_id,
            Participant.account_id,
            PreworkAssignment.id,
            PreworkAssignment.status,
            PreworkAssignment.sent_at,
            invite_subquery.c.invite_count,
            invite_subquery.c.last_invite_sent_at,
            PreworkAssignment.completed_at,
        )
        .join(Participant, SessionParticipant.participant_id == Participant.id)
        .outerjoin(
            ParticipantAccount,
            Participant.account_id == ParticipantAccount.id,
        )
        .outerjoin(
            PreworkAssignment,
            (PreworkAssignment.session_id == session_id)
            & (PreworkAssignment.participant_account_id == ParticipantAccount.id),
        )
        .outerjoin(
            invite_subquery,
            invite_subquery.c.participant_id
            == SessionParticipant.participant_id,
        )
        .filter(SessionParticipant.session_id == session_id)
    )

    results: Dict[int, ParticipantPreworkStatus] = {}
    for (
        participant_id,
        account_id,
        assignment_id,
        status,
        sent_at,
        invite_count,
        last_invite_sent_at,
        completed_at,
    ) in query.all():
        results[participant_id] = ParticipantPreworkStatus(
            participant_id=participant_id,
            account_id=account_id,
            assignment_id=assignment_id,
            status=status,
            sent_at=sent_at,
            invite_count=int(invite_count or 0),
            last_invite_sent_at=last_invite_sent_at,
            completed_at=completed_at,
        )
    return results

