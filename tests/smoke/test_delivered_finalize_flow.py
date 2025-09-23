from datetime import date, datetime, timezone

from app.app import db
from app.models import (
    Client,
    MaterialOrderItem,
    Participant,
    Session,
    SessionParticipant,
    SessionShipping,
    User,
    WorkshopType,
)
from app.routes.sessions import MATERIALS_OUTSTANDING_MESSAGE


def test_delivered_and_finalize_guards(app, client):
    with app.app_context():
        admin = User(email="admin@example.com", is_admin=True)
        admin.set_password("pw")
        facilitator = User(email="facilitator@example.com", is_kt_delivery=True)
        facilitator.set_password("pw")
        workshop_type = WorkshopType(code="WT", name="Workshop", cert_series="fn")
        client_record = Client(name="Client")
        session = Session(
            title="Workshop",
            start_date=date.today(),
            end_date=date.today(),
            workshop_language="en",
            region="NA",
            number_of_class_days=1,
            workshop_type=workshop_type,
            client=client_record,
            lead_facilitator=facilitator,
        )
        materials_only_session = Session(
            title="Materials",
            start_date=date.today(),
            end_date=date.today(),
            workshop_language="en",
            region="NA",
            number_of_class_days=1,
            workshop_type=workshop_type,
            client=client_record,
            lead_facilitator=facilitator,
            delivery_type="Material only",
            materials_only=True,
        )
        participant = Participant(email="learner@example.com", full_name="Learner")
        db.session.add_all(
            [
                admin,
                facilitator,
                workshop_type,
                client_record,
                session,
                materials_only_session,
                participant,
            ]
        )
        db.session.flush()
        db.session.add_all(
            [
                SessionParticipant(session_id=session.id, participant_id=participant.id),
                SessionShipping(
                    session_id=session.id,
                    order_type="KT-Run Standard materials",
                    material_sets=1,
                ),
                MaterialOrderItem(
                    session_id=session.id,
                    catalog_ref="manual:1",
                    title_snapshot="Kit",
                    quantity=1,
                    language="en",
                    format="Digital",
                    processed=False,
                ),
            ]
        )
        db.session.commit()
        admin_id = admin.id
        facilitator_id = facilitator.id
        session_id = session.id
        materials_id = materials_only_session.id

    with client.session_transaction() as sess:
        sess["user_id"] = admin_id

    # Ready fails until all materials processed
    ready_resp = client.post(f"/sessions/{session_id}/mark-ready", follow_redirects=True)
    assert MATERIALS_OUTSTANDING_MESSAGE in ready_resp.get_data(as_text=True)

    with app.app_context():
        for item in MaterialOrderItem.query.filter_by(session_id=session_id).all():
            item.processed = True
            item.processed_at = datetime.now(timezone.utc)
        db.session.commit()

    ready_resp = client.post(f"/sessions/{session_id}/mark-ready", follow_redirects=True)
    body = ready_resp.get_data(as_text=True)
    assert "Ready for delivery" in body or "Provisioned" in body

    # Finalize action hidden until delivered
    detail_before = client.get(f"/sessions/{session_id}")
    assert "Finalize session" not in detail_before.get_data(as_text=True)

    # Facilitator sees Delivered button on workshop view before marking delivered
    client.get("/logout")
    with client.session_transaction() as sess:
        sess["user_id"] = facilitator_id
    pre_view = client.get(f"/workshops/{session_id}")
    assert f"/sessions/{session_id}/mark-delivered" in pre_view.get_data(as_text=True)

    # Materials-only workshop view redirects back to session detail
    redirect = client.get(f"/workshops/{materials_id}", follow_redirects=True)
    text = redirect.get_data(as_text=True)
    assert "Material only sessions use the session detail view." in text

    # Mark delivered and confirm finalize button appears on session detail
    client.get("/logout")
    with client.session_transaction() as sess:
        sess["user_id"] = admin_id
    delivered = client.post(f"/sessions/{session_id}/mark-delivered", follow_redirects=True)
    assert "Session marked delivered" in delivered.get_data(as_text=True)
    detail_after = client.get(f"/sessions/{session_id}")
    assert "Finalize session" in detail_after.get_data(as_text=True)

    with app.app_context():
        fresh = db.session.get(Session, session_id)
        assert fresh.delivered
        assert fresh.delivered_at is not None
