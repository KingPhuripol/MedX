from app.config import DEFAULT_DATABASE_URL, Settings
from app.db import make_engine


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "default_provider": "mock", "research_prototype": True}


def test_database_url_default_and_override(monkeypatch, tmp_path):
    assert Settings.from_env().database_url == DEFAULT_DATABASE_URL == "sqlite:///./backend/dev.db"
    assert make_engine(DEFAULT_DATABASE_URL).dialect.name == "sqlite"

    override = f"sqlite:///{tmp_path / 'other.db'}"
    monkeypatch.setenv("DATABASE_URL", override)
    settings = Settings.from_env()
    assert settings.database_url == override
    assert str(make_engine(settings.database_url).url) == override

    pg = "postgresql+psycopg://u:p@127.0.0.1:5432/db"
    monkeypatch.setenv("DATABASE_URL", pg)
    assert make_engine(Settings.from_env().database_url).dialect.name == "postgresql"


def test_network_is_blocked_during_pytest():
    """S0-A08: the whole pytest run executes with inet sockets disabled (pytest-socket)."""
    import socket

    import pytest
    from pytest_socket import SocketBlockedError

    with pytest.raises(SocketBlockedError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)
