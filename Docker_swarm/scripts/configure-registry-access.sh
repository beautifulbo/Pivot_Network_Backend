#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/common.sh"

load_env

registry_host="${1:-$REGISTRY_HOST}"
registry_host="$(normalize_registry_host "$registry_host")"
registry_url="https://${registry_host}/v2/"

echo "Using public HTTPS registry endpoint: ${registry_url}"
echo "No Docker insecure-registry or local CA installation is required."

if command -v curl >/dev/null 2>&1; then
  curl -fsS -I "$registry_url"
else
  echo "curl is not installed; skipped live probe." >&2
fi
