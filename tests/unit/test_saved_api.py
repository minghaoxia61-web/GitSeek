from fastapi.testclient import TestClient

from apps.api.main import app


def test_saved_repositories_are_persisted_per_device() -> None:
    with TestClient(app) as client:
        saved = client.post(
            "/api/v1/saved",
            json={"device_id": "device-test-001", "repository": "example/demo"},
        )
        listed = client.get("/api/v1/saved?device_id=device-test-001")
        removed = client.delete(
            "/api/v1/saved/example/demo?device_id=device-test-001"
        )

    assert saved.status_code == 201
    assert saved.json()["repositories"] == ["example/demo"]
    assert listed.json()["repositories"] == ["example/demo"]
    assert removed.json()["repositories"] == []
