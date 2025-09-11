import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.app import create_app, db
from app.models import MaterialDefault, MaterialsOption, WorkshopType


@pytest.fixture
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    app = create_app()
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()


@pytest.mark.smoke
def test_material_default_unique(app):
    with app.app_context():
        wt = WorkshopType(code="AAA", name="Type A", cert_series="fn")
        opt = MaterialsOption(order_type="KT-Run Standard materials", title="Item A", formats=["Physical"])
        db.session.add_all([wt, opt])
        db.session.commit()
        ref = f"materials_options:{opt.id}"
        d1 = MaterialDefault(
            workshop_type_id=wt.id,
            delivery_type="Onsite",
            region_code="NA",
            language="en",
            catalog_ref=ref,
            default_format="Physical",
        )
        db.session.add(d1)
        db.session.commit()
        d2 = MaterialDefault(
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
