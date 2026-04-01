from __future__ import annotations

import argparse
import html
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from playwright.sync_api import Browser, Page, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from environment_check.windows_bootstrap import bootstrap_windows_environment


REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_ROOT = REPO_ROOT / "docs"
ASSETS_ROOT = DOCS_ROOT / "assets"
DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"
DEFAULT_SELLER_URL = "http://127.0.0.1:3847"
DEFAULT_BUYER_URL = "http://127.0.0.1:3857"
DEFAULT_PLATFORM_URL = "http://127.0.0.1:8000/platform-ui"
DEFAULT_PASSWORD = "super-secret-password"
DEFAULT_SELLER_EMAIL = "seller-real-chain@example.com"
DEFAULT_SELLER_NAME = "Real Chain Seller"
DEFAULT_LOCAL_TAG = "python:3.12-alpine"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def run_id() -> str:
    return utc_now().strftime("%Y%m%d-%H%M%S")


def mask_secret(value: str, *, keep: int = 6) -> str:
    if not value:
        return ""
    if len(value) <= keep:
        return "*" * len(value)
    return f"{value[:keep]}...{len(value)}"


def sanitize(value: Any) -> Any:
    secret_keys = {
        "access_token",
        "session_token",
        "license_token",
        "connect_code",
        "password",
        "buyer_token",
        "token",
    }
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if key in secret_keys and isinstance(item, str):
                sanitized[key] = mask_secret(item)
            else:
                sanitized[key] = sanitize(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    return value


def ensure_ok(response: requests.Response, title: str) -> Any:
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict) and payload.get("ok") is False:
        raise RuntimeError(f"{title} failed: {payload}")
    return payload


def wait_until(predicate, *, timeout: float = 120.0, interval: float = 2.0, description: str = "condition") -> Any:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            value = predicate()
            if value:
                return value
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        time.sleep(interval)
    if last_error is not None:
        raise RuntimeError(f"Timed out waiting for {description}: {last_error}") from last_error
    raise RuntimeError(f"Timed out waiting for {description}")


def wait_for_endpoint(url: str, *, timeout: float = 30.0) -> None:
    def _probe() -> bool:
        response = requests.get(url, timeout=10)
        return response.ok

    wait_until(_probe, timeout=timeout, interval=1.0, description=url)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def render_environment_report_html(report: dict[str, Any]) -> str:
    local_summary = report.get("local_summary") or {}
    remote_summary = report.get("remote_check") or {}
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>Environment Check Report</title>
  <style>
    body {{
      margin: 0;
      padding: 24px;
      background: #f4efe8;
      color: #132427;
      font-family: "Aptos", "Segoe UI", sans-serif;
    }}
    .shell {{
      display: grid;
      gap: 18px;
      width: min(1320px, 100%);
      margin: 0 auto;
    }}
    .hero, .panel {{
      border-radius: 24px;
      border: 1px solid rgba(19, 36, 39, 0.12);
      background: rgba(255, 255, 255, 0.86);
      box-shadow: 0 18px 36px rgba(19, 36, 39, 0.08);
      padding: 20px;
    }}
    .hero {{
      background: linear-gradient(135deg, rgba(17, 48, 51, 0.96), rgba(11, 112, 120, 0.92));
      color: #eef7f7;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px;
    }}
    .item {{
      padding: 12px 14px;
      border-radius: 16px;
      background: rgba(19, 36, 39, 0.05);
      margin-top: 10px;
    }}
    .ok {{ color: #21784f; }}
    .warn {{ color: #a66b1a; }}
    pre {{
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      background: #0d1e20;
      color: #dfeae9;
      border-radius: 18px;
      padding: 16px;
      overflow: auto;
      max-height: 520px;
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <h1>environment_check smoke report</h1>
      <p>Generated at {html.escape(str(report.get("generated_at") or utc_now().isoformat()))}. This page is a browser-friendly render of the latest dry-run report.</p>
    </section>
    <section class="grid">
      <div class="panel">
        <h2>Local Summary</h2>
        <div class="item"><strong>runtime_ready:</strong> <span class="{'ok' if local_summary.get('runtime_ready') else 'warn'}">{html.escape(str(local_summary.get("runtime_ready")))}</span></div>
        <div class="item"><strong>codex_ready:</strong> <span class="{'ok' if local_summary.get('codex_ready') else 'warn'}">{html.escape(str(local_summary.get("codex_ready")))}</span></div>
        <div class="item"><strong>seller MCP:</strong> {html.escape(str(local_summary.get("seller_codex_mcp_attached")))}</div>
        <div class="item"><strong>buyer MCP:</strong> {html.escape(str(local_summary.get("buyer_codex_mcp_attached")))}</div>
        <div class="item"><strong>windows_apply_command:</strong> {html.escape(str(local_summary.get("windows_apply_command") or ""))}</div>
      </div>
      <div class="panel">
        <h2>Remote Summary</h2>
        <div class="item"><strong>ok:</strong> <span class="{'ok' if remote_summary.get('ok') else 'warn'}">{html.escape(str(remote_summary.get("ok")))}</span></div>
        <div class="item"><strong>server_uses_wireguard:</strong> {html.escape(str(remote_summary.get("server_uses_wireguard")))}</div>
        <div class="item"><strong>hostname:</strong> {html.escape(str(remote_summary.get("hostname") or ""))}</div>
        <div class="item"><strong>service_active:</strong> {html.escape(str(remote_summary.get("service_active")))}</div>
        <div class="item"><strong>interface_has_ipv4:</strong> {html.escape(str(remote_summary.get("interface_has_ipv4")))}</div>
        <div class="item"><strong>peer_count:</strong> {html.escape(str(remote_summary.get("peer_count")))}</div>
      </div>
    </section>
    <section class="panel">
      <h2>Raw JSON</h2>
      <pre>{html.escape(json.dumps(report, ensure_ascii=False, indent=2))}</pre>
    </section>
  </main>
</body>
</html>
"""


def expect_json_response(page: Page, url_fragment: str, action, *, timeout_ms: int = 180_000) -> dict[str, Any]:
    with page.expect_response(lambda response: url_fragment in response.url, timeout=timeout_ms) as response_info:
        action()
    response = response_info.value
    payload = response.json()
    return payload


def mask_token_on_page(page: Page, token: str) -> None:
    if not token:
        return
    masked = mask_secret(token)
    page.evaluate(
        """([token, masked]) => {
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            const nodes = [];
            while (walker.nextNode()) nodes.push(walker.currentNode);
            for (const node of nodes) {
              if (node.textContent && node.textContent.includes(token)) {
                node.textContent = node.textContent.split(token).join(masked);
              }
            }
            for (const input of document.querySelectorAll('input, textarea')) {
              if (typeof input.value === 'string' && input.value.includes(token)) {
                input.value = input.value.split(token).join(masked);
              }
            }
        }""",
        [token, masked],
    )


def load_dashboard(page: Page, state_dir: str | None = None) -> None:
    if state_dir:
        page.evaluate("(stateDir) => loadDashboard(false)", state_dir)
    else:
        page.evaluate("() => loadDashboard()")
    page.wait_for_timeout(1000)


def ssh_service_snapshot(host: str, port: int, user: str, password: str, session_id: int) -> dict[str, Any]:
    if not host or not user or not password:
        return {"ok": False, "skipped": True, "reason": "missing_remote_credentials"}
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=host, port=port, username=user, password=password, timeout=20, banner_timeout=20, auth_timeout=20)
    try:
        command = (
            "docker service ls --format '{{.Name}} {{.Replicas}}' "
            f"| grep -E '^(runtime-{session_id}|gateway-{session_id}) ' || true"
        )
        stdin, stdout, stderr = client.exec_command(command, timeout=30)
        stdout_text = stdout.read().decode("utf-8", "replace").strip()
        stderr_text = stderr.read().decode("utf-8", "replace").strip()
        return {
            "ok": True,
            "command": command,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "services": [line.strip() for line in stdout_text.splitlines() if line.strip()],
        }
    finally:
        client.close()


def db_session_snapshot(session_id: int) -> dict[str, Any]:
    database_path = REPO_ROOT / "backend" / "live_ui_test.sqlite3"
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            """
            select
              id,
              status,
              gateway_status,
              gateway_service_name,
              gateway_protocol,
              gateway_port,
              seller_wireguard_target,
              buyer_wireguard_client_address,
              runtime_image,
              image_offer_id,
              source_type,
              source_ref,
              created_at,
              started_at,
              ended_at
            from runtime_access_sessions
            where id = ?
            """,
            (session_id,),
        ).fetchone()
    finally:
        connection.close()
    return dict(row) if row is not None else {}


def seller_flow(
    page: Page,
    *,
    assets_dir: Path,
    seller_email: str,
    seller_name: str,
    password: str,
    seller_state_dir: str,
    backend_url: str,
    repository: str,
    remote_tag: str,
) -> dict[str, Any]:
    intent = f"请把这台 Windows 节点用 12% 共享比例接入平台，并准备售卖 {DEFAULT_LOCAL_TAG} 容器，仓库目标是 {repository}:{remote_tag}。"
    page.goto(DEFAULT_SELLER_URL, wait_until="networkidle")
    page.fill("#email", seller_email)
    page.fill("#password", password)
    page.fill("#display_name", seller_name)
    page.fill("#backend_url", backend_url)
    page.fill("#intent", intent)
    page.fill("#state_dir", seller_state_dir)
    page.fill("#registry", "pivotcompute.store")
    page.fill("#local_tag", DEFAULT_LOCAL_TAG)
    page.fill("#repository", repository)
    page.fill("#remote_tag", remote_tag)

    intent_preview = expect_json_response(
        page,
        "/api/intents/explain",
        lambda: page.locator('button[onclick="runIntentPreview()"]').click(),
    )
    page.wait_for_timeout(1000)
    page.screenshot(path=str(assets_dir / "01-seller-intent-preview.png"), full_page=True)

    installer = expect_json_response(
        page,
        "/api/installer",
        lambda: page.locator('button[onclick="runInstaller()"]').click(),
    )
    page.wait_for_timeout(1000)
    page.screenshot(path=str(assets_dir / "02-seller-installer-dry-run.png"), full_page=True)

    onboarding = expect_json_response(
        page,
        "/api/onboarding",
        lambda: page.locator('button[onclick="runOnboarding()"]').click(),
        timeout_ms=240_000,
    )
    page.wait_for_timeout(1500)
    page.evaluate("() => loadDashboard(false)")
    page.wait_for_timeout(1200)
    page.screenshot(path=str(assets_dir / "03-seller-onboarding.png"), full_page=True)

    registry_check = expect_json_response(
        page,
        "/api/registry/trust",
        lambda: page.locator('button[onclick="configureRegistryTrust()"]').click(),
        timeout_ms=180_000,
    )

    push = expect_json_response(
        page,
        "/api/images/push",
        lambda: page.locator('button[onclick="runPushImage()"]').click(),
        timeout_ms=360_000,
    )
    page.wait_for_timeout(1500)
    page.evaluate("() => loadDashboard(false)")
    page.wait_for_timeout(1200)
    page.screenshot(path=str(assets_dir / "04-seller-push-image.png"), full_page=True)

    return {
        "seller_state_dir": seller_state_dir,
        "intent": intent,
        "repository": repository,
        "remote_tag": remote_tag,
        "intent_preview": intent_preview,
        "installer": installer,
        "onboarding": onboarding,
        "registry_check": registry_check,
        "push": push,
    }


def poll_active_offers(access_token: str, *, backend_url: str) -> list[dict[str, Any]]:
    headers = {"Authorization": f"Bearer {access_token}"}

    def _fetch() -> list[dict[str, Any]] | None:
        response = requests.get(f"{backend_url}/api/v1/buyer/catalog/offers", headers=headers, timeout=20)
        offers = ensure_ok(response, "read offers")
        return offers if offers else None

    return wait_until(_fetch, timeout=180.0, interval=5.0, description="active offers")


def platform_flow(
    page: Page,
    *,
    assets_dir: Path,
    backend_url: str,
    buyer_email: str,
    buyer_name: str,
    password: str,
    repository: str,
    remote_tag: str,
    fallback_repository: str,
    fallback_tag: str,
) -> dict[str, Any]:
    page.goto(DEFAULT_PLATFORM_URL, wait_until="networkidle")
    page.fill("#backend_base", backend_url)
    page.fill("#email", buyer_email)
    page.fill("#password", password)
    page.fill("#display_name", buyer_name)

    register = expect_json_response(page, "/api/v1/auth/register", lambda: page.click("#register_btn"))
    login = expect_json_response(page, "/api/v1/auth/login", lambda: page.click("#login_btn"))
    access_token = str(login.get("access_token") or "")
    active_offers = poll_active_offers(access_token, backend_url=backend_url)
    fresh_offer = next(
        (item for item in active_offers if item.get("repository") == repository and item.get("tag") == remote_tag),
        None,
    )
    fallback_offer = next(
        (item for item in active_offers if item.get("repository") == fallback_repository and item.get("tag") == fallback_tag),
        None,
    )
    offer = fresh_offer or fallback_offer or active_offers[0]
    offer_selection_mode = (
        "fresh_seller_offer"
        if fresh_offer is not None
        else "fallback_existing_active_offer"
        if fallback_offer is not None
        else "first_active_offer"
    )

    offer_items = page.locator("#offer_list .item")
    wait_until(
        lambda: any(
            str(offer.get("repository") or "") in (offer_items.nth(index).text_content(timeout=2_000) or "")
            and str(offer.get("tag") or "") in (offer_items.nth(index).text_content(timeout=2_000) or "")
            for index in range(offer_items.count())
        ),
        timeout=120.0,
        interval=2.0,
        description="offer visible in platform UI",
    )
    target_item = page.locator("#offer_list .item").filter(
        has_text=f"{offer.get('repository')}:{offer.get('tag')}"
    ).first
    target_item.locator("button").click()
    page.wait_for_timeout(1000)
    page.screenshot(path=str(assets_dir / "05-platform-login-and-offers.png"), full_page=True)

    page.fill("#order_minutes", "45")
    order = expect_json_response(page, "/api/v1/buyer/orders", lambda: page.click("#order_btn"))
    license_token = str(order.get("license_token") or "")
    mask_token_on_page(page, license_token)
    page.wait_for_timeout(500)
    page.screenshot(path=str(assets_dir / "06-platform-create-order.png"), full_page=True)

    redeem = expect_json_response(page, "/api/v1/buyer/orders/redeem", lambda: page.click("#redeem_btn"))
    mask_token_on_page(page, license_token)
    page.wait_for_timeout(500)
    page.screenshot(path=str(assets_dir / "07-platform-redeem-license.png"), full_page=True)

    offer_detail_response = requests.get(
        f"{backend_url}/api/v1/buyer/catalog/offers/{offer['offer_id']}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20,
    )
    offer_detail = ensure_ok(offer_detail_response, "read offer detail")

    return {
        "buyer_email": buyer_email,
        "buyer_name": buyer_name,
        "register": register,
        "login": {"ok": True, "user": login.get("user"), "access_token": mask_secret(access_token)},
        "active_offers": active_offers,
        "offer": offer,
        "offer_selection_mode": offer_selection_mode,
        "fresh_offer_visible": fresh_offer is not None,
        "offer_detail": offer_detail,
        "order": order,
        "redeem": redeem,
        "license_token_masked": mask_secret(license_token),
        "license_token": license_token,
    }


def wait_for_codex_job(job_id: str) -> dict[str, Any]:
    def _fetch() -> dict[str, Any] | None:
        response = requests.get(f"{DEFAULT_BUYER_URL}/api/codex/jobs/{job_id}", timeout=20)
        payload = ensure_ok(response, "read codex job")
        job = payload.get("job") or {}
        if job.get("status") in {"completed", "failed", "cancelled"}:
            return payload
        return None

    return wait_until(_fetch, timeout=900.0, interval=5.0, description=f"CodeX job {job_id}")


def buyer_flow(
    page: Page,
    *,
    assets_dir: Path,
    backend_url: str,
    buyer_email: str,
    password: str,
    license_token: str,
    workspace_path: str,
    prompt: str,
) -> dict[str, Any]:
    page.goto(DEFAULT_BUYER_URL, wait_until="networkidle")
    page.fill("#backend_url", backend_url)
    page.fill("#email", buyer_email)
    page.fill("#password", password)
    page.fill("#license_token", license_token)
    page.fill("#codex_workspace_path", workspace_path)
    page.fill("#codex_prompt", prompt)
    page.fill("#exec_command", "python -V")

    start = expect_json_response(
        page,
        "/api/runtime/start-licensed-shell",
        lambda: page.locator('button[onclick="startLicensedShell()"]').click(),
        timeout_ms=180_000,
    )
    session = start.get("session") or {}
    local_id = str(session.get("local_id") or "")
    session_id = int(session.get("session_id") or 0)

    connect = expect_json_response(
        page,
        f"/api/runtime/sessions/{local_id}/connect",
        lambda: page.locator('button[onclick="connectActiveSession()"]').click(),
        timeout_ms=180_000,
    )
    exec_result = expect_json_response(
        page,
        f"/api/runtime/sessions/{local_id}/exec",
        lambda: page.locator('button[onclick="execActiveSession()"]').click(),
        timeout_ms=180_000,
    )

    mask_token_on_page(page, license_token)
    page.locator('button[onclick="openTerminal()"]').click()
    page.wait_for_timeout(2000)
    page.locator("#terminal").click(position={"x": 30, "y": 30})
    page.keyboard.type("python -V")
    page.keyboard.press("Enter")
    page.wait_for_timeout(3000)
    page.screenshot(path=str(assets_dir / "08-buyer-connected-terminal.png"), full_page=True)

    codex_start = expect_json_response(
        page,
        "/api/codex/jobs",
        lambda: page.locator('button[onclick="startCodexJob()"]').click(),
        timeout_ms=180_000,
    )
    job = codex_start.get("job") or {}
    job_id = str(job.get("job_id") or "")
    completed_job = wait_for_codex_job(job_id)
    page.locator('button[onclick="refreshCurrentCodexJob()"]').click()
    page.wait_for_timeout(2000)
    mask_token_on_page(page, license_token)
    page.screenshot(path=str(assets_dir / "09-buyer-codex-job.png"), full_page=True)

    downloaded_path = Path(workspace_path) / "downloaded" / "codex_roundtrip_result.txt"
    downloaded_text = downloaded_path.read_text(encoding="utf-8") if downloaded_path.exists() else ""

    return {
        "start": start,
        "connect": connect,
        "exec": exec_result,
        "codex_start": codex_start,
        "codex_completed": completed_job,
        "session_id": session_id,
        "local_id": local_id,
        "downloaded_result_path": str(downloaded_path),
        "downloaded_result_exists": downloaded_path.exists(),
        "downloaded_result_text": downloaded_text,
    }


def run(browser: Browser, args: argparse.Namespace) -> dict[str, Any]:
    current_run_id = run_id()
    assets_dir = ASSETS_ROOT / f"ui-full-closed-loop-{current_run_id}"
    assets_dir.mkdir(parents=True, exist_ok=True)
    summary_path = assets_dir / "summary.json"

    wait_for_endpoint(f"{DEFAULT_SELLER_URL}/api/health")
    wait_for_endpoint(f"{DEFAULT_BUYER_URL}/api/health")
    wait_for_endpoint(DEFAULT_PLATFORM_URL)

    buyer_email = f"buyer-ui-e2e-{current_run_id}@example.com"
    buyer_name = f"UI E2E Buyer {current_run_id}"
    seller_state_dir = str(REPO_ROOT / ".cache" / f"seller-ui-e2e-{current_run_id}")
    buyer_workspace = str(REPO_ROOT / ".cache" / f"buyer-codex-workspace-{current_run_id}")
    repository = f"seller/ui-e2e-python-{current_run_id.lower()}"
    remote_tag = "runtime"
    prompt = (
        "Create a local file named codex_roundtrip.py in this workspace. "
        "The script must print 'buyer codex roundtrip ok' and write the lines "
        "'buyer-codex-ui-e2e' and '56' into /workspace/codex_roundtrip_result.txt. "
        "Use buyerRuntimeAgent MCP to connect the selected session if needed, upload the script to /workspace, "
        "run it with python inside the container, verify the command output, and download "
        "/workspace/codex_roundtrip_result.txt back into this workspace under downloaded/codex_roundtrip_result.txt. "
        "Do not use handwritten curl. End with a concise summary of edited files, uploaded paths, commands, and downloads."
    )

    environment_report = bootstrap_windows_environment(
        apply=False,
        state_dir=str(REPO_ROOT / ".cache" / "environment-check-ui-run"),
        skip_remote_check=False,
        remote_ensure_up=True,
        remote_host=args.remote_host,
        remote_port=args.remote_port,
        remote_user=args.remote_user,
        remote_password=args.remote_password,
        remote_interface=args.remote_interface,
        remote_endpoint_host=args.remote_endpoint_host,
        remote_endpoint_port=args.remote_endpoint_port,
        report_path=str(assets_dir / "environment-check.json"),
    )
    environment_report["generated_at"] = utc_now().isoformat()
    environment_html = render_environment_report_html(environment_report)
    environment_html_path = assets_dir / "environment-check.html"
    write_text(environment_html_path, environment_html)

    context = browser.new_context(viewport={"width": 1600, "height": 1400})
    seller_page = context.new_page()
    platform_page = context.new_page()
    buyer_page = context.new_page()

    summary: dict[str, Any] = {
        "run_id": current_run_id,
        "generated_at": utc_now().isoformat(),
        "assets_dir": str(assets_dir),
        "environment_check": {},
        "seller": {},
        "platform": {},
        "buyer": {},
        "remote": {},
        "database": {},
        "checkpoints": {},
    }
    try:
        seller_page.goto(environment_html_path.resolve().as_uri(), wait_until="networkidle")
        seller_page.screenshot(path=str(assets_dir / "00-environment-check-report.png"), full_page=True)
        summary["environment_check"] = environment_report
        write_json(summary_path, sanitize(summary))

        summary["seller"] = seller_flow(
            seller_page,
            assets_dir=assets_dir,
            seller_email=args.seller_email,
            seller_name=args.seller_name,
            password=args.password,
            seller_state_dir=seller_state_dir,
            backend_url=args.backend_url,
            repository=repository,
            remote_tag=remote_tag,
        )
        write_json(summary_path, sanitize(summary))

        summary["platform"] = platform_flow(
            platform_page,
            assets_dir=assets_dir,
            backend_url=args.backend_url,
            buyer_email=buyer_email,
            buyer_name=buyer_name,
            password=args.password,
            repository=repository,
            remote_tag=remote_tag,
            fallback_repository=args.fallback_repository,
            fallback_tag=args.fallback_tag,
        )
        write_json(summary_path, sanitize(summary))

        summary["buyer"] = buyer_flow(
            buyer_page,
            assets_dir=assets_dir,
            backend_url=args.backend_url,
            buyer_email=buyer_email,
            password=args.password,
            license_token=summary["platform"]["license_token"],
            workspace_path=buyer_workspace,
            prompt=prompt,
        )
        session_id = int(summary["buyer"].get("session_id") or 0)
        if session_id:
            summary["remote"]["during_active_session"] = ssh_service_snapshot(
                args.remote_host,
                args.remote_port,
                args.remote_user,
                args.remote_password,
                session_id,
            )
        stop = expect_json_response(
            buyer_page,
            f"/api/runtime/sessions/{summary['buyer']['local_id']}/stop",
            lambda: buyer_page.locator('button[onclick="stopActiveSession()"]').click(),
            timeout_ms=180_000,
        )
        summary["buyer"]["stop"] = stop
        buyer_page.wait_for_timeout(1500)
        if session_id:
            summary["database"]["session_after_stop"] = db_session_snapshot(session_id)
            summary["remote"]["after_stop"] = ssh_service_snapshot(
                args.remote_host,
                args.remote_port,
                args.remote_user,
                args.remote_password,
                session_id,
            )

        summary["checkpoints"] = {
            "seller_ui_operation": True,
            "buyer_ui_operation": True,
            "seller_natural_language_onboarding": bool(summary["seller"].get("onboarding", {}).get("ok")),
            "seller_natural_language_listing_full_automation": False,
            "seller_image_listed_via_ui_push": bool(summary["seller"].get("push", {}).get("ok")),
            "buyer_platform_register_login": bool(
                summary["platform"].get("register", {}).get("ok")
                and summary["platform"].get("login", {}).get("user")
            ),
            "buyer_obtained_license": bool(summary["platform"].get("order", {}).get("license_token")),
            "buyer_opened_container_terminal": bool(summary["buyer"].get("connect", {}).get("session", {}).get("connection_status") == "connected"),
            "buyer_could_exec_in_container": "Python 3.12" in json.dumps(summary["buyer"].get("exec", {}), ensure_ascii=False),
            "buyer_codex_nl_orchestration": bool(
                summary["buyer"].get("codex_completed", {}).get("job", {}).get("status") == "completed"
            ),
            "buyer_codex_downloaded_result": bool(summary["buyer"].get("downloaded_result_exists")),
            "environment_check_local_ready": bool(summary["environment_check"].get("local_summary", {}).get("runtime_ready")),
            "environment_check_remote_ready": bool(summary["environment_check"].get("remote_wireguard", {}).get("ok")),
        }
        return summary
    finally:
        write_json(summary_path, sanitize(summary))
        context.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the full seller->platform->buyer UI closed loop with screenshots.")
    parser.add_argument("--backend-url", default=DEFAULT_BACKEND_URL)
    parser.add_argument("--seller-email", default=DEFAULT_SELLER_EMAIL)
    parser.add_argument("--seller-name", default=DEFAULT_SELLER_NAME)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--remote-host", required=True)
    parser.add_argument("--remote-port", type=int, default=22)
    parser.add_argument("--remote-user", required=True)
    parser.add_argument("--remote-password", required=True)
    parser.add_argument("--remote-interface", default="wg0")
    parser.add_argument("--remote-endpoint-host", default="")
    parser.add_argument("--remote-endpoint-port", type=int, default=45182)
    parser.add_argument("--fallback-repository", default="seller/real-chain-python")
    parser.add_argument("--fallback-tag", default="20260401")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            summary = run(browser, args)
        finally:
            browser.close()
    sanitized = sanitize(summary)
    print(f"Run completed. Summary written to {sanitized['assets_dir']}\\summary.json")


if __name__ == "__main__":
    main()
