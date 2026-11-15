#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
REPORT_DIR="${1:-$REPO_DIR/reports}"

if ! command -v cosign >/dev/null 2>&1; then
  echo "Az SBOM-aláíráshoz Cosign szükséges." >&2
  exit 2
fi

for component in backend frontend; do
  sbom="$REPORT_DIR/${component}-sbom.spdx.json"
  bundle="$sbom.sigstore.json"
  if [[ ! -s "$sbom" ]]; then
    echo "Hiányzik vagy üres az SBOM: $sbom" >&2
    exit 2
  fi

  cosign sign-blob --yes --bundle "$bundle" "$sbom"
done

echo "Mindkét SBOM aláírási csomagja elkészült."
