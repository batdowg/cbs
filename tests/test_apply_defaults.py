import os
from datetime import date

import pytest

from app.app import create_app, db
from app.models import (
    User,
    WorkshopType,
    Session,
    SessionShipping,
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
        opt = MaterialsOption(
            order_type="KT-Run Standard materials", title="ItemA", formats=["Digital"]
        )
        opt2 = MaterialsOption(
            order_type="KT-Run Standard materials", title="ItemB", formats=["Digital"]
        )
        db.session.add_all([admin, wt, opt, opt2])
        db.session.commit()
        default = WorkshopTypeMaterialDefault(
            workshop_type_id=wt.id,
            delivery_type="Onsite",
            region_code="NA",
            language="en",
            catalog_ref=f"materials_options:{opt.id}",
            default_format="Digital",
            quantity_basis="Per learner",
            active=True,
        )
        default2 = WorkshopTypeMaterialDefault(
            workshop_type_id=wt.id,
            delivery_type="Onsite",
            region_code="NA",
            language="en",
            catalog_ref=f"materials_options:{opt2.id}",
            default_format="Digital",
            quantity_basis="Per order",
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
        db.session.add_all([default, default2, sess, p1, p2])
        db.session.commit()
        shipment = SessionShipping(
            session_id=sess.id, material_sets=5, order_type="KT-Run Standard materials"
        )
        db.session.add(shipment)
        db.session.commit()
        sp1 = SessionParticipant(session_id=sess.id, participant_id=p1.id)
        sp2 = SessionParticipant(session_id=sess.id, participant_id=p2.id)
        db.session.add_all([sp1, sp2])
        db.session.commit()
        return admin.id, sess.id, opt2.id


@pytest.mark.smoke
def test_material_item_flow(app):
    admin_id, sess_id, opt2_id = setup_session(app)
    client = app.test_client()
    login(client, admin_id)

    resp = client.post(f"/sessions/{sess_id}/materials/apply-defaults")
    assert resp.status_code == 302
    with app.app_context():
        items = (
            MaterialOrderItem.query.filter_by(session_id=sess_id)
            .order_by(MaterialOrderItem.id)
            .all()
        )
        assert len(items) == 2
        per_learner = items[0]
        per_order = items[1]
        assert per_learner.quantity == 5
        assert per_order.quantity == 1
        item_id = per_learner.id

    resp = client.post(
        f"/sessions/{sess_id}/materials/items/{item_id}/qty",
        json={"quantity": 8},
    )
    assert resp.status_code == 200
    with app.app_context():
        assert db.session.get(MaterialOrderItem, item_id).quantity == 8

    with app.app_context():
        shipment = SessionShipping.query.filter_by(session_id=sess_id).first()
        shipment.material_sets = 7
        db.session.commit()
    resp = client.post(f"/sessions/{sess_id}/materials/apply-defaults")
    assert resp.status_code == 302
    with app.app_context():
        per_learner = db.session.get(MaterialOrderItem, item_id)
        per_order = MaterialOrderItem.query.filter_by(
            session_id=sess_id, catalog_ref=f"materials_options:{opt2_id}"
        ).first()
        assert per_learner.quantity == 7
        assert per_order.quantity == 1
