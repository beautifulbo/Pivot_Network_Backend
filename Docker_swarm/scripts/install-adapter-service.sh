#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/common.sh"

load_env

SERVICE_NAME="pivot-swarm-adapter.service"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}"
PYTHON_BIN="${ADAPTER_PYTHON_BIN:-python3.11}"
VENV_PATH="${REPO_ROOT}/.venv-swarm-adapter"
BACKEND_DIR="${REPO_ROOT}/backend"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  dnf install -y python3.11 python3.11-pip >/dev/null || dnf install -y python3.11 >/dev/null
fi

"$PYTHON_BIN" -m venv "$VENV_PATH"
"$VENV_PATH/bin/python" -m pip install --upgrade pip >/dev/null
"$VENV_PATH/bin/pip" install -e "$BACKEND_DIR" >/dev/null

cat >"$SERVICE_PATH" <<EOF
[Unit]
Description=Pivot Docker Swarm Adapter
After=network-online.target docker.service wg-quick@wg0.service
Wants=network-online.target
Requires=docker.service

[Service]
Type=simple
User=root
WorkingDirectory=${BACKEND_DIR}
Environment=PYTHONPATH=${BACKEND_DIR}
Environment=SWARM_ADAPTER_BASE_URL=
Environment=SWARM_MANAGER_LOCAL_MODE=true
Environment=WIREGUARD_SERVER_LOCAL_MODE=true
Environment=WIREGUARD_SERVER_SSH_ENABLED=false
EnvironmentFile=${ENV_FILE}
ExecStart=${VENV_PATH}/bin/uvicorn app.swarm_adapter_main:app --host 0.0.0.0 --port 8010
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "$SERVICE_NAME"
systemctl --no-pager --full status "$SERVICE_NAME" | sed -n '1,40p'
curl -fsS http://127.0.0.1:8010/health
