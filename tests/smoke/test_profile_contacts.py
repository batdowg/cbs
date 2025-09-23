import io
import os

from app.app import db
from app.models import ParticipantAccount, User
from app.shared.profile_images import resolve_profile_image

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_profile_contact_fields_persist(app, client):
    with app.app_context():
        user = User(email="user@example.com", is_admin=True, region="NA")
        user.set_password("pw")
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    form_data = {
        "form": "profile",
        "full_name": "Staff Member",
        "title": "Coach",
        "preferred_language": "en",
        "certificate_name": "Certificate Name",
        "phone": "+1 555-0100",
        "city": "Springfield",
        "state": "IL",
        "country": "",
        "profile_image": (io.BytesIO(PNG_BYTES), "avatar.png"),
    }
    resp = client.post(
        "/profile",
        data=form_data,
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    html = resp.get_data(as_text=True)
    assert resp.request.path == "/profile"
    assert "+1 555-0100" in html
    assert "Springfield" in html

    with app.app_context():
        user = db.session.get(User, user_id)
        account = ParticipantAccount.query.filter_by(email="user@example.com").one()
        assert user.phone == "+1 555-0100"
        assert user.city == "Springfield"
        assert user.state == "IL"
        assert user.country is None
        assert user.profile_image_path is not None
        stored_path = user.profile_image_path
        resolved = resolve_profile_image(stored_path)
        assert resolved is not None
        stored = os.path.join(app.config.get("SITE_ROOT", "/srv"), resolved.lstrip("/"))
        assert os.path.isfile(stored)
        db_account = db.session.get(ParticipantAccount, account.id)
        assert db_account.phone == "+1 555-0100"
        assert db_account.city == "Springfield"
        assert db_account.state == "IL"
