from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seller_client.agent_mcp import _default_state_dir, _ensure_client_dirs, environment_check
from seller_client.windows_elevation import (
    current_user_task_identity,
    is_windows_platform,
    session_gateway_bridge_launcher_path,
    session_gateway_bridge_root,
    session_gateway_bridge_task_name,
    wireguard_helper_create_task_command,
    wireguard_helper_launcher_path,
    wireguard_helper_query_task_command,
    wireguard_helper_request_path,
    wireguard_helper_result_path,
    wireguard_helper_root,
    wireguard_helper_script_path,
    wireguard_helper_task_command,
    wireguard_helper_task_name,
    windows_is_elevated,
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def codex_config_path() -> Path:
    return Path.home() / ".codex" / "config.toml"


def codex_server_name() -> str:
    return "sellerNodeAgent"


def buyer_codex_server_name() -> str:
    return "buyerRuntimeAgent"


def _toml_basic_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _normalized_path(value: str) -> str:
    if is_windows_platform():
        return value.replace("\\", "/")
    return value


def _desired_mcp_block(server_name: str, relative_agent_path: str) -> str:
    python_exe = _normalized_path(shutil.which("python") or sys.executable)
    agent_path = repo_root() / relative_agent_path
    cwd_path = repo_root()
    return (
        f"\n[mcp_servers.{server_name}]\n"
        f"command = {_toml_basic_string(python_exe)}\n"
        f"args = [{_toml_basic_string(agent_path.as_posix())}]\n"
        f"cwd = {_toml_basic_string(cwd_path.as_posix())}\n"
    )


def desired_mcp_block() -> str:
    return _desired_mcp_block(codex_server_name(), "seller_client/agent_mcp.py")


def desired_buyer_mcp_block() -> str:
    return _desired_mcp_block(buyer_codex_server_name(), "buyer_client/agent_mcp.py")


def desired_mcp_blocks() -> list[tuple[str, str]]:
    return [
        (codex_server_name(), desired_mcp_block()),
        (buyer_codex_server_name(), desired_buyer_mcp_block()),
    ]


def codex_installed() -> bool:
    return shutil.which("codex") is not None


def _run_command(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "ok": completed.returncode == 0,
    }


def _run_powershell(script: str) -> dict[str, Any]:
    return _run_command(["powershell", "-NoProfile", "-Command", script])


def environment_check_windows_apply_command() -> str:
    return f'powershell -ExecutionPolicy Bypass -File "{repo_root() / "environment_check" / "install_windows.ps1"}" -Apply'


def windows_wireguard_helper_task_installed() -> bool:
    if not is_windows_platform():
        return False
    query = _run_powershell(
        (
            "$ErrorActionPreference='Stop'; "
            f"Get-ScheduledTask -TaskName '{wireguard_helper_task_name()}' | Out-Null; "
            "Write-Output 'INSTALLED'"
        )
    )
    return bool(query["ok"])


def ensure_windows_wireguard_helper_task(dry_run: bool = False) -> dict[str, Any]:
    if not is_windows_platform():
        return {"ok": True, "skipped": True, "reason": "not_windows"}

    helper_root = wireguard_helper_root()
    helper_root.mkdir(parents=True, exist_ok=True)
    python_exe = shutil.which("python") or sys.executable
    launcher_path = wireguard_helper_launcher_path()
    launcher_text = (
        "@echo off\r\n"
        f'"{python_exe}" "{wireguard_helper_script_path()}" '
        f'--request-file "{wireguard_helper_request_path()}" '
        f'--result-file "{wireguard_helper_result_path()}"\r\n'
    )
    if not dry_run:
        launcher_path.write_text(launcher_text, encoding="utf-8")
    task_exists = windows_wireguard_helper_task_installed()
    elevated = windows_is_elevated()
    if task_exists and (dry_run or not elevated):
        return {
            "ok": True,
            "changed": False,
            "task_name": wireguard_helper_task_name(),
            "launcher_path": str(launcher_path),
            "request_path": str(wireguard_helper_request_path()),
            "result_path": str(wireguard_helper_result_path()),
        }

    payload = {
        "task_name": wireguard_helper_task_name(),
        "task_command": wireguard_helper_task_command(),
        "launcher_path": str(launcher_path),
        "request_path": str(wireguard_helper_request_path()),
        "result_path": str(wireguard_helper_result_path()),
        "admin_required": True,
        "elevated": elevated,
        "force_recreate": bool(task_exists and elevated and not dry_run),
    }
    if dry_run:
        return {"ok": True, "changed": True, "dry_run": True, **payload}

    delete_result = None
    if task_exists:
        delete_result = _run_powershell(
            (
                "$ErrorActionPreference='SilentlyContinue'; "
                f"Unregister-ScheduledTask -TaskName '{wireguard_helper_task_name()}' -Confirm:$false -ErrorAction SilentlyContinue; "
                "Write-Output 'REMOVED'"
            )
        )
    create_script = (
        "$ErrorActionPreference='Stop'; "
        f"$action = New-ScheduledTaskAction -Execute '{launcher_path}'; "
        "$trigger = New-ScheduledTaskTrigger -Once -At ([datetime]'2000-01-01T23:59:00'); "
        f"$principal = New-ScheduledTaskPrincipal -UserId '{current_user_task_identity()}' "
        "-LogonType Interactive -RunLevel Highest; "
        f"Register-ScheduledTask -TaskName '{wireguard_helper_task_name()}' "
        "-Action $action -Trigger $trigger -Principal $principal -Force | Out-Null; "
        "Write-Output 'REGISTERED'"
    )
    create_result = _run_powershell(create_script)
    return {
        "ok": bool(create_result["ok"]),
        "changed": bool(create_result["ok"]),
        "delete_result": delete_result,
        "create_result": create_result,
        **payload,
    }


def _windows_task_installed(task_name: str) -> bool:
    query = _run_powershell(
        (
            "$ErrorActionPreference='SilentlyContinue'; "
            f"Get-ScheduledTask -TaskName '{task_name}' -ErrorAction SilentlyContinue | Out-Null; "
            "if ($?) { 'INSTALLED' }"
        )
    )
    return bool(query["ok"])


def _windows_task_info(task_name: str) -> dict[str, Any]:
    query = _run_powershell(
        (
            "$ErrorActionPreference='SilentlyContinue'; "
            f"$task = Get-ScheduledTask -TaskName '{task_name}' -ErrorAction SilentlyContinue; "
            f"if (-not $task) {{ Write-Output '{{\"ok\":false,\"task_name\":\"{task_name}\",\"installed\":false}}'; exit 0 }}; "
            f"$info = Get-ScheduledTaskInfo -TaskName '{task_name}' -ErrorAction SilentlyContinue; "
            "[pscustomobject]@{"
            "ok = $true; "
            f"task_name = '{task_name}'; "
            "installed = $true; "
            "state = [string]$info.State; "
            "} | ConvertTo-Json -Compress"
        )
    )
    if not query["ok"]:
        return {"ok": False, "task_name": task_name, "installed": False, "query_result": query}
    try:
        payload = json.loads(query["stdout"] or "{}")
    except json.JSONDecodeError:
        payload = {"ok": False, "task_name": task_name, "installed": False, "raw": query["stdout"]}
    payload["query_result"] = query
    return payload


def _start_windows_task(task_name: str) -> dict[str, Any]:
    info = _windows_task_info(task_name)
    if not info.get("installed"):
        return {"ok": False, "task_name": task_name, "reason": "task_not_installed", "task_info": info}
    if str(info.get("state") or "").lower() == "running":
        return {"ok": True, "task_name": task_name, "already_running": True, "task_info": info}
    start_result = _run_powershell(
        (
            "$ErrorActionPreference='Stop'; "
            f"Start-ScheduledTask -TaskName '{task_name}'; "
            "Start-Sleep -Milliseconds 800; "
            "Write-Output 'STARTED'"
        )
    )
    task_info = _windows_task_info(task_name)
    return {
        "ok": bool(start_result["ok"]),
        "task_name": task_name,
        "start_result": start_result,
        "task_info": task_info,
    }


def ensure_windows_gateway_bridge_task(dry_run: bool = False) -> dict[str, Any]:
    if not is_windows_platform():
        return {"ok": True, "skipped": True, "reason": "not_windows"}

    bridge_root = session_gateway_bridge_root()
    bridge_root.mkdir(parents=True, exist_ok=True)
    launcher_path = session_gateway_bridge_launcher_path()
    python_exe = shutil.which("python") or sys.executable
    launcher_text = (
        "@echo off\r\n"
        f'cd /d "{repo_root()}"\r\n'
        f'"{python_exe}" -m seller_client.windows_gateway_bridge_manager\r\n'
    )
    if not dry_run:
        launcher_path.write_text(launcher_text, encoding="utf-8")

    task_name = session_gateway_bridge_task_name()
    task_exists = _windows_task_installed(task_name)
    payload = {
        "task_name": task_name,
        "launcher_path": str(launcher_path),
        "task_command": f'"{launcher_path}"',
        "state_dir": str(bridge_root),
    }
    if task_exists:
        if dry_run:
            return {"ok": True, "changed": False, **payload}
        start_result = _start_windows_task(task_name)
        return {"ok": True, "changed": False, "start_result": start_result, **payload}
    if dry_run:
        return {"ok": True, "changed": True, "dry_run": True, **payload}

    create_script = (
        "$ErrorActionPreference='Stop'; "
        f"$action = New-ScheduledTaskAction -Execute '{launcher_path}'; "
        "$trigger = New-ScheduledTaskTrigger -AtLogOn; "
        f"$principal = New-ScheduledTaskPrincipal -UserId '{current_user_task_identity()}' -LogonType Interactive; "
        f"Register-ScheduledTask -TaskName '{task_name}' "
        "-Action $action -Trigger $trigger -Principal $principal -Force | Out-Null; "
        "Write-Output 'REGISTERED'"
    )
    create_result = _run_powershell(create_script)
    start_result = _start_windows_task(task_name) if create_result["ok"] else None
    return {
        "ok": bool(create_result["ok"]),
        "changed": bool(create_result["ok"]),
        "create_result": create_result,
        "start_result": start_result,
        **payload,
    }


def ensure_windows_gateway_firewall_rule(dry_run: bool = False) -> dict[str, Any]:
    if not is_windows_platform():
        return {"ok": True, "skipped": True, "reason": "not_windows"}

    rule_name = "PivotSellerSessionGatewayTCP"
    query_script = (
        "$ErrorActionPreference='SilentlyContinue'; "
        f"$rule = Get-NetFirewallRule -DisplayName '{rule_name}' -ErrorAction SilentlyContinue; "
        "if ($rule) { 'INSTALLED' } else { 'MISSING' }"
    )
    query_result = _run_powershell(query_script)
    exists = "INSTALLED" in str(query_result.get("stdout") or "")
    payload = {
        "rule_name": rule_name,
        "local_ports": "20000-65535",
        "remote_address": "10.66.66.0/24",
        "interface_alias": "wg-seller",
    }
    if exists:
        return {"ok": True, "changed": False, "query_result": query_result, **payload}
    if dry_run:
        return {"ok": True, "changed": True, "dry_run": True, "query_result": query_result, **payload}

    create_script = (
        "$ErrorActionPreference='Stop'; "
        f"New-NetFirewallRule -DisplayName '{rule_name}' "
        "-Direction Inbound -Action Allow -Protocol TCP "
        "-LocalPort '20000-65535' -RemoteAddress '10.66.66.0/24' "
        "-InterfaceAlias 'wg-seller' | Out-Null; "
        "Write-Output 'REGISTERED'"
    )
    create_result = _run_powershell(create_script)
    return {"ok": bool(create_result["ok"]), "changed": bool(create_result["ok"]), "create_result": create_result, **payload}


def mcp_attached_to_codex(config_text: str | None = None) -> bool:
    if config_text is None:
        path = codex_config_path()
        if not path.exists():
            return False
        config_text = path.read_text(encoding="utf-8")
    return all(f"[mcp_servers.{server_name}]" in config_text for server_name, _ in desired_mcp_blocks())


def mcp_server_attachment_status(config_text: str | None = None) -> dict[str, bool]:
    if config_text is None:
        path = codex_config_path()
        if path.exists():
            config_text = path.read_text(encoding="utf-8")
        else:
            config_text = ""
    return {
        server_name: f"[mcp_servers.{server_name}]" in config_text
        for server_name, _ in desired_mcp_blocks()
    }


def upsert_mcp_block(config_text: str, server_name: str, block: str) -> str:
    pattern = re.compile(
        rf"(?ms)^\[mcp_servers\.{re.escape(server_name)}\]\n.*?(?=^\[|\Z)"
    )
    stripped = config_text.rstrip()
    if pattern.search(stripped):
        updated = pattern.sub(block.strip() + "\n\n", stripped, count=1)
        return updated.rstrip() + "\n"
    if not stripped:
        return block.lstrip()
    return stripped + block + "\n"


def attach_mcp_to_codex(dry_run: bool = False) -> dict[str, Any]:
    path = codex_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    updated = existing
    for server_name, block in desired_mcp_blocks():
        updated = upsert_mcp_block(updated, server_name, block)
    changed = updated != existing
    if not dry_run:
        path.write_text(updated, encoding="utf-8")
    return {"ok": True, "changed": changed, "config_path": str(path), "dry_run": dry_run}


def bootstrap_client(dry_run: bool = True, state_dir: str | None = None) -> dict[str, Any]:
    base_dir = Path(state_dir).expanduser().resolve() if state_dir else _default_state_dir()
    dirs = _ensure_client_dirs(base_dir)
    env = environment_check()
    codex_attach = attach_mcp_to_codex(dry_run=dry_run)
    mcp_status = mcp_server_attachment_status()
    windows_wireguard_helper = ensure_windows_wireguard_helper_task(dry_run=dry_run)
    windows_gateway_bridge = ensure_windows_gateway_bridge_task(dry_run=dry_run)
    windows_gateway_firewall = ensure_windows_gateway_firewall_rule(dry_run=dry_run)
    return {
        "ok": True,
        "dry_run": dry_run,
        "repo_root": str(repo_root()),
        "state_dir": str(base_dir),
        "dirs": dirs,
        "environment": env,
        "codex_installed": codex_installed(),
        "codex_config_path": str(codex_config_path()),
        "mcp_attached": all(mcp_status.values()),
        "codex_mcp_servers": mcp_status,
        "desired_codex_mcp_servers": [server_name for server_name, _ in desired_mcp_blocks()],
        "attach_result": codex_attach,
        "windows_wireguard_helper": windows_wireguard_helper,
        "windows_gateway_bridge": windows_gateway_bridge,
        "windows_gateway_firewall": windows_gateway_firewall,
        "needs_codex_install": not codex_installed(),
        "needs_codex_mcp_attach": not all(mcp_status.values()),
        "needs_docker_setup": not bool(env["docker_cli"]),
        "needs_wireguard_setup": not bool(env["wireguard_cli"] or env["wireguard_windows_exe"]),
        "needs_windows_wireguard_helper": bool(
            is_windows_platform()
            and (env["wireguard_cli"] or env["wireguard_windows_exe"])
            and not windows_wireguard_helper_task_installed()
        ),
        "needs_windows_gateway_bridge": bool(is_windows_platform() and not _windows_task_installed(session_gateway_bridge_task_name())),
        "needs_windows_gateway_firewall": bool(
            is_windows_platform() and not bool(windows_gateway_firewall.get("ok") and not windows_gateway_firewall.get("dry_run"))
        ),
        "windows_apply_command": environment_check_windows_apply_command() if is_windows_platform() else "",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seller client bootstrap installer skeleton.")
    parser.add_argument("--state-dir", default=None)
    parser.add_argument("--apply", action="store_true", help="Write config changes instead of dry-run.")
    args = parser.parse_args()

    result = bootstrap_client(dry_run=not args.apply, state_dir=args.state_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
