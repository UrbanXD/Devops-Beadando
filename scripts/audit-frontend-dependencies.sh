#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
REPORT_DIR="${1:-$REPO_DIR/reports}"

mkdir -p "$REPORT_DIR"
(cd "$REPO_DIR/frontend" && npm audit --audit-level=high --json) \
  > "$REPORT_DIR/npm-audit.json"
