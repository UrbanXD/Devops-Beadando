#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
ARTIFACT_DIR="${1:-$REPO_DIR/reports}"
REPORT_DIR="${2:-$REPO_DIR/reports}"
TRIVY_IMAGE="ghcr.io/aquasecurity/trivy:0.70.0@sha256:be1190afcb28352bfddc4ddeb71470835d16462af68d310f9f4bca710961a41e"
SOURCE_SHA="${SOURCE_SHA:-$(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || printf 'unknown')}"
RUN_ID="${RUN_ID:-}"
RUN_ATTEMPT="${RUN_ATTEMPT:-}"
REPOSITORY="${REPOSITORY:-}"

mkdir -p "$REPORT_DIR" "$REPORT_DIR/.trivy-cache"
REPORT_DIR="$(cd -- "$REPORT_DIR" && pwd -P)"
ARTIFACT_DIR="$(cd -- "$ARTIFACT_DIR" && pwd -P)"
TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/converter-image-scan.XXXXXX")" || exit 2
trap 'rm -rf "$TEMP_DIR"' EXIT

OVERALL_STATUS=0
ARTIFACT_STATUS=not-checked
BACKEND_SBOM_STATUS=not-run
FRONTEND_SBOM_STATUS=not-run
BACKEND_SCAN_STATUS=not-run
FRONTEND_SCAN_STATUS=not-run

write_metadata() {
  export SOURCE_SHA RUN_ID RUN_ATTEMPT REPOSITORY
  export ARTIFACT_STATUS BACKEND_SBOM_STATUS FRONTEND_SBOM_STATUS
  export BACKEND_SCAN_STATUS FRONTEND_SCAN_STATUS TRIVY_IMAGE
  python3 - "$REPORT_DIR/container-scan-metadata.json" \
    "$REPORT_DIR/.trivy-cache/db/metadata.json" \
    "$REPORT_DIR/container-image-manifest.json" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

report_path, db_path, manifest_path = sys.argv[1:]
try:
    db_metadata = json.loads(Path(db_path).read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    db_metadata = None
try:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    manifest = None

metadata = {
    "source_sha": os.environ["SOURCE_SHA"],
    "repository": os.environ.get("REPOSITORY") or None,
    "run_id": os.environ.get("RUN_ID") or None,
    "run_attempt": os.environ.get("RUN_ATTEMPT") or None,
    "scanned_at_utc": datetime.now(timezone.utc).isoformat(),
    "scanner": {"name": "Trivy", "version": "0.70.0", "image": os.environ["TRIVY_IMAGE"]},
    "vulnerability_database": db_metadata,
    "image_manifest": manifest,
    "scan_outcomes": {
        "artifact_verification": os.environ["ARTIFACT_STATUS"],
        "backend_sbom": os.environ["BACKEND_SBOM_STATUS"],
        "frontend_sbom": os.environ["FRONTEND_SBOM_STATUS"],
        "backend": os.environ["BACKEND_SCAN_STATUS"],
        "frontend": os.environ["FRONTEND_SCAN_STATUS"],
    },
}
Path(report_path).write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
PY
}
trap 'write_metadata; rm -rf "$TEMP_DIR"' EXIT

if ! command -v docker >/dev/null 2>&1; then
  echo "A konténervizsgálathoz Docker szükséges." >&2
  ARTIFACT_STATUS=error
  exit 2
fi

if ! (cd "$ARTIFACT_DIR" && sha256sum --check converter-images.tar.gz.sha256); then
  echo "A konténer artifact ellenőrzőösszege hibás vagy hiányzik." >&2
  ARTIFACT_STATUS=error
  exit 1
fi

if ! gzip -dc "$ARTIFACT_DIR/converter-images.tar.gz" | docker load; then
  echo "A konténer artifact betöltése nem sikerült." >&2
  ARTIFACT_STATUS=error
  exit 1
fi

if [[ "$ARTIFACT_DIR/container-image-manifest.json" != "$REPORT_DIR/container-image-manifest.json" ]]; then
  if ! cp "$ARTIFACT_DIR/container-image-manifest.json" "$REPORT_DIR/container-image-manifest.json"; then
    echo "A konténer manifest nem található." >&2
    ARTIFACT_STATUS=error
    exit 1
  fi
fi

if ! python3 - "$REPORT_DIR/container-image-manifest.json" "$SOURCE_SHA" "$RUN_ID" "$RUN_ATTEMPT" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

manifest_path, source_sha, run_id, run_attempt = sys.argv[1:]
manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
expected = {"source_sha": source_sha, "run_id": run_id, "run_attempt": run_attempt}
for key, value in expected.items():
    if value and manifest.get(key) != value:
        raise SystemExit(f"A container image manifest eltérő {key} értéket tartalmaz.")

for image in manifest["images"].values():
    image_id = subprocess.check_output(
        ["docker", "image", "inspect", "--format", "{{.Id}}", image["reference"]],
        text=True,
    ).strip()
    if image_id != image["image_id"]:
        raise SystemExit(f"A betöltött image ID nem egyezik: {image['reference']}")
PY
then
  echo "A konténer image manifest vagy image ID ellenőrzése sikertelen." >&2
  ARTIFACT_STATUS=error
  exit 1
fi
ARTIFACT_STATUS=success

cp "$REPORT_DIR/container-image-manifest.json" "$TEMP_DIR/container-image-manifest.json"
TRIVY_USER="$(id -u):$(id -g)"
run_trivy() {
  docker run --rm \
    --user "$TRIVY_USER" \
    -e HOME=/tmp \
    -v "$REPORT_DIR:/reports" \
    -v "$REPORT_DIR/.trivy-cache:/cache" \
    -v "$TEMP_DIR:/temp" \
    "$TRIVY_IMAGE" \
    --cache-dir /cache \
    "$@"
}

BACKEND_IMAGE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["images"]["backend"]["reference"])' "$REPORT_DIR/container-image-manifest.json")"
FRONTEND_IMAGE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["images"]["frontend"]["reference"])' "$REPORT_DIR/container-image-manifest.json")"

if docker save "$BACKEND_IMAGE" -o "$TEMP_DIR/backend.tar"; then
  if run_trivy image --input /temp/backend.tar --format spdx-json --output /reports/backend-sbom.spdx.json; then
    BACKEND_SBOM_STATUS=success
  else
    BACKEND_SBOM_STATUS=failed
    OVERALL_STATUS=1
  fi
  if run_trivy image --input /temp/backend.tar \
    --scanners vuln --format json --output /reports/backend-image-scan.json \
    --exit-code 0; then
    BACKEND_SCAN_STATUS=success
  else
    BACKEND_SCAN_EXIT_CODE=$?
    BACKEND_SCAN_STATUS="failed (exit $BACKEND_SCAN_EXIT_CODE)"
    OVERALL_STATUS=1
  fi
else
  BACKEND_SBOM_STATUS=failed
  BACKEND_SCAN_STATUS=failed
  OVERALL_STATUS=1
fi

if docker save "$FRONTEND_IMAGE" -o "$TEMP_DIR/frontend.tar"; then
  if run_trivy image --input /temp/frontend.tar --format spdx-json --output /reports/frontend-sbom.spdx.json; then
    FRONTEND_SBOM_STATUS=success
  else
    FRONTEND_SBOM_STATUS=failed
    OVERALL_STATUS=1
  fi
  if run_trivy image --input /temp/frontend.tar \
    --scanners vuln --format json --output /reports/frontend-image-scan.json \
    --exit-code 0; then
    FRONTEND_SCAN_STATUS=success
  else
    FRONTEND_SCAN_EXIT_CODE=$?
    FRONTEND_SCAN_STATUS="failed (exit $FRONTEND_SCAN_EXIT_CODE)"
    OVERALL_STATUS=1
  fi
else
  FRONTEND_SBOM_STATUS=failed
  FRONTEND_SCAN_STATUS=failed
  OVERALL_STATUS=1
fi

if [[ "$OVERALL_STATUS" -eq 0 ]]; then
  echo "A konténervizsgálat és SBOM-készítés befejeződött."
else
  echo "A konténervizsgálat találatot vagy hibát jelzett; nézd meg a reports/ mappát." >&2
fi
exit "$OVERALL_STATUS"
