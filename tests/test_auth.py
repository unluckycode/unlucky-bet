import os
import re
import tempfile
import unicodedata

import pytest

_tmp = tempfile.mkdtemp()
os.environ.update(
    UNLUCKYBET_DB=os.path.join(_tmp, "test.db"),
    UNLUCKYBET_DATA_DIR=_tmp,
    DISABLE_SCHEDULER="1",
    SECRET_KEY="test-secret",
)
os.environ.pop("DATABASE_URL", None)

from unluckybet import auth  # noqa: E402
from unluckybet.web import create_app  # noqa: E402

PASSWORD = "Zażółć gęślą 123"


@pytest.fixture()
def client(monkeypatch):
    # Wartość jak wklejona w panelu hostingu: spacje, nowa linia i cudzysłowy.
    monkeypatch.setenv("APP_PASSWORD", f'  "{PASSWORD}"\n')
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def _csrf(client):
    html = client.get("/login").get_data(as_text=True)
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def test_normalize_secret_strips_whitespace_quotes_and_nfc():
    nfd = unicodedata.normalize("NFD", PASSWORD)
    assert auth.normalize_secret(f"  '{nfd}' \r\n") == unicodedata.normalize("NFC", PASSWORD)
    assert auth.normalize_secret("") == ""


def test_protected_page_redirects_to_login(client):
    resp = client.get("/ligi")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_correct_password_with_polish_chars_logs_in(client):
    token = _csrf(client)
    resp = client.post("/login?next=/zaklady", data={"password": f" {PASSWORD} ", "csrf": token})
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/zaklady")
    assert client.get("/zaklady").status_code == 200


def test_decomposed_unicode_input_is_accepted(client):
    token = _csrf(client)
    resp = client.post("/login", data={"password": unicodedata.normalize("NFD", PASSWORD), "csrf": token})
    assert resp.status_code == 302


def test_wrong_password_message(client):
    token = _csrf(client)
    resp = client.post("/login", data={"password": "zle-haslo", "csrf": token})
    assert resp.status_code == 401
    assert 'data-error="wrong_password"' in resp.get_data(as_text=True)


def test_missing_session_cookie_is_not_reported_as_wrong_password(client):
    client.get("/login")
    client.delete_cookie("session")
    resp = client.post("/login", data={"password": PASSWORD, "csrf": "x"})
    assert resp.status_code == 400
    body = resp.get_data(as_text=True)
    assert 'data-error="no_session"' in body
    assert "Nieprawidłowe hasło" not in body


def test_stale_csrf_token(client):
    _csrf(client)
    resp = client.post("/login", data={"password": PASSWORD, "csrf": "stary-token"})
    assert resp.status_code == 400
    assert 'data-error="csrf"' in resp.get_data(as_text=True)


def test_password_not_configured(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "   ")
    c = create_app().test_client()
    assert c.get("/ligi").status_code == 200
    c.get("/login")
    resp = c.post("/login", data={"password": "cokolwiek", "csrf": "x"})
    assert resp.status_code == 503
    assert 'data-error="not_configured"' in resp.get_data(as_text=True)


def test_https_behind_proxy_sets_secure_cookie(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", PASSWORD)
    app = create_app()
    app.config["SESSION_COOKIE_SECURE"] = True
    c = app.test_client()
    resp = c.get("/login", headers={"X-Forwarded-Proto": "https"}, base_url="https://example.onrender.com")
    cookie = resp.headers.get("Set-Cookie", "")
    assert "Secure" in cookie and "HttpOnly" in cookie
