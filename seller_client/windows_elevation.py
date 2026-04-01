from __future__ import annotations

import ctypes
import os
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def is_windows_platform() -> bool:
    return os.name == "nt"


def windows_is_elevated() -> bool:
    if not is_windows_platform():
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


def program_data_dir() -> Path:
    base = os.environ.get("ProgramData", r"C:\ProgramData")
    return Path(base).expanduser().resolve()


def wireguard_helper_root() -> Path:
    return program_data_dir() / "PivotSeller" / "wireguard-elevated"


def session_gateway_bridge_root() -> Path:
    return program_data_dir() / "PivotSeller" / "gateway-bridge"


def wireguard_helper_request_path() -> Path:
    return wireguard_helper_root() / "request.json"


def wireguard_helper_result_path() -> Path:
    return wireguard_helper_root() / "result.json"


def wireguard_helper_task_name() -> str:
    return "PivotSellerWireGuardElevated"


def session_gateway_bridge_task_name() -> str:
    return "PivotSellerSessionGatewayBridge"


def wireguard_helper_script_path() -> Path:
    return REPO_ROOT / "seller_client" / "windows_elevated_helper.py"


def wireguard_helper_launcher_path() -> Path:
    return wireguard_helper_root() / "run-helper.cmd"


def session_gateway_bridge_launcher_path() -> Path:
    return session_gateway_bridge_root() / "run-gateway-bridge.cmd"


def preferred_python_executable() -> str:
    return shutil.which("python") or sys.executable


def wireguard_helper_task_command(python_executable: str | None = None) -> str:
    launcher_path = wireguard_helper_launcher_path()
    return f'"{launcher_path}"'


def wireguard_helper_create_task_command(python_executable: str | None = None) -> list[str]:
    return [
        "schtasks",
        "/Create",
        "/TN",
        wireguard_helper_task_name(),
        "/SC",
        "ONCE",
        "/SD",
        "2000/01/01",
        "/ST",
        "23:59",
        "/RL",
        "HIGHEST",
        "/TR",
        wireguard_helper_task_command(python_executable),
        "/F",
    ]


def wireguard_helper_query_task_command() -> list[str]:
    return [
        "schtasks",
        "/Query",
        "/TN",
        wireguard_helper_task_name(),
    ]


def wireguard_helper_run_task_command() -> list[str]:
    return [
        "schtasks",
        "/Run",
        "/TN",
        wireguard_helper_task_name(),
    ]


def current_user_task_identity() -> str:
    domain = os.environ.get("USERDOMAIN") or "."
    user = os.environ.get("USERNAME") or ""
    return f"{domain}\\{user}" if user else domain
