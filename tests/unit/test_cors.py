from fastapi.testclient import TestClient

from apps.api.main import app


def test_tauri_origin_can_preflight_api_requests() -> None:
    with TestClient(app) as client:
        response = client.options(
            "/api/v1/search",
            headers={
                "Origin": "http://tauri.localhost",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://tauri.localhost"
    assert "POST" in response.headers["access-control-allow-methods"]


def test_public_sites_origin_can_preflight_api_requests() -> None:
    origin = "https://openscout-gitseek.minghaoxia61.chatgpt.site"
    with TestClient(app) as client:
        response = client.options(
            "/api/v1/agent/runs",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "POST" in response.headers["access-control-allow-methods"]
