from fastapi.testclient import TestClient

from app import swarm_adapter_main
from app.services import swarm_adapter


def test_swarm_adapter_health_returns_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        swarm_adapter,
        "get_swarm_health",
        lambda: {
            "status": "ok",
            "adapter": "docker-cli",
            "reachable": True,
            "swarm": {
                "state": "active",
                "node_id": "node-1",
                "node_addr": "81.70.52.75",
                "control_available": True,
                "error": None,
            },
        },
    )

    with TestClient(swarm_adapter_main.app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["adapter"] == "docker-swarm-api"


def test_swarm_adapter_protected_route_requires_token(monkeypatch) -> None:
    original_token = swarm_adapter_main.settings.SWARM_ADAPTER_TOKEN
    swarm_adapter_main.settings.SWARM_ADAPTER_TOKEN = "secret-token"
    monkeypatch.setattr(
        swarm_adapter_main,
        "get_manager_overview",
        lambda _: {
            "manager_host": "pivotcompute.store",
            "manager_port": 2377,
            "swarm": {"state": "active", "node_id": "node-1", "node_addr": "81.70.52.75", "control_available": True},
            "node_list": "",
            "service_list": "",
        },
    )

    try:
        with TestClient(swarm_adapter_main.app) as client:
            unauthorized = client.get("/swarm/overview")
            authorized = client.get("/swarm/overview", headers={"X-Pivot-Adapter-Token": "secret-token"})
    finally:
        swarm_adapter_main.settings.SWARM_ADAPTER_TOKEN = original_token

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
