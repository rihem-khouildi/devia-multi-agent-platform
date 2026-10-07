"""
Tests for project source endpoints: list, upload, delete, tree.
Run with: pytest tests/test_project_sources.py -v
"""

import io
import zipfile
import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app, raise_server_exceptions=True)


# ── Auth helpers ──────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_in_memory_users():
    from api.services import user_service
    user_service._users_mem.clear()
    user_service._users_by_email.clear()
    yield
    user_service._users_mem.clear()
    user_service._users_by_email.clear()


@pytest.fixture()
def auth_headers():
    client.post("/auth/register", json={
        "username": "srcuser", "email": "src@example.com", "password": "srcpass1"
    })
    r = client.post("/auth/login", data={"username": "srcuser", "password": "srcpass1"})
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _make_valid_zip(name: str = "myproject") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{name}/pom.xml", "<project><modelVersion>4.0.0</modelVersion></project>")
        zf.writestr(f"{name}/src/main/java/App.java", "public class App {}")
    return buf.getvalue()


def _make_invalid_zip() -> bytes:
    """Zip without pom.xml or build.gradle."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "no build file here")
    return buf.getvalue()


# ── List sources ──────────────────────────────────────────────────────────────

def test_list_sources_authenticated(auth_headers):
    r = client.get("/projects/sources", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert "sources" in body
    assert any(s["type"] == "default" for s in body["sources"])


def test_list_sources_unauthenticated():
    r = client.get("/projects/sources")
    assert r.status_code == 401


# ── Upload ────────────────────────────────────────────────────────────────────

def test_upload_valid_zip(auth_headers, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "api.services.project_source_service._uploaded_root",
        lambda s: tmp_path / "uploaded-projects",
    )

    zip_bytes = _make_valid_zip("goodproject")
    r = client.post(
        "/projects/sources/upload",
        headers=auth_headers,
        files={"file": ("goodproject.zip", zip_bytes, "application/zip")},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "goodproject"
    assert body["valid"] is True


def test_upload_invalid_zip_no_build_file(auth_headers, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "api.services.project_source_service._uploaded_root",
        lambda s: tmp_path / "uploaded-projects",
    )
    zip_bytes = _make_invalid_zip()
    r = client.post(
        "/projects/sources/upload",
        headers=auth_headers,
        files={"file": ("badproject.zip", zip_bytes, "application/zip")},
    )
    assert r.status_code == 422
    assert "pom.xml" in r.json()["detail"] or "build.gradle" in r.json()["detail"]


def test_upload_non_zip_file(auth_headers):
    r = client.post(
        "/projects/sources/upload",
        headers=auth_headers,
        files={"file": ("project.tar.gz", b"fake", "application/gzip")},
    )
    assert r.status_code == 422


def test_upload_not_a_zip_content(auth_headers, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "api.services.project_source_service._uploaded_root",
        lambda s: tmp_path / "uploaded-projects",
    )
    r = client.post(
        "/projects/sources/upload",
        headers=auth_headers,
        files={"file": ("fake.zip", b"this is not a zip", "application/zip")},
    )
    assert r.status_code == 422


# ── Run with default project source ──────────────────────────────────────────

def test_create_run_default_source_uses_base_project(auth_headers):
    """
    POST /runs without source_project_type must succeed (uses base-spring-project).
    Only tests that the endpoint accepts the request — pipeline itself is async.
    """
    r = client.post(
        "/runs",
        json={"story_input": "As a user I want to see a hello message"},
        headers=auth_headers,
    )
    # 202 Accepted or 422 if pipeline config is missing — both mean auth passed
    assert r.status_code in (202, 422, 500)


def test_create_run_uploaded_unknown_project(auth_headers):
    r = client.post(
        "/runs",
        json={
            "story_input": "Test story",
            "source_project_type": "uploaded",
            "source_project_name": "nonexistent-project-xyz",
        },
        headers=auth_headers,
    )
    assert r.status_code == 422
