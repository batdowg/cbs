from datetime import date

from app.app import db
from app.models import Client, ParticipantAccount, Session, User, WorkshopType


def _login(client, email, password):
    return client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=True,
    )


def test_auth_roles_home_selection(app, client):
    with app.app_context():
        admin = User(
            email="admin@example.com",
            is_app_admin=True,
            is_admin=True,
            region="NA",
        )
        admin.set_password("pw")
        crm = User(email="crm@example.com", is_kcrm=True, region="NA")
        crm.set_password("pw")
        facilitator = User(
            email="facilitator@example.com",
            is_kt_delivery=True,
            region="NA",
        )
        facilitator.set_password("pw")
        contractor = User(
            email="contractor@example.com",
            is_kt_contractor=True,
            region="NA",
        )
        contractor.set_password("pw")
        participant = ParticipantAccount(
            email="learner@example.com", full_name="Learner", is_active=True
        )
        participant.set_password("pw")
        csa_account = ParticipantAccount(
            email="csa@example.com", full_name="CSA", is_active=True
        )
        csa_account.set_password("pw")
        workshop_type = WorkshopType(code="WT", name="Workshop", cert_series="fn")
        client_record = Client(name="Client")
        session = Session(
            title="CSA Session",
            start_date=date.today(),
            end_date=date.today(),
            workshop_language="en",
            region="NA",
            number_of_class_days=1,
            workshop_type=workshop_type,
            client=client_record,
            csa_account=csa_account,
        )
        db.session.add_all(
            [
                admin,
                crm,
                facilitator,
                contractor,
                participant,
                csa_account,
                workshop_type,
                client_record,
                session,
            ]
        )
        db.session.commit()

    # Admin stays on staff home and can switch to materials dashboard
    resp = _login(client, "admin@example.com", "pw")
    assert resp.request.path == "/home"
    admin_html = resp.get_data(as_text=True)
    assert "Switch views here." in admin_html
    assert "<label>View:</label>" in admin_html
    assert "Switch to Admin" not in admin_html
    cert_form = client.get("/certificates/new")
    assert cert_form.status_code == 200
    assert "New Certificate Session" in cert_form.get_data(as_text=True)
    response = client.get(
        "/settings/view", query_string={"view": "MATERIAL_MANAGER"}, follow_redirects=False
    )
    assert response.status_code == 302
    redirected = client.get("/home", follow_redirects=False)
    assert redirected.status_code == 302
    assert redirected.headers["Location"].endswith("/materials")
    client.get("/logout")

    # CRM lands on My Sessions
    resp = _login(client, "crm@example.com", "pw")
    assert resp.request.path == "/my-sessions"
    crm_html = resp.get_data(as_text=True)
    assert "Switch views here." in crm_html
    assert "<label>View:</label>" in crm_html
    assert "Switch to Admin" not in crm_html
    client.get("/logout")

    # Facilitator lands on My Sessions
    resp = _login(client, "facilitator@example.com", "pw")
    assert resp.request.path == "/my-sessions"
    facilitator_html = resp.get_data(as_text=True)
    assert "Switch views here." in facilitator_html
    assert "<label>View:</label>" in facilitator_html
    assert "Switch to Admin" not in facilitator_html
    client.get("/logout")

    # Contractor is routed to My Sessions
    resp = _login(client, "contractor@example.com", "pw")
    assert resp.request.path == "/my-sessions"
    contractor_html = resp.get_data(as_text=True)
    assert "Switch views here." not in contractor_html
    assert "<label>View:</label>" not in contractor_html
    assert "Switch to Admin" not in contractor_html
    client.get("/logout")

    # Learner account goes to participant workshops
    resp = _login(client, "learner@example.com", "pw")
    assert resp.request.path == "/my-workshops"
    learner_html = resp.get_data(as_text=True)
    assert "Switch views here." not in learner_html
    assert "<label>View:</label>" not in learner_html
    assert "Switch to Admin" not in learner_html
    client.get("/logout")

    # CSA account is routed to CSA dashboard
    resp = _login(client, "csa@example.com", "pw")
    assert resp.request.path == "/csa/my-sessions"
    csa_html = resp.get_data(as_text=True)
    assert "Switch views here." not in csa_html
    assert "<label>View:</label>" not in csa_html
    assert "Switch to Admin" not in csa_html
