from __future__ import annotations

from typing import Iterable, List

from .acl import (
    is_admin,
    is_contractor,
    is_delivery,
    is_kcrm,
    is_certificate_manager_only,
)


STAFF_VIEWS = [
    "ADMIN",
    "SESSION_MANAGER",
    "SESSION_ADMIN",
    "MATERIAL_MANAGER",
    "DELIVERY",
    "LEARNER",
]
DELIVERY_ONLY_VIEWS = ["DELIVERY", "SESSION_ADMIN", "LEARNER"]
CRM_ONLY_VIEWS = ["SESSION_MANAGER", "MATERIAL_MANAGER", "LEARNER"]
CSA_VIEWS = ["SESSION_ADMIN", "LEARNER"]


def _valid_staff_views(views: Iterable[str], default_view: str) -> List[str]:
    choices = [view.upper() for view in views]
    if default_view.upper() not in choices:
        choices.append(default_view.upper())
    return choices


def get_view_options(current_user) -> list[str]:
    """Return the ordered view options for the selector."""

    if not current_user:
        return []
    if is_certificate_manager_only(current_user):
        return ["CERTIFICATE_MANAGER"]
    if is_contractor(current_user):
        return []

    is_delivery_only = is_delivery(current_user) and not (
        is_admin(current_user) or is_kcrm(current_user)
    )
    if is_delivery_only:
        return DELIVERY_ONLY_VIEWS

    is_crm_only = is_kcrm(current_user) and not (
        is_delivery(current_user)
        or is_contractor(current_user)
        or is_admin(current_user)
    )
    if is_crm_only:
        return CRM_ONLY_VIEWS

    if is_admin(current_user) or is_kcrm(current_user) or is_delivery(current_user):
        return STAFF_VIEWS

    return []


def get_default_view(current_user) -> str:
    """Return the default view for a user when no preference is stored."""

    if not current_user:
        return "LEARNER"
    if is_certificate_manager_only(current_user):
        return "CERTIFICATE_MANAGER"
    if is_contractor(current_user):
        return "DELIVERY"
    if is_delivery(current_user) and not (
        is_admin(current_user) or is_kcrm(current_user)
    ):
        return "DELIVERY"
    if is_kcrm(current_user) and not (
        is_delivery(current_user) or is_contractor(current_user) or is_admin(current_user)
    ):
        return "SESSION_MANAGER"
    if is_admin(current_user) or is_kcrm(current_user) or is_delivery(current_user):
        return "ADMIN"
    return "LEARNER"


def get_active_view(current_user, request, is_csa: bool = False) -> str:
    """Resolve the active view for this request."""

    cookie_view = (request.cookies.get("active_view") or "").upper()
    if current_user:
        default_view = get_default_view(current_user)
        allowed = _valid_staff_views(get_view_options(current_user), default_view)
        if cookie_view in allowed:
            return cookie_view
        pref = (current_user.preferred_view or "").upper()
        if pref in allowed:
            return pref
        return default_view
    if is_csa:
        if cookie_view in CSA_VIEWS:
            return cookie_view
        return "SESSION_ADMIN"
    # participant context
    return "LEARNER"
