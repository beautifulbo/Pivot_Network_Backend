from fastapi.testclient import TestClient


def _register_and_login(client: TestClient, *, email: str, display_name: str) -> str:
    client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "super-secret-password",
            "display_name": display_name,
        },
    )
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "super-secret-password"},
    )
    return login_response.json()["access_token"]


def test_buyer_payment_topup_flow_and_idempotent_confirm(client: TestClient) -> None:
    buyer_token = _register_and_login(
        client,
        email="buyer-payments@example.com",
        display_name="Buyer Payments",
    )

    wallet_before = client.get(
        "/api/v1/buyer/wallet",
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert wallet_before.status_code == 200
    assert wallet_before.json()["balance_cny_credits"] == 100.0

    create_response = client.post(
        "/api/v1/buyer/payments",
        json={"amount_cny": 25.5, "channel": "manual", "subject": "Top up wallet"},
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert create_response.status_code == 201
    payment_payload = create_response.json()
    assert payment_payload["status"] == "pending"
    assert payment_payload["amount_cny"] == 25.5

    list_response = client.get(
        "/api/v1/buyer/payments",
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert list_response.status_code == 200
    assert payment_payload["id"] in [item["id"] for item in list_response.json()]

    read_response = client.get(
        f"/api/v1/buyer/payments/{payment_payload['id']}",
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert read_response.status_code == 200
    assert read_response.json()["status"] == "pending"

    confirm_response = client.post(
        f"/api/v1/buyer/payments/{payment_payload['id']}/confirm",
        json={"status": "succeeded", "third_party_txn_id": "txn-topup-001"},
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert confirm_response.status_code == 200
    confirmed = confirm_response.json()
    assert confirmed["status"] == "succeeded"
    assert confirmed["third_party_txn_id"] == "txn-topup-001"
    assert confirmed["latest_ledger_entry"]["entry_type"] == "topup_credit"
    assert confirmed["latest_ledger_entry"]["payment_order_id"] == payment_payload["id"]

    wallet_after = client.get(
        "/api/v1/buyer/wallet",
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert wallet_after.status_code == 200
    assert wallet_after.json()["balance_cny_credits"] == 125.5

    repeat_confirm_response = client.post(
        f"/api/v1/buyer/payments/{payment_payload['id']}/confirm",
        json={"status": "succeeded", "third_party_txn_id": "txn-topup-001"},
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert repeat_confirm_response.status_code == 200

    wallet_after_repeat = client.get(
        "/api/v1/buyer/wallet",
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert wallet_after_repeat.status_code == 200
    assert wallet_after_repeat.json()["balance_cny_credits"] == 125.5

    ledger_response = client.get(
        "/api/v1/buyer/wallet/ledger",
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert ledger_response.status_code == 200
    assert ledger_response.json()[0]["entry_type"] == "topup_credit"


def test_failed_payment_does_not_credit_wallet_and_isolation_is_enforced(client: TestClient) -> None:
    buyer_one_token = _register_and_login(
        client,
        email="buyer-payments-1@example.com",
        display_name="Buyer Payments One",
    )
    buyer_two_token = _register_and_login(
        client,
        email="buyer-payments-2@example.com",
        display_name="Buyer Payments Two",
    )

    create_response = client.post(
        "/api/v1/buyer/payments",
        json={"amount_cny": 40, "channel": "manual", "subject": "Top up wallet"},
        headers={"Authorization": f"Bearer {buyer_one_token}"},
    )
    assert create_response.status_code == 201
    payment_id = create_response.json()["id"]

    forbidden_read = client.get(
        f"/api/v1/buyer/payments/{payment_id}",
        headers={"Authorization": f"Bearer {buyer_two_token}"},
    )
    assert forbidden_read.status_code == 404

    forbidden_confirm = client.post(
        f"/api/v1/buyer/payments/{payment_id}/confirm",
        json={"status": "succeeded"},
        headers={"Authorization": f"Bearer {buyer_two_token}"},
    )
    assert forbidden_confirm.status_code == 404

    failed_confirm = client.post(
        f"/api/v1/buyer/payments/{payment_id}/confirm",
        json={"status": "failed"},
        headers={"Authorization": f"Bearer {buyer_one_token}"},
    )
    assert failed_confirm.status_code == 200
    assert failed_confirm.json()["status"] == "failed"
    assert failed_confirm.json()["latest_ledger_entry"] is None

    wallet_response = client.get(
        "/api/v1/buyer/wallet",
        headers={"Authorization": f"Bearer {buyer_one_token}"},
    )
    assert wallet_response.status_code == 200
    assert wallet_response.json()["balance_cny_credits"] == 100.0


def test_openapi_contains_legacy_and_new_payment_paths(client: TestClient) -> None:
    response = client.get("/api/v1/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/buyer/wallet" in paths
    assert "/api/v1/buyer/orders" in paths
    assert "/api/v1/buyer/runtime-sessions" in paths
    assert "/api/v1/buyer/payments" in paths
    assert "/api/v1/buyer/payments/{payment_id}" in paths
    assert "/api/v1/buyer/payments/{payment_id}/confirm" in paths
