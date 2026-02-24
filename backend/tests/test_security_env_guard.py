import importlib
import sys

import pytest


MODULE = "src.core.security"


def _reload_security():
    if MODULE in sys.modules:
        return importlib.reload(sys.modules[MODULE])
    return importlib.import_module(MODULE)


def test_dev_env_allows_fallback_secret(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.setenv("ECHOES_ENV", "development")

    mod = _reload_security()

    token = mod.create_access_token("alice")
    assert mod.decode_access_token(token) == "alice"


def test_prod_env_requires_secret(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.setenv("ECHOES_ENV", "production")

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY must be set"):
        _reload_security()
