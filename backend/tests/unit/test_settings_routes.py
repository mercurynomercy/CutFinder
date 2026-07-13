"""Tests for the settings routes, focused on POST /settings/omlx/test."""
from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client(env, models_result=None, raise_exc=None):
    from cutfinder.api.settings_routes import _build_router

    config = SimpleNamespace(env=SimpleNamespace(**env), prefs=SimpleNamespace())

    def load_config_fn(_lib):
        return config

    router = _build_router(
        load_config_fn=load_config_fn,
        save_prefs_fn=lambda *a, **k: None,
        get_library_fn=lambda: "/tmp/lib",
        save_global_fn=lambda *a, **k: None,
        save_global_prefs_fn=lambda *a, **k: None,
    )
    app = FastAPI()
    app.include_router(router)

    def fake_check(base_url, api_key, expected_models=None):
        if raise_exc is not None:
            raise raise_exc
        return list(models_result or [])

    return TestClient(app, raise_server_exceptions=False), fake_check


ENV = {
    "OMLX_BASE_URL": "http://localhost:1235/v1",
    "OMLX_API_KEY": "stored-key",
    "TEXT_MODEL": "Qwen3.6-35B-A3B",
    "VISION_MODEL": "Qwen3-VL-8B",
}


def test_test_connection_ok_uses_stored_key_when_blank():
    client, fake = _client(ENV, models_result=["Qwen3.6-35B-A3B", "Qwen3-VL-8B"])
    with mock.patch("cutfinder.adapters.omlx_check.check_omlx", side_effect=fake) as m:
        r = client.post("/api/settings/omlx/test", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["missing"] == []
    # blank key in body → falls back to stored key
    assert m.call_args.args[1] == "stored-key"


def test_test_connection_reports_missing_model():
    client, fake = _client(ENV, models_result=["Qwen3.6-35B-A3B"])
    with mock.patch("cutfinder.adapters.omlx_check.check_omlx", side_effect=fake):
        r = client.post("/api/settings/omlx/test", json={})
    body = r.json()
    assert body["ok"] is True
    assert body["missing"] == ["Qwen3-VL-8B"]


def test_test_connection_surfaces_auth_error():
    client, fake = _client(ENV, raise_exc=RuntimeError("OMLX returned HTTP 401: Invalid API key"))
    with mock.patch("cutfinder.adapters.omlx_check.check_omlx", side_effect=fake):
        r = client.post("/api/settings/omlx/test", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "Invalid API key" in body["error"]


def test_test_connection_empty_key_short_circuits():
    env = {**ENV, "OMLX_API_KEY": ""}
    client, fake = _client(env)
    with mock.patch("cutfinder.adapters.omlx_check.check_omlx", side_effect=fake) as m:
        r = client.post("/api/settings/omlx/test", json={"OMLX_API_KEY": ""})
    body = r.json()
    assert body["ok"] is False
    m.assert_not_called()  # never call check_omlx with empty key (it sys.exit)
