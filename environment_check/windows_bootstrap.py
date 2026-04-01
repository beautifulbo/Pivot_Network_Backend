from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import paramiko

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seller_client.installer import bootstrap_client

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / ".cache" / "environment_check"


def repo_root() -> Path:
    return REPO_ROOT


def install_windows_command() -> str:
    return f'powershell -ExecutionPolicy Bypass -File "{repo_root() / "environment_check" / "install_windows.ps1"}" -Apply'


def load_dotenv_file(path: Path | None = None) -> dict[str, str]:
    env_path = path or (repo_root() / ".env")
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


@dataclass
class RemoteWireGuardSettings:
    host: str
    port: int
    user: str
    password: str
    key_path: str
    interface_name: str
    config_path: str
    endpoint_host: str
    endpoint_port: int


def resolve_remote_wireguard_settings(
    *,
    host: str = "",
    port: int | None = None,
    user: str = "",
    password: str = "",
    key_path: str = "",
    interface_name: str = "",
    config_path: str = "",
    endpoint_host: str = "",
    endpoint_port: int | None = None,
    env_path: Path | None = None,
) -> RemoteWireGuardSettings:
    dotenv = load_dotenv_file(env_path)
    merged = {**dotenv, **{key: value for key, value in os.environ.items() if key.startswith("WIREGUARD_") or key.startswith("SWARM_")}}

    resolved_port = int(port or merged.get("WIREGUARD_SERVER_SSH_PORT") or 22)
    resolved_endpoint_port = int(endpoint_port or merged.get("WIREGUARD_ENDPOINT_PORT") or 0)
    resolved = RemoteWireGuardSettings(
        host=(host or merged.get("WIREGUARD_SERVER_SSH_HOST") or "").strip(),
        port=resolved_port,
        user=(user or merged.get("WIREGUARD_SERVER_SSH_USER") or "").strip(),
        password=password or merged.get("WIREGUARD_SERVER_SSH_PASSWORD") or "",
        key_path=(key_path or merged.get("WIREGUARD_SERVER_SSH_KEY_PATH") or "").strip(),
        interface_name=(interface_name or merged.get("WIREGUARD_SERVER_INTERFACE") or "wg0").strip() or "wg0",
        config_path=(config_path or merged.get("WIREGUARD_SERVER_CONFIG_PATH") or "/etc/wireguard/wg0.conf").strip()
        or "/etc/wireguard/wg0.conf",
        endpoint_host=(endpoint_host or merged.get("WIREGUARD_ENDPOINT_HOST") or merged.get("SWARM_MANAGER_HOST") or host or "").strip(),
        endpoint_port=resolved_endpoint_port,
    )
    return resolved


def _remote_settings_payload(settings: RemoteWireGuardSettings) -> dict[str, Any]:
    return {
        "host": settings.host,
        "port": settings.port,
        "user": settings.user,
        "password_configured": bool(settings.password),
        "key_path_configured": bool(settings.key_path),
        "interface_name": settings.interface_name,
        "config_path": settings.config_path,
        "endpoint_host": settings.endpoint_host,
        "endpoint_port": settings.endpoint_port,
    }


def _remote_exec(client: paramiko.SSHClient, command: str, *, timeout: int = 30) -> dict[str, Any]:
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    stdout_text = stdout.read().decode("utf-8", "replace").strip()
    stderr_text = stderr.read().decode("utf-8", "replace").strip()
    return {
        "ok": stdout.channel.recv_exit_status() == 0,
        "command": command,
        "stdout": stdout_text,
        "stderr": stderr_text,
    }


def _connect_remote_wireguard_server(settings: RemoteWireGuardSettings) -> paramiko.SSHClient:
    if not settings.host or not settings.user:
        raise RuntimeError("remote_wireguard_server_host_or_user_missing")
    if not settings.password and not settings.key_path:
        raise RuntimeError("remote_wireguard_server_credentials_missing")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kwargs: dict[str, Any] = {
        "hostname": settings.host,
        "port": settings.port,
        "username": settings.user,
        "timeout": 20,
        "banner_timeout": 20,
        "auth_timeout": 20,
    }
    if settings.key_path:
        kwargs["key_filename"] = settings.key_path
        if settings.password:
            kwargs["passphrase"] = settings.password
    else:
        kwargs["password"] = settings.password
    client.connect(**kwargs)
    return client


def _parse_swarm_stdout(stdout: str) -> dict[str, Any]:
    try:
        payload = json.loads(stdout) if stdout else {}
    except json.JSONDecodeError:
        return {}
    cluster = payload.get("Cluster") or {}
    return {
        "state": payload.get("LocalNodeState"),
        "node_addr": payload.get("NodeAddr"),
        "control_available": bool(payload.get("ControlAvailable")),
        "nodes": payload.get("Nodes"),
        "managers": payload.get("Managers"),
        "cluster_id": cluster.get("ID"),
    }


def check_remote_wireguard_server(
    settings: RemoteWireGuardSettings,
    *,
    ensure_up: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "settings": _remote_settings_payload(settings),
    }
    try:
        client = _connect_remote_wireguard_server(settings)
    except Exception as exc:  # noqa: BLE001
        payload["error"] = str(exc)
        return payload

    try:
        service_name = f"wg-quick@{settings.interface_name}"
        ensure_result = None
        if ensure_up:
            ensure_result = _remote_exec(client, f"systemctl enable --now {service_name}", timeout=60)

        hostname_result = _remote_exec(client, "hostname")
        enabled_result = _remote_exec(client, f"systemctl is-enabled {service_name} || true")
        active_result = _remote_exec(client, f"systemctl is-active {service_name} || true")
        interface_result = _remote_exec(client, f"ip -4 addr show {settings.interface_name} || true")
        wg_dump_result = _remote_exec(client, f"wg show {settings.interface_name} dump || true")
        service_status_result = _remote_exec(client, f"systemctl status {service_name} --no-pager --full | sed -n '1,40p' || true", timeout=60)
        udp_listener_result = _remote_exec(client, f"ss -lunp | grep -F ':{settings.endpoint_port}' || true" if settings.endpoint_port else "true")
        swarm_result = _remote_exec(client, "docker info --format '{{json .Swarm}}' || true")

        wg_lines = [line for line in (wg_dump_result.get("stdout") or "").splitlines() if line.strip()]
        peer_count = max(0, len(wg_lines) - 1)
        interface_has_ipv4 = f"inet " in str(interface_result.get("stdout") or "")
        service_active = str(active_result.get("stdout") or "").strip() == "active"
        service_enabled = str(enabled_result.get("stdout") or "").strip() == "enabled"
        endpoint_listening = True
        if settings.endpoint_port:
            endpoint_listening = f":{settings.endpoint_port}" in str(udp_listener_result.get("stdout") or "")

        payload.update(
            {
                "ok": service_active and interface_has_ipv4 and endpoint_listening,
                "server_uses_wireguard": service_active and interface_has_ipv4,
                "hostname": str(hostname_result.get("stdout") or "").strip(),
                "service_name": service_name,
                "service_enabled": service_enabled,
                "service_active": service_active,
                "interface_has_ipv4": interface_has_ipv4,
                "peer_count": peer_count,
                "ensure_result": ensure_result,
                "hostname_result": hostname_result,
                "enabled_result": enabled_result,
                "active_result": active_result,
                "interface_result": interface_result,
                "wg_dump_result": wg_dump_result,
                "service_status_result": service_status_result,
                "udp_listener_result": udp_listener_result,
                "swarm_result": swarm_result,
                "swarm": _parse_swarm_stdout(str(swarm_result.get("stdout") or "")),
            }
        )
        if not payload["ok"]:
            payload["error"] = "remote_wireguard_server_not_ready"
        return payload
    finally:
        client.close()


def _local_runtime_ready(result: dict[str, Any]) -> bool:
    blocking_flags = (
        "needs_codex_install",
        "needs_codex_mcp_attach",
        "needs_docker_setup",
        "needs_wireguard_setup",
        "needs_windows_wireguard_helper",
        "needs_windows_gateway_bridge",
        "needs_windows_gateway_firewall",
    )
    return not any(bool(result.get(flag)) for flag in blocking_flags)


def _local_summary(result: dict[str, Any]) -> dict[str, Any]:
    codex_mcp_servers = dict(result.get("codex_mcp_servers") or {})
    needs_codex_install = bool(result.get("needs_codex_install"))
    needs_codex_mcp_attach = bool(result.get("needs_codex_mcp_attach"))
    codex_ready = bool(not needs_codex_install and not needs_codex_mcp_attach)
    return {
        "runtime_ready": _local_runtime_ready(result),
        "codex_ready": codex_ready,
        "codex_cli_ready": bool(result.get("codex_installed")),
        "codex_config_path": result.get("codex_config_path") or "",
        "seller_codex_mcp_attached": bool(codex_mcp_servers.get("sellerNodeAgent")),
        "buyer_codex_mcp_attached": bool(codex_mcp_servers.get("buyerRuntimeAgent")),
        "needs_codex_install": needs_codex_install,
        "needs_codex_mcp_attach": needs_codex_mcp_attach,
        "codex_install_hint": (
            "Install Codex CLI first, then rerun environment_check."
            if needs_codex_install
            else ""
        ),
        "codex_mcp_hint": (
            "Run the Windows apply command once so sellerNodeAgent and buyerRuntimeAgent are attached to local Codex."
            if needs_codex_mcp_attach
            else ""
        ),
        "needs_docker_setup": bool(result.get("needs_docker_setup")),
        "needs_wireguard_setup": bool(result.get("needs_wireguard_setup")),
        "needs_windows_wireguard_helper": bool(result.get("needs_windows_wireguard_helper")),
        "needs_windows_gateway_bridge": bool(result.get("needs_windows_gateway_bridge")),
        "needs_windows_gateway_firewall": bool(result.get("needs_windows_gateway_firewall")),
        "windows_apply_command": result.get("windows_apply_command") or install_windows_command(),
    }


def _write_report(result: dict[str, Any], output_path: Path) -> str:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(output_path)


def bootstrap_windows_environment(
    *,
    apply: bool = False,
    state_dir: str | None = None,
    skip_remote_check: bool = False,
    remote_ensure_up: bool = False,
    remote_host: str = "",
    remote_port: int | None = None,
    remote_user: str = "",
    remote_password: str = "",
    remote_key_path: str = "",
    remote_interface: str = "",
    remote_config_path: str = "",
    remote_endpoint_host: str = "",
    remote_endpoint_port: int | None = None,
    report_path: str | None = None,
) -> dict[str, Any]:
    local_apply = bootstrap_client(dry_run=not apply, state_dir=state_dir)
    local_verify = bootstrap_client(dry_run=True, state_dir=state_dir) if apply else local_apply
    remote_settings = resolve_remote_wireguard_settings(
        host=remote_host,
        port=remote_port,
        user=remote_user,
        password=remote_password,
        key_path=remote_key_path,
        interface_name=remote_interface,
        config_path=remote_config_path,
        endpoint_host=remote_endpoint_host,
        endpoint_port=remote_endpoint_port,
    )
    remote_result = (
        {"ok": True, "skipped": True, "reason": "remote_check_skipped", "settings": _remote_settings_payload(remote_settings)}
        if skip_remote_check
        else check_remote_wireguard_server(remote_settings, ensure_up=remote_ensure_up)
    )
    result = {
        "ok": bool(_local_runtime_ready(local_verify) and remote_result.get("ok")),
        "requested_apply": apply,
        "repo_root": str(repo_root()),
        "recommended_install_command": install_windows_command(),
        "local_apply": local_apply,
        "local_verification": local_verify,
        "local_summary": _local_summary(local_verify),
        "remote_wireguard": remote_result,
    }
    output_file = Path(report_path).expanduser().resolve() if report_path else (DEFAULT_OUTPUT_DIR / "latest.json")
    result["report_path"] = _write_report(result, output_file)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap and verify the local Windows environment for Pivot runtime access.")
    parser.add_argument("--state-dir", default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--skip-remote-check", action="store_true")
    parser.add_argument("--remote-ensure-up", action="store_true")
    parser.add_argument("--remote-host", default="")
    parser.add_argument("--remote-port", type=int, default=None)
    parser.add_argument("--remote-user", default="")
    parser.add_argument("--remote-password", default="")
    parser.add_argument("--remote-key-path", default="")
    parser.add_argument("--remote-interface", default="")
    parser.add_argument("--remote-config-path", default="")
    parser.add_argument("--remote-endpoint-host", default="")
    parser.add_argument("--remote-endpoint-port", type=int, default=None)
    parser.add_argument("--report-path", default=None)
    args = parser.parse_args()

    result = bootstrap_windows_environment(
        apply=args.apply,
        state_dir=args.state_dir,
        skip_remote_check=args.skip_remote_check,
        remote_ensure_up=args.remote_ensure_up,
        remote_host=args.remote_host,
        remote_port=args.remote_port,
        remote_user=args.remote_user,
        remote_password=args.remote_password,
        remote_key_path=args.remote_key_path,
        remote_interface=args.remote_interface,
        remote_config_path=args.remote_config_path,
        remote_endpoint_host=args.remote_endpoint_host,
        remote_endpoint_port=args.remote_endpoint_port,
        report_path=args.report_path,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
