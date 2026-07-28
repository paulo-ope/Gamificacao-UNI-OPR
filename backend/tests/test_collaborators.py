"""Regression tests for backend/app/api/routes/collaborators.py - focused on the profile photo
upload endpoints (the newly-added, genuinely risky part: size/type validation and making sure the
audit log never chokes on raw image bytes)."""


def test_upload_photo_rejects_unsupported_content_type(client, make_collaborator):
    collaborator = make_collaborator()
    response = client.post(
        f"/api/collaborators/{collaborator.id}/photo",
        files={"file": ("nota.txt", b"conteudo qualquer", "text/plain")},
    )
    assert response.status_code == 422


def test_upload_photo_rejects_file_over_2mb(client, make_collaborator):
    collaborator = make_collaborator()
    oversized = b"\xff\xd8\xff" + b"0" * (2 * 1024 * 1024 + 1)
    response = client.post(
        f"/api/collaborators/{collaborator.id}/photo",
        files={"file": ("foto.jpg", oversized, "image/jpeg")},
    )
    assert response.status_code == 413


def test_upload_get_and_delete_photo_round_trip(client, make_collaborator):
    collaborator = make_collaborator()
    photo_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF-fake-but-fine-for-a-test"

    upload = client.post(
        f"/api/collaborators/{collaborator.id}/photo",
        files={"file": ("foto.jpg", photo_bytes, "image/jpeg")},
    )
    assert upload.status_code == 200

    registry = client.get("/api/collaborators/registry")
    assert registry.status_code == 200
    registered = registry.json()["registered"]
    item = next(i for i in registered if i["id"] == collaborator.id)
    assert item["has_photo"] is True

    fetched = client.get(f"/api/collaborators/{collaborator.id}/photo")
    assert fetched.status_code == 200
    assert fetched.content == photo_bytes
    assert fetched.headers["content-type"] == "image/jpeg"

    deleted = client.delete(f"/api/collaborators/{collaborator.id}/photo")
    assert deleted.status_code == 200

    fetched_again = client.get(f"/api/collaborators/{collaborator.id}/photo")
    assert fetched_again.status_code == 404


def test_audit_log_survives_photo_upload_without_crashing(client, make_collaborator, db_session):
    """Regression: `snapshot()` (audit_log.py) used to serialize every column of the ORM object,
    including raw photo bytes, straight into jsonable_encoder - which crashes with
    UnicodeDecodeError on real (non-UTF8) binary content like a JPEG. This must not happen,
    whether the change itself is the photo upload or any later unrelated edit to a collaborator
    that already has a photo."""
    from app.models import AuditLog, Collaborator

    collaborator = make_collaborator()
    upload = client.post(
        f"/api/collaborators/{collaborator.id}/photo",
        files={"file": ("foto.jpg", b"\xff\xd8\xff\xe0\x00\x10JFIF", "image/jpeg")},
    )
    assert upload.status_code == 200

    # A generic update (name change) on a collaborator that already HAS a photo must also survive -
    # this goes through the untouched `update_collaborator` route, which still calls the generic
    # `snapshot(collaborator)` covering every column, including `photo`.
    rename = client.put(f"/api/collaborators/{collaborator.id}", json={"name": "Novo Nome"})
    assert rename.status_code == 200

    logs = db_session.query(AuditLog).filter(AuditLog.entity == "collaborators").all()
    assert len(logs) >= 2

    refreshed = db_session.get(Collaborator, collaborator.id)
    assert refreshed.name == "Novo Nome"
    assert refreshed.photo is not None
