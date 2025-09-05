from __future__ import annotations

from typing import Dict, Optional
import secrets

from flask import current_app
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from ..app import db
from ..models import Participant, ParticipantAccount, User, AuditLog
from .strings import normalize_email
from ..constants import DEFAULT_PARTICIPANT_PASSWORD, ROLE_ATTRS, CONTRACTOR
from ..utils.acl import validate_role_combo, can_demote_to_contractor


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
) -> tuple[ParticipantAccount, Optional[str]]:
    """Ensure a ParticipantAccount exists for the given participant.

    Returns the account and a temp password if one was generated.
    """
    email_norm = normalize_email(participant.email or "")
    if cache is not None and email_norm in cache:
        account = cache[email_norm]
        participant.account_id = account.id
        db.session.add(participant)
        temp_password = None
        if account.password_hash is None:
            temp_password = DEFAULT_PARTICIPANT_PASSWORD
            account.set_password(temp_password)
        return account, temp_password

    user = User.query.filter(func.lower(User.email) == email_norm).first()
    if user and not participant.full_name:
        participant.full_name = user.full_name
    if user and not getattr(participant, "title", None):
        participant.title = user.title

    account = get_participant_account_by_email(email_norm)
    temp_password: Optional[str] = None
    if account:
        participant.account_id = account.id
        db.session.add(participant)
        current_app.logger.info(
            f"[ACCOUNT] found pa={account.id} email={email_norm}"
        )
        if account.password_hash is None:
            temp_password = DEFAULT_PARTICIPANT_PASSWORD
            account.set_password(temp_password)
        if cache is not None:
            cache[email_norm] = account
        return account, temp_password
    account = ParticipantAccount(
        email=email_norm,
        full_name=participant.full_name or (user.full_name if user else participant.email),
        certificate_name=participant.full_name or (user.full_name if user else participant.email),
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
    temp_password = DEFAULT_PARTICIPANT_PASSWORD
    account.set_password(temp_password)
    participant.account_id = account.id
    db.session.add(participant)
    if cache is not None:
        cache[email_norm] = account
    return account, temp_password


def promote_participant_to_user(email: str, role_names: list[str], actor) -> User:
    """Promote a participant account to a staff user."""
    account = get_participant_account_by_email(email)
    if not account:
        raise ValueError("Participant not found")
    validate_role_combo(role_names)
    if User.query.filter(func.lower(User.email) == account.email.lower()).first():
        raise ValueError("Already a user")
    user = User(email=account.email, full_name=account.full_name, region="NA")
    temp_password = secrets.token_urlsafe(8)
    user.set_password(temp_password)
    if hasattr(user, "must_change_password"):
        user.must_change_password = True
    for name, attr in ROLE_ATTRS.items():
        setattr(user, attr, name in role_names)
    db.session.add(user)
    db.session.add(
        AuditLog(
            user_id=actor.id,
            action="PROMOTE",
            details=f"email={user.email} roles={','.join(role_names)} actor={actor.id}",
        )
    )
    return user


def demote_user_to_contractor(user: User, actor) -> None:
    if not can_demote_to_contractor(actor, user):
        raise PermissionError
    for name, attr in ROLE_ATTRS.items():
        setattr(user, attr, False)
    user.is_kt_contractor = True
    db.session.add(user)
    db.session.add(
        AuditLog(
            user_id=actor.id,
            action="DEMOTE→CONTRACTOR",
            details=f"user_id={user.id} actor={actor.id}",
        )
    )
