from __future__ import annotations

from typing import Dict, Optional

from flask import current_app
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from ..app import db
from ..models import Participant, ParticipantAccount
from .strings import normalize_email


def get_participant_account_by_email(email: str) -> Optional[ParticipantAccount]:
    """Return participant account by email (case-insensitive)."""
    email_norm = normalize_email(email)
    if not email_norm:
        return None
    return ParticipantAccount.query.filter(
        func.lower(ParticipantAccount.email) == email_norm
    ).one_or_none()


def ensure_participant_account(
    participant: Participant, cache: Optional[Dict[str, ParticipantAccount]] = None
) -> ParticipantAccount:
    """Ensure a ParticipantAccount exists for the given participant."""
    email_norm = normalize_email(participant.email or "")
    if cache is not None and email_norm in cache:
        account = cache[email_norm]
        participant.account_id = account.id
        db.session.add(participant)
        return account

    account = get_participant_account_by_email(email_norm)
    if account:
        participant.account_id = account.id
        db.session.add(participant)
        current_app.logger.info(
            f"[ACCOUNT] found pa={account.id} email={email_norm}"
        )
        if cache is not None:
            cache[email_norm] = account
        return account

    account = ParticipantAccount(
        email=email_norm,
        full_name=participant.full_name or participant.email,
        certificate_name=participant.full_name or participant.email,
        is_active=True,
    )
    db.session.add(account)
    try:
        db.session.flush()
        current_app.logger.info(
            f"[ACCOUNT] created pa={account.id} email={email_norm}"
        )
    except IntegrityError:
        db.session.rollback()
        account = get_participant_account_by_email(email_norm)
        if account:
            current_app.logger.info(
                f"[ACCOUNT] reused pa={account.id} email={email_norm}"
            )
        else:
            raise
    participant.account_id = account.id
    db.session.add(participant)
    if cache is not None:
        cache[email_norm] = account
    return account
