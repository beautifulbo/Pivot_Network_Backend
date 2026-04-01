from __future__ import annotations

import asyncio
import base64
import json
import os
import shlex
import shutil
import subprocess
import tarfile
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

DOCKER_BIN = os.environ.get("PIVOT_DOCKER_BIN") or shutil.which("docker") or "docker"
LISTEN_HOST = os.environ.get("PIVOT_LISTEN_HOST", "127.0.0.1").strip() or "127.0.0.1"
SESSION_ID = int(os.environ.get("PIVOT_SESSION_ID", "0"))
RUNTIME_SERVICE_NAME = os.environ.get("PIVOT_RUNTIME_SERVICE_NAME", "")
BUYER_USER_ID = int(os.environ.get("PIVOT_BUYER_USER_ID", "0"))
SELLER_NODE_ID = int(os.environ.get("PIVOT_SELLER_NODE_ID", "0"))
GATEWAY_SERVICE_NAME = os.environ.get("PIVOT_GATEWAY_SERVICE_NAME", "")
SESSION_TOKEN = os.environ.get("PIVOT_SESSION_TOKEN", "")
SUPPORTED_FEATURES = [
    item.strip()
    for item in os.environ.get("PIVOT_SUPPORTED_FEATURES", "exec,logs,shell,files").split(",")
    if item.strip()
]


class GatewayError(RuntimeError):
    pass


class ExecRequest(BaseModel):
    command: str = Field(min_length=1, max_length=4000)


class UploadRequest(BaseModel):
    remote_path: str = Field(min_length=1, max_length=2000)
    archive_base64: str = Field(min_length=8)


def _decode_bytes(raw: bytes) -> str:
    return raw.decode("utf-8", "replace")


def _authorization_token(raw_header: str | None) -> str:
    if not raw_header:
        raise HTTPException(status_code=401, detail="missing_authorization")
    scheme, _, token = raw_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="invalid_authorization")
    return token.strip()


def _authorize_http(request: Request) -> None:
    token = _authorization_token(request.headers.get("authorization"))
    if token != SESSION_TOKEN:
        raise HTTPException(status_code=403, detail="invalid_session_token")


def _authorize_websocket(websocket: WebSocket) -> bool:
    try:
        token = _authorization_token(websocket.headers.get("authorization"))
    except HTTPException:
        return False
    return token == SESSION_TOKEN


def _run_command(command: list[str], *, timeout: float = 60.0) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def _runtime_container_id() -> str:
    result = _run_command(
        [DOCKER_BIN, "ps", "-q", "--filter", f"label=com.docker.swarm.service.name={RUNTIME_SERVICE_NAME}"],
        timeout=20.0,
    )
    if result.returncode != 0:
        detail = _decode_bytes(result.stderr or result.stdout).strip()
        raise GatewayError(f"docker_ps_failed:{detail or 'unknown error'}")
    container_ids = [line.strip() for line in _decode_bytes(result.stdout).splitlines() if line.strip()]
    if container_ids:
        return container_ids[0]

    fallback = _run_command(
        [DOCKER_BIN, "ps", "-aq", "--filter", f"label=com.docker.swarm.service.name={RUNTIME_SERVICE_NAME}"],
        timeout=20.0,
    )
    if fallback.returncode != 0:
        detail = _decode_bytes(fallback.stderr or fallback.stdout).strip()
        raise GatewayError(f"docker_ps_all_failed:{detail or 'unknown error'}")
    container_ids = [line.strip() for line in _decode_bytes(fallback.stdout).splitlines() if line.strip()]
    if not container_ids:
        raise GatewayError("runtime_container_not_found")
    return container_ids[0]


def _read_runtime_logs() -> str:
    container_id = _runtime_container_id()
    result = _run_command([DOCKER_BIN, "logs", container_id], timeout=20.0)
    if result.returncode != 0:
        detail = _decode_bytes(result.stderr or result.stdout).strip()
        raise GatewayError(f"docker_logs_failed:{detail or 'unknown error'}")
    return (_decode_bytes(result.stdout) + _decode_bytes(result.stderr)).replace("\r\n", "\n")


def _exec_once(command: str) -> dict[str, Any]:
    container_id = _runtime_container_id()
    result = _run_command([DOCKER_BIN, "exec", container_id, "sh", "-lc", command], timeout=60.0)
    return {
        "ok": result.returncode == 0,
        "command": command,
        "stdout": _decode_bytes(result.stdout),
        "stderr": _decode_bytes(result.stderr),
        "exit_code": int(result.returncode),
        "container_id": container_id,
    }


def _normalize_remote_path(remote_path: str) -> str:
    normalized = str(remote_path or "").strip()
    if not normalized:
        raise GatewayError("remote_path_missing")
    if not normalized.startswith("/"):
        normalized = f"/{normalized.lstrip('/')}"
    return normalized


def _path_size_bytes(path: Path) -> int:
    if path.is_file():
        return int(path.stat().st_size)
    return sum(int(item.stat().st_size) for item in path.rglob("*") if item.is_file())


def _ensure_remote_directory(container_id: str, remote_path: str) -> None:
    command = f"mkdir -p {shlex.quote(remote_path)}"
    result = _run_command([DOCKER_BIN, "exec", container_id, "sh", "-lc", command], timeout=30.0)
    if result.returncode != 0:
        detail = _decode_bytes(result.stderr or result.stdout).strip()
        raise GatewayError(f"docker_exec_mkdir_failed:{detail or 'unknown error'}")


def _single_extracted_entry(root: Path) -> Path:
    entries = [item for item in root.iterdir()]
    if len(entries) != 1:
        raise GatewayError("upload_archive_invalid_layout")
    return entries[0]


def _upload_archive(remote_path: str, archive_base64: str) -> dict[str, Any]:
    container_id = _runtime_container_id()
    normalized_remote_path = _normalize_remote_path(remote_path)
    raw_archive = base64.b64decode(archive_base64)
    with tempfile.TemporaryDirectory(prefix="pivot-gateway-upload-") as temp_dir:
        temp_root = Path(temp_dir)
        with tarfile.open(fileobj=BytesIO(raw_archive), mode="r:*") as archive:
            archive.extractall(temp_root, filter="data")
        source_path = _single_extracted_entry(temp_root)
        _ensure_remote_directory(container_id, normalized_remote_path)
        result = _run_command(
            [DOCKER_BIN, "cp", str(source_path), f"{container_id}:{normalized_remote_path}"],
            timeout=120.0,
        )
        if result.returncode != 0:
            detail = _decode_bytes(result.stderr or result.stdout).strip()
            raise GatewayError(f"docker_cp_upload_failed:{detail or 'unknown error'}")
        uploaded_path = f"{normalized_remote_path.rstrip('/')}/{source_path.name}"
        return {
            "ok": True,
            "remote_path": normalized_remote_path,
            "uploaded_path": uploaded_path,
            "entry_name": source_path.name,
            "is_dir": source_path.is_dir(),
            "size_bytes": _path_size_bytes(source_path),
            "container_id": container_id,
        }


def _download_path(remote_path: str) -> dict[str, Any]:
    container_id = _runtime_container_id()
    normalized_remote_path = _normalize_remote_path(remote_path)
    default_name = Path(normalized_remote_path.rstrip("/")).name or "download"
    with tempfile.TemporaryDirectory(prefix="pivot-gateway-download-") as temp_dir:
        temp_root = Path(temp_dir)
        destination = temp_root / default_name
        result = _run_command(
            [DOCKER_BIN, "cp", f"{container_id}:{normalized_remote_path}", str(destination)],
            timeout=120.0,
        )
        if result.returncode != 0:
            detail = _decode_bytes(result.stderr or result.stdout).strip()
            raise GatewayError(f"docker_cp_download_failed:{detail or 'unknown error'}")
        buffer = BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            archive.add(destination, arcname=destination.name)
        return {
            "ok": True,
            "path": normalized_remote_path,
            "entry_name": destination.name,
            "is_dir": destination.is_dir(),
            "size_bytes": _path_size_bytes(destination),
            "archive_base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
            "container_id": container_id,
        }


app = FastAPI(title="Pivot Windows Session Gateway Host")


@app.get("/")
async def read_health(request: Request) -> dict[str, Any]:
    _authorize_http(request)
    return {
        "ok": True,
        "session_id": SESSION_ID,
        "runtime_service_name": RUNTIME_SERVICE_NAME,
        "buyer_user_id": BUYER_USER_ID,
        "seller_node_id": SELLER_NODE_ID,
        "gateway_service_name": GATEWAY_SERVICE_NAME,
        "supported_features": SUPPORTED_FEATURES,
        "status": "online",
        "gateway_mode": "windows_host_bridge",
    }


@app.post("/exec")
async def exec_command(payload: ExecRequest, request: Request) -> dict[str, Any]:
    _authorize_http(request)
    try:
        return _exec_once(payload.command)
    except GatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/logs")
async def read_logs(
    request: Request,
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict[str, Any]:
    _authorize_http(request)
    try:
        logs = _read_runtime_logs()
    except GatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    lines = logs.splitlines()
    start = min(cursor, len(lines))
    end = min(start + limit, len(lines))
    excerpt = lines[start:end]
    return {
        "ok": True,
        "cursor": cursor,
        "next_cursor": end,
        "total_lines": len(lines),
        "logs": "\n".join(excerpt),
        "lines": excerpt,
    }


@app.post("/files/upload")
async def upload_files(payload: UploadRequest, request: Request) -> dict[str, Any]:
    _authorize_http(request)
    try:
        return _upload_archive(payload.remote_path, payload.archive_base64)
    except GatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/files/download")
async def download_files(
    request: Request,
    path: str = Query(min_length=1),
) -> dict[str, Any]:
    _authorize_http(request)
    try:
        return _download_path(path)
    except GatewayError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.websocket("/shell/ws")
async def shell_websocket(websocket: WebSocket) -> None:
    if not _authorize_websocket(websocket):
        await websocket.close(code=4401)
        return
    await websocket.accept()

    try:
        container_id = _runtime_container_id()
        process = await asyncio.create_subprocess_exec(
            DOCKER_BIN,
            "exec",
            "-i",
            container_id,
            "sh",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except Exception as exc:  # noqa: BLE001
        await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
        await websocket.close(code=1011)
        return

    stop_event = asyncio.Event()

    async def browser_to_runtime() -> None:
        try:
            while not stop_event.is_set():
                message = await websocket.receive_text()
                payload = json.loads(message)
                if payload.get("type") == "input":
                    if process.stdin:
                        process.stdin.write(str(payload.get("data") or "").encode("utf-8"))
                        await process.stdin.drain()
                elif payload.get("type") == "close":
                    break
        except WebSocketDisconnect:
            pass
        finally:
            stop_event.set()

    async def runtime_to_browser() -> None:
        try:
            while not stop_event.is_set():
                if process.stdout is None:
                    break
                chunk = await process.stdout.read(4096)
                if not chunk:
                    break
                await websocket.send_text(json.dumps({"type": "output", "data": chunk.decode("utf-8", "replace")}))
        finally:
            stop_event.set()

    browser_task = asyncio.create_task(browser_to_runtime())
    runtime_task = asyncio.create_task(runtime_to_browser())
    await stop_event.wait()
    for task in (browser_task, runtime_task):
        task.cancel()
    await asyncio.gather(browser_task, runtime_task, return_exceptions=True)

    if process.stdin:
        try:
            process.stdin.close()
        except Exception:
            pass
    try:
        await asyncio.wait_for(process.wait(), timeout=3)
    except asyncio.TimeoutError:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=3)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()

    try:
        await websocket.send_text(json.dumps({"type": "exit", "exit_code": int(process.returncode or 0)}))
    except Exception:
        pass
    try:
        await websocket.close()
    except Exception:
        pass


def main() -> None:
    gateway_port = int(os.environ.get("PIVOT_GATEWAY_PORT", "0"))
    uvicorn.run(app, host=LISTEN_HOST, port=gateway_port, log_level="warning")


if __name__ == "__main__":
    main()
