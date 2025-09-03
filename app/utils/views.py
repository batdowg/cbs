ALLOWED_VIEWS = ['ADMIN', 'SESSION_MANAGER', 'MATERIALS', 'DELIVERY', 'LEARNER']


def get_active_view(current_user, request) -> str:
    """Resolve the active view for this request."""
    cookie_view = (request.cookies.get('active_view') or '').upper()
    if current_user:
        if cookie_view in ALLOWED_VIEWS:
            return cookie_view
        pref = (current_user.preferred_view or '').upper()
        if pref in ALLOWED_VIEWS:
            return pref
        return 'ADMIN'
    # participant context
    return 'LEARNER'
