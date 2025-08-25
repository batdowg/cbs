from __future__ import annotations

from typing import Dict

from sqlalchemy import func

from ..app import db, User
from ..models import Participant, ParticipantAccount, SessionParticipant, Session


def provision_for_session(session: Session) -> Dict[str, int]:
    created = skipped_staff = reactivated = already_active = kept_password = 0
    links = SessionParticipant.query.filter_by(session_id=session.id).all()
    for link in links:
        participant = db.session.get(Participant, link.participant_id)
        if not participant:
            continue
        email = (participant.email or "").lower()
        if not email:
            continue
        # skip if staff user exists
        user = User.query.filter(func.lower(User.email) == email).first()
        if user:
            skipped_staff += 1
            continue
        account = ParticipantAccount.query.filter(
            func.lower(ParticipantAccount.email) == email
        ).first()
        if not account:
            account = ParticipantAccount(
                email=email,
                full_name=participant.full_name or "",
                certificate_name=participant.full_name or "",
                is_active=True,
            )
            account.set_password("KTRocks!")
            db.session.add(account)
            created += 1
        else:
            if account.password_hash:
                kept_password += 1
            else:
                account.set_password("KTRocks!")
            if not account.is_active:
                account.is_active = True
                reactivated += 1
            else:
                already_active += 1
            if not account.certificate_name and account.full_name:
                account.certificate_name = account.full_name
        if participant.account_id != account.id:
            participant.account_id = account.id
    db.session.commit()
    return {
        "created": created,
        "skipped_staff": skipped_staff,
        "reactivated": reactivated,
        "already_active": already_active,
        "kept_password": kept_password,
    }


def provision_participant_accounts_for_session(session_id: int) -> Dict[str, int]:
    session = db.session.get(Session, session_id)
    if not session:
        return {"created": 0, "skipped_staff": 0, "reactivated": 0, "already_active": 0}
    return provision_for_session(session)


def provision_new_participants_if_ready(session: Session) -> Dict[str, int]:
    if not session.ready_for_delivery:
        return {"created": 0, "skipped_staff": 0, "reactivated": 0, "already_active": 0}
    return provision_for_session(session)


def deactivate_orphan_accounts_for_session(session_id: int) -> int:
    deactivated = 0
    links = SessionParticipant.query.filter_by(session_id=session_id).all()
    for link in links:
        participant = db.session.get(Participant, link.participant_id)
        if not participant or not participant.account_id:
            continue
        account = db.session.get(ParticipantAccount, participant.account_id)
        if not account or not account.is_active:
            continue
        active_links = (
            db.session.query(SessionParticipant)
            .join(Session, SessionParticipant.session_id == Session.id)
            .filter(
                SessionParticipant.participant_id == participant.id,
                Session.status.notin_(["Cancelled", "Closed", "On Hold"]),
            )
            .count()
        )
        if active_links == 0:
            account.is_active = False
            deactivated += 1
    db.session.commit()
    return deactivated
