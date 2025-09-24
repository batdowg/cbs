import pytest
from datetime import date, time

from app.app import db
from app.models import (
    Client,
    ClientShippingLocation,
    ClientWorkshopLocation,
    MaterialOrderItem,
    ParticipantAccount,
    Session,
    SessionShipping,
    Settings,
    WorkshopType,
)
from app.services.materials_notifications import (
    get_materials_processor_recipients,
    notify_materials_processors,
)


def _ensure_settings(recipients: str | None = None) -> Settings:
    settings = Settings.get()
    if not settings:
        settings = Settings(id=1)
    notifications: dict[str, str] = {}
    if recipients is not None:
        notifications["materials_processors"] = recipients
    settings.mail_notifications = notifications
    db.session.merge(settings)
    db.session.commit()
    return settings


def _create_session_with_order(
    *,
    recipients: str,
    delivery_type: str = "Virtual",
) -> int:
    _ensure_settings(recipients)
    wt = WorkshopType(
        code="PSB",
        name="Problem Solving Basics",
        cert_series="fn",
        active=True,
    )
    client = Client(name="Acme Corp", data_region="NA")
    workshop_location = ClientWorkshopLocation(
        client=client,
        label="Acme HQ",
        address_line1="200 Innovation Way",
        city="Philadelphia",
        state="PA",
        postal_code="19106",
        country="USA",
    )
    shipping_location = ClientShippingLocation(
        client=client,
        title="Acme Receiving",
        contact_name="Jordan Lee",
        contact_phone="+1 555-123-4567",
        contact_email="jlee@example.com",
        address_line1="100 Market Street",
        address_line2="Suite 500",
        city="Philadelphia",
        state="PA",
        postal_code="19106",
        country="USA",
        is_active=True,
    )
    csa_account = ParticipantAccount(
        email="csa@example.com",
        full_name="Casey Analyst",
    )
    session = Session(
        title="Problem Solving Basics",
        client=client,
        workshop_type=wt,
        delivery_type=delivery_type,
        workshop_language="en",
        start_date=date(2025, 1, 10),
        end_date=date(2025, 1, 12),
        daily_start_time=time(9, 0),
        daily_end_time=time(17, 30),
        timezone="UTC",
        region="NA",
        shipping_location=shipping_location,
        workshop_location=workshop_location,
        csa_account=csa_account,
    )
    db.session.add(session)
    db.session.flush()
    shipment = SessionShipping(
        session_id=session.id,
        contact_name="Jordan Lee",
        contact_phone="+1 555-123-4567",
        contact_email="jlee@example.com",
        address_line1="100 Market Street",
        address_line2="Suite 500",
        city="Philadelphia",
        state="PA",
        postal_code="19106",
        country="USA",
        order_type="KT-Run Standard materials",
        materials_format="Physical",
        material_sets=10,
        special_instructions="Pack with care\nCall before delivery.",
    )
    db.session.add(shipment)
    item = MaterialOrderItem(
        session_id=session.id,
        catalog_ref="materials_options:42",
        title_snapshot="Participant Guide",
        language="en",
        format="Physical",
        quantity=20,
    )
    db.session.add(item)
    db.session.commit()
    return session.id


@pytest.mark.no_smoke
def test_get_materials_processor_recipients_normalizes(app):
    with app.app_context():
        settings = _ensure_settings(
            " First@example.com; second@example.com,Second@example.com , third@Example.com "
        )
        recipients = get_materials_processor_recipients()
    assert recipients == [
        "first@example.com",
        "second@example.com",
        "third@example.com",
    ]


@pytest.mark.no_smoke
def test_notify_created_sends_email_and_snapshot(monkeypatch, app):
    sent_messages: list[tuple[str, str, str, str | None]] = []

    def fake_send(to_addr, subject, body, html=None):
        sent_messages.append((to_addr, subject, body, html))
        return {"ok": True}

    monkeypatch.setattr(
        "app.services.materials_notifications.emailer.send", fake_send
    )

    with app.app_context():
        session_id = _create_session_with_order(
            recipients="proc1@example.com; proc2@example.com"
        )
        result = notify_materials_processors(session_id, reason="created")
        session = db.session.get(Session, session_id)
        fingerprint = session.materials_order_fingerprint
        notified_at = session.materials_notified_at

    assert result is True
    assert len(sent_messages) == 1
    to_addr, subject, body, html = sent_messages[0]
    assert to_addr == "proc1@example.com, proc2@example.com"
    assert subject == (
        f"[CBS] NEW Materials Order – Acme Corp – PSB – Session #{session_id}"
    )
    assert "Participant Guide" in html
    assert "Pack with care" in html
    assert "View order" in html
    assert "Materials Order – Session" in body
    assert fingerprint
    assert notified_at is not None


@pytest.mark.no_smoke
def test_notify_skip_when_no_changes(monkeypatch, app):
    sent_messages: list[tuple[str, str, str, str | None]] = []

    def fake_send(to_addr, subject, body, html=None):
        sent_messages.append((to_addr, subject, body, html))
        return {"ok": True}

    monkeypatch.setattr(
        "app.services.materials_notifications.emailer.send", fake_send
    )

    with app.app_context():
        session_id = _create_session_with_order(
            recipients="proc@example.com"
        )
        first = notify_materials_processors(session_id, reason="created")
        assert first is True
        sent_messages.clear()
        second = notify_materials_processors(session_id, reason="updated")
        session = db.session.get(Session, session_id)

    assert second is False
    assert sent_messages == []
    assert session.materials_order_fingerprint is not None


@pytest.mark.no_smoke
def test_notify_updates_on_change(monkeypatch, app):
    sent_messages: list[tuple[str, str, str, str | None]] = []

    def fake_send(to_addr, subject, body, html=None):
        sent_messages.append((to_addr, subject, body, html))
        return {"ok": True}

    monkeypatch.setattr(
        "app.services.materials_notifications.emailer.send", fake_send
    )

    with app.app_context():
        session_id = _create_session_with_order(
            recipients="proc@example.com"
        )
        notify_materials_processors(session_id, reason="created")
        original = db.session.get(Session, session_id).materials_order_fingerprint
        shipment = SessionShipping.query.filter_by(session_id=session_id).one()
        shipment.material_sets = 12
        db.session.commit()
        sent_messages.clear()
        updated = notify_materials_processors(session_id, reason="updated")
        session = db.session.get(Session, session_id)

    assert updated is True
    assert len(sent_messages) == 1
    assert session.materials_order_fingerprint != original


@pytest.mark.no_smoke
def test_notify_skips_when_no_recipients(monkeypatch, caplog, app):
    sent_messages: list[tuple[str, str, str, str | None]] = []

    def fake_send(to_addr, subject, body, html=None):
        sent_messages.append((to_addr, subject, body, html))
        return {"ok": True}

    monkeypatch.setattr(
        "app.services.materials_notifications.emailer.send", fake_send
    )

    with app.app_context():
        session_id = _create_session_with_order(recipients="")
        caplog.set_level("WARNING")
        caplog.clear()
        result = notify_materials_processors(session_id, reason="created")

    assert result is False
    assert sent_messages == []
    assert any(
        "No materials processor recipients configured" in message
        for message in caplog.messages
    )


@pytest.mark.no_smoke
def test_notify_skips_for_workshop_only(monkeypatch, app):
    sent_messages: list[tuple[str, str, str, str | None]] = []

    def fake_send(to_addr, subject, body, html=None):
        sent_messages.append((to_addr, subject, body, html))
        return {"ok": True}

    monkeypatch.setattr(
        "app.services.materials_notifications.emailer.send", fake_send
    )

    with app.app_context():
        session_id = _create_session_with_order(
            recipients="proc@example.com",
            delivery_type="Workshop Only",
        )
        result = notify_materials_processors(session_id, reason="created")
        session = db.session.get(Session, session_id)

    assert result is False
    assert sent_messages == []
    assert session.materials_notified_at is None
