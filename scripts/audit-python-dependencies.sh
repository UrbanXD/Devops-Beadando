#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
REPORT_DIR="${1:-$REPO_DIR/reports}"
PYTHON_BIN="${PYTHON_BIN:-$REPO_DIR/.venv/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN=python3
fi

mkdir -p "$REPORT_DIR"
"$PYTHON_BIN" -m pip_audit \
  -r "$REPO_DIR/backend/requirements.txt" \
  -r "$REPO_DIR/backend/requirements-dev.txt" \
  --format json \
  --output "$REPORT_DIR/pip-audit.json"
