import pytest

from app.deps import SESSION_COOKIE

from .conftest import PASSWORDS, ROLES

USERS = list(PASSWORDS)
ROLE_NAMES = ["nurse", "physician", "pharmacist"]


@pytest.mark.parametrize("username", USERS)
def test_login_each_role(client, username):
    resp = client.post("/api/auth/login", json={"username": username, "password": PASSWORDS[username]})
    assert resp.status_code == 200
    user = resp.json()["user"]
    assert user["role"] == ROLES[username]
    assert user["home"] == f"/{ROLES[username]}"
    assert "token" not in resp.text.lower()
    set_cookie = resp.headers["set-cookie"].lower()
    assert "httponly" in set_cookie and "samesite=lax" in set_cookie
    me = client.get("/api/me")
    assert me.status_code == 200 and me.json()["user"]["username"] == username
    assert client.get(f"/api/home/{ROLES[username]}").status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {"username": "nurse1", "password": "wrong-password"},
        {"username": "nobody", "password": "whatever"},
        {"username": "", "password": ""},
        {"username": "nurse1", "password": ""},
        {"username": "", "password": PASSWORDS["nurse1"]},
        {},
    ],
    ids=["wrong_password", "unknown_user", "empty_both", "empty_password", "empty_username", "missing"],
)
def test_login_rejects_bad_credentials(client, body):
    resp = client.post("/api/auth/login", json=body)
    assert resp.status_code == 401
    assert "set-cookie" not in resp.headers
    assert SESSION_COOKIE not in client.cookies
    assert "token" not in resp.json()
    assert client.get("/api/me").status_code == 401


@pytest.mark.parametrize("username", USERS)
@pytest.mark.parametrize("home", ROLE_NAMES)
def test_role_home_matrix(client, login, username, home):
    login(username)
    resp = client.get(f"/api/home/{home}")
    if home == ROLES[username]:
        assert resp.status_code == 200
        body = resp.json()
        assert body["role"] == home and body["message"] == "features arrive in later slices"
    else:
        assert resp.status_code == 403


@pytest.mark.parametrize("home", ROLE_NAMES)
def test_role_home_unauthenticated_is_401(client, home):
    assert client.get(f"/api/home/{home}").status_code == 401


def test_unknown_role_home_is_404(client, login):
    login("nurse1")
    assert client.get("/api/home/admin").status_code == 404


def test_logout_ends_session(client, login):
    login("nurse1")
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/me").status_code == 401


def test_expired_session_is_rejected(tmp_path):
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app
    from app.seed import seed_dev_users

    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'x.db'}", session_ttl_minutes=0))
    seed_dev_users(app.state.engine)
    with TestClient(app) as c:
        resp = c.post("/api/auth/login", json={"username": "nurse1", "password": PASSWORDS["nurse1"]})
        assert resp.status_code == 200
        token = resp.headers["set-cookie"].split(";")[0].split("=", 1)[1]
        c.cookies.set(SESSION_COOKIE, token)  # replay the token despite max_age=0
        assert c.get("/api/me").status_code == 401  # server-side expiry enforced
