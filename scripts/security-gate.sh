#!/usr/bin/env bash
set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
INPUT_DIR="${1:-$REPO_DIR/reports}"
REPORT_DIR="${2:-$REPO_DIR/reports}"
SOURCE_SHA="${SOURCE_SHA:-$(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || printf 'unknown')}"
export SOURCE_SHA

mkdir -p "$REPORT_DIR"
REPORT_DIR="$(cd -- "$REPORT_DIR" && pwd -P)"

python3 - "$INPUT_DIR" "$REPORT_DIR/security-gate.json" <<'PY'
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

input_root = Path(sys.argv[1])
output_path = Path(sys.argv[2])
source_sha = os.environ.get("SOURCE_SHA", "unknown")
is_ci = os.environ.get("GITHUB_ACTIONS") == "true"
event_name = os.environ.get("GITHUB_EVENT_NAME", "local")
repository = os.environ.get("GITHUB_REPOSITORY", "")
git_ref = os.environ.get("GITHUB_REF", "")
blocks = []
errors = []
checks = []


def add_check(name, status, findings=0, detail=None):
    item = {"name": name, "status": status, "findings": findings}
    if detail:
        item["detail"] = detail
    checks.append(item)
    if status == "BLOCK":
        blocks.append(item)
    elif status == "ERROR":
        errors.append(item)


def find_report(group, filename):
    root = input_root / group
    if not root.exists():
        root = input_root
    if not root.exists():
        add_check(filename, "ERROR", detail=f"A bemeneti mappa hiányzik: {root}")
        return None
    matches = list(root.rglob(filename))
    if len(matches) != 1:
        add_check(
            filename,
            "ERROR",
            detail=f"A jelentésből {len(matches)} példány található; pontosan egy szükséges.",
        )
        return None
    return matches[0]


def read_json(group, filename):
    path = find_report(group, filename)
    if path is None:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        add_check(filename, "ERROR", detail=f"A jelentés nem olvasható: {exc}")
        return None


def step_outcome(name):
    key = f"{name.upper()}_OUTCOME"
    value = os.environ.get(key)
    if value:
        return value
    return "not_run" if is_ci else "success"


if is_ci:
    for variable, label in (
        ("SECRET_JOB_RESULT", "secret-scan job"),
        ("PYTHON_AUDIT_JOB_RESULT", "Python audit job"),
        ("FRONTEND_AUDIT_JOB_RESULT", "frontend audit job"),
        ("CONTAINER_SECURITY_JOB_RESULT", "container scan job"),
    ):
        result = os.environ.get(variable, "")
        if result != "success":
            add_check(label, "ERROR", detail=f"A CI job állapota: {result or 'nem indult el'}.")


def check_secret_scan(name, filename, step_name):
    data = read_json("secret-scan", filename)
    if data is None:
        return
    if not isinstance(data, dict):
        add_check(name, "ERROR", detail="A jelentés formátuma hibás.")
        return
    outcome = data.get("outcome")
    findings = data.get("findings")
    count = data.get("findings_count")
    exit_code = data.get("exit_code")
    if not isinstance(findings, list) or type(count) is not int or count < 0 or count != len(findings):
        add_check(name, "ERROR", detail="A jelentés találati listája hiányos vagy hibás.")
        return
    if type(exit_code) is not int:
        add_check(name, "ERROR", detail="A jelentés scan kilépési kódja hiányzik vagy hibás.")
        return
    if data.get("source_commit") != source_sha:
        add_check(name, "ERROR", detail="A jelentés nem ehhez a forrás commithez tartozik.")
        return
    if outcome == "findings" and count > 0 and exit_code != 0:
        add_check(name, "BLOCK", findings=count, detail="Titoktalálat szerepel a jelentésben.")
    elif outcome == "clean" and count == 0 and exit_code == 0:
        if step_outcome(step_name) != "success":
            add_check(name, "ERROR", detail="A vizsgálat nem zárult sikeresen.")
        else:
            add_check(name, "PASS")
    else:
        add_check(name, "ERROR", detail=f"A vizsgálat állapota: {outcome!r}.")


def pip_audit_count(data):
    if not isinstance(data, dict) or not isinstance(data.get("dependencies"), list):
        raise ValueError("Nem ismert pip-audit JSON formátum.")
    count = 0
    for dependency in data["dependencies"]:
        if not isinstance(dependency, dict) or not isinstance(dependency.get("vulns"), list):
            raise ValueError("A pip-audit függőség rekordja hibás.")
        count += len(dependency["vulns"])
    return count


def check_python_audit():
    data = read_json("python-audit", "pip-audit.json")
    if data is None:
        return
    try:
        count = pip_audit_count(data)
    except ValueError as exc:
        add_check("python-dependencies", "ERROR", detail=str(exc))
        return
    if count:
        add_check("python-dependencies", "BLOCK", findings=count, detail="Ismert Python-függőségi sérülékenység.")
    elif step_outcome("python_audit") != "success":
        add_check("python-dependencies", "ERROR", detail="A Python audit nem zárult sikeresen.")
    else:
        add_check("python-dependencies", "PASS")


def check_frontend_audit():
    data = read_json("frontend-audit", "npm-audit.json")
    if data is None:
        return
    vulnerabilities = data.get("vulnerabilities") if isinstance(data, dict) else None
    if not isinstance(vulnerabilities, dict):
        add_check("frontend-dependencies", "ERROR", detail="Nem ismert npm audit JSON formátum.")
        return
    blocking = 0
    unknown = 0
    for vulnerability in vulnerabilities.values():
        if not isinstance(vulnerability, dict):
            unknown += 1
            continue
        severity = str(vulnerability.get("severity", "")).lower()
        if severity in {"high", "critical"}:
            blocking += 1
        elif severity not in {"info", "low", "moderate"}:
            unknown += 1
    if blocking:
        add_check("frontend-dependencies", "BLOCK", findings=blocking, detail="HIGH vagy CRITICAL npm sérülékenység.")
    elif unknown:
        add_check("frontend-dependencies", "ERROR", findings=unknown, detail="Ismeretlen npm sérülékenységi súlyosság.")
    elif step_outcome("frontend_audit") != "success":
        add_check("frontend-dependencies", "ERROR", detail="A frontend audit nem zárult sikeresen.")
    else:
        add_check("frontend-dependencies", "PASS")


def check_image_scan(component):
    filename = f"{component}-image-scan.json"
    data = read_json("container-scan", filename)
    if data is None:
        return
    if not isinstance(data, dict) or data.get("SchemaVersion") != 2 or not isinstance(data.get("Results"), list):
        add_check(f"{component}-image", "ERROR", detail="A Trivy jelentés hiányos vagy hibás.")
        return
    results = data["Results"]
    blocking = 0
    unknown = 0
    unfixed = 0
    unfixed_unknown = 0
    for result in results:
        if not isinstance(result, dict):
            unknown += 1
            continue
        vulnerabilities = result.get("Vulnerabilities") or []
        if not isinstance(vulnerabilities, list):
            unknown += 1
            continue
        for vulnerability in vulnerabilities:
            if not isinstance(vulnerability, dict):
                unknown += 1
                continue
            severity = str(vulnerability.get("Severity", "")).upper()
            if severity in {"HIGH", "CRITICAL"}:
                if vulnerability.get("FixedVersion"):
                    blocking += 1
                else:
                    unfixed += 1
            elif severity not in {"UNKNOWN", "LOW", "MEDIUM", "INFO"}:
                unknown += 1
            elif severity == "UNKNOWN":
                if vulnerability.get("FixedVersion"):
                    unknown += 1
                else:
                    unfixed_unknown += 1
    if blocking:
        add_check(f"{component}-image", "BLOCK", findings=blocking, detail="HIGH vagy CRITICAL image sérülékenység.")
    if unknown:
        add_check(f"{component}-image", "ERROR", findings=unknown, detail="Nem értékelhető Trivy lelet.")
    if not blocking and not unknown and step_outcome("container_scan") != "success":
        add_check(f"{component}-image", "ERROR", detail="A konténer scan lépés nem zárult sikeresen.")
    elif not blocking and not unknown:
        non_blocking = []
        if unfixed:
            non_blocking.append(f"{unfixed} HIGH/CRITICAL lelethez nincs javított csomagverzió")
        if unfixed_unknown:
            non_blocking.append(f"{unfixed_unknown} UNKNOWN lelethez nincs javított csomagverzió")
        detail = f"A riportban maradnak, de nem blokkolnak: {', '.join(non_blocking)}." if non_blocking else None
        add_check(
            f"{component}-image",
            "PASS",
            findings=unfixed + unfixed_unknown,
            detail=detail,
        )


def check_sbom(component):
    filename = f"{component}-sbom.spdx.json"
    data = read_json("image-sboms", filename)
    if data is None:
        return None
    if not isinstance(data, dict) or not str(data.get("spdxVersion", "")).startswith("SPDX-"):
        add_check(f"{component}-sbom", "ERROR", detail="Az SBOM nem érvényes SPDX JSON.")
        return None
    if not data.get("SPDXID") or not data.get("creationInfo"):
        add_check(f"{component}-sbom", "ERROR", detail="Az SPDX dokumentum kötelező mezője hiányzik.")
        return None
    path = find_report("image-sboms", filename)
    add_check(f"{component}-sbom", "PASS")
    return path


check_secret_scan("worktree-secrets", "filesystem-secret-scan.json", "filesystem_scan")
check_secret_scan("git-history-secrets", "git-history-secret-scan.json", "history_scan")
check_python_audit()
check_frontend_audit()

container_metadata = read_json("container-scan", "container-scan-metadata.json")
manifest = read_json("container-scan", "container-image-manifest.json")
if container_metadata is not None:
    if not isinstance(container_metadata, dict):
        add_check("container-metadata", "ERROR", detail="A konténer scan metadata formátuma hibás.")
    else:
        if container_metadata.get("source_sha") != source_sha:
            add_check("container-metadata", "ERROR", detail="A konténerjelentés más forrás commithez tartozik.")
        elif not isinstance(container_metadata.get("vulnerability_database"), dict):
            add_check("container-metadata", "ERROR", detail="A Trivy sérülékenységi adatbázis metaadata hiányzik.")
        else:
            outcomes = container_metadata.get("scan_outcomes", {})
            database = container_metadata["vulnerability_database"]
            scanner = container_metadata.get("scanner")
            try:
                database_next_update = datetime.fromisoformat(
                    str(database.get("NextUpdate", "")).replace("Z", "+00:00")
                )
                if database_next_update.tzinfo is None:
                    raise ValueError("Az adatbázis frissítési ideje nem tartalmaz időzónát.")
                database_is_current = database_next_update > datetime.now(timezone.utc)
            except (TypeError, ValueError):
                database_is_current = False
            required_outcomes = (
                "artifact_verification",
                "backend_sbom",
                "frontend_sbom",
                "backend",
                "frontend",
            )
            if not isinstance(scanner, dict) or scanner.get("name") != "Trivy" or not scanner.get("version") or not scanner.get("image"):
                add_check("container-metadata", "ERROR", detail="A Trivy scanner azonosítója hiányzik vagy hibás.")
            elif not isinstance(database.get("Version"), int) or not database.get("UpdatedAt") or not database.get("NextUpdate"):
                add_check("container-metadata", "ERROR", detail="A Trivy adatbázis verziója vagy frissítési ideje hiányzik.")
            elif not database_is_current:
                add_check("container-metadata", "ERROR", detail="A Trivy sérülékenységi adatbázis frissítési ideje lejárt vagy hibás.")
            elif is_ci and (
                container_metadata.get("repository") != repository
                or str(container_metadata.get("run_id")) != os.environ.get("GITHUB_RUN_ID")
                or str(container_metadata.get("run_attempt")) != os.environ.get("GITHUB_RUN_ATTEMPT")
            ):
                add_check("container-metadata", "ERROR", detail="A konténer scan nem ehhez a CI-futáshoz tartozik.")
            elif manifest is not None and container_metadata.get("image_manifest") != manifest:
                add_check("container-metadata", "ERROR", detail="A scan metadata és az image manifest eltér.")
            elif not isinstance(outcomes, dict) or any(outcomes.get(name) != "success" for name in required_outcomes):
                add_check("container-metadata", "ERROR", detail="A két image scan nem futott le teljesen.")
            else:
                add_check("container-metadata", "PASS")

if manifest is not None:
    if not isinstance(manifest, dict) or manifest.get("source_sha") != source_sha:
        add_check("image-manifest", "ERROR", detail="Az image manifest nem ehhez a forrás commithez tartozik.")
    elif not isinstance(manifest.get("images"), dict) or not {"backend", "frontend"}.issubset(manifest["images"]):
        add_check("image-manifest", "ERROR", detail="Az image manifestből image-adat hiányzik.")
    elif any(
        not isinstance(manifest["images"].get(component), dict)
        or not manifest["images"][component].get("reference")
        or not manifest["images"][component].get("image_id")
        for component in ("backend", "frontend")
    ):
        add_check("image-manifest", "ERROR", detail="Az image manifest hivatkozása vagy azonosítója hiányzik.")
    elif is_ci and (
        manifest.get("repository") != repository
        or str(manifest.get("run_id")) != os.environ.get("GITHUB_RUN_ID")
        or str(manifest.get("run_attempt")) != os.environ.get("GITHUB_RUN_ATTEMPT")
    ):
        add_check("image-manifest", "ERROR", detail="Az image manifest nem ehhez a CI-futáshoz tartozik.")
    else:
        add_check("image-manifest", "PASS")

check_image_scan("backend")
check_image_scan("frontend")
sboms = {component: check_sbom(component) for component in ("backend", "frontend")}

if event_name == "push":
    signing_outcome = os.environ.get("SBOM_SIGNING_OUTCOME", "not_run")
    signing_job_result = os.environ.get("SBOM_SIGNING_JOB_RESULT", "")
    if signing_job_result != "success":
        add_check("sbom-signatures", "ERROR", detail=f"Az SBOM-aláírás job állapota: {signing_job_result or 'nem indult el'}.")
    elif signing_outcome != "success":
        add_check("sbom-signatures", "ERROR", detail=f"Az SBOM-aláírás állapota: {signing_outcome}.")
    elif not repository or not git_ref:
        add_check("sbom-signatures", "ERROR", detail="A várt GitHub aláíró-azonosság nem állapítható meg.")
    elif (shutil_which := shutil.which("cosign")) is None:
        add_check("sbom-signatures", "ERROR", detail="A Cosign nem található az ellenőrzéshez.")
    else:
        identity = f"https://github.com/{repository}/.github/workflows/ci.yml@{git_ref}"
        verification_failures = []
        for component, sbom_path in sboms.items():
            if sbom_path is None:
                verification_failures.append(f"{component}: SBOM hiányzik")
                continue
            bundle = Path(f"{sbom_path}.sigstore.json")
            if not bundle.is_file() or bundle.stat().st_size == 0:
                verification_failures.append(f"{component}: aláírási bundle hiányzik")
                continue
            result = subprocess.run(
                [
                    shutil_which,
                    "verify-blob",
                    "--bundle",
                    str(bundle),
                    "--certificate-identity",
                    identity,
                    "--certificate-oidc-issuer",
                    "https://token.actions.githubusercontent.com",
                    str(sbom_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "ellenőrzési hiba").strip()
                verification_failures.append(f"{component}: {detail[:500]}")
        if verification_failures:
            add_check("sbom-signatures", "ERROR", detail="; ".join(verification_failures))
        else:
            add_check("sbom-signatures", "PASS", detail="A két SBOM aláírása és a GitHub workflow-identitás ellenőrizve.")
else:
    add_check("sbom-signatures", "PASS", detail="Push eseményen kívül nincs keyless aláírás; az ellenőrzés push eseményben fut.")

if errors:
    decision = "ERROR"
    exit_code = 2
elif blocks:
    decision = "BLOCK"
    exit_code = 1
else:
    decision = "PASS"
    exit_code = 0

report = {
    "policy_version": 1,
    "source_sha": source_sha,
    "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
    "event": event_name,
    "decision": decision,
    "rules": {
        "secrets": "block on any finding",
        "python_dependencies": "block on any known vulnerability",
        "npm_dependencies": "block on HIGH or CRITICAL",
        "container_images": "block on fixable HIGH or CRITICAL; report-only for unfixed HIGH, CRITICAL and UNKNOWN; unknown severity with a fix is an error",
        "reports": "missing, malformed, stale-source or incomplete reports are errors",
        "sbom_signatures": "verify Sigstore keyless signatures and exact workflow identity on push",
    },
    "checks": checks,
    "blocks": blocks,
    "errors": errors,
}
output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(f"Security gate: {decision}")
for item in blocks:
    print(f"BLOCK {item['name']}: {item.get('detail', '')}")
for item in errors:
    print(f"ERROR {item['name']}: {item.get('detail', '')}")
for item in checks:
    if item["status"] == "PASS" and item.get("detail"):
        print(f"PASS {item['name']}: {item['detail']}")
raise SystemExit(exit_code)
PY
