# Environment Check

`environment_check/` 是当前仓库的一次性管理员安装入口。

推荐入口：

```powershell
powershell -ExecutionPolicy Bypass -File "environment_check\install_windows.ps1" -Apply
```

它会统一完成：

- 本地 WireGuard elevated helper 安装
- 本地 session gateway bridge 计划任务安装与启动
- 本地 session gateway TCP 防火墙规则安装
- 本机 CodeX CLI / MCP readiness 检查与挂载
- 远端 WireGuard / Swarm 基础设施检查

远端检查默认读取仓库根目录 `.env` 里的 `WIREGUARD_SERVER_SSH_*`、`WIREGUARD_SERVER_INTERFACE`、`WIREGUARD_ENDPOINT_*`。

常用参数：

```powershell
powershell -ExecutionPolicy Bypass -File "environment_check\install_windows.ps1" -Apply -SkipRemoteCheck
```

```powershell
powershell -ExecutionPolicy Bypass -File "environment_check\install_windows.ps1" -Apply -RemoteEnsureUp
```

说明：

- `-SkipRemoteCheck` 只做本地安装。
- `-RemoteEnsureUp` 会尝试在远端执行 `systemctl enable --now wg-quick@wg0`，适合维护者排障。
- 结果会落到 `.cache/environment_check/latest.json`。

CodeX note:

- Windows 安装入口现在会同时把 `sellerNodeAgent` 和 `buyerRuntimeAgent` 挂到本机 Codex。
- 环境报告里的 `local_summary` 会明确给出 `codex_cli_ready`、`seller_codex_mcp_attached`、`buyer_codex_mcp_attached`。
- 用户管理员执行一次后，buyer 侧的 CodeX orchestration 面板就能直接复用这套本地配置，不需要再手改 `~/.codex/config.toml`。
