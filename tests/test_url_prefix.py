"""The app is served under config.URL_PREFIX (e.g. /stardash) next to other apps on one NGINX."""
import pytest

import config
from app import create_app, normalise_prefix


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config, "URL_PREFIX", "/stardash")
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


@pytest.mark.parametrize("raw, expected", [
    ("/stardash", "/stardash"), ("stardash/", "/stardash"), ("", ""), ("/", ""), (None, ""),
])
def test_normalise_prefix(raw, expected):
    assert normalise_prefix(raw) == expected


def test_login_page_served_under_prefix_with_prefixed_links(client):
    res = client.get("/stardash/login")
    assert res.status_code == 200
    body = res.get_data(as_text=True)
    assert 'href="/stardash/static/css/style.css"' in body
    assert 'window.APP_ROOT = "/stardash"' in body


def test_paths_outside_prefix_are_not_served(client):
    assert client.get("/login").status_code == 404
    assert client.get("/otherapp/login").status_code == 404
    assert client.get("/stardashboard/login").status_code == 404


def test_root_redirects_into_prefix(client):
    res = client.get("/")
    assert res.status_code in (301, 302, 308)
    assert res.headers["Location"].endswith("/stardash/")


def test_login_required_redirect_keeps_prefix(client):
    res = client.get("/stardash/dashboard/1")
    assert res.status_code == 302
    assert res.headers["Location"].startswith("/stardash/login?next=")
    assert "next=/dashboard/1" in res.headers["Location"]


def test_api_returns_json_401_under_prefix(client):
    res = client.get("/stardash/api/views")
    assert res.status_code == 401 and res.is_json


def test_session_cookie_is_scoped_to_prefix(client):
    app = client.application
    assert app.config["SESSION_COOKIE_PATH"] == "/stardash/"
    assert app.config["SESSION_COOKIE_NAME"] == "stardash_session"
    with client.session_transaction() as s:
        s["username"] = "x"
    cookie = client.get_cookie("stardash_session", path="/stardash/")
    assert cookie is not None


def test_no_prefix_serves_at_root(monkeypatch):
    monkeypatch.setattr(config, "URL_PREFIX", "")
    app = create_app()
    res = app.test_client().get("/login")
    assert res.status_code == 200
    assert 'href="/static/css/style.css"' in res.get_data(as_text=True)
