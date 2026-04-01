from __future__ import annotations

from textwrap import dedent


def build_session_gateway_script() -> str:
    return dedent(
        """
        import asyncio
        import base64
        import http.client
        import json
        import os
        import posixpath
        import shlex
        import socket
        import stat
        import tarfile
        from io import BytesIO
        from typing import Any
        from urllib.parse import quote

        import uvicorn
        from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
        from pydantic import BaseModel, Field

        API_VERSION = "v1.43"
        DOCKER_SOCKET_PATH = "/var/run/docker.sock"
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


        class UnixSocketHTTPConnection(http.client.HTTPConnection):
            def __init__(self, unix_socket_path: str):
                super().__init__("localhost")
                self.unix_socket_path = unix_socket_path

            def connect(self) -> None:
                self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.sock.settimeout(30)
                self.sock.connect(self.unix_socket_path)


        class ExecRequest(BaseModel):
            command: str = Field(min_length=1, max_length=4000)


        class UploadRequest(BaseModel):
            remote_path: str = Field(min_length=1, max_length=2000)
            archive_base64: str = Field(min_length=8)


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


        def _docker_request(
            method: str,
            path: str,
            *,
            payload: dict[str, Any] | None = None,
            body: bytes | None = None,
            headers: dict[str, str] | None = None,
        ) -> tuple[int, dict[str, str], bytes]:
            request_headers = {"Host": "localhost"}
            if headers:
                request_headers.update(headers)
            request_body = body
            if payload is not None:
                request_body = json.dumps(payload).encode("utf-8")
                request_headers["Content-Type"] = "application/json"
            if request_body is not None:
                request_headers["Content-Length"] = str(len(request_body))
            connection = UnixSocketHTTPConnection(DOCKER_SOCKET_PATH)
            try:
                connection.request(method, f"/{API_VERSION}{path}", body=request_body, headers=request_headers)
                response = connection.getresponse()
                response_headers = {key.lower(): value for key, value in response.getheaders()}
                return response.status, response_headers, response.read()
            finally:
                connection.close()


        def _docker_json(
            method: str,
            path: str,
            *,
            payload: dict[str, Any] | None = None,
            expected_statuses: tuple[int, ...] = (200, 201, 204),
        ) -> Any:
            status, _, raw_body = _docker_request(method, path, payload=payload)
            if status not in expected_statuses:
                detail = raw_body.decode("utf-8", "replace").strip()
                raise GatewayError(f"docker_api_{method.lower()}_{path}_failed:{status}:{detail}")
            if not raw_body:
                return {}
            return json.loads(raw_body.decode("utf-8"))


        def _runtime_container_id() -> str:
            filters = quote(
                json.dumps({"label": [f"com.docker.swarm.service.name={RUNTIME_SERVICE_NAME}"]}),
                safe="",
            )
            containers = _docker_json("GET", f"/containers/json?all=1&filters={filters}")
            if not isinstance(containers, list) or not containers:
                raise GatewayError("runtime_container_not_found")
            running = [item for item in containers if str(item.get("State") or "").lower() == "running"]
            ordered = running or containers
            ordered.sort(key=lambda item: int(item.get("Created") or 0), reverse=True)
            container_id = str(ordered[0].get("Id") or "")
            if not container_id:
                raise GatewayError("runtime_container_id_missing")
            return container_id


        def _docker_exec_create(container_id: str, command: list[str], *, attach_stdin: bool, tty: bool) -> str:
            payload = {
                "AttachStdout": True,
                "AttachStderr": True,
                "AttachStdin": attach_stdin,
                "Tty": tty,
                "Cmd": command,
            }
            response = _docker_json("POST", f"/containers/{container_id}/exec", payload=payload, expected_statuses=(201,))
            exec_id = str(response.get("Id") or "")
            if not exec_id:
                raise GatewayError("docker_exec_create_missing_id")
            return exec_id


        def _docker_exec_start(exec_id: str, *, tty: bool) -> bytes:
            status, _, raw_body = _docker_request(
                "POST",
                f"/exec/{exec_id}/start",
                payload={"Detach": False, "Tty": tty},
            )
            if status != 200:
                detail = raw_body.decode("utf-8", "replace").strip()
                raise GatewayError(f"docker_exec_start_failed:{status}:{detail}")
            return raw_body


        def _docker_exec_inspect(exec_id: str) -> dict[str, Any]:
            response = _docker_json("GET", f"/exec/{exec_id}/json")
            if not isinstance(response, dict):
                raise GatewayError("docker_exec_inspect_invalid_payload")
            return response


        def _docker_exec_resize(exec_id: str, rows: int, cols: int) -> None:
            status, _, raw_body = _docker_request("POST", f"/exec/{exec_id}/resize?h={rows}&w={cols}")
            if status not in (200, 201):
                detail = raw_body.decode("utf-8", "replace").strip()
                raise GatewayError(f"docker_exec_resize_failed:{status}:{detail}")


        def _docker_exec_start_socket(exec_id: str, *, tty: bool) -> tuple[socket.socket, bytes]:
            payload = json.dumps({"Detach": False, "Tty": tty}).encode("utf-8")
            raw_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            raw_socket.settimeout(30)
            raw_socket.connect(DOCKER_SOCKET_PATH)
            request = (
                f"POST /{API_VERSION}/exec/{exec_id}/start HTTP/1.1\\r\\n"
                "Host: localhost\\r\\n"
                "Content-Type: application/json\\r\\n"
                f"Content-Length: {len(payload)}\\r\\n"
                "Connection: Upgrade\\r\\n"
                "Upgrade: tcp\\r\\n"
                "\\r\\n"
            ).encode("utf-8") + payload
            raw_socket.sendall(request)
            header = b""
            while b"\\r\\n\\r\\n" not in header:
                chunk = raw_socket.recv(4096)
                if not chunk:
                    raise GatewayError("docker_exec_socket_closed_during_handshake")
                header += chunk
            response_head, remainder = header.split(b"\\r\\n\\r\\n", 1)
            status_line = response_head.splitlines()[0] if response_head else b""
            if b"101" not in status_line and b"200" not in status_line:
                raise GatewayError(f"docker_exec_socket_failed:{status_line.decode('utf-8', 'replace')}")
            raw_socket.settimeout(None)
            return raw_socket, remainder


        def _decode_stream_chunk(raw_body: bytes) -> tuple[str, str]:
            stdout = bytearray()
            stderr = bytearray()
            index = 0
            while index + 8 <= len(raw_body):
                stream_type = raw_body[index]
                size = int.from_bytes(raw_body[index + 4 : index + 8], byteorder="big", signed=False)
                start = index + 8
                end = start + size
                if stream_type not in (0, 1, 2) or end > len(raw_body):
                    text = raw_body.decode("utf-8", "replace")
                    return text, ""
                chunk = raw_body[start:end]
                if stream_type == 2:
                    stderr.extend(chunk)
                else:
                    stdout.extend(chunk)
                index = end
            if index == len(raw_body) and (stdout or stderr):
                return stdout.decode("utf-8", "replace"), stderr.decode("utf-8", "replace")
            text = raw_body.decode("utf-8", "replace")
            return text, ""


        def _read_runtime_logs() -> str:
            container_id = _runtime_container_id()
            status, _, raw_body = _docker_request(
                "GET",
                f"/containers/{container_id}/logs?stdout=1&stderr=1&timestamps=0",
            )
            if status != 200:
                detail = raw_body.decode("utf-8", "replace").strip()
                raise GatewayError(f"docker_logs_failed:{status}:{detail}")
            stdout, stderr = _decode_stream_chunk(raw_body)
            return (stdout + stderr).replace("\\r\\n", "\\n")


        def _exec_once(command: str) -> dict[str, Any]:
            container_id = _runtime_container_id()
            exec_id = _docker_exec_create(container_id, ["sh", "-lc", command], attach_stdin=False, tty=False)
            raw_body = _docker_exec_start(exec_id, tty=False)
            inspect = _docker_exec_inspect(exec_id)
            stdout, stderr = _decode_stream_chunk(raw_body)
            return {
                "ok": int(inspect.get("ExitCode") or 0) == 0,
                "command": command,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": int(inspect.get("ExitCode") or 0),
                "container_id": container_id,
            }


        def _normalize_remote_path(remote_path: str) -> str:
            normalized = str(remote_path or "").strip()
            if not normalized:
                raise GatewayError("remote_path_missing")
            if not normalized.startswith("/"):
                normalized = f"/{normalized.lstrip('/')}"
            return normalized


        def _ensure_remote_directory(container_id: str, remote_path: str) -> None:
            exec_id = _docker_exec_create(
                container_id,
                ["sh", "-lc", f"mkdir -p {shlex.quote(remote_path)}"],
                attach_stdin=False,
                tty=False,
            )
            _docker_exec_start(exec_id, tty=False)
            inspect = _docker_exec_inspect(exec_id)
            if int(inspect.get("ExitCode") or 0) != 0:
                raise GatewayError("docker_mkdir_remote_failed")


        def _archive_top_level_details(raw_archive: bytes) -> tuple[str, bool, int]:
            with tarfile.open(fileobj=BytesIO(raw_archive), mode="r:*") as archive:
                members = [member for member in archive.getmembers() if member.name and member.name != "."]
                if not members:
                    raise GatewayError("upload_archive_empty")
                top_level = sorted({member.name.split("/", 1)[0] for member in members})
                if len(top_level) != 1:
                    raise GatewayError("upload_archive_invalid_layout")
                entry_name = top_level[0]
                matching_members = [
                    member for member in members if member.name == entry_name or member.name.startswith(f"{entry_name}/")
                ]
                is_dir = any(member.isdir() for member in matching_members) or len(matching_members) > 1
                size_bytes = sum(int(member.size or 0) for member in matching_members if member.isfile())
                return entry_name, is_dir, size_bytes


        def _docker_upload_archive(container_id: str, remote_path: str, raw_archive: bytes) -> None:
            status, _, raw_body = _docker_request(
                "PUT",
                f"/containers/{container_id}/archive?path={quote(remote_path, safe='/')}",
                body=raw_archive,
                headers={"Content-Type": "application/x-tar"},
            )
            if status != 200:
                detail = raw_body.decode("utf-8", "replace").strip()
                raise GatewayError(f"docker_upload_archive_failed:{status}:{detail}")


        def _docker_download_archive(container_id: str, remote_path: str) -> tuple[bytes, dict[str, Any]]:
            status, headers, raw_body = _docker_request(
                "GET",
                f"/containers/{container_id}/archive?path={quote(remote_path, safe='/')}",
            )
            if status != 200:
                detail = raw_body.decode("utf-8", "replace").strip()
                raise GatewayError(f"docker_download_archive_failed:{status}:{detail}")
            header_value = headers.get("x-docker-container-path-stat") or ""
            if not header_value:
                return raw_body, {}
            decoded = base64.b64decode(header_value).decode("utf-8", "replace")
            path_stat = json.loads(decoded)
            if not isinstance(path_stat, dict):
                return raw_body, {}
            return raw_body, path_stat


        def _upload_archive(remote_path: str, archive_base64: str) -> dict[str, Any]:
            container_id = _runtime_container_id()
            normalized_remote_path = _normalize_remote_path(remote_path)
            raw_archive = base64.b64decode(archive_base64)
            entry_name, is_dir, size_bytes = _archive_top_level_details(raw_archive)
            _ensure_remote_directory(container_id, normalized_remote_path)
            _docker_upload_archive(container_id, normalized_remote_path, raw_archive)
            uploaded_path = posixpath.join(normalized_remote_path.rstrip("/") or "/", entry_name)
            return {
                "ok": True,
                "remote_path": normalized_remote_path,
                "uploaded_path": uploaded_path,
                "entry_name": entry_name,
                "is_dir": is_dir,
                "size_bytes": size_bytes,
                "container_id": container_id,
            }


        def _download_path(remote_path: str) -> dict[str, Any]:
            container_id = _runtime_container_id()
            normalized_remote_path = _normalize_remote_path(remote_path)
            raw_archive, path_stat = _docker_download_archive(container_id, normalized_remote_path)
            path_mode = int(path_stat.get("mode") or 0)
            entry_name = str(path_stat.get("name") or posixpath.basename(normalized_remote_path.rstrip("/")) or "download")
            is_dir = stat.S_ISDIR(path_mode)
            size_bytes = int(path_stat.get("size") or 0)
            if size_bytes <= 0:
                with tarfile.open(fileobj=BytesIO(raw_archive), mode="r:*") as archive:
                    size_bytes = sum(int(member.size or 0) for member in archive.getmembers() if member.isfile())
            return {
                "ok": True,
                "path": normalized_remote_path,
                "entry_name": entry_name,
                "is_dir": is_dir,
                "size_bytes": size_bytes,
                "archive_base64": base64.b64encode(raw_archive).decode("ascii"),
                "container_id": container_id,
            }


        app = FastAPI(title="Pivot Session Gateway")


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
                "logs": "\\n".join(excerpt),
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
                exec_id = _docker_exec_create(container_id, ["sh"], attach_stdin=True, tty=True)
                raw_socket, initial_remainder = await asyncio.to_thread(_docker_exec_start_socket, exec_id, tty=True)
                initial_rows = int(websocket.query_params.get("rows") or 24)
                initial_cols = int(websocket.query_params.get("cols") or 80)
                await asyncio.to_thread(_docker_exec_resize, exec_id, initial_rows, initial_cols)
            except Exception as exc:
                await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
                await websocket.close(code=1011)
                return

            stop_event = asyncio.Event()

            async def bridge_browser_to_runtime() -> None:
                try:
                    while not stop_event.is_set():
                        message = await websocket.receive_text()
                        payload = json.loads(message)
                        if payload.get("type") == "input":
                            await asyncio.to_thread(
                                raw_socket.sendall,
                                str(payload.get("data") or "").encode("utf-8"),
                            )
                        elif payload.get("type") == "resize":
                            rows = max(1, int(payload.get("rows") or 24))
                            cols = max(1, int(payload.get("cols") or 80))
                            await asyncio.to_thread(_docker_exec_resize, exec_id, rows, cols)
                        elif payload.get("type") == "close":
                            break
                except WebSocketDisconnect:
                    pass
                except Exception as exc:
                    try:
                        await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
                    except Exception:
                        pass
                finally:
                    stop_event.set()


            async def bridge_runtime_to_browser() -> None:
                try:
                    if initial_remainder:
                        await websocket.send_text(
                            json.dumps({"type": "output", "data": initial_remainder.decode("utf-8", "replace")})
                        )
                    while not stop_event.is_set():
                        chunk = await asyncio.to_thread(raw_socket.recv, 4096)
                        if not chunk:
                            break
                        await websocket.send_text(
                            json.dumps({"type": "output", "data": chunk.decode("utf-8", "replace")})
                        )
                except Exception as exc:
                    try:
                        await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
                    except Exception:
                        pass
                finally:
                    stop_event.set()


            browser_task = asyncio.create_task(bridge_browser_to_runtime())
            runtime_task = asyncio.create_task(bridge_runtime_to_browser())
            await stop_event.wait()
            for task in (browser_task, runtime_task):
                task.cancel()
            try:
                raw_socket.close()
            except Exception:
                pass

            try:
                inspect = await asyncio.to_thread(_docker_exec_inspect, exec_id)
                await websocket.send_text(
                    json.dumps({"type": "exit", "exit_code": int(inspect.get("ExitCode") or 0)})
                )
            except Exception:
                pass
            try:
                await websocket.close()
            except Exception:
                pass


        if __name__ == "__main__":
            gateway_port = int(os.environ.get("PIVOT_GATEWAY_PORT", "0"))
            uvicorn.run(app, host="0.0.0.0", port=gateway_port, log_level="warning")
        """
    ).strip()
