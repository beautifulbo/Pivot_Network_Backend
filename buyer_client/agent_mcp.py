from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server import FastMCP

DEFAULT_BUYER_SERVER_URL = "http://127.0.0.1:3857"
DEFAULT_REMOTE_WORKSPACE = "/workspace"


def _buyer_server_url(explicit: str | None = None) -> str:
    value = explicit or os.environ.get("PIVOT_BUYER_SERVER_URL") or DEFAULT_BUYER_SERVER_URL
    return value.rstrip("/")


def _default_local_id(explicit: str | None = None) -> str:
    return str(explicit or os.environ.get("PIVOT_BUYER_DEFAULT_LOCAL_ID") or "").strip()


def _default_state_dir(explicit: str | None = None) -> str:
    return str(explicit or os.environ.get("PIVOT_BUYER_STATE_DIR") or "").strip()


def _remote_workspace(explicit: str | None = None) -> str:
    return str(explicit or os.environ.get("PIVOT_BUYER_REMOTE_WORKSPACE") or DEFAULT_REMOTE_WORKSPACE).strip()


def _request_json(
    method: str,
    path: str,
    *,
    buyer_server_url: str | None = None,
    payload: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    base_url = _buyer_server_url(buyer_server_url)
    url = f"{base_url}/{path.lstrip('/')}"
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.request(
                method.upper(),
                url,
                json=payload,
                params=params,
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        return {"ok": False, "error": str(exc), "status": None, "url": url}

    try:
        data = response.json()
    except ValueError:
        data = {"raw": response.text}
    return {
        "ok": response.is_success,
        "status": response.status_code,
        "url": url,
        "data": data,
    }


def _resolved_local_id(local_id: str | None = None) -> str:
    resolved = _default_local_id(local_id)
    if not resolved:
        raise RuntimeError("missing_local_session_id")
    return resolved


def _state_payload(state_dir: str | None = None) -> dict[str, Any]:
    resolved = _default_state_dir(state_dir)
    return {"state_dir": resolved} if resolved else {}


mcp = FastMCP(
    name="buyer-runtime-agent",
    instructions=(
        "Local buyer runtime orchestration MCP server. "
        "Use it to inspect buyer sessions through the local buyer server, connect to the "
        "seller session gateway, run commands in the remote container, read logs, and move "
        "files between the local workspace and the active runtime."
    ),
)


@mcp.tool(description="Return a basic liveness payload for the local buyer runtime MCP server.")
def ping() -> dict[str, Any]:
    return {
        "status": "ok",
        "agent": "buyer-runtime-agent",
        "buyer_server_url": _buyer_server_url(),
        "default_local_id": _default_local_id(),
        "remote_workspace": _remote_workspace(),
    }


@mcp.tool(description="Read the local buyer dashboard with cached sessions, helper status, and recent activity.")
def buyer_dashboard(
    buyer_server_url: str | None = None,
    state_dir: str | None = None,
) -> dict[str, Any]:
    response = _request_json(
        "GET",
        "/api/dashboard",
        buyer_server_url=buyer_server_url,
        params=_state_payload(state_dir),
    )
    return response["data"] if response["ok"] else response


@mcp.tool(description="Read one local buyer session by local_id. If omitted, use the default session configured for this Codex run.")
def read_buyer_session(
    local_id: str | None = None,
    buyer_server_url: str | None = None,
) -> dict[str, Any]:
    response = _request_json(
        "GET",
        f"/api/runtime/sessions/{_resolved_local_id(local_id)}",
        buyer_server_url=buyer_server_url,
    )
    return response["data"] if response["ok"] else response


@mcp.tool(description="Connect the buyer session to the seller gateway and activate WireGuard when needed.")
def connect_buyer_session(
    local_id: str | None = None,
    activate_wireguard: bool = True,
    buyer_server_url: str | None = None,
    state_dir: str | None = None,
) -> dict[str, Any]:
    response = _request_json(
        "POST",
        f"/api/runtime/sessions/{_resolved_local_id(local_id)}/connect",
        buyer_server_url=buyer_server_url,
        payload={
            "activate_wireguard": bool(activate_wireguard),
            **_state_payload(state_dir),
        },
    )
    return response["data"] if response["ok"] else response


@mcp.tool(description="Run one command inside the connected buyer runtime container through the session gateway.")
def exec_buyer_runtime(
    command: str,
    local_id: str | None = None,
    buyer_server_url: str | None = None,
    state_dir: str | None = None,
) -> dict[str, Any]:
    response = _request_json(
        "POST",
        f"/api/runtime/sessions/{_resolved_local_id(local_id)}/exec",
        buyer_server_url=buyer_server_url,
        payload={
            "command": command,
            **_state_payload(state_dir),
        },
    )
    return response["data"] if response["ok"] else response


@mcp.tool(description="Read runtime logs from the seller gateway. Use tail=true to grab the latest lines.")
def read_buyer_runtime_logs(
    local_id: str | None = None,
    cursor: int = 0,
    limit: int = 200,
    tail: bool = False,
    buyer_server_url: str | None = None,
) -> dict[str, Any]:
    response = _request_json(
        "GET",
        f"/api/runtime/sessions/{_resolved_local_id(local_id)}/logs",
        buyer_server_url=buyer_server_url,
        params={
            "cursor": max(0, int(cursor)),
            "limit": max(1, int(limit)),
            "tail": bool(tail),
        },
    )
    return response["data"] if response["ok"] else response


@mcp.tool(description="Upload a local file or directory from this machine into the active runtime workspace.")
def upload_local_content_to_buyer_runtime(
    local_path: str,
    remote_path: str | None = None,
    local_id: str | None = None,
    buyer_server_url: str | None = None,
    state_dir: str | None = None,
) -> dict[str, Any]:
    response = _request_json(
        "POST",
        f"/api/runtime/sessions/{_resolved_local_id(local_id)}/files/upload",
        buyer_server_url=buyer_server_url,
        payload={
            "local_path": local_path,
            "remote_path": remote_path or _remote_workspace(),
            **_state_payload(state_dir),
        },
        timeout=120.0,
    )
    return response["data"] if response["ok"] else response


@mcp.tool(description="Download a file or directory from the runtime container back to the local machine.")
def download_buyer_runtime_content(
    remote_path: str,
    local_path: str,
    local_id: str | None = None,
    buyer_server_url: str | None = None,
    state_dir: str | None = None,
) -> dict[str, Any]:
    response = _request_json(
        "POST",
        f"/api/runtime/sessions/{_resolved_local_id(local_id)}/files/download",
        buyer_server_url=buyer_server_url,
        payload={
            "remote_path": remote_path,
            "local_path": local_path,
            **_state_payload(state_dir),
        },
        timeout=120.0,
    )
    return response["data"] if response["ok"] else response


@mcp.tool(description="Stop the active buyer runtime session after work is complete.")
def stop_buyer_session(
    local_id: str | None = None,
    buyer_server_url: str | None = None,
    state_dir: str | None = None,
) -> dict[str, Any]:
    response = _request_json(
        "POST",
        f"/api/runtime/sessions/{_resolved_local_id(local_id)}/stop",
        buyer_server_url=buyer_server_url,
        payload=_state_payload(state_dir),
        timeout=60.0,
    )
    return response["data"] if response["ok"] else response


if __name__ == "__main__":
    mcp.run()
