# Seller Client MCP Prototype

这是当前卖家节点客户端的本地 `MCP` 原型。

目标不是立即提供完整 GUI，而是先把卖家端最关键的本地 Agent 能力做实：

- Agent 配置本地环境
- Agent 准备和连接服务器侧 `WireGuard`
- Agent 检查、拉起和使用本机 Docker
- Agent 测量本机和容器状态
- Agent 构建并上传 Docker 镜像到服务器 registry
- Agent 管理已上传到服务器 registry 的镜像
- Agent 辅助节点加入和离开 Swarm

## 职责边界

- `environment_check`：统一安装 / 检测入口，负责管理员安装、WireGuard helper、session gateway bridge、防火墙规则，以及 CodeX CLI / MCP readiness 检查。
- `seller_client`：只负责卖家节点接入、镜像上架 / 下架、节点和容器资源管理，以及卖家侧自然语言上架流程。
- `buyer_client`：负责 buyer runtime session、终端、文件上传下载，以及 buyer 侧 CodeX orchestration。

seller client 不负责 buyer 在容器里具体做什么；它负责把节点和镜像准备成“可售、可接入、可运行”的状态。

## 2026-04-01 实测结论

- seller 上传镜像的正式入口已经切到 `pivotcompute.store`。Docker 实际走的是 `https://pivotcompute.store/v2/` 这条公开证书的 `443` HTTPS 入口。
- Docker 镜像名要写成 `pivotcompute.store/<repo>:<tag>`。不要写 `https://pivotcompute.store/<repo>:<tag>`，也不要额外拼 `:443`。
- `81.70.52.75:5000` 现在只该视为服务器内部 registry / nginx 反代链路的一部分，不再是 seller client 需要兼容的正式入口。
- `2026-04-01` 我在本机用全新状态目录 `D:\AI\Pivot_backend_build_team\.cache\seller-readme-20260401-1140` 真实跑通了完整 seller 链路：
  - onboarding 成功，节点 `550w-9a2b402abaee` 已注册到平台
  - Registry HTTPS 检查成功，`trust_mode=public_https`
  - 镜像 `pivotcompute.store/seller/readme-full-chain-alpine:20260401-1140` 推送成功
  - digest 为 `sha256:d51206646bec5c00395224838350a037c00b9d1841eafdcae313fb38aeea442b`
  - 平台 `/api/v1/platform/image-offers` 中已出现 1 条匹配 offer
- 这条验证说明：seller 现在已经不需要本地 CA 安装，也不需要 Docker `insecure-registry` 配置，就能通过公开证书链完成推送。

## 当前工具

- `ping`
- `host_summary`
- `environment_check`
- `configure_environment`
- `register_seller_account`
- `login_seller_account`
- `issue_node_registration_token`
- `register_node_with_platform`
- `send_node_heartbeat`
- `report_image_to_platform`
- `fetch_registry_certificate`
- `configure_registry_trust`
- `get_client_config`
- `fetch_codex_runtime_bootstrap`
- `prepare_wireguard_profile`
- `generate_wireguard_keypair`
- `request_wireguard_bootstrap`
- `bootstrap_wireguard_from_platform`
- `wireguard_summary`
- `connect_server_vpn`
- `disconnect_server_vpn`
- `docker_summary`
- `ensure_docker_engine`
- `join_swarm_manager`
- `leave_swarm`
- `swarm_summary`
- `list_docker_images`
- `list_docker_containers`
- `create_docker_container`
- `inspect_container`
- `measure_container`
- `build_image`
- `tag_image_for_server`
- `push_image`
- `push_image_to_server`
- `push_and_report_image`
- `probe_registry`
- `list_uploaded_images`
- `list_uploaded_image_tags`
- `delete_uploaded_image`
- `explain_seller_intent`
- `onboard_seller_from_intent`

## 运行方式

在仓库根目录执行：

```powershell
python seller_client\agent_mcp.py
```

当前默认使用 `stdio` 传输。

本地网页控制面可直接运行：

```powershell
python seller_client\agent_server.py
```

然后打开：

```text
http://127.0.0.1:3847
```

当前本地网页已经具备：

- 本地 dashboard / readiness 检查
- 卖家自然语言意图预览
- 安装器 dry-run 入口
- 卖家 CodeX runtime 拉取入口
- WireGuard profile bootstrap 入口
- 卖家 onboarding 触发入口
- 本地动作日志
- registry HTTPS 连通性检查入口
- 镜像推送与平台登记入口
- 平台节点 / 镜像回显

当前 WireGuard onboarding 已推进到：

- seller-Agent 本地生成 WireGuard keypair
- seller-Agent 从后端获取 bootstrap profile
- 后端在启用 SSH 时自动把 peer 写入服务器 `wg0`
- seller-Agent 写本地 profile
- seller-Agent 在条件满足时尝试拉起本地 WireGuard

Windows 当前真实边界：

- 如果本地 seller-Agent 不是管理员权限，`wireguard.exe /installtunnelservice` 会被拒绝
- 当前已补出 `PivotSellerWireGuardElevated` scheduled-task helper 路径
- 如果 helper 还没装好，seller onboarding 仍然可以继续完成账号登录、节点注册、Swarm 检查和镜像推送，但本地 `wg-seller` 会停在 `activation_failed`
- 需要先执行一次：

```powershell
powershell -ExecutionPolicy Bypass -File "environment_check\install_windows.ps1" -Apply
```

这样安装器会请求 UAC，并注册后续可复用的受权 helper task，同时统一检查 / 挂载本机 CodeX 的 `sellerNodeAgent` 与 `buyerRuntimeAgent` MCP 配置。

## 当前边界

这还不是完整卖家客户端成品。

当前已经覆盖的是：

- 本地配置与状态文件
- 安装器骨架
- CodeX 环境检测与 MCP 挂载骨架
- WireGuard 配置文件生成与启停入口
- 公开 HTTPS registry 证书检查入口
- 平台后端注册 / 登录 / 节点令牌 / 节点注册 / 心跳 / 镜像登记入口
- Docker 检查、启动、镜像和容器操作
- Swarm join / leave 入口
- 服务器 registry 查询和删除接口

## 当前排障结论

- 如果 seller 推送已经成功，但 `report_image_to_platform` 报 `connection refused`，先检查本地 backend 是否还在监听 `127.0.0.1:8000`。
- 我在 `2026-04-01` 的第一次复测里遇到过 `docker compose` 启动的本地 backend 以 `Exited (137)` 退出，表现就是 push 成功但上报失败。
- 这种情况下，先重启本地 backend，再重新执行 `push_and_report_image`；不要把它误判成 registry 证书问题。

## 安装器与界面

- Windows 一次性管理员安装入口：`environment_check/install_windows.ps1`
- 兼容入口：`seller_client/install_windows.ps1`
- Linux 安装器骨架：`seller_client/install_linux.sh`
- 安装器逻辑：`seller_client/installer.py`
- 本地 Web 控制面：`seller_client/agent_server.py` + `seller_client/web/index.html`
- 最小 GUI 壳子：`seller_client/gui_app.py`

当前还没有的是：

- 安装器真正自动化
- 自动节点注册协议
- 自动心跳与任务回传
- 后端下发 CodeX API key
- WireGuard 真正自动接入
- 一键式 Windows / Linux 全自动环境安装
