from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict

from sqlalchemy.orm import Query

from ..app import db
from ..models import Participant, ParticipantAccount, PreworkAssignment, SessionParticipant


@dataclass
class ParticipantPreworkStatus:
    """Lightweight view of a participant's prework state for a session."""

    participant_id: int
    account_id: int | None
    assignment_id: int | None
    status: str | None
    sent_at: datetime | None
    completed_at: datetime | None

    @property
    def is_submitted(self) -> bool:
        return bool(self.completed_at)


def get_participant_prework_status(session_id: int) -> Dict[int, ParticipantPreworkStatus]:
    """Return a mapping of participant id → prework status for the session."""

    query: Query = (
        db.session.query(
            SessionParticipant.participant_id,
            Participant.account_id,
            PreworkAssignment.id,
            PreworkAssignment.status,
            PreworkAssignment.sent_at,
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
        .filter(SessionParticipant.session_id == session_id)
    )

    results: Dict[int, ParticipantPreworkStatus] = {}
    for (
        participant_id,
        account_id,
        assignment_id,
        status,
        sent_at,
        completed_at,
    ) in query.all():
        results[participant_id] = ParticipantPreworkStatus(
            participant_id=participant_id,
            account_id=account_id,
            assignment_id=assignment_id,
            status=status,
            sent_at=sent_at,
            completed_at=completed_at,
        )
    return results

