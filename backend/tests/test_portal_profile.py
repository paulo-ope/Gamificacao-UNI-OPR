from fastapi.testclient import TestClient

from app.core.security import get_current_user
from app.db.session import get_db
from app.main import app
from app.models import User


def _portal_client(db_session, user: User):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_portal_profile_allows_only_own_contact_fields(db_session, make_collaborator):
    collaborator = make_collaborator(name="Ana Portal", regional="UNI NORTE", role="Tecnica")
    user = User(
        name="Ana Portal",
        email="ana@login.local",
        role="collaborator",
        active=True,
        password_hash="x",
        collaborator_id=collaborator.id,
    )
    db_session.add(user)
    db_session.commit()

    try:
        with _portal_client(db_session, user) as client:
            response = client.get("/api/portal/profile")
            assert response.status_code == 200
            assert response.json()["name"] == "Ana Portal"
            assert response.json()["regional"] == "UNI NORTE"

            update = client.put("/api/portal/profile", json={"phone": "(69) 99999-0000", "email": "ana@contato.local"})
            assert update.status_code == 200
            assert update.json()["phone"] == "(69) 99999-0000"
            assert update.json()["email"] == "ana@contato.local"

            protected = client.put("/api/portal/profile", json={"regional": "UNI SUL"})
            assert protected.status_code == 422
    finally:
        app.dependency_overrides.clear()

    db_session.refresh(collaborator)
    assert collaborator.regional == "UNI NORTE"


def test_portal_profile_photo_is_limited_to_linked_collaborator(db_session, make_collaborator):
    collaborator = make_collaborator(name="Bruno Portal")
    other = make_collaborator(name="Outro Colaborador")
    other.photo = b"other-photo"
    other.photo_content_type = "image/png"
    user = User(
        name="Bruno Portal",
        email="bruno@login.local",
        role="collaborator",
        active=True,
        password_hash="x",
        collaborator_id=collaborator.id,
    )
    db_session.add(user)
    db_session.commit()

    try:
        with _portal_client(db_session, user) as client:
            upload = client.post("/api/portal/profile/photo", files={"file": ("perfil.png", b"own-photo", "image/png")})
            assert upload.status_code == 200
            assert upload.json()["has_photo"] is True

            photo = client.get("/api/portal/profile/photo")
            assert photo.status_code == 200
            assert photo.content == b"own-photo"
    finally:
        app.dependency_overrides.clear()

    db_session.refresh(other)
    assert other.photo == b"other-photo"
