from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE_DIR = REPO_ROOT / ".cache" / "seller-gateway-bridge"
SCAN_INTERVAL_SECONDS = 2.0


@dataclass
class ManagedGatewayHost:
    session_id: int
    gateway_port: int
    container_id: str
    runtime_service_name: str
    session_token: str
    process: subprocess.Popen[bytes]
    log_path: Path


def _run_command(command: list[str], *, timeout: float = 30.0) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def _decode_bytes(raw: bytes) -> str:
    return raw.decode("utf-8", "replace")


def _env_map(inspect_payload: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in (inspect_payload.get("Config", {}) or {}).get("Env", []) or []:
        key, _, value = str(item).partition("=")
        if key:
            values[key] = value
    return values


def extract_gateway_session_metadata(inspect_payload: dict[str, Any]) -> dict[str, Any] | None:
    env = _env_map(inspect_payload)
    session_id = str(env.get("PIVOT_SESSION_ID") or "").strip()
    runtime_service_name = str(env.get("PIVOT_RUNTIME_SERVICE_NAME") or "").strip()
    session_token = str(env.get("PIVOT_SESSION_TOKEN") or "").strip()
    gateway_port = str(env.get("PIVOT_GATEWAY_PORT") or "").strip()
    if not session_id or not runtime_service_name or not session_token or not gateway_port:
        return None
    try:
        session_id_value = int(session_id)
        gateway_port_value = int(gateway_port)
    except ValueError:
        return None
    supported_features = [
        item.strip()
        for item in str(env.get("PIVOT_SUPPORTED_FEATURES") or "exec,logs,shell,files").split(",")
        if item.strip()
    ]
    return {
        "session_id": session_id_value,
        "gateway_port": gateway_port_value,
        "container_id": str(inspect_payload.get("Id") or ""),
        "runtime_service_name": runtime_service_name,
        "gateway_service_name": str(env.get("PIVOT_GATEWAY_SERVICE_NAME") or f"gateway-{session_id_value}"),
        "buyer_user_id": str(env.get("PIVOT_BUYER_USER_ID") or ""),
        "seller_node_id": str(env.get("PIVOT_SELLER_NODE_ID") or ""),
        "session_token": session_token,
        "supported_features": supported_features,
    }


def discover_gateway_sessions() -> dict[int, dict[str, Any]]:
    ps_result = _run_command(["docker", "ps", "--format", "{{.ID}} {{.Names}}"], timeout=20.0)
    if ps_result.returncode != 0:
        return {}
    container_ids: list[str] = []
    for line in _decode_bytes(ps_result.stdout).splitlines():
        container_id, _, name = line.strip().partition(" ")
        if container_id and name.startswith("gateway-"):
            container_ids.append(container_id)
    if not container_ids:
        return {}
    inspect_result = _run_command(["docker", "inspect", *container_ids], timeout=30.0)
    if inspect_result.returncode != 0:
        return {}
    try:
        payload = json.loads(_decode_bytes(inspect_result.stdout))
    except json.JSONDecodeError:
        return {}
    sessions: dict[int, dict[str, Any]] = {}
    for item in payload:
        metadata = extract_gateway_session_metadata(item)
        if metadata is not None:
            sessions[int(metadata["session_id"])] = metadata
    return sessions


def _spawn_gateway_host(metadata: dict[str, Any], *, state_dir: Path, bind_host: str) -> ManagedGatewayHost:
    state_dir.mkdir(parents=True, exist_ok=True)
    log_path = state_dir / f"gateway-{metadata['session_id']}.log"
    log_handle = log_path.open("ab")
    env = os.environ.copy()
    env.update(
        {
            "PIVOT_SESSION_ID": str(metadata["session_id"]),
            "PIVOT_GATEWAY_PORT": str(metadata["gateway_port"]),
            "PIVOT_RUNTIME_SERVICE_NAME": str(metadata["runtime_service_name"]),
            "PIVOT_GATEWAY_SERVICE_NAME": str(metadata["gateway_service_name"]),
            "PIVOT_SESSION_TOKEN": str(metadata["session_token"]),
            "PIVOT_SUPPORTED_FEATURES": ",".join(metadata.get("supported_features") or []),
            "PIVOT_BUYER_USER_ID": str(metadata.get("buyer_user_id") or ""),
            "PIVOT_SELLER_NODE_ID": str(metadata.get("seller_node_id") or ""),
            "PIVOT_LISTEN_HOST": bind_host,
        }
    )
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        [sys.executable, "-m", "seller_client.windows_session_gateway_host"],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )
    return ManagedGatewayHost(
        session_id=int(metadata["session_id"]),
        gateway_port=int(metadata["gateway_port"]),
        container_id=str(metadata["container_id"]),
        runtime_service_name=str(metadata["runtime_service_name"]),
        session_token=str(metadata["session_token"]),
        process=process,
        log_path=log_path,
    )


def _stop_gateway_host(managed: ManagedGatewayHost) -> None:
    if managed.process.poll() is None:
        managed.process.terminate()
        try:
            managed.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            managed.process.kill()
            managed.process.wait(timeout=3)


def main() -> None:
    state_dir = Path(os.environ.get("PIVOT_GATEWAY_BRIDGE_STATE_DIR") or DEFAULT_STATE_DIR).expanduser().resolve()
    bind_host = os.environ.get("PIVOT_GATEWAY_BIND_HOST", "127.0.0.1").strip() or "127.0.0.1"
    managed_hosts: dict[int, ManagedGatewayHost] = {}
    running = True

    def _handle_signal(signum: int, _frame: Any) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    while running:
        active = discover_gateway_sessions()

        for session_id, metadata in active.items():
            existing = managed_hosts.get(session_id)
            if existing and existing.process.poll() is None and existing.container_id == metadata["container_id"]:
                continue
            if existing:
                _stop_gateway_host(existing)
            managed_hosts[session_id] = _spawn_gateway_host(metadata, state_dir=state_dir, bind_host=bind_host)

        for session_id in list(managed_hosts):
            if session_id in active:
                continue
            _stop_gateway_host(managed_hosts.pop(session_id))

        time.sleep(SCAN_INTERVAL_SECONDS)

    for managed in list(managed_hosts.values()):
        _stop_gateway_host(managed)


if __name__ == "__main__":
    main()
