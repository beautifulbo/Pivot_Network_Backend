from __future__ import annotations

import base64
import json
import subprocess
from textwrap import dedent

import paramiko

from app.core.config import Settings
from app.services.adapter_client import AdapterClientError, adapter_enabled, adapter_request


class WireGuardServerError(RuntimeError):
    pass


class _LocalClient:
    def close(self) -> None:
        return None


def _ssh_client(settings: Settings) -> paramiko.SSHClient:
    if not settings.WIREGUARD_SERVER_SSH_ENABLED:
        raise WireGuardServerError("wireguard_server_ssh_disabled")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    connect_kwargs: dict[str, object] = {
        "hostname": settings.WIREGUARD_SERVER_SSH_HOST,
        "port": settings.WIREGUARD_SERVER_SSH_PORT,
        "username": settings.WIREGUARD_SERVER_SSH_USER,
        "timeout": 20,
        "banner_timeout": 20,
        "auth_timeout": 20,
    }
    if settings.WIREGUARD_SERVER_SSH_KEY_PATH:
        connect_kwargs["key_filename"] = settings.WIREGUARD_SERVER_SSH_KEY_PATH
        if settings.WIREGUARD_SERVER_SSH_PASSWORD:
            connect_kwargs["passphrase"] = settings.WIREGUARD_SERVER_SSH_PASSWORD
    elif settings.WIREGUARD_SERVER_SSH_PASSWORD:
        connect_kwargs["password"] = settings.WIREGUARD_SERVER_SSH_PASSWORD
    else:
        raise WireGuardServerError("wireguard_server_ssh_credentials_missing")

    client.connect(**connect_kwargs)
    return client


def _exec(client: paramiko.SSHClient | _LocalClient, command: str) -> dict[str, object]:
    if isinstance(client, _LocalClient):
        try:
            result = subprocess.run(
                ["bash", "-lc", command],
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
        except FileNotFoundError as exc:
            raise WireGuardServerError("wireguard_server_local_shell_missing") from exc
        except subprocess.TimeoutExpired:
            return {
                "command": command,
                "stdout": "",
                "stderr": "wireguard_server_local_command_timed_out",
                "ok": False,
            }
        return {
            "command": command,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "ok": result.returncode == 0,
        }

    stdin, stdout, stderr = client.exec_command(command, timeout=30)
    stdout_text = stdout.read().decode("utf-8", "replace").strip()
    stderr_text = stderr.read().decode("utf-8", "replace").strip()
    return {
        "command": command,
        "stdout": stdout_text,
        "stderr": stderr_text,
        "ok": stdout.channel.recv_exit_status() == 0,
    }


def _remote_upsert_peer_command(
    *,
    config_path: str,
    public_key: str,
    allowed_ips: str,
    persistent_keepalive: int,
) -> str:
    payload = base64.b64encode(
        json.dumps(
            {
                "config_path": config_path,
                "public_key": public_key,
                "allowed_ips": allowed_ips,
                "persistent_keepalive": persistent_keepalive,
            }
        ).encode("utf-8")
    ).decode("ascii")
    script = dedent(
        """
        import base64
        import json
        from pathlib import Path

        def extract_field(block: str, field_name: str) -> str:
            prefix = f"{field_name} = "
            for line in block.splitlines():
                if line.startswith(prefix):
                    return line[len(prefix):].strip()
            return ""

        payload = json.loads(base64.b64decode("__PAYLOAD__").decode("utf-8"))
        path = Path(payload["config_path"])
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        blocks = [block.strip() for block in text.split("\\n\\n") if block.strip()]
        desired = (
            "[Peer]\\n"
            f"PublicKey = {payload['public_key']}\\n"
            f"AllowedIPs = {payload['allowed_ips']}\\n"
            f"PersistentKeepalive = {payload['persistent_keepalive']}"
        )
        replaced = False
        next_blocks = []
        removed_public_keys = []
        for block in blocks:
            if not block.startswith("[Peer]"):
                next_blocks.append(block)
                continue

            block_public_key = extract_field(block, "PublicKey")
            block_allowed_ips = extract_field(block, "AllowedIPs")

            if block_public_key == payload["public_key"]:
                if not replaced:
                    next_blocks.append(desired)
                    replaced = True
                continue

            if block_allowed_ips == payload["allowed_ips"]:
                if block_public_key:
                    removed_public_keys.append(block_public_key)
                continue

            next_blocks.append(block)
        if not replaced:
            next_blocks.append(desired)
        path.write_text("\\n\\n".join(next_blocks).rstrip() + "\\n", encoding="utf-8")
        print(json.dumps({"changed": True, "path": str(path), "removed_public_keys": removed_public_keys}))
        """
    ).replace("__PAYLOAD__", payload)
    return f"python3 - <<'PY'\n{script}\nPY"


def _runtime_remove_peer_command(interface_name: str, public_key: str) -> str:
    return (
        f"if wg show {interface_name} >/dev/null 2>&1; then "
        f"wg set {interface_name} peer '{public_key}' remove; fi"
    )


def _parse_json_stdout(result: dict[str, object]) -> dict[str, object]:
    stdout = str(result.get("stdout") or "")
    try:
        return json.loads(stdout) if stdout else {}
    except json.JSONDecodeError:
        return {}


def apply_server_peer(
    settings: Settings,
    *,
    public_key: str,
    client_address: str,
    persistent_keepalive: int,
) -> dict[str, object]:
    if adapter_enabled(settings):
        try:
            return adapter_request(
                settings,
                method="POST",
                path="/wireguard/peers/apply",
                payload={
                    "public_key": public_key,
                    "client_address": client_address,
                    "persistent_keepalive": persistent_keepalive,
                },
            )
        except AdapterClientError as exc:
            raise WireGuardServerError(f"wireguard_adapter_apply_failed: {exc}") from exc

    client: paramiko.SSHClient | _LocalClient = (
        _LocalClient() if settings.WIREGUARD_SERVER_LOCAL_MODE else _ssh_client(settings)
    )
    try:
        allowed_ips = client_address
        upsert_result = _exec(
            client,
            _remote_upsert_peer_command(
                config_path=settings.WIREGUARD_SERVER_CONFIG_PATH,
                public_key=public_key,
                allowed_ips=allowed_ips,
                persistent_keepalive=persistent_keepalive,
            ),
        )
        if not upsert_result["ok"]:
            raise WireGuardServerError(
                f"wireguard_server_config_update_failed: {upsert_result['stderr'] or upsert_result['stdout']}"
            )
        upsert_payload = _parse_json_stdout(upsert_result)
        removed_runtime_peers: list[dict[str, object]] = []
        for removed_key in upsert_payload.get("removed_public_keys", []):
            remove_result = _exec(
                client,
                _runtime_remove_peer_command(settings.WIREGUARD_SERVER_INTERFACE, str(removed_key)),
            )
            removed_runtime_peers.append(remove_result)
            if not remove_result["ok"]:
                raise WireGuardServerError(
                    f"wireguard_server_runtime_cleanup_failed: {remove_result['stderr'] or remove_result['stdout']}"
                )

        apply_result = _exec(
            client,
            (
                f"if wg show {settings.WIREGUARD_SERVER_INTERFACE} >/dev/null 2>&1; then "
                f"wg set {settings.WIREGUARD_SERVER_INTERFACE} "
                f"peer '{public_key}' allowed-ips '{allowed_ips}' persistent-keepalive {persistent_keepalive}; "
                f"else systemctl restart wg-quick@{settings.WIREGUARD_SERVER_INTERFACE}; fi"
            ),
        )
        if not apply_result["ok"]:
            raise WireGuardServerError(
                f"wireguard_server_runtime_apply_failed: {apply_result['stderr'] or apply_result['stdout']}"
            )

        inspect_result = _exec(client, f"wg show {settings.WIREGUARD_SERVER_INTERFACE}")
        return {
            "ok": True,
            "upsert_result": upsert_result,
            "removed_runtime_peers": removed_runtime_peers,
            "apply_result": apply_result,
            "inspect_result": inspect_result,
        }
    finally:
        client.close()


def remove_server_peer(settings: Settings, *, public_key: str) -> dict[str, object]:
    if adapter_enabled(settings):
        try:
            return adapter_request(
                settings,
                method="POST",
                path="/wireguard/peers/remove",
                payload={"public_key": public_key},
            )
        except AdapterClientError as exc:
            raise WireGuardServerError(f"wireguard_adapter_remove_failed: {exc}") from exc

    client: paramiko.SSHClient | _LocalClient = (
        _LocalClient() if settings.WIREGUARD_SERVER_LOCAL_MODE else _ssh_client(settings)
    )
    try:
        payload = base64.b64encode(
            json.dumps({"config_path": settings.WIREGUARD_SERVER_CONFIG_PATH, "public_key": public_key}).encode("utf-8")
        ).decode("ascii")
        cleanup_script = dedent(
            """
            python3 - <<'PY'
            import base64
            import json
            from pathlib import Path

            payload = json.loads(base64.b64decode("__PAYLOAD__").decode("utf-8"))
            path = Path(payload["config_path"])
            text = path.read_text(encoding="utf-8") if path.exists() else ""
            blocks = [block.strip() for block in text.split("\\n\\n") if block.strip()]
            kept = []
            removed = 0
            for block in blocks:
                if block.startswith("[Peer]") and f"PublicKey = {payload['public_key']}" in block:
                    removed += 1
                    continue
                kept.append(block)
            path.write_text("\\n\\n".join(kept).rstrip() + "\\n", encoding="utf-8")
            print(json.dumps({"removed": removed}))
            PY
            """
        ).replace("__PAYLOAD__", payload)
        config_result = _exec(client, cleanup_script)
        runtime_result = _exec(
            client,
            f"if wg show {settings.WIREGUARD_SERVER_INTERFACE} >/dev/null 2>&1; then wg set {settings.WIREGUARD_SERVER_INTERFACE} peer '{public_key}' remove; fi",
        )
        inspect_result = _exec(client, f"wg show {settings.WIREGUARD_SERVER_INTERFACE}")
        return {
            "ok": bool(config_result["ok"] and runtime_result["ok"]),
            "config_result": config_result,
            "runtime_result": runtime_result,
            "inspect_result": inspect_result,
        }
    finally:
        client.close()
