from typing import Any, Dict, List

from .acl import can_manage_users

MenuItem = Dict[str, Any]


def _staff_base_menu(user, show_resources: bool) -> List[MenuItem]:
    items: List[MenuItem] = []
    items.append({'id': 'home', 'label': 'Home', 'endpoint': 'home'})
    items.append({'id': 'my_sessions', 'label': 'My Sessions', 'endpoint': 'my_sessions.list_my_sessions'})
    if user.is_app_admin or user.is_admin:
        items.append({'id': 'sessions', 'label': 'Sessions', 'endpoint': 'sessions.list_sessions'})
    if user.is_app_admin or user.is_admin or user.is_kcrm or user.is_kt_delivery or user.is_kt_contractor:
        items.append({'id': 'materials', 'label': 'Materials', 'endpoint': 'materials_orders.list_orders'})
    items.append({'id': 'surveys', 'label': 'Surveys', 'endpoint': 'surveys'})
    if show_resources:
        items.append({'id': 'my_resources', 'label': 'My Resources', 'endpoint': 'learner.my_resources'})
    profile_children = [
        {'id': 'profile_details', 'label': 'My Profile', 'endpoint': 'learner.profile'},
        {'id': 'profile_certs', 'label': 'My Certificates', 'endpoint': 'learner.my_certs'},
    ]
    items.append({'id': 'profile', 'label': 'My Profile', 'children': profile_children})
    settings_children: List[MenuItem] = []
    if can_manage_users(user):
        settings_children.extend([
            {'id': 'clients', 'label': 'Clients', 'endpoint': 'clients.list_clients'},
            {'id': 'workshop_types', 'label': 'Workshop Types', 'endpoint': 'workshop_types.list_types'},
            {'id': 'languages', 'label': 'Languages', 'endpoint': 'settings_languages.list_langs'},
            {'id': 'materials_settings', 'label': 'Material settings', 'children': [
                {'id': 'standard', 'label': 'Standard', 'endpoint': 'settings_materials.list_options', 'args': {'slug': 'standard'}},
                {'id': 'modular', 'label': 'Modular', 'endpoint': 'settings_materials.list_options', 'args': {'slug': 'modular'}},
                {'id': 'ldi', 'label': 'LDI', 'endpoint': 'settings_materials.list_options', 'args': {'slug': 'ldi'}},
                {'id': 'bulk', 'label': 'Bulk Order', 'endpoint': 'settings_materials.list_options', 'args': {'slug': 'bulk'}},
                {'id': 'simulation', 'label': 'Simulation', 'endpoint': 'settings_materials.list_options', 'args': {'slug': 'simulation'}},
            ]},
        ])
    if user.is_app_admin or user.is_admin or user.is_kt_delivery or getattr(user, 'is_kt_facilitator', False) or user.is_kt_contractor:
        settings_children.append({'id': 'resources', 'label': 'Resources', 'endpoint': 'settings_resources.list_resources'})
    if user.is_app_admin or user.is_admin or user.is_kt_staff or user.is_kt_delivery or user.is_kt_contractor:
        settings_children.append({'id': 'simulation_outlines', 'label': 'Simulation Outlines', 'endpoint': 'settings_simulations.list_simulations'})
    if can_manage_users(user):
        settings_children.extend([
            {'id': 'users', 'label': 'Users', 'endpoint': 'users.list_users'},
            {'id': 'mail', 'label': 'Mail Settings', 'endpoint': 'settings_mail.settings'},
            {'id': 'roles', 'label': 'Roles Matrix', 'endpoint': 'settings_roles.roles_matrix'},
        ])
    if settings_children:
        items.append({'id': 'settings', 'label': 'Settings', 'children': settings_children})
    items.append({'id': 'logout', 'label': 'Logout', 'endpoint': 'auth.logout'})
    return items


def _participant_menu(show_resources: bool, is_csa: bool) -> List[MenuItem]:
    items: List[MenuItem] = []
    items.append({'id': 'home', 'label': 'Home', 'endpoint': 'home'})
    if is_csa:
        items.append({'id': 'my_sessions', 'label': 'My Sessions', 'endpoint': 'csa.my_sessions'})
        items.append({'id': 'my_workshops', 'label': 'My Workshops', 'endpoint': 'learner.my_workshops'})
    else:
        items.append({'id': 'my_workshops', 'label': 'My Workshops', 'endpoint': 'learner.my_workshops'})
    if show_resources:
        items.append({'id': 'my_resources', 'label': 'My Resources', 'endpoint': 'learner.my_resources'})
    items.append({'id': 'profile', 'label': 'My Profile', 'endpoint': 'learner.profile'})
    items.append({'id': 'logout', 'label': 'Logout', 'endpoint': 'auth.logout'})
    return items


VIEW_FILTERS = {
    'ADMIN': {'home', 'my_sessions', 'sessions', 'materials', 'surveys', 'my_resources', 'profile', 'settings', 'logout'},
    'SESSION_MANAGER': {'home', 'my_sessions', 'sessions', 'surveys', 'my_resources', 'profile', 'logout'},
    'MATERIALS': {'home', 'my_sessions', 'materials', 'surveys', 'my_resources', 'profile', 'settings', 'logout'},
    'DELIVERY': {'home', 'my_sessions', 'surveys', 'my_resources', 'profile', 'logout'},
    'LEARNER': {'home', 'my_workshops', 'my_resources', 'profile', 'logout'},
    'CSA': {'home', 'my_sessions', 'my_workshops', 'my_resources', 'profile', 'logout'},
}


def build_menu(current_user, active_view: str, show_resources: bool, is_csa: bool = False) -> List[MenuItem]:
    if current_user:
        menu = _staff_base_menu(current_user, show_resources)
    else:
        menu = _participant_menu(show_resources, is_csa)
    allowed = VIEW_FILTERS.get(active_view, VIEW_FILTERS['LEARNER'])
    filtered = [item for item in menu if item['id'] in allowed]
    return filtered
