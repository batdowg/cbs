from datetime import datetime, timezone

from app.app import db
from app.models import Client, MaterialOrderItem, Session, SessionShipping, User, WorkshopType
from app.routes.materials import MATERIALS_OUTSTANDING_MESSAGE


def _finalize(client, session_id, items):
    data = {"action": "finalize"}
    for index, item in enumerate(items):
        prefix = f"items[{index}]"
        data[f"{prefix}[id]"] = str(item["id"])
        data[f"{prefix}[quantity]"] = str(item["quantity"])
        data[f"{prefix}[language]"] = item.get("language", "en")
        data[f"{prefix}[format]"] = item.get("format", "Digital")
        if item.get("processed"):
            data[f"{prefix}[processed]"] = "1"
    return client.post(
        f"/sessions/{session_id}/materials",
        data=data,
        follow_redirects=True,
    )


def test_materials_finalize_blocks_and_sets_flags(app, client):
    with app.app_context():
        admin = User(email="admin@example.com", is_admin=True)
        admin.set_password("pw")
        workshop_type = WorkshopType(code="WT", name="Workshop", cert_series="fn")
        client_record = Client(name="Client")
        session = Session(
            title="Lifecycle",
            start_date=datetime.utcnow().date(),
            end_date=datetime.utcnow().date(),
            workshop_language="en",
            region="NA",
            number_of_class_days=1,
            workshop_type=workshop_type,
            client=client_record,
        )
        db.session.add_all([admin, workshop_type, client_record, session])
        db.session.flush()
        shipment = SessionShipping(
            session_id=session.id,
            order_type="KT-Run Standard materials",
            material_sets=1,
        )
        db.session.add(shipment)
        first_item = MaterialOrderItem(
            session_id=session.id,
            catalog_ref="manual:1",
            title_snapshot="Kit",
            quantity=1,
            language="en",
            format="Digital",
            processed=True,
            processed_at=datetime.now(timezone.utc),
        )
        second_item = MaterialOrderItem(
            session_id=session.id,
            catalog_ref="manual:2",
            title_snapshot="Guide",
            quantity=1,
            language="en",
            format="Digital",
            processed=False,
        )
        db.session.add_all([first_item, second_item])
        db.session.commit()
        admin_id = admin.id
        session_id = session.id
        first_id = first_item.id
        second_id = second_item.id

    with client.session_transaction() as sess:
        sess["user_id"] = admin_id

    # First attempt should block because one item is unprocessed
    resp = _finalize(
        client,
        session_id,
        [
            {"id": first_id, "quantity": 1, "language": "en", "format": "Digital", "processed": True},
            {"id": second_id, "quantity": 1, "language": "en", "format": "Digital"},
        ],
    )
    assert MATERIALS_OUTSTANDING_MESSAGE in resp.get_data(as_text=True)
    with app.app_context():
        fresh = db.session.get(Session, session_id)
        assert not fresh.ready_for_delivery
        assert not fresh.materials_ordered

    # Mark every item processed and finalize again
    resp = _finalize(
        client,
        session_id,
        [
            {"id": first_id, "quantity": 1, "language": "en", "format": "Digital", "processed": True},
            {"id": second_id, "quantity": 1, "language": "en", "format": "Digital", "processed": True},
        ],
    )
    body = resp.get_data(as_text=True)
    assert "Materials order finalized" in body
    with app.app_context():
        fresh = db.session.get(Session, session_id)
        shipment = SessionShipping.query.filter_by(session_id=session_id).first()
        assert fresh.materials_ordered
        assert fresh.materials_ordered_at is not None
        assert fresh.ready_for_delivery
        assert fresh.ready_at is not None
        assert shipment.status == "Finalized"
