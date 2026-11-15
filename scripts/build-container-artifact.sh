#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
ARTIFACT_DIR="${1:-$REPO_DIR/reports}"
SOURCE_SHA="${SOURCE_SHA:-$(git -C "$REPO_DIR" rev-parse HEAD)}"
RUN_ID="${RUN_ID:-local}"
RUN_ATTEMPT="${RUN_ATTEMPT:-1}"
REPOSITORY="${REPOSITORY:-local}"
BACKEND_IMAGE="converter-backend:$SOURCE_SHA"
FRONTEND_IMAGE="converter-frontend:$SOURCE_SHA"

mkdir -p "$ARTIFACT_DIR"
ARTIFACT_DIR="$(cd -- "$ARTIFACT_DIR" && pwd -P)"
docker build -t "$BACKEND_IMAGE" "$REPO_DIR/backend"
docker build -t "$FRONTEND_IMAGE" "$REPO_DIR/frontend"

export SOURCE_SHA RUN_ID RUN_ATTEMPT REPOSITORY BACKEND_IMAGE FRONTEND_IMAGE
python3 - "$ARTIFACT_DIR/container-image-manifest.json" <<'PY'
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

images = {
    "backend": os.environ["BACKEND_IMAGE"],
    "frontend": os.environ["FRONTEND_IMAGE"],
}
manifest = {
    "format_version": 1,
    "source_sha": os.environ["SOURCE_SHA"],
    "repository": os.environ["REPOSITORY"],
    "run_id": os.environ["RUN_ID"],
    "run_attempt": os.environ["RUN_ATTEMPT"],
    "built_at_utc": datetime.now(timezone.utc).isoformat(),
    "images": {},
}
for name, reference in images.items():
    image_id = subprocess.check_output(
        ["docker", "image", "inspect", "--format", "{{.Id}}", reference],
        text=True,
    ).strip()
    manifest["images"][name] = {"reference": reference, "image_id": image_id}

Path(sys.argv[1]).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
PY

docker save "$BACKEND_IMAGE" "$FRONTEND_IMAGE" \
  | gzip -1 > "$ARTIFACT_DIR/converter-images.tar.gz"
(cd "$ARTIFACT_DIR" && sha256sum converter-images.tar.gz > converter-images.tar.gz.sha256)
