"""Pytest plugin recording the normalized qualification evidence bundle.

Emits ``evidence/manifest.json`` (machine-readable) and ``evidence/REPORT.md``
(human-readable) — the durable committed evidence bundle per D-09. Raw pytest
output is never committed.

Writing only happens when ``GAMMA_QUAL_EVIDENCE`` is set (``make verify`` and
the CI profiles set it), so named subsets never overwrite the durable bundle
with a partial run.

D-10 clean-pass policy: the tooling performs single runs only — there is no
retry loop — and a rerun never flips a recorded outcome. This statement is
recorded verbatim in the manifest.

D-16 disclosure: P0-02 probes attribute each subcheck as ``sdk-internal``
(blocking under D-13/D-16) or ``admission-modeled`` (extension-side defense
in depth). The report renders that split so the owner can see what
extension-level checks do and do not waive.
"""

from __future__ import annotations

import datetime
import json
import os
import platform
import sys
from pathlib import Path

import pytest

from harness import db as db_module
from harness import pins as pins_module

SCHEMA_VERSION = "1"
P0_IDS = [f"P0-{i:02d}" for i in range(1, 15)]
EVIDENCE_ENV = "GAMMA_QUAL_EVIDENCE"
P0_MODULE_PATTERN = __import__("re").compile(r"test_p0_(\d{2})_")

REPO_ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = REPO_ROOT / "evidence"
MANIFEST_PATH = EVIDENCE_DIR / "manifest.json"
REPORT_PATH = EVIDENCE_DIR / "REPORT.md"

RERUN_POLICY = (
    "Single run only (D-10 clean-pass policy): the tooling performs one run "
    "per verify command and has no retry loop; a rerun does not flip a "
    "recorded outcome."
)

SUBCHECK_KINDS = ("sdk-internal", "admission-modeled")

# nodeid -> list of markers
_MARKERS: dict[str, list[str]] = {}
# nodeid -> {outcome, duration}
_RESULTS: dict[str, dict] = {}
# nodeid -> [{name, kind}]
_SUBCHECKS: dict[str, list[dict[str, str]]] = {}
# nodeid -> {name: json-safe data} — per-test observations (e.g. per-relay ACK)
_OBSERVATIONS: dict[str, dict] = {}
# session-level FX float-boundary measurement (P0-13)
_FX_MEASUREMENT: dict | None = None
_CURRENT_NODEID: str | None = None


def note_subcheck(name: str, kind: str) -> None:
    """Attribute a P0-02 subcheck to the currently running test.

    kind: "sdk-internal" (blocking under D-13/D-16) or "admission-modeled"
    (extension-side defense in depth).
    """
    if kind not in SUBCHECK_KINDS:
        raise ValueError(f"unknown subcheck kind: {kind!r}")
    if _CURRENT_NODEID is None:
        raise RuntimeError("note_subcheck called outside a running test")
    _SUBCHECKS.setdefault(_CURRENT_NODEID, []).append({"name": name, "kind": kind})


def note_observation(name: str, data) -> None:
    """Attach a JSON-safe observation to the currently running test.

    Used for the per-relay ACK classification (P0-04) and any other
    normalized result a PINS.md qualification-results row points at.
    """
    if _CURRENT_NODEID is None:
        raise RuntimeError("note_observation called outside a running test")
    _OBSERVATIONS.setdefault(_CURRENT_NODEID, {})[name] = data


def set_fx_measurement(data: dict) -> None:
    """Record the measured FX float-boundary error (P0-13) for the manifest."""
    global _FX_MEASUREMENT
    _FX_MEASUREMENT = data


def _p0_id(nodeid: str) -> str | None:
    module = nodeid.split("::", 1)[0]
    basename = module.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    match = P0_MODULE_PATTERN.search(basename)
    if not match:
        return None
    return f"P0-{int(match.group(1)):02d}"


def _final_outcome(phases: dict[str, str]) -> str:
    if phases.get("setup") == "failed":
        return "error"
    if phases.get("call") == "failed":
        return "failed"
    if phases.get("teardown") == "failed":
        return "error"
    if "skipped" in phases.values():
        return "skipped"
    if phases.get("call") in ("passed", "xfailed"):
        return "passed"
    if not phases.get("call"):
        return "error" if "call" not in phases and phases.get("setup") == "passed" else "skipped"
    return phases.get("call", "unknown")


def _normalized_results() -> list[dict]:
    """The normalized per-test results list from the LIVE accumulator."""
    results = []
    for nodeid in sorted(_RESULTS):
        entry = _RESULTS[nodeid]
        results.append(
            {
                "nodeid": nodeid,
                "outcome": _final_outcome(entry["phases"]),
                "duration_s": round(entry["duration"], 6),
                "markers": _MARKERS.get(nodeid, []),
                "p0": _p0_id(nodeid),
                "subchecks": _SUBCHECKS.get(nodeid, []),
                "observations": _OBSERVATIONS.get(nodeid, {}),
            }
        )
    return results


def p0_coverage(results: list[dict]) -> dict[str, dict]:
    """The single shared P0-01..P0-14 coverage derivation.

    Consumed by BOTH the session-end serializer and the P0-14 closure
    assertion (via the ``evidence_results`` fixture), so the two can never
    diverge.
    """
    coverage: dict[str, dict] = {}
    for p0 in P0_IDS:
        tests = [r["nodeid"] for r in results if r["p0"] == p0]
        failed = [
            r
            for r in results
            if r["p0"] == p0 and r["outcome"] not in ("passed", "skipped")
        ]
        if not tests:
            status = "pending"
        elif failed:
            status = "fail"
        else:
            status = "pass"
        coverage[p0] = {"status": status, "tests": tests}
    return coverage


@pytest.fixture
def evidence_results(request):
    """Live in-session evidence for the P0-14 closure gate.

    Exposes the plugin's per-test results accumulator (NOT the serialized
    manifest — that is written only at session end, so an in-session file
    read would see absent or stale data), the shared ``p0_coverage``
    derivation, the session's active selection state (``-m`` marker
    expression and ``-k`` filter), and the currently running nodeid so the
    closure test can count itself.
    """
    config = request.config
    return {
        "results": _normalized_results(),
        "p0_coverage": p0_coverage(_normalized_results()),
        "current_nodeid": request.node.nodeid,
        "selection": {
            "markexpr": (config.getoption("-m") or "").strip(),
            "keyword": (config.getoption("-k") or "").strip(),
            # Positional collection args are also a subset selection unless
            # they are exactly the configured testpaths (bare `pytest`
            # resolves to them): `pytest <path>` cannot hold complete P0
            # coverage either.
            "file_or_dir": [
                str(a).rstrip("/\\") for a in config.args
            ],
            "testpaths": [
                str(p).rstrip("/\\") for p in (config.getini("testpaths") or [])
            ],
        },
    }


def pytest_itemcollected(item):
    _MARKERS[item.nodeid] = sorted(m.name for m in item.iter_markers())


def pytest_runtest_logstart(nodeid, location):
    global _CURRENT_NODEID
    _CURRENT_NODEID = nodeid


def pytest_runtest_logreport(report):
    entry = _RESULTS.setdefault(
        report.nodeid, {"phases": {}, "duration": 0.0}
    )
    entry["phases"][report.when] = report.outcome
    entry["duration"] += report.duration or 0.0


def pytest_sessionfinish(session, exitstatus):
    if os.environ.get(EVIDENCE_ENV) != "1":
        return
    results = _normalized_results()
    manifest = _build_manifest(results, int(exitstatus))
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n")
    REPORT_PATH.write_text(_render_report(manifest))


def _build_manifest(results: list[dict], exitstatus: int) -> dict:
    outcomes = [r["outcome"] for r in results]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "verify_command": "make verify",
        "rerun_policy": RERUN_POLICY,
        "profile": {
            "python": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "machine": platform.machine(),
            "platform": sys.platform,
            # Dialect name only — never the raw LNBITS_DATABASE_URL (credentials).
            "database_dialect": db_module.dialect_name(),
        },
        "pins": pins_module.snapshot(),
        "fx_measurement": _FX_MEASUREMENT,
        "results": results,
        "summary": {
            "total": len(results),
            "passed": outcomes.count("passed"),
            "failed": outcomes.count("failed"),
            "errors": outcomes.count("error"),
            "skipped": outcomes.count("skipped"),
            "exit_status": exitstatus,
            "p0_coverage": p0_coverage(results),
        },
    }


def _render_report(manifest: dict) -> str:
    profile = manifest["profile"]
    pins = manifest["pins"]
    summary = manifest["summary"]
    lines: list[str] = []
    lines.append("# GammaMarkets Qualification Report")
    lines.append("")
    lines.append(f"- Generated (UTC): {manifest['generated_at']}")
    lines.append(f"- Verify command: `{manifest['verify_command']}`")
    lines.append(
        f"- Profile: Python {profile['python']} ({profile['python_implementation']}), "
        f"{profile['machine']}/{profile['platform']}, "
        f"database dialect: {profile['database_dialect']}"
    )
    lines.append(
        f"- Pins: nostr-sdk {pins.get('nostr_sdk')}, LNbits {pins.get('lnbits_tag')} "
        f"at {str(pins.get('lnbits_commit'))[:12]}, "
        f"NIP-32 namespace `{pins.get('nip32_namespace')}`"
    )
    native = pins.get("nostr_sdk_native_library")
    if isinstance(native, dict):
        lines.append(
            f"- Tested binary: {native['filename']} "
            f"(sha256 {str(native['sha256'])[:16]}..., {native['size_bytes']} bytes)"
        )
    lines.append(f"- Result: {summary['passed']}/{summary['total']} passed "
                 f"({summary['failed']} failed, {summary['errors']} errors, "
                 f"{summary['skipped']} skipped), exit status {summary['exit_status']}")
    lines.append("")
    lines.append(f"Rerun policy: {manifest['rerun_policy']}")
    lines.append("")
    lines.append("## FX Float-Boundary Measurement (P0-13)")
    lines.append("")
    fx = manifest.get("fx_measurement")
    if fx:
        lines.append(
            f"- Measured maximum relative float error: `{fx['max_relative_error']}`"
        )
        lines.append(
            f"- Corresponding absolute sat error: `{fx['max_abs_sat_error']}`"
        )
        lines.append(f"- Worst-case sample: `{fx['worst_case']}`")
    else:
        lines.append("_Not recorded (subset run — no P0-13 measurement test ran)._")
    lines.append("")
    lines.append("## P0 Coverage Map (P0-01..P0-14)")
    lines.append("")
    lines.append("| P0 | Status | Tests |")
    lines.append("| --- | --- | --- |")
    for p0, info in summary["p0_coverage"].items():
        count = len(info["tests"])
        lines.append(f"| {p0} | {info['status']} | {count} |")
    lines.append("")
    lines.append("### Coverage pointers")
    lines.append("")
    for p0, info in summary["p0_coverage"].items():
        pointers = ", ".join(f"`{t}`" for t in info["tests"]) or "—"
        lines.append(f"- **{p0}**: {pointers}")
    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append("| Test | P0 | Markers | Outcome | Duration (s) |")
    lines.append("| --- | --- | --- | --- | --- |")
    for r in manifest["results"]:
        lines.append(
            f"| `{r['nodeid']}` | {r['p0'] or '-'} | {', '.join(r['markers']) or '-'} "
            f"| {r['outcome']} | {r['duration_s']:.3f} |"
        )
    lines.append("")
    failures = [r for r in manifest["results"] if r["outcome"] not in ("passed", "skipped")]
    lines.append("## Failures")
    lines.append("")
    if failures:
        for r in failures:
            lines.append(f"- `{r['nodeid']}`: {r['outcome']}")
    else:
        lines.append("None.")
    lines.append("")
    subcheck_rows = [
        (r, s) for r in manifest["results"] for s in r["subchecks"]
    ]
    lines.append("## D-16 Disclosure — Subcheck Attribution")
    lines.append("")
    lines.append(
        "P0-02 subchecks are attributed as `sdk-internal` (blocking under "
        "D-13/D-16: an SDK-internal regression cannot be waived) or "
        "`admission-modeled` (extension-side defense in depth only)."
    )
    lines.append("")
    if subcheck_rows:
        lines.append("| Test | Subcheck | Attribution |")
        lines.append("| --- | --- | --- |")
        for r, s in subcheck_rows:
            lines.append(f"| `{r['nodeid']}` | {s['name']} | {s['kind']} |")
    else:
        lines.append("_No attributed subchecks in this run._")
    lines.append("")
    p0_02 = summary["p0_coverage"].get("P0-02", {})
    lines.append(
        f"P0-02 SDK security/FFI/crypto status this run: **{p0_02.get('status', 'pending')}**."
    )
    lines.append("")
    lines.append("## Platform Claims (D-12)")
    lines.append("")
    lines.append(
        "Blocking claims are Linux x86_64 and Linux ARM64 on SQLite AND "
        "PostgreSQL; macOS runs are advisory developer checks only. This "
        "report records only what THIS run's profile observed — see the CI "
        "artifacts below for the full blocking matrix."
    )
    lines.append("")
    lines.append("## CI Artifacts")
    lines.append("")
    lines.append(
        "For each blocking profile (Linux x86_64 + SQLite, Linux x86_64 + "
        "PostgreSQL, Linux ARM64 + SQLite, Linux ARM64 + PostgreSQL) and the "
        "advisory macOS profile, CI uploads: the raw pytest output, the "
        "generated `evidence/REPORT.md`, and the canonical "
        "`evidence/manifest.json`."
    )
    lines.append("")
    lines.append(
        "External relay smoke is opt-in only (`GAMMA_QUAL_SMOKE_RELAY`) and "
        "is never the authoritative source of a pass."
    )
    lines.append("")
    lines.append("## Approval Status (D-11)")
    lines.append("")
    lines.append(
        "Evidence record only — **owner approval of `PINS.md` remains "
        "explicitly pending** and is required before Phase 2. Nothing in "
        "this report constitutes approval."
    )
    lines.append("")
    return "\n".join(lines) + "\n"
