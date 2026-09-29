#!/usr/bin/env bash
# Release-B conformance matrix driver (GAM-05).
#
#   ./run_matrix.sh matrix   — full gate: nostrrelay env + drills + Plebeian
#   ./run_matrix.sh env      — nostrrelay gated-relay env probes only
#   ./run_matrix.sh plebeian — Plebeian external-client matrix only
#   ./run_matrix.sh drills   — runtime drill suite (AUTH/paid/overload/egress)
#
# Every battery writes a durable JSON report under evidence/conformance/
# and `matrix` merges per-artifact entries into evidence/manifest.json +
# evidence/REPORT.md (entries follow the existing manifest schema:
# artifact, tested revision set, platform, outcome). Any failure exits
# non-zero — an unrecorded divergence or a failed core-flow run fails the
# gate.
set -u

cd "$(dirname "$0")/../.." || exit 2
REPO="$PWD"
EVID="$REPO/evidence/conformance"
mkdir -p "$EVID"

# Isolated data folder — never share the developer/CI qual-data dir.
export LNBITS_DATA_FOLDER="${LNBITS_DATA_FOLDER:-$REPO/.cache/qual-data-conformance}"
mkdir -p "$LNBITS_DATA_FOLDER"

# Kill stray conformance servers from a previous interrupted run.
pkill -f "nostrrelay_env.py serve" 2>/dev/null
pkill -f "nak serve" 2>/dev/null

rc_env=0 rc_drills=0 rc_pleb=0

run_env() {
	echo "== nostrrelay gated-relay environment =="
	uv run python tests/conformance/nostrrelay_env.py run \
		--json-out "$EVID/nostrrelay-env.json" \
		>"$EVID/nostrrelay-env.log" 2>&1
	rc_env=$?
	tail -3 "$EVID/nostrrelay-env.log" | sed 's/^/   /'
	[ $rc_env -eq 0 ] && echo "   nostrrelay env: PASS" || echo "   nostrrelay env: FAIL (see $EVID/nostrrelay-env.log)"
}

run_drills() {
	echo "== runtime drill suite =="
	uv run pytest tests/runtime/test_release_b_drills.py -q \
		>"$EVID/drills.log" 2>&1
	rc_drills=$?
	tail -3 "$EVID/drills.log" | sed 's/^/   /'
}

run_plebeian() {
	echo "== Plebeian external-client matrix =="
	uv run python tests/conformance/plebeian_matrix.py run \
		--json-out "$EVID/plebeian-matrix.json" \
		>"$EVID/plebeian-matrix.log" 2>&1
	rc_pleb=$?
	tail -3 "$EVID/plebeian-matrix.log" | sed 's/^/   /'
	[ $rc_pleb -eq 0 ] && echo "   plebeian matrix: PASS" || echo "   plebeian matrix: FAIL (see $EVID/plebeian-matrix.log)"
}

emit_evidence() {
	uv run python - "$REPO" "$rc_env" "$rc_drills" "$rc_pleb" <<'PYEOF'
"""Merge the conformance entries into evidence/manifest.json and append
the Release-B section to evidence/REPORT.md. Idempotent: the manifest
`conformance.release_b` block is rewritten per run; the REPORT section is
delimited by markers and replaced."""
import json
import platform
import re
import sys
import time
from pathlib import Path

repo = Path(sys.argv[1])
rc_env, rc_drills, rc_pleb = (int(sys.argv[i]) for i in (2, 3, 4))
evid = repo / "evidence" / "conformance"
manifest_path = repo / "evidence" / "manifest.json"
report_path = repo / "evidence" / "REPORT.md"

def head(path):
    try:
        import subprocess
        return subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=15,
        ).stdout.strip()
    except Exception:
        return ""

def load(name):
    p = evid / name
    return json.loads(p.read_text()) if p.exists() else None

env_rep = load("nostrrelay-env.json")
plb_rep = load("plebeian-matrix.json")

platform_s = f"{platform.system().lower()}-{platform.machine()} py{platform.python_version()}"
host_rev = head(repo / ".cache" / "lnbits")
ext_rev = head(repo)

entries = []
if env_rep is not None:
    entries.append({
        "artifact": "nostrrelay-env",
        "report": "evidence/conformance/nostrrelay-env.json",
        "outcome": env_rep["outcome"],
        "revisions": {
            "infinitemarkets": ext_rev,
            "lnbits_host": host_rev,
            "nostr_sdk": "0.44.8",
            "nostrrelay": env_rep.get("pins", {}).get("nostrrelay_commit"),
        },
        "platform": platform_s,
        "probes": {p["name"]: p["outcome"] for p in env_rep["probes"]},
    })
if rc_drills is not None:
    log = (evid / "drills.log")
    summary = ""
    if log.exists():
        tail = log.read_text().strip().splitlines()
        summary = tail[-1] if tail else ""
    entries.append({
        "artifact": "release-b-drills",
        "report": "evidence/conformance/drills.log",
        "outcome": "pass" if rc_drills == 0 else "fail",
        "revisions": {
            "infinitemarkets": ext_rev,
            "lnbits_host": host_rev,
            "nostr_sdk": "0.44.8",
        },
        "platform": platform_s,
        "pytest_summary": summary,
    })
if plb_rep is not None:
    entries.append({
        "artifact": "plebeian-matrix",
        "report": "evidence/conformance/plebeian-matrix.json",
        "outcome": plb_rep["outcome"],
        "revisions": {
            "infinitemarkets": ext_rev,
            "lnbits_host": host_rev,
            "nostr_sdk": "0.44.8",
            "plebeian_market": plb_rep.get("plebeian_commit"),
            "bun": plb_rep.get("bun"),
            "nak": plb_rep.get("nak"),
        },
        "platform": platform_s,
        "probes": {p["name"]: p["outcome"] for p in plb_rep["probes"]},
        "known_deltas": [d["id"] for d in plb_rep.get("deltas", [])],
    })

block = {
    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "gate": "release-b",
    "entries": entries,
    "manual_items": [
        "live plebeian.market public-relay smoke — checklist in "
        "tests/conformance/README.md (manual-only per 03-VALIDATION.md)"
    ],
}

manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
manifest.setdefault("schema_version", "1")
manifest["conformance"] = manifest.get("conformance") or {}
manifest["conformance"]["release_b"] = block
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

# REPORT.md — replace-or-append the delimited Release-B section.
start = "<!-- release-b-conformance:start -->"
end = "<!-- release-b-conformance:end -->"
lines = [
    start,
    "",
    "## Release-B Conformance (GAM-05)",
    "",
    f"- Generated (UTC): {block['generated_at']}",
    f"- Platform (this run): {platform_s} — advisory profile; blocking matrix per PINS.md §2",
    "",
    "| Artifact | Outcome | Tested revisions |",
    "| --- | --- | --- |",
]
for e in entries:
    revs = ", ".join(
        f"{k}={v}" for k, v in e["revisions"].items() if v
    )
    lines.append(f"| {e['artifact']} | {e['outcome']} | {revs} |")
lines += [
    "",
]
if plb_rep is not None:
    lines.append("### Known-delta register (D-32)")
    lines.append("")
    for d in plb_rep.get("deltas", []):
        lines.append(f"- **{d['id']}** — {d['summary']} _(evidence: {d['evidence']})_")
    lines.append("")
lines += [
    "Manual-only (not a pass source): live `plebeian.market` public-relay "
    "smoke — checklist in `tests/conformance/README.md`; results land in "
    "`.planning/phases/03-release-b-gamma-nip-17-orders/03-VERIFICATION.md`.",
    "",
    end,
]
section = "\n".join(lines) + "\n"
report = report_path.read_text() if report_path.exists() else ""
pattern = re.compile(re.escape(start) + ".*?" + re.escape(end) + "\n?", re.S)
if pattern.search(report):
    report = pattern.sub(section, report)
else:
    report = report.rstrip() + "\n\n" + section
report_path.write_text(report)

failed = [e["artifact"] for e in entries if e["outcome"] != "pass"]
print(f"conformance evidence: {len(entries)} entries; failed={failed or 'none'}")
sys.exit(1 if failed else 0)
PYEOF
}

case "${1:-matrix}" in
	env)
		run_env; exit $rc_env ;;
	plebeian)
		run_plebeian; exit $rc_pleb ;;
	drills)
		run_drills; exit $rc_drills ;;
	emit)
		# Re-merge the durable JSON reports into evidence — use after a
		# `make verify` regenerates manifest.json/REPORT.md.
		emit_evidence
		exit $? ;;
	matrix)
		run_env
		run_drills
		run_plebeian
		emit_evidence
		rc_emit=$?
		echo "== matrix summary: env=$rc_env drills=$rc_drills plebeian=$rc_pleb emit=$rc_emit =="
		[ "$rc_env" -eq 0 ] && [ "$rc_drills" -eq 0 ] && [ "$rc_pleb" -eq 0 ] && [ "$rc_emit" -eq 0 ]
		exit $? ;;
	*)
		echo "usage: $0 [matrix|env|plebeian|drills|emit]" >&2; exit 2 ;;
esac
