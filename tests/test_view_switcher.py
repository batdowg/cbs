import os
import pytest

from app.app import create_app, db, User, ParticipantAccount


@pytest.fixture
def app():
    os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
    os.makedirs('/srv', exist_ok=True)
    app = create_app()
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def login(client, email, password):
    return client.post('/login', data={'email': email, 'password': password}, follow_redirects=True)


def test_view_filters_nav_not_rbac(app):
    with app.app_context():
        u = User(email='staff@example.com', is_admin=True)
        u.set_password('pw')
        db.session.add(u)
        db.session.commit()
    client = app.test_client()
    login(client, 'staff@example.com', 'pw')
    client.get('/settings/view', query_string={'view': 'DELIVERY'})
    resp = client.get('/home')
    assert b'href="/sessions"' not in resp.data
    resp2 = client.get('/sessions')
    assert resp2.status_code == 200


def test_home_dashboard_per_view(app):
    with app.app_context():
        u = User(email='mat@example.com', is_admin=True)
        u.set_password('pw')
        db.session.add(u)
        db.session.commit()
    client = app.test_client()
    login(client, 'mat@example.com', 'pw')
    client.get('/settings/view', query_string={'view': 'MATERIALS'})
    resp = client.get('/home')
    assert b'Materials Dashboard' in resp.data


def test_cookie_override_and_clear(app):
    with app.app_context():
        u = User(email='sess@example.com', is_admin=True, preferred_view='SESSION_MANAGER')
        u.set_password('pw')
        db.session.add(u)
        db.session.commit()
    client = app.test_client()
    login(client, 'sess@example.com', 'pw')
    resp = client.get('/home')
    assert b'Sessions Dashboard' in resp.data
    client.get('/settings/view', query_string={'view': 'MATERIALS'})
    resp = client.get('/home')
    assert b'Materials Dashboard' in resp.data
    client.get('/settings/view', query_string={'view': 'INVALID'})
    resp = client.get('/home')
    assert b'Sessions Dashboard' in resp.data


def test_participant_forced_learner_view(app):
    with app.app_context():
        p = ParticipantAccount(email='learner@example.com', full_name='L', is_active=True)
        p.set_password('pw')
        db.session.add(p)
        db.session.commit()
    client = app.test_client()
    client.set_cookie('active_view', 'ADMIN', domain='localhost')
    login(client, 'learner@example.com', 'pw')
    resp = client.get('/home', follow_redirects=True)
    assert resp.request.path == '/my-workshops'
    assert b'Admin Dashboard' not in resp.data


def test_staff_view_switcher_shows_session_admin_option(app):
    with app.app_context():
        u = User(email='staff2@example.com', is_admin=True)
        u.set_password('pw')
        db.session.add(u)
        db.session.commit()
    client = app.test_client()
    login(client, 'staff2@example.com', 'pw')
    resp = client.get('/home')
    assert b'action="/settings/view"' in resp.data
    form_chunk = resp.data.split(b'action="/settings/view"')[1].split(b'</form>')[0]
    assert b'<option value="CSA"' in form_chunk
    assert b'Session Admin' in form_chunk
