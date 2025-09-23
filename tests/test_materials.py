import os
from datetime import date, datetime
import pytest

from app.app import create_app, db
from app.models import (
    User,
    WorkshopType,
    Session,
    MaterialType,
    Material,
    Client,
    ClientShippingLocation,
    SessionShipping,
    MaterialsOption,
    MaterialOrderItem,
    Participant,
    SessionParticipant,
)


@pytest.fixture
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.makedirs("/srv", exist_ok=True)
    app = create_app()
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


def _create_session_with_material_order(app):
    with app.app_context():
        admin = User(email="admin-ready@example.com", is_app_admin=True, is_admin=True)
        admin.set_password("x")
        wt = WorkshopType(code="WT", name="Workshop", cert_series="fn")
        client = Client(name="ClientA")
        option = MaterialsOption(
            title="Kit",
            order_type="KT-Run Standard materials",
            quantity_basis="Per learner",
        )
        participant = Participant(email="learner@example.com")
        session = Session(
            title="Ready Test",
            workshop_type=wt,
            client=client,
            start_date=date.today(),
            end_date=date.today(),
            delivery_type="In person",
            workshop_language="en",
            region="NA",
            capacity=10,
            number_of_class_days=1,
        )
        db.session.add_all([admin, wt, client, option, participant, session])
        db.session.flush()
        db.session.add(
            SessionParticipant(session_id=session.id, participant_id=participant.id)
        )
        item = MaterialOrderItem(
            session_id=session.id,
            catalog_ref=f"materials_options:{option.id}",
            title_snapshot=option.title,
            description_snapshot=option.description,
            quantity=1,
            language="en",
            format="Digital",
            processed=False,
        )
        db.session.add(item)
        db.session.commit()
        return admin.id, session.id


def test_materials_page_loads(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True, is_admin=True)
        admin.set_password("x")
        wt = WorkshopType(code="WT", name="WT", cert_series="fn")
        mt = MaterialType(name="Kit")
        client = Client(name="C1")
        ship = ClientShippingLocation(
            client=client,
            contact_name="CN",
            address_line1="A1",
            city="City",
            postal_code="123",
            country="US",
        )
        db.session.add_all([admin, wt, mt, client, ship])
        db.session.commit()
        mat = Material(material_type_id=mt.id, name="Sample Kit")
        sess = Session(
            title="S1",
            workshop_type=wt,
            start_date=date.today(),
            end_date=date.today(),
            client=client,
            shipping_location=ship,
        )
        db.session.add_all([mat, sess])
        db.session.commit()
        admin_id = admin.id
        session_id = sess.id
    client = app.test_client()
    with client.session_transaction() as sess_tx:
        sess_tx["user_id"] = admin_id
    resp = client.get(f"/sessions/{session_id}/materials")
    assert resp.status_code == 200
    assert f"Material Order {session_id} - S1".encode() in resp.data


def test_materials_page_without_client(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True, is_admin=True)
        admin.set_password("x")
        wt = WorkshopType(code="WT", name="WT", cert_series="fn")
        mt = MaterialType(name="Kit")
        mat = Material(material_type_id=mt.id, name="Sample Kit")
        sess = Session(
            title="S1",
            workshop_type=wt,
            start_date=date.today(),
            end_date=date.today(),
        )
        db.session.add_all([admin, wt, mt, mat, sess])
        db.session.commit()
        admin_id = admin.id
        session_id = sess.id
    client = app.test_client()
    with client.session_transaction() as sess_tx:
        sess_tx["user_id"] = admin_id
    resp = client.get(f"/sessions/{session_id}/materials")
    assert resp.status_code == 200
    assert f"Material Order {session_id} - S1".encode() in resp.data


def test_material_order_delivery_actions(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True, is_admin=True)
        admin.set_password("x")
        wt = WorkshopType(code="WT", name="WT", cert_series="fn")
        sess = Session(title="S1", workshop_type=wt)
        db.session.add_all([admin, wt, sess])
        db.session.commit()
        shipment = SessionShipping(session_id=sess.id)
        db.session.add(shipment)
        db.session.commit()
        admin_id = admin.id
        session_id = sess.id
    client = app.test_client()
    with client.session_transaction() as sess_tx:
        sess_tx["user_id"] = admin_id
        sess_tx["_csrf_token"] = "t1"
    resp = client.post(
        f"/sessions/{session_id}/materials/deliver", data={"csrf_token": "t1"}
    )
    assert resp.status_code == 302
    with app.app_context():
        ship = SessionShipping.query.filter_by(session_id=session_id).first()
        assert ship.status == "Delivered"
        assert ship.delivered_at is not None
    with client.session_transaction() as sess_tx:
        sess_tx["_csrf_token"] = "t2"
    resp = client.post(
        f"/sessions/{session_id}/materials/deliver", data={"csrf_token": "t2"}
    )
    assert resp.status_code == 403
    with client.session_transaction() as sess_tx:
        sess_tx["_csrf_token"] = "t3"
    resp = client.post(
        f"/sessions/{session_id}/materials/undeliver", data={"csrf_token": "t3"}
    )
    assert resp.status_code == 302
    with app.app_context():
        ship = SessionShipping.query.filter_by(session_id=session_id).first()
        assert ship.status == "In progress"
        assert ship.delivered_at is None


@pytest.mark.smoke
def test_materials_order_status_transitions(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True, is_admin=True)
        admin.set_password("x")
        wt = WorkshopType(code="WT", name="WT", cert_series="fn")
        client = Client(name="C1")
        db.session.add_all([admin, wt, client])
        db.session.commit()
        option = MaterialsOption(
            order_type="KT-Run Standard materials",
            title="Standard Kit",
            formats=["Digital"],
            quantity_basis="Per order",
        )
        sess = Session(
            title="S1",
            workshop_type=wt,
            start_date=date.today(),
            end_date=date.today(),
            client=client,
        )
        db.session.add_all([option, sess])
        db.session.commit()
        admin_id = admin.id
        session_id = sess.id
        option_id = option.id
    client_tc = app.test_client()
    with client_tc.session_transaction() as sess_tx:
        sess_tx["user_id"] = admin_id
    resp = client_tc.get(f"/sessions/{session_id}/materials")
    assert resp.status_code == 200
    with app.app_context():
        shipment = SessionShipping.query.filter_by(session_id=session_id).first()
        assert shipment.status == "New"
    form_data = {
        "action": "update_header",
        "order_type": "KT-Run Standard materials",
        "materials_format": "",
        "material_sets": "5",
        "credits": "2",
        "items[new0][option_id]": str(option_id),
        "items[new0][language]": "en",
        "items[new0][format]": "Digital",
        "items[new0][quantity]": "3",
    }
    resp = client_tc.post(
        f"/sessions/{session_id}/materials", data=form_data, follow_redirects=False
    )
    assert resp.status_code == 302
    with app.app_context():
        shipment = SessionShipping.query.filter_by(session_id=session_id).first()
        assert shipment.status == "In progress"
        item = MaterialOrderItem.query.filter_by(session_id=session_id).first()
        assert item and not item.processed
        item_id = item.id

        item_id = item.id
    update_data = {
        "action": "update_header",
        "order_type": "KT-Run Standard materials",
        "materials_format": "",
        "material_sets": "5",
        "credits": "2",
        f"items[{item_id}][id]": str(item_id),
        f"items[{item_id}][option_id]": str(option_id),
        f"items[{item_id}][language]": "en",
        f"items[{item_id}][format]": "Digital",
        f"items[{item_id}][quantity]": "3",
        f"items[{item_id}][processed]": "1",
    }
    resp = client_tc.post(
        f"/sessions/{session_id}/materials", data=update_data, follow_redirects=False
    )
    assert resp.status_code == 302
    with app.app_context():
        shipment = SessionShipping.query.filter_by(session_id=session_id).first()
        assert shipment.status == "Processed"
        item = MaterialOrderItem.query.filter_by(session_id=session_id).first()
        assert item and item.processed
    unprocess_data = update_data.copy()
    unprocess_data.pop(f"items[{item_id}][processed]")
    resp = client_tc.post(
        f"/sessions/{session_id}/materials",
        data=unprocess_data,
        follow_redirects=False,
    )
    assert resp.status_code == 302
    with app.app_context():
        shipment = SessionShipping.query.filter_by(session_id=session_id).first()
        assert shipment.status == "In progress"
        item = MaterialOrderItem.query.filter_by(session_id=session_id).first()
        assert item and not item.processed

    finalize_data = {
        "action": "finalize",
        "order_type": "KT-Run Standard materials",
        "materials_format": "",
        "material_sets": "5",
        "credits": "2",
        f"items[{item_id}][id]": str(item_id),
        f"items[{item_id}][option_id]": str(option_id),
        f"items[{item_id}][language]": "en",
        f"items[{item_id}][format]": "Digital",
        f"items[{item_id}][quantity]": "3",
    }
    resp = client_tc.post(
        f"/sessions/{session_id}/materials", data=finalize_data, follow_redirects=True
    )
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "There are still material order items outstanding" in html
    with app.app_context():
        shipment = SessionShipping.query.filter_by(session_id=session_id).first()
        sess_obj = db.session.get(Session, session_id)
        assert shipment.status != "Finalized"
        assert sess_obj.ready_for_delivery is False
        assert sess_obj.materials_ordered is False

    # Mark item processed and finalize successfully
    resp = client_tc.post(
        f"/sessions/{session_id}/materials", data=update_data, follow_redirects=False
    )
    assert resp.status_code == 302
    resp = client_tc.post(
        f"/sessions/{session_id}/materials", data=finalize_data, follow_redirects=False
    )
    assert resp.status_code == 302
    with app.app_context():
        shipment = SessionShipping.query.filter_by(session_id=session_id).first()
        sess_obj = db.session.get(Session, session_id)
        assert shipment.status == "Finalized"
        assert sess_obj.ready_for_delivery is True
        assert sess_obj.materials_ordered is True
        assert sess_obj.status == "New"

    post_finalize_update = {
        "action": "update_header",
        "order_type": "KT-Run Standard materials",
        "materials_format": "",
        "material_sets": "5",
        "credits": "2",
        f"items[{item_id}][id]": str(item_id),
        f"items[{item_id}][option_id]": str(option_id),
        f"items[{item_id}][language]": "en",
        f"items[{item_id}][format]": "Digital",
        f"items[{item_id}][quantity]": "4",
    }
    resp = client_tc.post(
        f"/sessions/{session_id}/materials",
        data=post_finalize_update,
        follow_redirects=False,
    )
    assert resp.status_code == 302
    with app.app_context():
        shipment = SessionShipping.query.filter_by(session_id=session_id).first()
        item = MaterialOrderItem.query.filter_by(session_id=session_id).first()
        assert shipment.status == "Finalized"
        assert item.quantity == 4


@pytest.mark.smoke
def test_materials_order_finalize_sets_session_flags(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True, is_admin=True)
        admin.set_password("x")
        wt = WorkshopType(code="WT", name="WT", cert_series="fn")
        client = Client(name="C1")
        db.session.add_all([admin, wt, client])
        db.session.commit()
        sess = Session(
            title="Bulk Session",
            workshop_type=wt,
            start_date=date.today(),
            end_date=date.today(),
            client=client,
            materials_only=True,
        )
        db.session.add(sess)
        db.session.commit()
        admin_id = admin.id
        session_id = sess.id
    client_tc = app.test_client()
    with client_tc.session_transaction() as sess_tx:
        sess_tx["user_id"] = admin_id
    resp = client_tc.get(f"/sessions/{session_id}/materials")
    assert resp.status_code == 200
    with app.app_context():
        shipment = SessionShipping.query.filter_by(session_id=session_id).first()
        assert shipment.status == "New"
        assert shipment.order_type == "Client-run Bulk order"
        assert db.session.get(Session, session_id).ready_for_delivery is False
    finalize_data = {
        "action": "finalize",
        "order_type": "Client-Run Bulk order",
        "materials_format": "",
        "material_sets": "0",
        "credits": "2",
    }
    resp = client_tc.post(
        f"/sessions/{session_id}/materials", data=finalize_data, follow_redirects=False
    )
    assert resp.status_code == 302
    with app.app_context():
        shipment = SessionShipping.query.filter_by(session_id=session_id).first()
        sess_obj = db.session.get(Session, session_id)
        assert shipment.status == "Finalized"
        assert shipment.order_type == "Client-Run Bulk order"
        assert sess_obj.ready_for_delivery is True
        assert sess_obj.materials_ordered is True
        assert sess_obj.status == "Closed"
        assert sess_obj.computed_status == "Closed"
    change_data = {
        "action": "update_header",
        "order_type": "Client-Run Bulk order",
        "materials_format": "",
        "material_sets": "3",
        "credits": "2",
    }
    resp = client_tc.post(
        f"/sessions/{session_id}/materials", data=change_data, follow_redirects=False
    )
    assert resp.status_code == 403
    with app.app_context():
        shipment = SessionShipping.query.filter_by(session_id=session_id).first()
        sess_obj = db.session.get(Session, session_id)
        assert shipment.status == "Finalized"
        assert sess_obj.ready_for_delivery is True
        assert sess_obj.status == "Closed"
        assert sess_obj.computed_status == "Closed"


def test_session_ready_requires_processed_materials(app):
    admin_id, session_id = _create_session_with_material_order(app)
    client_tc = app.test_client()
    with client_tc.session_transaction() as sess_tx:
        sess_tx["user_id"] = admin_id

    resp = client_tc.post(
        f"/sessions/{session_id}/mark-ready", follow_redirects=True
    )
    assert resp.status_code == 200
    assert "There are still material order items outstanding" in resp.get_data(as_text=True)
    with app.app_context():
        sess_obj = db.session.get(Session, session_id)
        assert sess_obj.ready_for_delivery is False
        assert sess_obj.materials_ordered is False

    with app.app_context():
        item = MaterialOrderItem.query.filter_by(session_id=session_id).first()
        item.processed = True
        item.processed_at = datetime.utcnow()
        item.processed_by_id = admin_id
        db.session.commit()

    resp = client_tc.post(
        f"/sessions/{session_id}/mark-ready", follow_redirects=False
    )
    assert resp.status_code == 302
    with app.app_context():
        sess_obj = db.session.get(Session, session_id)
        assert sess_obj.ready_for_delivery is True
        assert sess_obj.materials_ordered is True


def test_edit_session_materials_ordered_blocks_unprocessed_items(app):
    admin_id, session_id = _create_session_with_material_order(app)
    client_tc = app.test_client()
    with client_tc.session_transaction() as sess_tx:
        sess_tx["user_id"] = admin_id
    with app.app_context():
        sess_obj = db.session.get(Session, session_id)
        client_id = sess_obj.client_id
        wt_id = sess_obj.workshop_type_id

    form_data = {
        "title": "Ready Test",
        "client_id": str(client_id),
        "region": "NA",
        "workshop_language": "en",
        "start_date": date.today().isoformat(),
        "end_date": date.today().isoformat(),
        "capacity": "10",
        "delivery_type": "In person",
        "workshop_type_id": str(wt_id),
        "materials_ordered": "1",
        "daily_start_time": "08:00",
        "daily_end_time": "17:00",
        "number_of_class_days": "1",
    }
    resp = client_tc.post(
        f"/sessions/{session_id}/edit", data=form_data, follow_redirects=False
    )
    assert resp.status_code == 400
    assert "There are still material order items outstanding" in resp.get_data(
        as_text=True
    )
    with app.app_context():
        sess_obj = db.session.get(Session, session_id)
        assert sess_obj.materials_ordered is False

    with app.app_context():
        item = MaterialOrderItem.query.filter_by(session_id=session_id).first()
        item.processed = True
        item.processed_at = datetime.utcnow()
        item.processed_by_id = admin_id
        db.session.commit()

    resp = client_tc.post(
        f"/sessions/{session_id}/edit", data=form_data, follow_redirects=False
    )
    assert resp.status_code == 302
    with app.app_context():
        sess_obj = db.session.get(Session, session_id)
        assert sess_obj.materials_ordered is True
