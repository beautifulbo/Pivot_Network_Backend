from pathlib import Path

from environment_check.windows_bootstrap import (
    bootstrap_windows_environment,
    load_dotenv_file,
    resolve_remote_wireguard_settings,
)


def test_load_dotenv_file_reads_quoted_values(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        'WIREGUARD_SERVER_SSH_HOST="pivotcompute.store"\n'
        "WIREGUARD_SERVER_SSH_PORT=22\n"
        "WIREGUARD_SERVER_SSH_PASSWORD=@secret\n",
        encoding="utf-8",
    )

    payload = load_dotenv_file(env_path)

    assert payload["WIREGUARD_SERVER_SSH_HOST"] == "pivotcompute.store"
    assert payload["WIREGUARD_SERVER_SSH_PORT"] == "22"
    assert payload["WIREGUARD_SERVER_SSH_PASSWORD"] == "@secret"


def test_resolve_remote_wireguard_settings_uses_dotenv_defaults(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "WIREGUARD_SERVER_SSH_HOST=81.70.52.75",
                "WIREGUARD_SERVER_SSH_PORT=22",
                "WIREGUARD_SERVER_SSH_USER=root",
                "WIREGUARD_SERVER_SSH_PASSWORD=@secret",
                "WIREGUARD_SERVER_INTERFACE=wg0",
                "WIREGUARD_SERVER_CONFIG_PATH=/etc/wireguard/wg0.conf",
                "WIREGUARD_ENDPOINT_HOST=pivotcompute.store",
                "WIREGUARD_ENDPOINT_PORT=45182",
            ]
        ),
        encoding="utf-8",
    )

    settings = resolve_remote_wireguard_settings(env_path=env_path)

    assert settings.host == "81.70.52.75"
    assert settings.port == 22
    assert settings.user == "root"
    assert settings.password == "@secret"
    assert settings.interface_name == "wg0"
    assert settings.config_path == "/etc/wireguard/wg0.conf"
    assert settings.endpoint_host == "pivotcompute.store"
    assert settings.endpoint_port == 45182


def test_bootstrap_windows_environment_writes_report(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "environment_check.windows_bootstrap.bootstrap_client",
        lambda dry_run=True, state_dir=None: {
            "ok": True,
            "codex_installed": True,
            "codex_config_path": "C:/Users/Administrator/.codex/config.toml",
            "codex_mcp_servers": {"sellerNodeAgent": True, "buyerRuntimeAgent": True},
            "needs_codex_install": False,
            "needs_codex_mcp_attach": False,
            "needs_docker_setup": False,
            "needs_wireguard_setup": False,
            "needs_windows_wireguard_helper": False,
            "needs_windows_gateway_bridge": False,
            "needs_windows_gateway_firewall": False,
            "windows_apply_command": "powershell -ExecutionPolicy Bypass -File helper.ps1 -Apply",
            "state_dir": state_dir,
        },
    )
    monkeypatch.setattr(
        "environment_check.windows_bootstrap.check_remote_wireguard_server",
        lambda settings, ensure_up=False: {"ok": True, "server_uses_wireguard": True, "settings": {"host": settings.host}},
    )

    report_path = tmp_path / "report.json"
    result = bootstrap_windows_environment(
        apply=True,
        state_dir=str(tmp_path / "state"),
        report_path=str(report_path),
    )

    assert result["ok"] is True
    assert report_path.exists()
    assert result["local_summary"]["runtime_ready"] is True
    assert result["local_summary"]["codex_ready"] is True
    assert result["local_summary"]["seller_codex_mcp_attached"] is True
    assert result["local_summary"]["buyer_codex_mcp_attached"] is True
    assert result["remote_wireguard"]["server_uses_wireguard"] is True


def test_bootstrap_windows_environment_marks_codex_as_environment_issue(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "environment_check.windows_bootstrap.bootstrap_client",
        lambda dry_run=True, state_dir=None: {
            "ok": True,
            "codex_installed": False,
            "codex_config_path": "C:/Users/Administrator/.codex/config.toml",
            "codex_mcp_servers": {"sellerNodeAgent": False, "buyerRuntimeAgent": False},
            "needs_codex_install": True,
            "needs_codex_mcp_attach": True,
            "needs_docker_setup": False,
            "needs_wireguard_setup": False,
            "needs_windows_wireguard_helper": False,
            "needs_windows_gateway_bridge": False,
            "needs_windows_gateway_firewall": False,
            "windows_apply_command": "powershell -ExecutionPolicy Bypass -File helper.ps1 -Apply",
            "state_dir": state_dir,
        },
    )
    monkeypatch.setattr(
        "environment_check.windows_bootstrap.check_remote_wireguard_server",
        lambda settings, ensure_up=False: {"ok": True, "server_uses_wireguard": True, "settings": {"host": settings.host}},
    )

    result = bootstrap_windows_environment(
        apply=False,
        state_dir=str(tmp_path / "state"),
        report_path=str(tmp_path / "report.json"),
    )

    assert result["ok"] is False
    assert result["local_summary"]["runtime_ready"] is False
    assert result["local_summary"]["codex_ready"] is False
    assert result["local_summary"]["needs_codex_install"] is True
    assert result["local_summary"]["needs_codex_mcp_attach"] is True
