#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/common.sh"

load_env
require_swarm_active

container_name="${1:-$LOCAL_SELLER_CONTAINER_NAME}"
node_name="${2:-$LOCAL_SELLER_NODE_NAME}"
compute_node_id="${3:-$LOCAL_SELLER_COMPUTE_NODE_ID}"
seller_user_id="${4:-$LOCAL_SELLER_USER_ID}"
accelerator="${5:-$LOCAL_SELLER_ACCELERATOR}"
manager_ip="$(manager_addr)"
worker_token="$(docker swarm join-token --quiet worker)"

if ! docker inspect "$container_name" >/dev/null 2>&1; then
  docker volume create "$LOCAL_SELLER_DOCKER_VOLUME" >/dev/null

  docker run -d \
    --privileged \
    --restart unless-stopped \
    --name "$container_name" \
    --hostname "$node_name" \
    --cpus "$LOCAL_SELLER_NODE_CPUS" \
    --memory "$LOCAL_SELLER_NODE_MEMORY" \
    -e DOCKER_TLS_CERTDIR= \
    -v "$LOCAL_SELLER_DOCKER_VOLUME:/var/lib/docker" \
    "$LOCAL_SELLER_DOCKER_IMAGE" >/dev/null
fi

for _ in $(seq 1 60); do
  if docker exec "$container_name" docker info >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! docker exec "$container_name" docker info >/dev/null 2>&1; then
  echo "Local seller node Docker daemon did not become ready in time." >&2
  exit 1
fi

seller_state="$(docker exec "$container_name" docker info --format '{{.Swarm.LocalNodeState}}')"
if [[ "$seller_state" == "inactive" ]]; then
  docker exec "$container_name" docker swarm join --token "$worker_token" "$manager_ip:2377"
fi

for _ in $(seq 1 60); do
  if docker node ls --format '{{.Hostname}}' | grep -qx "$node_name"; then
    break
  fi
  sleep 1
done

if ! docker node ls --format '{{.Hostname}}' | grep -qx "$node_name"; then
  echo "Local seller node did not appear in swarm node list." >&2
  exit 1
fi

"$SCRIPT_DIR/label-compute-node.sh" "$node_name" "$compute_node_id" "$seller_user_id" "$accelerator"
