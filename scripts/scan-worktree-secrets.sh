#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
REPORT_DIR="${1:-$REPO_DIR/reports}"
TRIVY_IMAGE="ghcr.io/aquasecurity/trivy:0.70.0@sha256:be1190afcb28352bfddc4ddeb71470835d16462af68d310f9f4bca710961a41e"

umask 077
mkdir -p "$REPORT_DIR" || exit 2
TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/converter-secret-scan.XXXXXX")" || exit 2
trap 'rm -rf "$TEMP_DIR"' EXIT

SOURCE_SHA="${SOURCE_SHA:-$(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || printf 'unknown')}"

if ! command -v docker >/dev/null 2>&1; then
  echo "A munkafa titokvizsgálatához Docker szükséges." >&2
  exit 2
fi

if docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp \
  -v "$REPO_DIR:/workspace:ro" \
  -v "$TEMP_DIR:/temp" \
  "$TRIVY_IMAGE" \
  fs \
  --scanners secret \
  --format json \
  --output /temp/filesystem-secret-scan.raw.json \
  --exit-code 1 \
  /workspace; then
  SCAN_EXIT_CODE=0
else
  SCAN_EXIT_CODE=$?
fi

if python3 - \
  "$TEMP_DIR/filesystem-secret-scan.raw.json" \
  "$REPORT_DIR/filesystem-secret-scan.json" \
  "$SOURCE_SHA" \
  "$SCAN_EXIT_CODE" \
  "$TRIVY_IMAGE" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

raw_path, report_path, source_sha, exit_code, trivy_image = sys.argv[1:]
findings = []
error = None
try:
    raw_report = json.loads(Path(raw_path).read_text(encoding="utf-8"))
    for result in raw_report.get("Results") or []:
        for secret in result.get("Secrets") or []:
            findings.append({
                "target": result.get("Target"),
                "rule_id": secret.get("RuleID"),
                "category": secret.get("Category"),
                "severity": secret.get("Severity"),
                "title": secret.get("Title"),
                "start_line": secret.get("StartLine"),
                "end_line": secret.get("EndLine"),
            })
except (OSError, json.JSONDecodeError) as exc:
    error = str(exc)

code = int(exit_code)
if error or (code != 0 and not findings):
    outcome = "error"
elif findings:
    outcome = "findings"
else:
    outcome = "clean"

report = {
    "scanner": {"name": "Trivy", "version": "0.70.0", "image": trivy_image},
    "source_commit": source_sha,
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "outcome": outcome,
    "exit_code": code,
    "findings_count": len(findings),
    "findings": findings,
    "secret_values_in_report": False,
}
if error:
    report["error"] = error
Path(report_path).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
if outcome != "clean":
    raise SystemExit(1)
PY
then
  echo "A munkafa titokvizsgálata nem talált találatot."
else
  echo "A munkafa titokvizsgálata találatot vagy hibát jelzett; nézd meg a jelentést." >&2
  exit 1
fi
