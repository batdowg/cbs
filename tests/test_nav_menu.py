from __future__ import annotations

from flask import url_for

from app.app import db
from app.models import Language, User


def _login(client, user_id: int) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def _ensure_language() -> None:
    if not Language.query.filter_by(name="English").first():
        db.session.add(Language(name="English", sort_order=1, is_active=True))
        db.session.flush()


def test_sidebar_positions_new_certificate_session(app, client):
    with app.app_context():
        _ensure_language()
        admin = User(email="admin@example.com", is_admin=True, is_app_admin=True)
        admin.set_password("pw")
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id

    with app.test_request_context():
        cert_href = url_for("certificate_sessions.new")

    _login(client, admin_id)

    response = client.get("/home", follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    nav_start = html.index('<nav class="kt-nav">')
    nav_end = html.index("</nav>", nav_start)
    nav_html = html[nav_start:nav_end]
    assert cert_href in nav_html
    new_order_index = nav_html.index("New Order")
    cert_index = nav_html.index("New Certificate Session")
    workshop_index = nav_html.index("Workshop Dashboard")
    assert new_order_index < cert_index < workshop_index

    cert_page = client.get(cert_href)
    assert cert_page.status_code == 200
    page_html = cert_page.get_data(as_text=True)
    nav_start = page_html.index('<nav class="kt-nav">')
    nav_end = page_html.index("</nav>", nav_start)
    nav_html = page_html[nav_start:nav_end]
    link_start = nav_html.index(f'<a href="{cert_href}"')
    link_end = nav_html.index("</a>", link_start)
    link_markup = nav_html[link_start:link_end]
    assert 'aria-current="page"' in link_markup

