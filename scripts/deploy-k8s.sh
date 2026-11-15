#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
CHART_DIR="$REPO_DIR/deploy/helm/converter"
KIND_CLUSTER="${KIND_CLUSTER:-converter}"
KUBE_CONTEXT_OVERRIDE="${KUBE_CONTEXT:-}"
SECRET_ENV_FILE=""

usage() {
  cat >&2 <<EOF
Használat:
  $0 cluster [kind-klaszter]
  $0 build <verzió-tag> [kind-klaszter]
  $0 <development|staging> <verzió-tag> [kind-klaszter]
  $0 rollback <development|staging> <helm-revízió> [kind-klaszter]

A Kind-klaszter alapértelmezése: converter. A kubectl context alapértelmezése: kind-<klaszter>.
EOF
  exit 2
}

cleanup() {
  if [[ -n "$SECRET_ENV_FILE" ]]; then
    rm -f "$SECRET_ENV_FILE"
  fi
}
trap cleanup EXIT

require_commands() {
  local command_name
  for command_name in "$@"; do
    command -v "$command_name" >/dev/null 2>&1 || {
      echo "Hiba: a(z) $command_name parancs nem található." >&2
      exit 1
    }
  done
}

set_cluster_context() {
  KIND_CLUSTER="${1:-$KIND_CLUSTER}"
  KUBE_CONTEXT="${KUBE_CONTEXT_OVERRIDE:-kind-$KIND_CLUSTER}"
}

ensure_kind_cluster() {
  local clusters
  clusters="$(kind get clusters)"
  if grep -Fxq -- "$KIND_CLUSTER" <<< "$clusters"; then
    printf 'Meglévő Kind klaszter használata: %s\n' "$KIND_CLUSTER"
  else
    kind create cluster --name "$KIND_CLUSTER"
  fi
  kind export kubeconfig --name "$KIND_CLUSTER" >/dev/null
}

ensure_existing_kind_context() {
  local clusters
  clusters="$(kind get clusters)"
  if ! grep -Fxq -- "$KIND_CLUSTER" <<< "$clusters"; then
    printf 'Hiba: a(z) %s nevű Kind-klaszter nem létezik; rollback nem futtatható.\n' \
      "$KIND_CLUSTER" >&2
    exit 1
  fi
  kind export kubeconfig --name "$KIND_CLUSTER" >/dev/null
}

validate_image_tag() {
  local image_tag="$1"
  if [[ ! "$image_tag" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$ || "$image_tag" == "latest" ]]; then
    echo "Hiba: használj érvényes, a latest-től eltérő image taget." >&2
    exit 2
  fi
}

build_image() {
  local reference="$1"
  local context="$2"

  if docker image inspect "$reference" >/dev/null 2>&1; then
    printf 'Meglévő image megtartása: %s (új verzióhoz új tag szükséges)\n' "$reference"
  else
    docker build --pull -t "$reference" "$context"
  fi
}

build_and_load_images() {
  local image_tag="$1"
  build_image "converter-backend:$image_tag" "$REPO_DIR/backend"
  build_image "converter-frontend:$image_tag" "$REPO_DIR/frontend"
  kind load docker-image \
    "converter-backend:$image_tag" \
    "converter-frontend:$image_tag" \
    --name "$KIND_CLUSTER"
  printf 'Image-ek betöltve: converter-backend:%s, converter-frontend:%s\n' \
    "$image_tag" "$image_tag"
}

select_environment() {
  case "$1" in
    development)
      NAMESPACE="converter-dev"
      VALUES_FILE="$CHART_DIR/values-development.yaml"
      ;;
    staging)
      NAMESPACE="converter-staging"
      VALUES_FILE="$CHART_DIR/values-staging.yaml"
      ;;
    *) usage ;;
  esac
}

ensure_runtime_secret() {
  local postgres_password
  local jwt_secret_key
  local database_url

  if kubectl --context "$KUBE_CONTEXT" -n "$NAMESPACE" \
    get secret converter-runtime >/dev/null 2>&1; then
    postgres_password="$(kubectl --context "$KUBE_CONTEXT" -n "$NAMESPACE" \
      get secret converter-runtime -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 --decode)"
    jwt_secret_key="$(kubectl --context "$KUBE_CONTEXT" -n "$NAMESPACE" \
      get secret converter-runtime -o jsonpath='{.data.JWT_SECRET_KEY}' | base64 --decode)"
    if [[ -z "$postgres_password" || -z "$jwt_secret_key" ]]; then
      echo "Hiba: a converter-runtime Secretből hiányzik egy szükséges érték." >&2
      exit 1
    fi
    printf 'A meglévő Secret újrafelhasználása a(z) %s namespace-ben.\n' "$NAMESPACE"
  else
    require_commands openssl
    postgres_password="${POSTGRES_PASSWORD:-$(openssl rand -hex 32)}"
    jwt_secret_key="${JWT_SECRET_KEY:-$(openssl rand -hex 32)}"
  fi

  if [[ ${#jwt_secret_key} -lt 32 ]]; then
    echo "Hiba: a JWT_SECRET_KEY legalább 32 karakter legyen." >&2
    exit 2
  fi

  database_url="$(POSTGRES_PASSWORD="$postgres_password" python3 -c \
    'import os; from urllib.parse import quote; print("postgresql+psycopg://converter:" + quote(os.environ["POSTGRES_PASSWORD"], safe="") + "@db:5432/converter")')"

  umask 077
  SECRET_ENV_FILE="$(mktemp)"
  {
    printf 'POSTGRES_DB=converter\nPOSTGRES_USER=converter\n'
    printf 'POSTGRES_PASSWORD=%s\n' "$postgres_password"
    printf 'JWT_SECRET_KEY=%s\n' "$jwt_secret_key"
    printf 'DATABASE_URL=%s\n' "$database_url"
  } > "$SECRET_ENV_FILE"

  kubectl --context "$KUBE_CONTEXT" -n "$NAMESPACE" create secret generic converter-runtime \
    --from-env-file="$SECRET_ENV_FILE" \
    --dry-run=client -o yaml \
    | kubectl --context "$KUBE_CONTEXT" -n "$NAMESPACE" apply -f -
  rm -f "$SECRET_ENV_FILE"
  SECRET_ENV_FILE=""
}

print_deployment_diagnostics() {
  echo "A kiadás nem állt készen; Kubernetes állapot:" >&2
  kubectl --context "$KUBE_CONTEXT" -n "$NAMESPACE" get pods -o wide >&2 || true
  kubectl --context "$KUBE_CONTEXT" -n "$NAMESPACE" \
    get events --sort-by=.lastTimestamp | tail -25 >&2 || true

  local pod
  while IFS= read -r pod; do
    [[ -n "$pod" ]] || continue
    kubectl --context "$KUBE_CONTEXT" -n "$NAMESPACE" logs "$pod" \
      --all-containers=true --previous --tail=40 >&2 \
      || kubectl --context "$KUBE_CONTEXT" -n "$NAMESPACE" logs "$pod" \
        --all-containers=true --tail=40 >&2 \
      || true
  done < <(kubectl --context "$KUBE_CONTEXT" -n "$NAMESPACE" \
    get pods -l app.kubernetes.io/component=web -o name)
}

deploy_environment() {
  local environment="$1"
  local image_tag="$2"
  local cluster_name="${3:-$KIND_CLUSTER}"
  set_cluster_context "$cluster_name"
  select_environment "$environment"
  validate_image_tag "$image_tag"
  require_commands docker kind kubectl helm python3 base64 mktemp

  ensure_kind_cluster
  kubectl --context "$KUBE_CONTEXT" cluster-info >/dev/null
  build_and_load_images "$image_tag"

  kubectl --context "$KUBE_CONTEXT" create namespace "$NAMESPACE" \
    --dry-run=client -o yaml \
    | kubectl --context "$KUBE_CONTEXT" apply -f -
  ensure_runtime_secret

  helm lint "$CHART_DIR" --values "$VALUES_FILE" \
    --set-string "image.backend.tag=$image_tag" \
    --set-string "image.frontend.tag=$image_tag"

  if ! helm upgrade --install converter "$CHART_DIR" \
    --kube-context "$KUBE_CONTEXT" \
    --namespace "$NAMESPACE" \
    --values "$VALUES_FILE" \
    --set-string "image.backend.tag=$image_tag" \
    --set-string "image.frontend.tag=$image_tag" \
    --wait --timeout 5m; then
    print_deployment_diagnostics
    return 1
  fi

  kubectl --context "$KUBE_CONTEXT" -n "$NAMESPACE" rollout status deployment/api --timeout=5m
  kubectl --context "$KUBE_CONTEXT" -n "$NAMESPACE" rollout status deployment/web --timeout=5m
  kubectl --context "$KUBE_CONTEXT" -n "$NAMESPACE" get deployments,statefulsets,pods,pvc
}

rollback_environment() {
  local environment="$1"
  local revision="$2"
  local cluster_name="${3:-$KIND_CLUSTER}"
  set_cluster_context "$cluster_name"
  select_environment "$environment"
  [[ "$revision" =~ ^[1-9][0-9]*$ ]] || usage
  require_commands kind kubectl helm
  ensure_existing_kind_context
  kubectl --context "$KUBE_CONTEXT" cluster-info >/dev/null

  helm history converter --kube-context "$KUBE_CONTEXT" --namespace "$NAMESPACE"
  helm rollback converter "$revision" \
    --kube-context "$KUBE_CONTEXT" \
    --namespace "$NAMESPACE" \
    --wait --timeout 5m
  kubectl --context "$KUBE_CONTEXT" -n "$NAMESPACE" rollout status deployment/api --timeout=5m
  kubectl --context "$KUBE_CONTEXT" -n "$NAMESPACE" rollout status deployment/web --timeout=5m
  kubectl --context "$KUBE_CONTEXT" -n "$NAMESPACE" get deployments,statefulsets,pods
}

ACTION="${1:-}"
case "$ACTION" in
  cluster)
    [[ $# -le 2 ]] || usage
    require_commands kind
    set_cluster_context "${2:-$KIND_CLUSTER}"
    ensure_kind_cluster
    printf 'Kubernetes context: %s\n' "$KUBE_CONTEXT"
    ;;
  build)
    [[ $# -ge 2 && $# -le 3 ]] || usage
    validate_image_tag "$2"
    require_commands docker kind
    set_cluster_context "${3:-$KIND_CLUSTER}"
    ensure_kind_cluster
    build_and_load_images "$2"
    ;;
  development|staging)
    [[ $# -ge 2 && $# -le 3 ]] || usage
    deploy_environment "$1" "$2" "${3:-$KIND_CLUSTER}"
    ;;
  rollback)
    [[ $# -ge 3 && $# -le 4 ]] || usage
    rollback_environment "$2" "$3" "${4:-$KIND_CLUSTER}"
    ;;
  *) usage ;;
esac
