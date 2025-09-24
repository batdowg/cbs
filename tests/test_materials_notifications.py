from __future__ import annotations

from datetime import date, time

import pytest

from app.app import db
from app.models import (
    Client,
    ClientShippingLocation,
    ClientWorkshopLocation,
    MaterialOrderItem,
    ParticipantAccount,
    ProcessorAssignment,
    Session,
    SessionShipping,
    User,
    WorkshopType,
)
from app.services.materials_notifications import (
    materials_bucket_for,
    notify_materials_processors,
    resolve_processor_emails,
)


def _create_admin(email: str, name: str | None = None) -> User:
    user = User(
        email=email,
        full_name=name,
        is_admin=True,
    )
    db.session.add(user)
    db.session.flush()
    return user


def _assign_processor(region: str, processing_type: str, user: User) -> None:
    db.session.add(
        ProcessorAssignment(
            region=region,
            processing_type=processing_type,
            user_id=user.id,
        )
    )


def _reset_processors() -> None:
    ProcessorAssignment.query.delete()
    User.query.delete()
    db.session.commit()


def _create_session_with_order(
    *,
    region: str = "NA",
    materials_format: str = "ALL_PHYSICAL",
    delivery_type: str = "Virtual",
    order_type: str = "KT-Run Standard materials",
) -> int:
    wt = WorkshopType.query.filter_by(code="PSB").first()
    if not wt:
        wt = WorkshopType(
            code="PSB",
            name="Problem Solving Basics",
            cert_series="fn",
            active=True,
        )
        db.session.add(wt)
        db.session.flush()
    client = Client.query.filter_by(name="Acme Corp").first()
    if not client:
        client = Client(name="Acme Corp", data_region="NA")
        db.session.add(client)
        db.session.flush()
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
    csa_account = ParticipantAccount.query.filter_by(email="csa@example.com").first()
    if not csa_account:
        csa_account = ParticipantAccount(
            email="csa@example.com",
            full_name="Casey Analyst",
        )
        db.session.add(csa_account)
        db.session.flush()
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
        region=region,
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
        order_type=order_type,
        materials_format=materials_format,
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
def test_materials_bucket_for_simulation_by_order_type():
    session = Session()
    shipment = SessionShipping(order_type="Simulation", materials_format="ALL_DIGITAL")
    assert materials_bucket_for(shipment, session) == "Simulation"


@pytest.mark.no_smoke
def test_materials_bucket_for_simulation_by_workshop_type():
    wt = WorkshopType(code="SIM", name="Simulation", cert_series="fn", active=True, simulation_based=True)
    session = Session(workshop_type=wt)
    shipment = SessionShipping(order_type="KT-Run Standard materials", materials_format="ALL_PHYSICAL")
    assert materials_bucket_for(shipment, session) == "Simulation"


@pytest.mark.no_smoke
@pytest.mark.parametrize(
    "materials_format,expected",
    [
        ("ALL_DIGITAL", "Digital"),
        ("ALL_PHYSICAL", "Physical"),
        ("MIXED", "Physical"),
    ],
)
def test_materials_bucket_for_format_mapping(materials_format, expected):
    session = Session()
    shipment = SessionShipping(order_type="KT-Run Standard materials", materials_format=materials_format)
    assert materials_bucket_for(shipment, session) == expected


@pytest.mark.no_smoke
def test_materials_bucket_for_other_path():
    session = Session()
    shipment = SessionShipping(order_type="KT-Run Standard materials", materials_format=None)
    assert materials_bucket_for(shipment, session) == "Other"


@pytest.mark.no_smoke
def test_resolve_processor_emails_exact_match(app):
    with app.app_context():
        _reset_processors()
        user1 = _create_admin("eu.one@example.com", "Processor One")
        user2 = _create_admin("eu.two@example.com", "Processor Two")
        _assign_processor("EU", "Physical", user1)
        _assign_processor("EU", "Physical", user2)
        db.session.commit()

        recipients = resolve_processor_emails("EU", "Physical")

    assert recipients == ["eu.one@example.com", "eu.two@example.com"]


@pytest.mark.no_smoke
def test_resolve_processor_emails_fallback_region_other(app):
    with app.app_context():
        _reset_processors()
        user = _create_admin("region.other@example.com", "Region Other")
        _assign_processor("SEA", "Other", user)
        db.session.commit()

        recipients = resolve_processor_emails("SEA", "Simulation")

    assert recipients == ["region.other@example.com"]


@pytest.mark.no_smoke
def test_resolve_processor_emails_fallback_other_bucket(app):
    with app.app_context():
        _reset_processors()
        user = _create_admin("other.bucket@example.com", "Other Bucket")
        _assign_processor("Other", "Digital", user)
        db.session.commit()

        recipients = resolve_processor_emails("NA", "Digital")

    assert recipients == ["other.bucket@example.com"]


@pytest.mark.no_smoke
def test_resolve_processor_emails_fallback_other_other(app):
    with app.app_context():
        _reset_processors()
        user = _create_admin("catchall@example.com", "Catch All")
        _assign_processor("Other", "Other", user)
        db.session.commit()

        recipients = resolve_processor_emails("NA", "Simulation")

    assert recipients == ["catchall@example.com"]


@pytest.mark.no_smoke
def test_resolve_processor_emails_deduplicates(app):
    with app.app_context():
        _reset_processors()
        user_a = _create_admin("dup@example.com ", "Dup A")
        user_b = _create_admin("dup@example.com", "Dup B")
        _assign_processor("EU", "Digital", user_a)
        _assign_processor("EU", "Digital", user_b)
        db.session.commit()

        recipients = resolve_processor_emails("EU", "Digital")

    assert recipients == ["dup@example.com"]


@pytest.mark.no_smoke
def test_notify_created_sends_email_and_snapshot(monkeypatch, app):
    sent_messages: list[tuple[list[str], str, str, str | None]] = []

    def fake_send(to_addr, subject, body, html=None):
        sent_messages.append((to_addr, subject, body, html))
        return {"ok": True}

    monkeypatch.setattr(
        "app.services.materials_notifications.emailer.send", fake_send
    )

    with app.app_context():
        _reset_processors()
        session_id = _create_session_with_order(region="NA", materials_format="ALL_PHYSICAL")
        proc1 = _create_admin("proc1@example.com", "Proc One")
        proc2 = _create_admin("proc2@example.com", "Proc Two")
        _assign_processor("NA", "Physical", proc1)
        _assign_processor("NA", "Physical", proc2)
        db.session.commit()

        result = notify_materials_processors(session_id, reason="created")
        session = db.session.get(Session, session_id)
        fingerprint = session.materials_order_fingerprint
        notified_at = session.materials_notified_at

    assert result is True
    assert len(sent_messages) == 1
    to_addr, subject, body, html = sent_messages[0]
    assert to_addr == ["proc1@example.com", "proc2@example.com"]
    assert subject == (
        f"[CBS] NEW Materials Order – Acme Corp – PSB – Session #{session_id}"
    )
    assert "Participant Guide" in (html or "")
    assert "Pack with care" in (html or "")
    assert "View order" in (html or "")
    assert "Materials Order – Session" in body
    assert "Region" in (html or "")
    assert fingerprint
    assert notified_at is not None


@pytest.mark.no_smoke
def test_notify_skip_when_no_changes(monkeypatch, app):
    sent_messages: list[tuple[list[str], str, str, str | None]] = []

    def fake_send(to_addr, subject, body, html=None):
        sent_messages.append((to_addr, subject, body, html))
        return {"ok": True}

    monkeypatch.setattr(
        "app.services.materials_notifications.emailer.send", fake_send
    )

    with app.app_context():
        _reset_processors()
        session_id = _create_session_with_order(region="NA", materials_format="ALL_PHYSICAL")
        proc = _create_admin("proc@example.com", "Proc")
        _assign_processor("NA", "Physical", proc)
        db.session.commit()

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
    sent_messages: list[tuple[list[str], str, str, str | None]] = []

    def fake_send(to_addr, subject, body, html=None):
        sent_messages.append((to_addr, subject, body, html))
        return {"ok": True}

    monkeypatch.setattr(
        "app.services.materials_notifications.emailer.send", fake_send
    )

    with app.app_context():
        _reset_processors()
        session_id = _create_session_with_order(region="NA", materials_format="ALL_PHYSICAL")
        proc = _create_admin("proc@example.com", "Proc")
        _assign_processor("NA", "Physical", proc)
        db.session.commit()

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
def test_materials_order_recipients_follow_region_and_bucket(monkeypatch, app):
    sent_messages: list[tuple[list[str], str, str, str | None]] = []

    def fake_send(to_addr, subject, body, html=None):
        sent_messages.append((to_addr, subject, body, html))
        return {"ok": True}

    monkeypatch.setattr(
        "app.services.materials_notifications.emailer.send", fake_send
    )

    with app.app_context():
        _reset_processors()
        session_id = _create_session_with_order(region="EU", materials_format="ALL_PHYSICAL")
        physical_proc = _create_admin("eu.physical@example.com", "EU Physical")
        digital_proc = _create_admin("eu.digital@example.com", "EU Digital")
        _assign_processor("EU", "Physical", physical_proc)
        _assign_processor("EU", "Digital", digital_proc)
        db.session.commit()

        first = notify_materials_processors(session_id, reason="created")
        assert first is True
        assert len(sent_messages) == 1
        first_to, first_subject, *_ = sent_messages[0]
        assert first_subject.startswith("[CBS] NEW Materials Order")
        assert first_to == ["eu.physical@example.com"]
        shipment = SessionShipping.query.filter_by(session_id=session_id).one()
        shipment.materials_format = "ALL_DIGITAL"
        db.session.commit()
        sent_messages.clear()
        second = notify_materials_processors(session_id, reason="updated")

    assert second is True
    assert len(sent_messages) == 1
    to_addr, subject, body, html = sent_messages[0]
    assert subject.startswith("[CBS] UPDATED Materials Order")
    assert to_addr == ["eu.digital@example.com"]
    assert "Processing type" in (html or "")


@pytest.mark.no_smoke
def test_notify_skips_when_no_processors_configured(monkeypatch, caplog, app):
    sent_messages: list[tuple[list[str], str, str, str | None]] = []

    def fake_send(to_addr, subject, body, html=None):
        sent_messages.append((to_addr, subject, body, html))
        return {"ok": True}

    monkeypatch.setattr(
        "app.services.materials_notifications.emailer.send", fake_send
    )

    with app.app_context():
        _reset_processors()
        session_id = _create_session_with_order(region="NA", materials_format="ALL_PHYSICAL")
        caplog.set_level("WARNING")
        caplog.clear()
        result = notify_materials_processors(session_id, reason="created")

    assert result is False
    assert sent_messages == []
    assert any(
        "[MAIL-NO-RECIPIENTS]" in message and "bucket=Physical" in message
        for message in caplog.messages
    )


@pytest.mark.no_smoke
def test_notify_skips_for_workshop_only(monkeypatch, app):
    sent_messages: list[tuple[list[str], str, str, str | None]] = []

    def fake_send(to_addr, subject, body, html=None):
        sent_messages.append((to_addr, subject, body, html))
        return {"ok": True}

    monkeypatch.setattr(
        "app.services.materials_notifications.emailer.send", fake_send
    )

    with app.app_context():
        _reset_processors()
        session_id = _create_session_with_order(
            region="NA", materials_format="ALL_PHYSICAL", delivery_type="Workshop Only"
        )
        proc = _create_admin("proc@example.com", "Proc")
        _assign_processor("NA", "Physical", proc)
        db.session.commit()

        result = notify_materials_processors(session_id, reason="created")
        session = db.session.get(Session, session_id)

    assert result is False
    assert sent_messages == []
    assert session.materials_notified_at is None

@pytest.mark.no_smoke
def test_notify_uses_envelope_list_for_multiple_recipients(monkeypatch, app):
    from app import emailer
    from app.models import Settings

    sendmail_calls: list[tuple[str, list[str], str]] = []

    class DummySMTP:
        def __init__(self, host, port):
            self.host = host
            self.port = port

        def starttls(self):
            return None

        def login(self, user, password):
            return None

        def sendmail(self, from_addr, to_addrs, message):
            sendmail_calls.append((from_addr, to_addrs, message))

        def quit(self):
            return None

    monkeypatch.setattr(Settings, "get", staticmethod(lambda: None))
    monkeypatch.setenv("SMTP_HOST", "smtp.office365.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_FROM_DEFAULT", "noreply@example.com")
    monkeypatch.setenv("SMTP_FROM_NAME", "CBS")
    monkeypatch.setenv("SMTP_USER", "smtp-user")
    monkeypatch.setenv("SMTP_PASS", "smtp-pass")
    monkeypatch.setattr(emailer.smtplib, "SMTP", lambda host, port: DummySMTP(host, port))
    monkeypatch.setattr(emailer.smtplib, "SMTP_SSL", lambda host, port: DummySMTP(host, port))

    with app.app_context():
        _reset_processors()
        session_id = _create_session_with_order(region="NA", materials_format="ALL_PHYSICAL")
        proc1 = _create_admin("Proc1@Example.com", "Proc One")
        proc2 = _create_admin("proc2@example.com", "Proc Two")
        _assign_processor("NA", "Physical", proc1)
        _assign_processor("NA", "Physical", proc2)
        db.session.commit()

        result = notify_materials_processors(session_id, reason="created")

    assert result is True
    assert len(sendmail_calls) == 1
    from_addr, to_addrs, message = sendmail_calls[0]
    assert from_addr == "noreply@example.com"
    assert to_addrs == ["proc1@example.com", "proc2@example.com"]
    assert "To: proc1@example.com, proc2@example.com" in message


