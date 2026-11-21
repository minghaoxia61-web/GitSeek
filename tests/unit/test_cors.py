import pytest
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


@pytest.mark.parametrize(
    "origin",
    [
        "https://openscout-gitseek.minghaoxia61.chatgpt.site",
        "https://minghaoxia61-web.github.io",
        "https://gitseek-nbt5rbp5z8r.qoder.website",
    ],
)
def test_public_web_origin_can_preflight_api_requests(origin: str) -> None:
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


@pytest.mark.parametrize(
    "origin",
    [
        "https://another-site.qoder.website",
        "https://gitseek-nbt5rbp5z8r.qoder.website.example.com",
        "http://gitseek-nbt5rbp5z8r.qoder.website",
    ],
)
def test_unlisted_web_origin_is_rejected(origin: str) -> None:
    with TestClient(app) as client:
        response = client.options(
            "/api/v1/search",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
