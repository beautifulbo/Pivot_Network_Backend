from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from app.core.config import Settings


class AdapterClientError(RuntimeError):
    pass


def adapter_enabled(settings: Settings) -> bool:
    return bool(settings.SWARM_ADAPTER_BASE_URL.strip())


def adapter_request(
    settings: Settings,
    *,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_url = settings.SWARM_ADAPTER_BASE_URL.rstrip("/")
    if not base_url:
        raise AdapterClientError("swarm_adapter_base_url_not_configured")

    url = f"{base_url}{path if path.startswith('/') else '/' + path}"
    headers = {"Accept": "application/json"}
    if settings.SWARM_ADAPTER_TOKEN:
        headers["X-Pivot-Adapter-Token"] = settings.SWARM_ADAPTER_TOKEN

    body: bytes | None = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(url, data=body, headers=headers, method=method.upper())

    try:
        with urllib.request.urlopen(request, timeout=settings.SWARM_ADAPTER_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8", "replace").strip()
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace").strip()
        detail = _extract_error_detail(raw) or getattr(exc, "reason", "") or f"http_{exc.code}"
        raise AdapterClientError(detail) from exc
    except urllib.error.URLError as exc:
        raise AdapterClientError(f"adapter_unreachable: {exc.reason}") from exc

    if not raw:
        return {}

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AdapterClientError("adapter_invalid_json_response") from exc

    if not isinstance(parsed, dict):
        raise AdapterClientError("adapter_unexpected_response_payload")

    return parsed


def _extract_error_detail(raw: str) -> str:
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if isinstance(parsed, dict):
        detail = parsed.get("detail")
        if isinstance(detail, str):
            return detail
        return json.dumps(parsed, ensure_ascii=False)
    return raw
