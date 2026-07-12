from fastapi.testclient import TestClient
from uuid import uuid4

from app.core.safety import is_allowed_upload
from app.main import _access_db_path, _is_under_data_root, app


def test_health_reports_hosted_limits():
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "max_batch_cases" in payload
    assert "max_concurrent_jobs" in payload
    assert "storage_dir" in payload


def test_upload_extension_policy_matches_hosted_demo():
    assert is_allowed_upload("subject_001.nii")
    assert is_allowed_upload("subject_001.nii.gz")
    assert is_allowed_upload("aparc+aseg.mgz")
    assert is_allowed_upload("FreeSurferColorLUT.txt")
    assert not is_allowed_upload("legacy_file.mgh")
    assert not is_allowed_upload("script.sh")


def test_access_log_database_is_not_static_served():
    assert not _is_under_data_root(_access_db_path())


def test_backend_session_required_for_demo():
    client = TestClient(app)
    response = client.post("/api/demo/run")
    assert response.status_code == 401


def test_login_returns_session_and_history_payload():
    client = TestClient(app)
    email = f"history-test-{uuid4().hex}@example.com"
    response = client.post("/api/access/login", json={"email": email, "password": "history-test-pass"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["token"]
    assert payload["email"] == email
    assert "recent_validations" in payload
    session = client.get("/api/access/session", headers={"Authorization": f"Bearer {payload['token']}"})
    assert session.status_code == 200
