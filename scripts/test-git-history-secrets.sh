#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
SCAN_SCRIPT="$PROJECT_ROOT/scripts/scan-git-history-secrets.sh"
TEMP_DIR="$(mktemp -d)"
TEST_REPO="$TEMP_DIR/history-fixture"
trap 'rm -rf -- "$TEMP_DIR"' EXIT

mkdir -p "$TEST_REPO"
git -C "$TEST_REPO" init --quiet
git -C "$TEST_REPO" symbolic-ref HEAD refs/heads/main
git -C "$TEST_REPO" config user.name "History Scan Test"
git -C "$TEST_REPO" config user.email "history-scan@example.invalid"

token_prefix="ghp"
token_body="$(printf '%04x%04x%04x%04x%04x%04x%04x%04x%04x' \
  "$RANDOM" "$RANDOM" "$RANDOM" "$RANDOM" "$RANDOM" \
  "$RANDOM" "$RANDOM" "$RANDOM" "$RANDOM")"
synthetic_token="$(printf '%s_%s' "$token_prefix" "$token_body")"

printf 'GITHUB_TOKEN=%s\n' "$synthetic_token" > "$TEST_REPO/.env"
git -C "$TEST_REPO" add .env
git -C "$TEST_REPO" commit --quiet -m "Add synthetic credential fixture"

rm "$TEST_REPO/.env"
printf 'A próbatitok törölve lett a munkafából.\n' > "$TEST_REPO/README.md"
git -C "$TEST_REPO" add -A
git -C "$TEST_REPO" commit --quiet -m "Remove synthetic credential fixture"

if bash "$SCAN_SCRIPT" "$TEST_REPO"; then
  echo "HIBA: a törölt próbatitkot a history scan nem találta meg." >&2
  exit 1
else
  scan_exit_code=$?
fi

if [[ "$scan_exit_code" -ne 1 ]]; then
  echo "HIBA: a history scan hibával állt le (kilépési kód: $scan_exit_code)." >&2
  exit 1
fi

python3 - "$TEST_REPO/reports/git-history-secret-scan.json" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if report.get("outcome") != "findings" or report.get("findings_count", 0) < 1:
    raise SystemExit("HIBA: a jelentés nem jelzi a history-ban talált próbatitkot.")
if not any(item.get("file") == ".env" for item in report.get("findings", [])):
    raise SystemExit("HIBA: a jelentés nem a törölt .env fájlra mutat.")
if report.get("secret_values_in_report") is not False:
    raise SystemExit("HIBA: a jelentés nem garantálja a titokértékek kihagyását.")
PY

echo "Rendben: a törölt, mesterséges token a Git history-ban felismerhető volt."
