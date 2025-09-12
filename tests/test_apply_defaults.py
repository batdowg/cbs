import os
from datetime import date

import pytest

from app.app import create_app, db
from app.models import (
    User,
    WorkshopType,
    Session,
    MaterialsOption,
    WorkshopTypeMaterialDefault,
    MaterialOrderItem,
    Participant,
    SessionParticipant,
)


@pytest.fixture
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    app = create_app()
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def setup_session(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True, is_admin=True)
        admin.set_password("x")
        wt = WorkshopType(code="WT", name="WT", cert_series="fn")
        opt = MaterialsOption(order_type="KT-Run Standard materials", title="ItemA", formats=["Digital"])
        db.session.add_all([admin, wt, opt])
        db.session.commit()
        default = WorkshopTypeMaterialDefault(
            workshop_type_id=wt.id,
            delivery_type="Onsite",
            region_code="NA",
            language="en",
            catalog_ref=f"materials_options:{opt.id}",
            default_format="Digital",
            active=True,
        )
        sess = Session(
            title="S1",
            workshop_type_id=wt.id,
            delivery_type="Onsite",
            region="NA",
            workshop_language="en",
            start_date=date.today(),
            end_date=date.today(),
        )
        p1 = Participant(email="a@a", full_name="A")
        p2 = Participant(email="b@b", full_name="B")
        db.session.add_all([default, sess, p1, p2])
        db.session.commit()
        sp1 = SessionParticipant(session_id=sess.id, participant_id=p1.id)
        sp2 = SessionParticipant(session_id=sess.id, participant_id=p2.id)
        db.session.add_all([sp1, sp2])
        db.session.commit()
        return admin.id, sess.id


@pytest.mark.smoke
def test_apply_defaults(app):
    admin_id, sess_id = setup_session(app)
    client = app.test_client()
    login(client, admin_id)
    resp = client.post(f"/sessions/{sess_id}/materials/apply-defaults")
    assert resp.status_code == 302
    with app.app_context():
        items = MaterialOrderItem.query.filter_by(session_id=sess_id).all()
        assert len(items) == 1
        assert items[0].quantity == 2
    resp = client.post(f"/sessions/{sess_id}/materials/apply-defaults")
    assert resp.status_code == 302
    with app.app_context():
        assert MaterialOrderItem.query.filter_by(session_id=sess_id).count() == 1
