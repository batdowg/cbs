from __future__ import annotations

"""Sidebar navigation configuration.

The mapping in ``VIEW_MENUS`` is **display only** – it controls which links are
rendered for a given View. Permission checks live in the routes themselves.
"""

from copy import deepcopy
from typing import Any, Dict, List

from flask import request, url_for

MenuItem = Dict[str, Any]


# --- Common menu items ----------------------------------------------------

HOME: MenuItem = {"id": "home", "label": "Home", "endpoint": "home"}
NEW_ORDER: MenuItem = {
    "id": "new_order",
    "label": "New Order",
    "href": "https://cbs.ktapps.net/sessions/new",
}
NEW_CERTIFICATE_SESSION: MenuItem = {
    "id": "new_certificate_session",
    "label": "New Certificate Session",
    "endpoint": "certificates.new_certificate_session",
}
WORKSHOP_DASHBOARD: MenuItem = {
    "id": "sessions",
    "label": "Workshop Dashboard",
    "endpoint": "sessions.list_sessions",
}
MATERIAL_DASHBOARD: MenuItem = {
    "id": "materials",
    "label": "Material Dashboard",
    "endpoint": "materials_orders.list_orders",
}
SURVEYS: MenuItem = {"id": "surveys", "label": "Surveys", "endpoint": "surveys"}
MY_SESSIONS: MenuItem = {
    "id": "my_sessions",
    "label": "My Sessions",
    "endpoint": "my_sessions.list_my_sessions",
}
MY_WORKSHOPS: MenuItem = {
    "id": "my_workshops",
    "label": "My Workshops",
    "endpoint": "learner.my_workshops",
}
MY_RESOURCES: MenuItem = {
    "id": "my_resources",
    "label": "My Resources",
    "endpoint": "learner.my_resources",
}
MY_CERTS: MenuItem = {
    "id": "my_certificates",
    "label": "My Certificates",
    "endpoint": "learner.my_certs",
}
PROFILE_LINK: MenuItem = {
    "id": "profile_details",
    "label": "My Profile",
    "endpoint": "learner.profile",
}
PROFILE_GROUP: MenuItem = {
    "id": "profile",
    "label": "My Profile",
    "children": [PROFILE_LINK, MY_RESOURCES, {"id": "profile_certs", "label": "My Certificates", "endpoint": "learner.my_certs"}],
}
LOGOUT: MenuItem = {"id": "logout", "label": "Logout", "endpoint": "auth.logout"}

# Settings submenu items
CLIENTS: MenuItem = {
    "id": "clients",
    "label": "Clients",
    "endpoint": "clients.list_clients",
}
WORKSHOP_TYPES: MenuItem = {
    "id": "workshop_types",
    "label": "Workshop Types",
    "endpoint": "workshop_types.list_types",
}
MATERIAL_SETTINGS: MenuItem = {
    "id": "material_settings",
    "label": "Material Settings",
    "children": [
        {
            "id": "standard",
            "label": "Standard",
            "endpoint": "settings_materials.list_options",
            "args": {"slug": "standard"},
        },
        {
            "id": "modular",
            "label": "Modular",
            "endpoint": "settings_materials.list_options",
            "args": {"slug": "modular"},
        },
        {
            "id": "ldi",
            "label": "LDI",
            "endpoint": "settings_materials.list_options",
            "args": {"slug": "ldi"},
        },
        {
            "id": "bulk",
            "label": "Bulk Order",
            "endpoint": "settings_materials.list_options",
            "args": {"slug": "bulk"},
        },
        {
            "id": "simulation",
            "label": "Simulation",
            "endpoint": "settings_materials.list_options",
            "args": {"slug": "simulation"},
        },
    ],
}
SIMULATION_OUTLINES: MenuItem = {
    "id": "simulation_outlines",
    "label": "Simulation Outlines",
    "endpoint": "settings_simulations.list_simulations",
}
RESOURCES_SETTING: MenuItem = {
    "id": "resources",
    "label": "Resources",
    "endpoint": "settings_resources.list_resources",
}
LANGUAGES: MenuItem = {
    "id": "languages",
    "label": "Languages",
    "endpoint": "settings_languages.list_langs",
}
CERT_TEMPLATES: MenuItem = {
    "id": "certificate_templates",
    "label": "Certificate Templates",
    "endpoint": "settings_cert_templates.list_series",
}
USERS: MenuItem = {"id": "users", "label": "Users", "endpoint": "users.list_users"}
MAIL_SETTINGS: MenuItem = {
    "id": "mail_settings",
    "label": "Mail & Notification",
    "endpoint": "settings_mail.settings",
}

SETTINGS_ALL = [
    CLIENTS,
    WORKSHOP_TYPES,
    MATERIAL_SETTINGS,
    SIMULATION_OUTLINES,
    RESOURCES_SETTING,
    LANGUAGES,
    CERT_TEMPLATES,
    USERS,
    MAIL_SETTINGS,
]
SETTINGS_SESSION_MANAGER = [CLIENTS, WORKSHOP_TYPES, RESOURCES_SETTING, CERT_TEMPLATES]
SETTINGS_MATERIAL_MANAGER = [
    CLIENTS,
    WORKSHOP_TYPES,
    MATERIAL_SETTINGS,
    SIMULATION_OUTLINES,
    RESOURCES_SETTING,
]
SETTINGS_DELIVERY = [RESOURCES_SETTING]


# --- View → menu mapping --------------------------------------------------

VIEW_MENUS: Dict[str, List[MenuItem]] = {
    "ADMIN": [
        HOME,
        NEW_ORDER,
        NEW_CERTIFICATE_SESSION,
        WORKSHOP_DASHBOARD,
        MATERIAL_DASHBOARD,
        SURVEYS,
        PROFILE_GROUP,
        {"id": "settings", "label": "Settings", "children": SETTINGS_ALL},
        LOGOUT,
    ],
    "SESSION_MANAGER": [
        HOME,
        NEW_ORDER,
        NEW_CERTIFICATE_SESSION,
        WORKSHOP_DASHBOARD,
        MATERIAL_DASHBOARD,
        SURVEYS,
        PROFILE_GROUP,
        {"id": "settings", "label": "Settings", "children": SETTINGS_SESSION_MANAGER},
        LOGOUT,
    ],
    "SESSION_ADMIN": [
        HOME,
        MY_SESSIONS,
        NEW_CERTIFICATE_SESSION,
        WORKSHOP_DASHBOARD,
        MATERIAL_DASHBOARD,
        PROFILE_GROUP,
        LOGOUT,
    ],
    "MATERIAL_MANAGER": [
        HOME,
        NEW_ORDER,
        NEW_CERTIFICATE_SESSION,
        MATERIAL_DASHBOARD,
        PROFILE_GROUP,
        {"id": "settings", "label": "Settings", "children": SETTINGS_MATERIAL_MANAGER},
        LOGOUT,
    ],
    "DELIVERY": [
        HOME,
        MY_SESSIONS,
        NEW_CERTIFICATE_SESSION,
        WORKSHOP_DASHBOARD,
        SURVEYS,
        PROFILE_GROUP,
        {"id": "settings", "label": "Settings", "children": SETTINGS_DELIVERY},
        LOGOUT,
    ],
    "LEARNER": [
        HOME,
        MY_WORKSHOPS,
        MY_RESOURCES,
        MY_CERTS,
        {"id": "profile", "label": "My Profile", "endpoint": "learner.profile"},
        LOGOUT,
    ],
}


def _mark_paths(items: List[MenuItem]) -> None:
    """Populate ``href`` and active/ancestor flags for the given items."""

    current_path = request.path
    for item in items:
        endpoint = item.get("endpoint")
        args = item.get("args") or {}
        href = item.get("href")
        if endpoint:
            href = url_for(endpoint, **args)
            item["href"] = href
            item["is_current"] = href == current_path
        elif href:
            item["href"] = href
            item["is_current"] = href == current_path
        else:
            item["href"] = None
            item["is_current"] = False
        children = item.get("children") or []
        if children:
            _mark_paths(children)
            item["is_ancestor"] = any(
                child.get("is_current") or child.get("is_ancestor")
                for child in children
            )
        else:
            item["is_ancestor"] = False


def build_menu(active_view: str) -> List[MenuItem]:
    """Return the menu items for ``active_view`` with active-state flags."""

    menu = deepcopy(VIEW_MENUS.get(active_view, VIEW_MENUS["LEARNER"]))
    _mark_paths(menu)
    return menu

