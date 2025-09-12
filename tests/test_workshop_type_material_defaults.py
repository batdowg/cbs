import os
import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.app import create_app, db
from app.models import User, WorkshopTypeMaterialDefault, MaterialsOption, WorkshopType


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


@pytest.mark.smoke
def test_material_default_unique(app):
    with app.app_context():
        wt = WorkshopType(code="AAA", name="Type A", cert_series="fn")
        opt = MaterialsOption(order_type="KT-Run Standard materials", title="Item A", formats=["Physical"])
        db.session.add_all([wt, opt])
        db.session.commit()
        ref = f"materials_options:{opt.id}"
        d1 = WorkshopTypeMaterialDefault(
            workshop_type_id=wt.id,
            delivery_type="Onsite",
            region_code="NA",
            language="en",
            catalog_ref=ref,
            default_format="Physical",
        )
        db.session.add(d1)
        db.session.commit()
        d2 = WorkshopTypeMaterialDefault(
            workshop_type_id=wt.id,
            delivery_type="Onsite",
            region_code="NA",
            language="en",
            catalog_ref=ref,
            default_format="Physical",
        )
        db.session.add(d2)
        with pytest.raises(Exception):
            db.session.commit()


@pytest.mark.smoke
def test_delete_default_row(app):
    with app.app_context():
        admin = User(email="admin@example.com", is_app_admin=True, is_admin=True)
        admin.set_password("x")
        wt = WorkshopType(code="BBB", name="Type B", cert_series="fn")
        opt = MaterialsOption(order_type="KT-Run Standard materials", title="Item A", formats=["Digital"])
        db.session.add_all([admin, wt, opt])
        db.session.commit()
        d = WorkshopTypeMaterialDefault(
            workshop_type_id=wt.id,
            delivery_type="Onsite",
            region_code="NA",
            language="en",
            catalog_ref=f"materials_options:{opt.id}",
            default_format="Digital",
            active=True,
        )
        db.session.add(d)
        db.session.commit()
        admin_id = admin.id
        d_id = d.id
    client = app.test_client()
    login(client, admin_id)
    resp = client.post(f"/workshop-types/defaults/{d_id}/delete")
    assert resp.status_code == 200
    with app.app_context():
        assert db.session.get(WorkshopTypeMaterialDefault, d_id) is None
