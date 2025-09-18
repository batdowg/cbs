import os
from datetime import date

import pytest

from app.app import create_app, db
from app.models import (
    Client,
    MaterialOrderItem,
    Session,
    SessionShipping,
    User,
    WorkshopType,
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


@pytest.fixture
def dashboard_setup(app):
    with app.app_context():
        wt = WorkshopType(code="WT", name="Workshop", cert_series="fn")
        client = Client(name="Client A")
        admin = User(email="admin@example.com", is_app_admin=True, is_admin=True, region="NA")
        admin.set_password("x")
        crm = User(email="crm@example.com", is_kcrm=True, region="NA")
        crm.set_password("x")
        facilitator = User(email="fac@example.com", is_kt_delivery=True, region="NA")
        facilitator.set_password("x")
        contractor = User(email="contractor@example.com", is_kt_contractor=True, region="NA")
        contractor.set_password("x")

        material_only = Session(
            title="Material Only Engagement",
            workshop_type=wt,
            client=client,
            start_date=date.today(),
            end_date=date.today(),
            region="NA",
            materials_only=True,
            delivery_type="Material only",
        )
        with_materials_flag = Session(
            title="Workshop With Materials",
            workshop_type=wt,
            client=client,
            start_date=date.today(),
            end_date=date.today(),
            region="NA",
            materials_ordered=True,
        )
        with_order_item = Session(
            title="Workshop With Order Item",
            workshop_type=wt,
            client=client,
            start_date=date.today(),
            end_date=date.today(),
            region="NA",
        )
        no_materials = Session(
            title="Workshop Without Materials",
            workshop_type=wt,
            client=client,
            start_date=date.today(),
            end_date=date.today(),
            region="NA",
            no_material_order=True,
        )
        toggle_session = Session(
            title="Workshop Toggle Materials",
            workshop_type=wt,
            client=client,
            start_date=date.today(),
            end_date=date.today(),
            region="NA",
            no_material_order=True,
        )

        db.session.add_all(
            [
                wt,
                client,
                admin,
                crm,
                facilitator,
                contractor,
                material_only,
                with_materials_flag,
                with_order_item,
                no_materials,
                toggle_session,
            ]
        )
        db.session.commit()

        shipping = SessionShipping(
            session_id=with_order_item.id,
            order_date=date.today(),
            order_type="KT-Run Standard materials",
        )
        db.session.add(shipping)
        db.session.flush()
        db.session.add(
            MaterialOrderItem(
                session_id=with_order_item.id,
                catalog_ref="KIT-1",
                title_snapshot="Kit",
                quantity=5,
            )
        )
        client.crm_user_id = crm.id
        db.session.commit()

        return {
            "admin_id": admin.id,
            "crm_id": crm.id,
            "facilitator_id": facilitator.id,
            "contractor_id": contractor.id,
            "material_only_title": material_only.title,
            "with_materials_title": with_materials_flag.title,
            "with_order_item_title": with_order_item.title,
            "no_materials_title": no_materials.title,
            "toggle_title": toggle_session.title,
            "toggle_session_id": toggle_session.id,
        }


def login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


@pytest.mark.parametrize(
    "user_key",
    ["admin_id", "crm_id", "facilitator_id", "contractor_id"],
)
def test_workshop_dashboard_excludes_material_only_for_all_roles(app, dashboard_setup, user_key):
    client = app.test_client()
    login(client, dashboard_setup[user_key])
    resp = client.get("/sessions")
    assert resp.status_code == 200
    assert dashboard_setup["material_only_title"].encode() not in resp.data
    assert dashboard_setup["with_materials_title"].encode() in resp.data
    assert dashboard_setup["with_order_item_title"].encode() in resp.data
    assert dashboard_setup["no_materials_title"].encode() in resp.data
    assert b"Showing 4 workshops" in resp.data


@pytest.mark.parametrize(
    "user_key",
    ["admin_id", "crm_id", "facilitator_id", "contractor_id"],
)
def test_materials_dashboard_filters_workshop_only_sessions(app, dashboard_setup, user_key):
    client = app.test_client()
    login(client, dashboard_setup[user_key])
    resp = client.get("/materials")
    assert resp.status_code == 200
    assert dashboard_setup["material_only_title"].encode() in resp.data
    assert dashboard_setup["with_materials_title"].encode() in resp.data
    assert dashboard_setup["with_order_item_title"].encode() in resp.data
    assert dashboard_setup["no_materials_title"].encode() not in resp.data
    assert dashboard_setup["toggle_title"].encode() not in resp.data
    assert b"Showing 3 materials-enabled sessions" in resp.data


def test_material_toggle_moves_between_dashboards(app, dashboard_setup):
    client = app.test_client()
    login(client, dashboard_setup["admin_id"])
    toggle_title = dashboard_setup["toggle_title"].encode()

    resp = client.get("/sessions")
    assert resp.status_code == 200
    assert toggle_title in resp.data

    resp = client.get("/materials")
    assert resp.status_code == 200
    assert toggle_title not in resp.data

    with app.app_context():
        sess = db.session.get(Session, dashboard_setup["toggle_session_id"])
        sess.no_material_order = False
        sess.materials_ordered = True
        db.session.commit()

    resp = client.get("/materials")
    assert resp.status_code == 200
    assert toggle_title in resp.data
    assert b"Showing 4 materials-enabled sessions" in resp.data

    with app.app_context():
        sess = db.session.get(Session, dashboard_setup["toggle_session_id"])
        sess.materials_ordered = False
        sess.no_material_order = True
        db.session.commit()

    resp = client.get("/materials")
    assert resp.status_code == 200
    assert toggle_title not in resp.data
    assert b"Showing 3 materials-enabled sessions" in resp.data
