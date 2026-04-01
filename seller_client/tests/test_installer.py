from pathlib import Path

from seller_client.installer import (
    attach_mcp_to_codex,
    buyer_codex_server_name,
    bootstrap_client,
    codex_server_name,
    desired_mcp_block,
    environment_check_windows_apply_command,
    ensure_windows_wireguard_helper_task,
    mcp_attached_to_codex,
    upsert_mcp_block,
)


def test_attach_mcp_to_codex_writes_block(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setattr("seller_client.installer.codex_config_path", lambda: config_path)

    result = attach_mcp_to_codex(dry_run=False)

    assert result["ok"] is True
    assert config_path.exists()
    assert mcp_attached_to_codex(config_path.read_text(encoding="utf-8")) is True
    assert f"[mcp_servers.{codex_server_name()}]" in config_path.read_text(encoding="utf-8")
    assert f"[mcp_servers.{buyer_codex_server_name()}]" in config_path.read_text(encoding="utf-8")


def test_bootstrap_client_returns_expected_status_fields(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.toml"
    monkeypatch.setattr("seller_client.installer.codex_config_path", lambda: config_path)

    result = bootstrap_client(dry_run=True, state_dir=str(tmp_path / "state"))

    assert result["ok"] is True
    assert "needs_codex_install" in result
    assert "needs_codex_mcp_attach" in result
    assert "codex_mcp_servers" in result
    assert "needs_docker_setup" in result
    assert "needs_wireguard_setup" in result
    assert "dirs" in result
    assert result["windows_apply_command"] == environment_check_windows_apply_command()


def test_ensure_windows_wireguard_helper_task_dry_run(monkeypatch) -> None:
    monkeypatch.setattr("seller_client.installer.is_windows_platform", lambda: True)
    monkeypatch.setattr("seller_client.installer.windows_wireguard_helper_task_installed", lambda: False)
    monkeypatch.setattr("seller_client.installer.windows_is_elevated", lambda: False)

    result = ensure_windows_wireguard_helper_task(dry_run=True)

    assert result["ok"] is True
    assert result["changed"] is True
    assert result["dry_run"] is True
    assert result["admin_required"] is True


def test_desired_mcp_block_normalizes_windows_python_path(monkeypatch) -> None:
    monkeypatch.setattr("seller_client.installer.shutil.which", lambda name: r"C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.EXE")

    block = desired_mcp_block()

    assert 'command = "C:/Users/Administrator/AppData/Local/Programs/Python/Python312/python.EXE"' in block
    assert 'command = "C:\\Users\\Administrator' not in block


def test_upsert_mcp_block_replaces_existing_invalid_block() -> None:
    original = (
        '[mcp_servers.sellerNodeAgent]\n'
        'command = "C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python312\\python.EXE"\n'
        'args = ["D:/old.py"]\n'
        '\n'
        '[features]\n'
        'rmcp_client = true\n'
    )
    replacement = (
        '\n[mcp_servers.sellerNodeAgent]\n'
        'command = "C:/Users/Administrator/AppData/Local/Programs/Python/Python312/python.EXE"\n'
        'args = ["D:/AI/Pivot_backend_build_team/seller_client/agent_mcp.py"]\n'
        'cwd = "D:/AI/Pivot_backend_build_team"\n'
    )

    updated = upsert_mcp_block(original, codex_server_name(), replacement)

    assert 'command = "C:/Users/Administrator/AppData/Local/Programs/Python/Python312/python.EXE"' in updated
    assert 'args = ["D:/old.py"]' not in updated
    assert '[features]' in updated
