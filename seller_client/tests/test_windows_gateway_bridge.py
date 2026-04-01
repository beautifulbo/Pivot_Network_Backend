from seller_client.windows_gateway_bridge_manager import extract_gateway_session_metadata


def test_extract_gateway_session_metadata_reads_env_payload() -> None:
    payload = {
        "Id": "container-123",
        "Config": {
            "Env": [
                "PIVOT_SESSION_ID=42",
                "PIVOT_GATEWAY_PORT=20042",
                "PIVOT_RUNTIME_SERVICE_NAME=runtime-42",
                "PIVOT_GATEWAY_SERVICE_NAME=gateway-42",
                "PIVOT_SESSION_TOKEN=secret-token",
                "PIVOT_SUPPORTED_FEATURES=exec,logs,shell,files",
                "PIVOT_BUYER_USER_ID=2",
                "PIVOT_SELLER_NODE_ID=5",
            ]
        },
    }

    assert extract_gateway_session_metadata(payload) == {
        "session_id": 42,
        "gateway_port": 20042,
        "container_id": "container-123",
        "runtime_service_name": "runtime-42",
        "gateway_service_name": "gateway-42",
        "buyer_user_id": "2",
        "seller_node_id": "5",
        "session_token": "secret-token",
        "supported_features": ["exec", "logs", "shell", "files"],
    }


def test_extract_gateway_session_metadata_returns_none_for_missing_required_fields() -> None:
    assert extract_gateway_session_metadata({"Config": {"Env": ["PIVOT_SESSION_ID=42"]}}) is None
