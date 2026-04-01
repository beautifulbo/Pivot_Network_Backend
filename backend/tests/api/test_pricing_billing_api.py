from datetime import UTC, datetime

from sqlalchemy import select

from app.models.platform import ResourceRateCard


def test_buyer_wallet_defaults_to_100_credits(client) -> None:
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "wallet-buyer@example.com",
            "password": "super-secret-password",
            "display_name": "Wallet Buyer",
        },
    )
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "wallet-buyer@example.com", "password": "super-secret-password"},
    )
    buyer_token = login_response.json()["access_token"]

    wallet_response = client.get(
        "/api/v1/buyer/wallet",
        headers={"Authorization": f"Bearer {buyer_token}"},
    )

    assert wallet_response.status_code == 200
    assert wallet_response.json()["balance_cny_credits"] == 100.0

    frontend_response = client.get("/platform-ui/")
    assert frontend_response.status_code == 200
    assert "Pivot Platform UI" in frontend_response.text


def test_publish_image_offer_and_create_billed_session(client, monkeypatch) -> None:
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "seller-offer@example.com",
            "password": "super-secret-password",
            "display_name": "Offer Seller",
        },
    )
    seller_login = client.post(
        "/api/v1/auth/login",
        json={"email": "seller-offer@example.com", "password": "super-secret-password"},
    )
    seller_token = seller_login.json()["access_token"]
    node_token_response = client.post(
        "/api/v1/platform/node-registration-token",
        json={"label": "offer-node", "expires_hours": 48},
        headers={"Authorization": f"Bearer {seller_token}"},
    )
    node_token = node_token_response.json()["node_registration_token"]
    register_node_response = client.post(
        "/api/v1/platform/nodes/register",
        json={
            "node_id": "offer-node-001",
            "device_fingerprint": "device-offer-001",
            "hostname": "docker-desktop",
            "system": "Windows",
            "machine": "AMD64",
            "shared_percent_preference": 10,
            "capabilities": {"cpu_count_logical": 24, "memory_total_mb": 32768},
            "seller_intent": "offer seller test",
            "docker_status": "ready",
            "swarm_state": "state=active node_id=ql6wifxs5vfs2d8ezr884pihx",
            "node_class": "cpu-basic",
        },
        headers={"Authorization": f"Bearer {node_token}"},
    )
    assert register_node_response.status_code == 200

    monkeypatch.setattr("app.services.image_offer_publishing.validate_runtime_image_on_node", lambda settings, **kwargs: {"ok": True})
    monkeypatch.setattr(
        "app.services.image_offer_publishing.probe_node_capabilities_on_node",
        lambda settings, **kwargs: {"ok": True, "probe": {"cpu_logical": 24, "memory_total_mb": 32768, "gpus": []}},
    )

    def fake_ensure_current_rate_card(db):
        card = db.scalar(select(ResourceRateCard).order_by(ResourceRateCard.id.desc()))
        if card is None:
            card = ResourceRateCard(
                status="active",
                effective_hour=datetime.now(UTC).replace(tzinfo=None),
                usd_cny_rate=7.2,
                cpu_price_usd_per_hour=0.03,
                ram_price_usd_per_gib_hour=0.004,
                gpu_price_usd_per_hour={},
                source_summary={},
            )
            db.add(card)
            db.commit()
            db.refresh(card)
        return card

    monkeypatch.setattr("app.services.image_offer_publishing.ensure_current_rate_card", fake_ensure_current_rate_card)

    image_response = client.post(
        "/api/v1/platform/images/report",
        json={
            "node_id": "offer-node-001",
            "repository": "seller/offer-demo",
            "tag": "v1",
            "digest": "sha256:offer",
            "registry": "pivotcompute.store",
            "source_image": "python:3.12-alpine",
            "status": "uploaded",
        },
        headers={"Authorization": f"Bearer {node_token}"},
    )

    assert image_response.status_code == 200
    offer_list_response = client.get(
        "/api/v1/platform/image-offers",
        headers={"Authorization": f"Bearer {seller_token}"},
    )
    assert offer_list_response.status_code == 200
    offer_payload = offer_list_response.json()[0]
    assert offer_payload["offer_status"] == "active"
    assert offer_payload["current_billable_price_cny_per_hour"] is not None

    client.post(
        "/api/v1/auth/register",
        json={
            "email": "buyer-offer@example.com",
            "password": "super-secret-password",
            "display_name": "Offer Buyer",
        },
    )
    buyer_login = client.post(
        "/api/v1/auth/login",
        json={"email": "buyer-offer@example.com", "password": "super-secret-password"},
    )
    buyer_token = buyer_login.json()["access_token"]

    catalog_response = client.get(
        "/api/v1/buyer/catalog/offers",
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert catalog_response.status_code == 200
    assert offer_payload["id"] in [item["offer_id"] for item in catalog_response.json()]

    monkeypatch.setattr(
        "app.api.routes.buyer.create_runtime_session_bundle",
        lambda settings, **kwargs: {"ok": True, "runtime": {"ok": True}, "gateway": {"ok": True}},
    )
    monkeypatch.setattr(
        "app.api.routes.buyer.inspect_runtime_session_bundle",
        lambda settings, **kwargs: {
            "runtime": {
                "tasks": [{"CurrentState": "Running 1 second ago", "DesiredState": "Running"}],
                "current_task": {"CurrentState": "Running 1 second ago", "DesiredState": "Running"},
                "logs": "offer runtime started",
            },
            "gateway": {
                "tasks": [{"CurrentState": "Running 1 second ago", "DesiredState": "Running"}],
                "current_task": {"CurrentState": "Running 1 second ago", "DesiredState": "Running"},
                "logs": "",
            },
        },
    )

    create_session_response = client.post(
        "/api/v1/buyer/runtime-sessions",
        json={
            "offer_id": offer_payload["id"],
            "session_mode": "code_run",
            "source_type": "inline_code",
            "code_filename": "main.py",
            "code_content": "print('hello')",
        },
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert create_session_response.status_code == 200
    session_payload = create_session_response.json()
    assert session_payload["offer_id"] == offer_payload["id"]
    assert session_payload["seller_node_key"] == "offer-node-001"

    session_id = session_payload["session_id"]
    status_response = client.get(
        f"/api/v1/buyer/runtime-sessions/{session_id}",
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert status_response.status_code == 200
    assert status_response.json()["offer_id"] == offer_payload["id"]
    assert status_response.json()["current_hourly_price_cny"] == offer_payload["current_billable_price_cny_per_hour"]

    order_response = client.post(
        "/api/v1/buyer/orders",
        json={"offer_id": offer_payload["id"], "requested_duration_minutes": 90},
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert order_response.status_code == 200
    order_payload = order_response.json()
    assert order_payload["offer_id"] == offer_payload["id"]
    assert order_payload["order_status"] == "issued"
    assert order_payload["license_token"]

    order_list_response = client.get(
        "/api/v1/buyer/orders",
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert order_list_response.status_code == 200
    assert order_payload["id"] in [item["id"] for item in order_list_response.json()]

    redeem_response = client.post(
        "/api/v1/buyer/orders/redeem",
        json={"license_token": order_payload["license_token"]},
    )
    assert redeem_response.status_code == 200
    assert redeem_response.json()["order_id"] == order_payload["id"]
    assert redeem_response.json()["order_status"] == "redeemed"

    start_session_response = client.post(
        f"/api/v1/buyer/orders/{order_payload['id']}/start-session",
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert start_session_response.status_code == 200
    assert start_session_response.json()["order_id"] == order_payload["id"]
    assert start_session_response.json()["offer_id"] == offer_payload["id"]
    assert start_session_response.json()["gateway_port"] is not None
