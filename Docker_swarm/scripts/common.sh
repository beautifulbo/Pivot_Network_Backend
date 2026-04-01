#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SWARM_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd -- "$SWARM_DIR/.." && pwd)"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/.env}"
DEFAULT_APP_STACK_NAME="pivot-backend-build-team"
DEFAULT_PORTAINER_STACK_NAME="portainer"
DEFAULT_BENCHMARK_STACK_NAME="pivot-benchmark"
LOCAL_REGISTRY_NAME="${LOCAL_REGISTRY_NAME:-pivot-swarm-registry}"
LOCAL_REGISTRY_PORT="${LOCAL_REGISTRY_PORT:-5000}"

default_registry_host() {
  echo "pivotcompute.store"
}

normalize_registry_host() {
  local registry_host="$1"

  case "${registry_host,,}" in
    ""|"pivotcompute.store"|"https://pivotcompute.store"|"pivotcompute.store:443"|"https://pivotcompute.store:443"|"81.70.52.75"|"81.70.52.75:5000"|"https://81.70.52.75:5000"|"http://81.70.52.75:5000")
      echo "pivotcompute.store"
      ;;
    *)
      echo "$registry_host"
      ;;
  esac
}

load_env() {
  if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
  fi

  export REGISTRY_HOST="$(normalize_registry_host "${REGISTRY_HOST:-$(default_registry_host)}")"
  export REGISTRY_BIND_IP="${REGISTRY_BIND_IP:-0.0.0.0}"
  export BACKEND_SWARM_IMAGE="${BACKEND_SWARM_IMAGE:-$REGISTRY_HOST/pivot-backend-build-team/backend:swarm-local}"
  export BENCHMARK_SWARM_IMAGE="${BENCHMARK_SWARM_IMAGE:-$REGISTRY_HOST/pivot-backend-build-team/benchmark-worker:swarm-local}"
  export STACK_NAME="${STACK_NAME:-$DEFAULT_APP_STACK_NAME}"
  export PORTAINER_STACK_NAME="${PORTAINER_STACK_NAME:-$DEFAULT_PORTAINER_STACK_NAME}"
  export BENCHMARK_STACK_NAME="${BENCHMARK_STACK_NAME:-$DEFAULT_BENCHMARK_STACK_NAME}"
  export PORTAINER_AGENT_IMAGE="${PORTAINER_AGENT_IMAGE:-$REGISTRY_HOST/portainer/agent:lts}"
  export PORTAINER_SERVER_IMAGE="${PORTAINER_SERVER_IMAGE:-$REGISTRY_HOST/portainer/portainer-ce:lts}"
  export BENCHMARK_JOB_ID="${BENCHMARK_JOB_ID:-bench-local-001}"
  export BENCHMARK_LISTING_ID="${BENCHMARK_LISTING_ID:-listing-local-001}"
  export BENCHMARK_REQUESTED_PROFILE="${BENCHMARK_REQUESTED_PROFILE:-cpu-small}"
  export BENCHMARK_KEEPALIVE_SECONDS="${BENCHMARK_KEEPALIVE_SECONDS:-1800}"
  export LOCAL_SELLER_NODE_NAME="${LOCAL_SELLER_NODE_NAME:-seller-local-001}"
  export LOCAL_SELLER_CONTAINER_NAME="${LOCAL_SELLER_CONTAINER_NAME:-pivot-local-seller-node}"
  export LOCAL_SELLER_DOCKER_VOLUME="${LOCAL_SELLER_DOCKER_VOLUME:-pivot-local-seller-node-data}"
  export LOCAL_SELLER_NODE_CPUS="${LOCAL_SELLER_NODE_CPUS:-1.0}"
  export LOCAL_SELLER_NODE_MEMORY="${LOCAL_SELLER_NODE_MEMORY:-1024m}"
  export LOCAL_SELLER_DOCKER_IMAGE="${LOCAL_SELLER_DOCKER_IMAGE:-docker:26.1-dind}"
  export LOCAL_SELLER_COMPUTE_NODE_ID="${LOCAL_SELLER_COMPUTE_NODE_ID:-compute-local-001}"
  export LOCAL_SELLER_USER_ID="${LOCAL_SELLER_USER_ID:-seller-local-001}"
  export LOCAL_SELLER_ACCELERATOR="${LOCAL_SELLER_ACCELERATOR:-cpu}"
  export BENCHMARK_TARGET_COMPUTE_NODE_ID="${BENCHMARK_TARGET_COMPUTE_NODE_ID:-$LOCAL_SELLER_COMPUTE_NODE_ID}"
}

require_swarm_active() {
  local state
  state="$(docker info --format '{{.Swarm.LocalNodeState}}')"
  if [[ "$state" != "active" ]]; then
    echo "Docker Swarm is not active on this machine. Run init-manager.sh first." >&2
    exit 1
  fi
}

manager_addr() {
  docker info --format '{{.Swarm.NodeAddr}}'
}

resolve_node_ref() {
  local ref="$1"

  if [[ "$ref" == "self" ]]; then
    docker info --format '{{.Swarm.NodeID}}'
    return 0
  fi

  local node_id
  node_id="$(docker node ls --format '{{.ID}} {{.Hostname}}' | awk -v ref="$ref" '$1 == ref || $2 == ref {print $1; exit}')"

  if [[ -z "$node_id" ]]; then
    echo "Unable to resolve node reference: $ref" >&2
    exit 1
  fi

  echo "$node_id"
}

node_hostname() {
  docker node inspect "$1" --format '{{.Description.Hostname}}'
}

node_role() {
  docker node inspect "$1" --format '{{.Spec.Role}}'
}

node_status() {
  docker node inspect "$1" --format '{{.Status.State}}'
}

node_availability() {
  docker node inspect "$1" --format '{{.Spec.Availability}}'
}

node_label() {
  local node_id="$1"
  local key="$2"

  docker node inspect "$node_id" --format "{{index .Spec.Labels \"$key\"}}"
}

is_truthy() {
  case "${1,,}" in
    true|1|yes)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

is_control_plane_node() {
  local node_id="$1"
  local role
  local platform_role
  local control_plane

  role="$(node_role "$node_id")"
  platform_role="$(node_label "$node_id" "platform.role")"
  control_plane="$(node_label "$node_id" "platform.control_plane")"

  if [[ "$role" == "manager" ]] || [[ "$platform_role" == "control-plane" ]] || is_truthy "$control_plane"; then
    return 0
  fi

  return 1
}

find_node_with_compute_node_id() {
  local compute_node_id="$1"
  local exclude_node_id="${2:-}"
  local node_id
  local current_compute_node_id

  while IFS= read -r node_id; do
    [[ -z "$node_id" ]] && continue
    [[ -n "$exclude_node_id" && "$node_id" == "$exclude_node_id" ]] && continue

    current_compute_node_id="$(node_label "$node_id" "platform.compute_node_id")"
    if [[ "$current_compute_node_id" == "$compute_node_id" ]]; then
      echo "$node_id"
      return 0
    fi
  done < <(docker node ls -q)

  return 1
}

ensure_no_running_replicated_tasks() {
  local node_id="$1"
  local task_name
  local desired_state
  local current_state
  local service_name
  local service_mode

  while IFS='|' read -r task_name desired_state current_state; do
    [[ -z "$task_name" ]] && continue
    [[ "$desired_state" != "Running" ]] && continue

    service_name="${task_name%.*}"
    service_mode="$(docker service inspect "$service_name" --format '{{if .Spec.Mode.Global}}global{{else}}replicated{{end}}')"
    if [[ "$service_mode" != "global" ]]; then
      echo "Refusing to drain node $(node_hostname "$node_id"): running replicated task $task_name ($current_state)." >&2
      return 1
    fi
  done < <(docker node ps "$node_id" --format '{{.Name}}|{{.DesiredState}}|{{.CurrentState}}')
}

ensure_local_registry() {
  local running
  local current_binding=""
  local desired_binding="${REGISTRY_BIND_IP}:${LOCAL_REGISTRY_PORT}"

  running="$(docker inspect --format '{{.State.Running}}' "$LOCAL_REGISTRY_NAME" 2>/dev/null || true)"
  current_binding="$(docker inspect --format '{{with (index .HostConfig.PortBindings "5000/tcp")}}{{(index . 0).HostIp}}:{{(index . 0).HostPort}}{{end}}' "$LOCAL_REGISTRY_NAME" 2>/dev/null || true)"

  if [[ "$current_binding" == ":${LOCAL_REGISTRY_PORT}" ]]; then
    current_binding="0.0.0.0:${LOCAL_REGISTRY_PORT}"
  fi

  if [[ "$running" == "true" && "$current_binding" == "$desired_binding" ]]; then
    return 0
  fi

  if docker inspect "$LOCAL_REGISTRY_NAME" >/dev/null 2>&1; then
    docker rm -f "$LOCAL_REGISTRY_NAME" >/dev/null
  fi

  docker run -d \
    --restart unless-stopped \
    --name "$LOCAL_REGISTRY_NAME" \
    -p "${REGISTRY_BIND_IP}:${LOCAL_REGISTRY_PORT}:5000" \
    registry:2 >/dev/null
}

cache_image_in_local_registry() {
  local upstream_image="$1"
  local cached_image="$2"

  docker pull "$upstream_image"
  docker tag "$upstream_image" "$cached_image"
  docker push "$cached_image"
}
