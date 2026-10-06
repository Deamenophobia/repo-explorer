from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from repo_explorer.api import create_app
from repo_explorer.config import Settings, load_settings

CORPUS = Path(__file__).resolve().parents[2] / "examples" / "repository"
ORIGIN = "http://127.0.0.1:3000"


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        corpus_dir=CORPUS,
        data_dir=tmp_path / "data",
        config_file=tmp_path / "settings.json",
        mode="demo",
        cors_origins=[],
    )


def test_headless_client_works_without_enabling_browser_origins(settings):
    with TestClient(create_app(settings)) as client:
        run = client.post("/api/runs", json={"question": "repository ingestion"})
        assert run.status_code == 200
        assert run.json()["status"] == "completed"
        response = client.get("/api/corpus", headers={"Origin": ORIGIN})
        assert "access-control-allow-origin" not in response.headers
        preflight = client.options(
            "/api/runs",
            headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST"},
        )
        assert "access-control-allow-origin" not in preflight.headers


def test_custom_frontend_can_configure_ask_and_resume_a_review(settings):
    configured = Settings(**{**settings.model_dump(), "cors_origins": [ORIGIN]})
    with TestClient(create_app(configured), headers={"Origin": ORIGIN}) as client:
        for method in ("GET", "POST", "PUT"):
            preflight = client.options(
                "/api/settings" if method == "PUT" else "/api/runs",
                headers={
                    "Access-Control-Request-Method": method,
                    "Access-Control-Request-Headers": "content-type",
                },
            )
            assert preflight.status_code == 200
            assert preflight.headers["access-control-allow-origin"] == ORIGIN
            assert "access-control-allow-credentials" not in preflight.headers

        document = client.get("/api/settings").json()
        assert "cors_origins" not in document["values"]
        assert "cors_origins" not in document["schema"]["properties"]
        saved = client.put(
            "/api/settings", json={**document["values"], "workspace_name": "Custom client"}
        )
        assert saved.status_code == 200
        assert saved.headers["access-control-allow-origin"] == ORIGIN
        assert "cors_origins" not in settings.config_file.read_text()

        response = client.post(
            "/api/runs",
            json={"question": "Review the human review checkpoint policy", "intent": "review"},
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == ORIGIN
        run = response.json()
        assert run["status"] == "awaiting_review"
        assert client.get(f"/api/runs/{run['id']}").json() == run
        decision_path = f"/api/runs/{run['id']}/decision"
        approved = client.post(decision_path, json={"approved": True})
        assert approved.json()["status"] == "approved"
        assert approved.headers["access-control-allow-origin"] == ORIGIN
        conflict = client.post(decision_path, json={"approved": False})
        assert conflict.status_code == 409
        assert conflict.headers["access-control-allow-origin"] == ORIGIN

        invalid = client.post("/api/runs", json={"question": " "})
        assert invalid.status_code == 422
        assert invalid.headers["access-control-allow-origin"] == ORIGIN
        forbidden_setting = client.put(
            "/api/settings", json={**document["values"], "cors_origins": [ORIGIN]}
        )
        assert forbidden_setting.status_code == 422


def test_unlisted_browser_origin_is_not_granted_access(settings):
    configured = Settings(**{**settings.model_dump(), "cors_origins": [ORIGIN]})
    with TestClient(create_app(configured)) as client:
        headers = {"Origin": "http://localhost:3000"}
        preflight = client.options(
            "/api/runs", headers={**headers, "Access-Control-Request-Method": "POST"}
        )
        assert preflight.status_code == 400
        assert "access-control-allow-origin" not in preflight.headers
        response = client.get("/api/corpus", headers=headers)
        assert "access-control-allow-origin" not in response.headers


def test_origins_load_from_server_environment(settings, monkeypatch):
    monkeypatch.setenv("REPO_EXPLORER_CONFIG_FILE", str(settings.config_file))
    monkeypatch.setenv("REPO_EXPLORER_CORS_ORIGINS", f'["{ORIGIN}", "https://example.org"]')
    assert load_settings().cors_origins == [ORIGIN, "https://example.org"]


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "https://*.example.org",
        "null",
        "file:///index.html",
        "http://localhost:3000/",
        "http://localhost:3000/ui",
        "http://user:password@localhost:3000",
        "http://localhost:3000?query=yes",
        "http://localhost:3000#fragment",
        "http://localhost:99999",
        "http://local host:3000",
    ],
)
def test_invalid_origins_fail_at_startup(settings, origin):
    with pytest.raises(ValidationError):
        Settings(**{**settings.model_dump(), "cors_origins": [origin]})
