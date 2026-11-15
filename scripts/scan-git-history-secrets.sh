#!/usr/bin/env bash
set -euo pipefail

TRUFFLEHOG_IMAGE="ghcr.io/trufflesecurity/trufflehog:3.99.8@sha256:674b2f187620a19df77f44cf9a7d77efcc581a5662accef2f2739cbb46ba4a3a"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_DIR="${1:-$SCRIPT_DIR/..}"

if ! REPO_DIR="$(cd -- "$REPO_DIR" && pwd -P)"; then
  echo "Nem találom a megadott könyvtárat." >&2
  exit 2
fi

if ! git -C "$REPO_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "A megadott könyvtár nem Git-tároló." >&2
  exit 2
fi

REPORT_DIR="$REPO_DIR/reports"
REPORT_PATH="$REPORT_DIR/git-history-secret-scan.json"
FINDINGS_PATH="$REPORT_DIR/git-history-secret-findings.json"
SOURCE_COMMIT="$(git -C "$REPO_DIR" rev-parse HEAD)"
mkdir -p "$REPORT_DIR"
printf '[]\n' > "$FINDINGS_PATH"

write_report() {
  local outcome="$1"
  local exit_code="$2"

  python3 - "$REPORT_PATH" "$SOURCE_COMMIT" "$outcome" "$exit_code" "$TRUFFLEHOG_IMAGE" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

report_path, source_commit, outcome, exit_code, image = sys.argv[1:]
findings_path = Path(report_path).with_name("git-history-secret-findings.json")
findings = json.loads(findings_path.read_text(encoding="utf-8"))
report = {
    "scanner": {
        "name": "TruffleHog",
        "version": "3.99.8",
        "image": image,
    },
    "repository": os.environ.get("GITHUB_REPOSITORY"),
    "source_commit": source_commit,
    "run_id": os.environ.get("GITHUB_RUN_ID"),
    "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
    "scan_scope": "all local refs and full Git history",
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "outcome": outcome,
    "exit_code": int(exit_code),
    "findings_count": len(findings),
    "findings": findings,
    "secret_values_in_report": False,
}
Path(report_path).write_text(
    json.dumps(report, indent=2) + "\n", encoding="utf-8"
)
PY
}

if [[ "$(git -C "$REPO_DIR" rev-parse --is-shallow-repository)" == "true" ]]; then
  write_report "error" 2
  echo "A teljes history vizsgálatához teljes Git-klón szükséges (shallow clone)." >&2
  exit 2
fi

if ! command -v docker >/dev/null 2>&1; then
  write_report "error" 2
  echo "A history scan futtatásához Docker szükséges." >&2
  exit 2
fi

set +e
docker run --rm --network none \
  --volume "$REPO_DIR:/scan:ro" \
  "$TRUFFLEHOG_IMAGE" \
  git file:///scan \
  --json \
  --no-verification \
  --results=verified,unverified,unknown \
  --fail \
  --fail-on-scan-errors \
  --no-update \
  --log-level=-1 \
  2>/dev/null |
  python3 -c '
import json
import sys
from pathlib import Path

findings = []
for line in sys.stdin:
    if not line.strip():
        continue
    try:
        result = json.loads(line)
    except json.JSONDecodeError:
        print("TruffleHog produced a non-JSON scan result.", file=sys.stderr)
        sys.exit(2)
    metadata = result.get("SourceMetadata") or {}
    source_data = metadata.get("Data") or {}
    git_data = source_data.get("Git") or {}
    findings.append({
        "detector": result.get("DetectorName"),
        "verified": result.get("Verified"),
        "commit": git_data.get("commit"),
        "file": git_data.get("file"),
        "line": git_data.get("line"),
        "timestamp": git_data.get("timestamp"),
    })

Path(sys.argv[1]).write_text(
    json.dumps(findings, indent=2) + "\n", encoding="utf-8"
)
' "$FINDINGS_PATH"
scan_exit_code=$?
set -e

case "$scan_exit_code" in
  0)
    write_report "clean" "$scan_exit_code"
    echo "A teljes Git history vizsgálata nem talált titokjelöltet."
    ;;
  183)
    write_report "findings" "$scan_exit_code"
    echo "A Git history titokjelöltet tartalmaz. A jelentés nem tárol titokértéket." >&2
    exit 1
    ;;
  *)
    write_report "error" "$scan_exit_code"
    echo "A Git history scan nem futott le megfelelően (kilépési kód: $scan_exit_code)." >&2
    exit 2
    ;;
esac
