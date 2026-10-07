"""
Tests for authentication endpoints: register, login, me.
Run with: pytest tests/test_auth.py -v
"""

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app, raise_server_exceptions=True)


@pytest.fixture(autouse=True)
def clear_in_memory_users():
    """Reset the in-memory user store between tests."""
    from api.services import user_service
    user_service._users_mem.clear()
    user_service._users_by_email.clear()
    yield
    user_service._users_mem.clear()
    user_service._users_by_email.clear()


# ── Register ──────────────────────────────────────────────────────────────────

def test_register_success():
    r = client.post("/auth/register", json={
        "username": "alice",
        "email": "alice@example.com",
        "password": "secret123",
    })
    assert r.status_code == 201
    body = r.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_register_duplicate_username():
    payload = {"username": "bob", "email": "bob@example.com", "password": "pass123"}
    client.post("/auth/register", json=payload)
    r = client.post("/auth/register", json={**payload, "email": "bob2@example.com"})
    assert r.status_code == 409
    assert "Username" in r.json()["detail"]


def test_register_duplicate_email():
    client.post("/auth/register", json={"username": "carol", "email": "carol@x.com", "password": "pass123"})
    r = client.post("/auth/register", json={"username": "carol2", "email": "carol@x.com", "password": "pass123"})
    assert r.status_code == 409
    assert "Email" in r.json()["detail"]


def test_register_short_password():
    r = client.post("/auth/register", json={
        "username": "dave", "email": "dave@x.com", "password": "123"
    })
    assert r.status_code == 422


def test_register_short_username():
    r = client.post("/auth/register", json={
        "username": "ab", "email": "ab@x.com", "password": "password"
    })
    assert r.status_code == 422


# ── Login ─────────────────────────────────────────────────────────────────────

def _register_and_get_token(username="testuser", email="test@example.com", password="testpass"):
    r = client.post("/auth/register", json={"username": username, "email": email, "password": password})
    assert r.status_code == 201
    return r.json()["access_token"]


def test_login_success():
    _register_and_get_token()
    r = client.post("/auth/login", data={"username": "testuser", "password": "testpass"})
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_login_wrong_password():
    _register_and_get_token()
    r = client.post("/auth/login", data={"username": "testuser", "password": "wrongpass"})
    assert r.status_code == 401


def test_login_unknown_user():
    r = client.post("/auth/login", data={"username": "nobody", "password": "whatever"})
    assert r.status_code == 401


# ── /auth/me ──────────────────────────────────────────────────────────────────

def test_me_authenticated():
    token = _register_and_get_token()
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == "testuser"
    assert body["email"] == "test@example.com"
    assert "id" in body


def test_me_without_token():
    r = client.get("/auth/me")
    assert r.status_code == 401


def test_me_with_invalid_token():
    r = client.get("/auth/me", headers={"Authorization": "Bearer this.is.not.valid"})
    assert r.status_code == 401


# ── Protected endpoint returns 401 without token ──────────────────────────────

def test_protected_runs_list_without_token():
    r = client.get("/runs")
    assert r.status_code == 401


def test_protected_create_run_without_token():
    r = client.post("/runs", json={"story_input": "As a user I want to log in"})
    assert r.status_code == 401


def test_protected_project_sources_without_token():
    r = client.get("/projects/sources")
    assert r.status_code == 401
