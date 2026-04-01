from app.services.session_gateway_template import build_session_gateway_script
from app.services.swarm_manager import _session_gateway_entrypoint


def test_session_gateway_entrypoint_writes_script_without_indentation() -> None:
    entrypoint = _session_gateway_entrypoint(build_session_gateway_script())

    assert "cat >/tmp/pivot-session-gateway.py <<'PY'\nimport asyncio\n" in entrypoint
    assert "python /tmp/pivot-session-gateway.py" in entrypoint
    assert "python - <<'PY'" not in entrypoint

