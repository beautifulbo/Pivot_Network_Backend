import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import seller_client.agent_server as agent_server


def test_agent_server_health_endpoint_returns_ok() -> None:
    client = TestClient(agent_server.app)
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_agent_server_serves_index_page() -> None:
    client = TestClient(agent_server.app)
    response = client.get("/")

    assert response.status_code == 200
    assert "Pivot Seller Console" in response.text


def test_dashboard_endpoint_returns_structured_summary(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_server,
        "get_client_config",
        lambda state_dir=None: {
            "ok": True,
            "data": {
                "auth": {
                    "seller_email": "seller@example.com",
                    "access_token": "***",
                    "node_registration_token": "***",
                },
                "server": {
                    "backend_url": "http://127.0.0.1:8000",
                    "registry": "pivotcompute.store",
                },
                "docker": {"last_pushed_image": "seller/demo:v1"},
                "runtime": {
                    "codex_runtime_ready": True,
                    "codex_provider": "OpenAI",
                    "wireguard_profile_status": "prepared",
                },
            },
            "dirs": {},
        },
    )
    monkeypatch.setattr(
        agent_server,
        "_load_client_config",
        lambda base_dir=None: {
            "auth": {
                "seller_email": "seller@example.com",
                "access_token": "token",
                "node_registration_token": "node-token",
            }
        },
    )
    monkeypatch.setattr(
        agent_server,
        "environment_check",
        lambda: {
            "platform": "Windows",
            "python": "python",
            "docker_cli": "docker",
            "codex_cli": "codex",
            "wireguard_cli": "wg",
            "wireguard_windows_exe": "",
        },
    )
    monkeypatch.setattr(
        agent_server,
        "mcp_server_attachment_status",
        lambda config_text=None: {"sellerNodeAgent": True, "buyerRuntimeAgent": True},
    )
    monkeypatch.setattr(
        agent_server,
        "docker_summary",
        lambda: {"ok": True, "info": {"stdout": "swarm_state=active control=false"}},
    )
    monkeypatch.setattr(
        agent_server,
        "swarm_summary",
        lambda: {"info": {"ok": True, "stdout": "state=active node_id=node-001"}},
    )
    monkeypatch.setattr(
        agent_server,
        "wireguard_summary",
        lambda state_dir=None: {
            "platform": "Windows",
            "config_path": "d:/tmp/wg-seller.conf",
            "client_address": "10.88.0.10/32",
            "client_public_key": "client-public",
            "profile_status": "prepared",
        },
    )
    monkeypatch.setattr(
        agent_server,
        "list_uploaded_images",
        lambda state_dir=None: {"ok": True, "registry": "http://registry", "repositories": ["seller/demo"]},
    )
    monkeypatch.setattr(
        agent_server,
        "_platform_snapshot",
        lambda state_dir: {
            "ok": True,
            "backend_url": "http://127.0.0.1:8000",
            "overview": {
                "node_count": 1,
                "image_count": 1,
                "nodes": [
                    {
                        "node_key": "node-001",
                        "hostname": "seller-host",
                        "status": "available",
                        "shared_percent_preference": 10,
                        "wireguard_ready_for_buyer": True,
                        "wireguard_target": "10.66.66.10",
                    }
                ],
                "images": [{"repository": "seller/demo", "tag": "v1", "push_ready": True}],
            },
            "activity": [{"event_type": "node_registered"}],
            "swarm": {"swarm": {"state": "active", "nodes": 2}},
        },
    )
    monkeypatch.setattr(agent_server, "_default_node_key", lambda base_dir=None: "node-001")
    monkeypatch.setattr(agent_server, "_read_local_activity", lambda state_dir, limit=20: [])

    client = TestClient(agent_server.app)
    response = client.get("/api/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["seller_email"] == "seller@example.com"
    assert payload["summary"]["node_count"] == 1
    assert payload["summary"]["image_count"] == 1
    assert payload["summary"]["node_id"] == "node-001"
    assert any(item["id"] == "codex_mcp" and item["status"] == "success" for item in payload["readiness"])
    assert any(item["id"] == "platform_node" and item["status"] == "success" for item in payload["readiness"])
    assert any(item["id"] == "platform_wireguard_ready" and item["status"] == "success" for item in payload["readiness"])


def test_onboarding_endpoint_records_local_activity(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        agent_server,
        "onboard_seller_from_intent",
        lambda **kwargs: {
            "ok": True,
            "message": "done",
            "explanation": {"explanation": "已理解接入意图。", "share_percent_preference": 10},
            "configure_result": {"ok": True},
            "environment": {
                "platform": "Windows",
                "docker_cli": "docker",
                "codex_cli": "codex",
                "wireguard_cli": "wg",
                "wireguard_windows_exe": "",
            },
            "docker": {"ok": True, "action": "already_running"},
            "register_result": {"ok": True},
            "login_result": {"ok": True},
            "node_token_result": {"ok": True},
            "codex_runtime_result": {"ok": True, "data": {"provider": {"name": "OpenAI"}, "model": "gpt-5.4"}},
            "register_node_result": {"ok": True},
            "wireguard_result": {
                "ok": True,
                "keypair_result": {"ok": True, "public_key": "pub"},
                "bootstrap_result": {"ok": True, "data": {"activation_mode": "profile_only"}},
                "profile_result": {"ok": True},
            },
            "heartbeat_result": {"ok": True},
        },
    )

    client = TestClient(agent_server.app)
    response = client.post(
        "/api/onboarding",
        json={
            "intent": "我想把电脑接入平台",
            "email": "seller@example.com",
            "password": "secret",
            "state_dir": str(tmp_path),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["action"] == "onboarding"

    activity_response = client.get(f"/api/local-activity?state_dir={str(tmp_path)}")
    assert activity_response.status_code == 200
    items = activity_response.json()["items"]
    assert len(items) == 1
    assert items[0]["action"] == "onboarding"
    assert items[0]["title"] == "卖家节点接入"


def test_intent_explain_endpoint_returns_next_steps(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_server,
        "explain_seller_intent",
        lambda intent: {
            "ok": True,
            "intent": intent,
            "share_percent_preference": 10,
            "explanation": "已把意图解释成节点接入请求。",
        },
    )

    client = TestClient(agent_server.app)
    response = client.post("/api/intents/explain", json={"intent": "请帮我接入节点"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["share_percent_preference"] == 10
    assert len(payload["next_steps"]) == 3


def test_wireguard_bootstrap_endpoint_records_local_activity(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        agent_server,
        "bootstrap_wireguard_from_platform",
        lambda **kwargs: {
            "ok": True,
            "keypair_result": {"ok": True, "public_key": "pub"},
            "bootstrap_result": {"ok": True, "data": {"activation_mode": "profile_only"}},
            "profile_result": {"ok": True},
        },
    )

    client = TestClient(agent_server.app)
    response = client.post("/api/wireguard/bootstrap", json={"state_dir": str(tmp_path)})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["action"] == "wireguard_bootstrap"


def test_swarm_ensure_joined_endpoint_records_local_activity(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        agent_server,
        "ensure_joined_to_platform_swarm",
        lambda **kwargs: {
            "ok": True,
            "action": "already_joined",
            "swarm_summary": {"info": {"ok": True, "stdout": "state=active"}},
        },
    )

    client = TestClient(agent_server.app)
    response = client.post("/api/swarm/ensure-joined", json={"state_dir": str(tmp_path)})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["action"] == "swarm_join"
