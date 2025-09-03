STAFF_VIEWS = ['ADMIN', 'SESSION_MANAGER', 'MATERIALS', 'DELIVERY', 'LEARNER']
CSA_VIEWS = ['CSA', 'LEARNER']


def get_active_view(current_user, request, is_csa: bool = False) -> str:
    """Resolve the active view for this request."""
    cookie_view = (request.cookies.get('active_view') or '').upper()
    if current_user:
        if cookie_view in STAFF_VIEWS:
            return cookie_view
        pref = (current_user.preferred_view or '').upper()
        if pref in STAFF_VIEWS:
            return pref
        return 'ADMIN'
    if is_csa:
        if cookie_view in CSA_VIEWS:
            return cookie_view
        return 'CSA'
    # participant context
    return 'LEARNER'
