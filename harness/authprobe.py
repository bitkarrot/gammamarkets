"""P0-12 probes: host auth/privacy/lifecycle boundary models + probe router.

The probe router exists ONLY inside test fixtures — it is never committed
runtime code (T-03-03). It exercises the boundaries the production extension
must enforce, at probe level:

- authenticated-session + route-enforced same-origin check for state-changing
  mutations (host CORS is never trusted, section 21.29);
- bearer-token-in-header for the public status surface — token carriage in
  path or query is never accepted — with ``Referrer-Policy: no-referrer``
  and ``Cache-Control: no-store`` (section 5.4);
- audit/header capture that redacts bearer tokens, bolt11 strings,
  recipient addresses, and PII before persistence (sections 5.4/16);
- bounded startup registration through ``task_manager.create_permanent_task``
  with a readiness gate that stays closed until the startup reconciliation
  pass completes (section 10);
- cancellation-safe ``finally`` cleanup of SDK clients and scoped stop-hook
  cancellation of extension-owned handles only — ``cancel_all_tasks()`` is
  forbidden (section 10);
- production-ready topology refusal for unsupported deployments
  (multi-process SQLite, CockroachDB — section 14).
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

# fastapi is a host dependency — safe to import at module level. The lnbits
# auth dependency stays lazily imported inside build_probe_router so this
# module does not pull the host into non-host test sessions.
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

# --- audit/header redaction (sections 5.4, 16) --------------------------------

#: Header names whose values are credentials and MUST be redacted in any
#: request/header capture (section 5.4: X-Order-Token redaction is mandatory).
SENSITIVE_HEADER_NAMES = frozenset(
    {
        "x-order-token",
        "authorization",
        "cookie",
        "set-cookie",
        "proxy-authorization",
    }
)

#: Audit field names whose VALUES are secret or PII — stored only as
#: redaction markers, never verbatim (section 16).
SENSITIVE_FIELD_NAMES = frozenset(
    {
        "token",
        "x_order_token",
        "access_token",
        "bearer",
        "bolt11",
        "invoice",
        "payment_request",
        "address",
        "recipient",
        "email",
        "phone",
        "contact",
        "nsec",
        "secret",
        "password",
        "private_key",
        "conversation_key",
        "content",
        "public_token",
    }
)

#: BOLT11 invoice prefixes on any network — a value matching this is
#: redacted even if it arrives under an innocuous field name.
BOLT11_RE = re.compile(r"^ln(bc|tb|bcrt|sb|tbs)[0-9a-z]+$", re.IGNORECASE)

#: 64-hex secrets (key material as raw hex) are redacted too.
HEX64_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)

REDACTED = "<redacted>"


def redact_value(name: str, value) -> object:
    """Redact a single audit field value by name and by value shape."""
    lname = name.lower().replace("-", "_")
    if lname in SENSITIVE_FIELD_NAMES or name in SENSITIVE_FIELD_NAMES:
        return REDACTED
    if isinstance(value, str):
        if BOLT11_RE.match(value):
            return "<redacted:bolt11>"
        if HEX64_RE.match(value):
            return "<redacted:hex64>"
    return value


def redacted_headers(headers) -> dict[str, str]:
    """A header dict safe to persist/log: credential headers replaced."""
    return {
        name: (REDACTED if name.lower() in SENSITIVE_HEADER_NAMES else value)
        for name, value in headers.items()
    }


@dataclass
class AuditLog:
    """Minimal audit capture: rows hold only redacted markers + identifiers.

    Models the section 16 rule — persisted audit rows must never contain
    keys, addresses, bolt11 strings, or decrypted content in full.
    """

    rows: list[dict] = field(default_factory=list)

    def record(self, event: str, **fields) -> dict:
        row = {"event": event}
        for name, value in fields.items():
            row[name] = redact_value(name, value)
        self.rows.append(row)
        return row

    def record_request_headers(self, event: str, headers) -> dict:
        """Persist a request-header audit row with mandatory redaction."""
        row = {"event": event, "headers": redacted_headers(headers)}
        self.rows.append(row)
        return row


# --- probe router (test-fixture only) ------------------------------------------


def build_probe_router(
    *,
    canonical_origin: str,
    order_token: str,
    audit: AuditLog,
):
    """Build the P0-12 probe router for mounting inside the host app fixture.

    ``canonical_origin`` models ``GAMMAMARKETS_PUBLIC_BASE_URL`` — the same-
    origin check is enforced by the route itself because host CORS is never
    trusted for mutation authorization (section 21.29).
    """
    from lnbits.decorators import access_token_payload

    router = APIRouter(prefix="/gammamarkets-qual-probe")

    @router.post("/mutate")
    async def mutate(
        request: Request,
        payload=Depends(access_token_payload),
    ):
        """State-changing probe: authenticated session AND same-origin."""
        origin = request.headers.get("origin")
        audit.record(
            "gammamarkets.probe.mutate",
            usr=getattr(payload, "usr", None),
            origin=origin or "<none>",
        )
        if origin != canonical_origin:
            raise HTTPException(403, "cross-origin or missing Origin rejected")
        return {"ok": True, "usr": getattr(payload, "usr", None)}

    @router.get("/order-status")
    async def order_status(request: Request):
        """Public-status probe: bearer token in X-Order-Token header only."""
        audit.record_request_headers(
            "gammamarkets.probe.order-status", dict(request.headers)
        )
        token = request.headers.get("x-order-token")
        if token != order_token:
            raise HTTPException(401, "missing or invalid order token")
        return JSONResponse(
            {"state": "awaiting_payment", "order": "gq-order-01"},
            headers={
                "Referrer-Policy": "no-referrer",
                "Cache-Control": "no-store",
            },
        )

    return router


# --- startup / readiness / lifecycle models (section 10) -----------------------


@dataclass
class ProbeLifecycle:
    """Model of the section-10 extension lifecycle.

    ``start`` performs ONLY bounded synchronous registration through
    ``task_manager.create_permanent_task`` — no inline network or
    reconciliation work. Readiness stays closed until the startup
    reconciliation task reports its first completed pass
    (``mark_startup_reconciled``), gating checkout and subscriptions.
    """

    task_manager: object
    handles: list = field(default_factory=list)
    reconciled: bool = False

    def start(self, registrations: dict[str, Callable[[], Awaitable]]) -> list:
        """Register each named task; return the owned Task handles.

        Registration only — the factories are invoked by the task manager's
        wrapper on the running loop, never inline here.
        """
        for name, factory in registrations.items():
            self.handles.append(
                self.task_manager.create_permanent_task(factory, name=name)
            )
        return list(self.handles)

    def mark_startup_reconciled(self) -> None:
        """Called when the startup reconciliation pass completes."""
        self.reconciled = True

    @property
    def ready(self) -> bool:
        return self.reconciled

    def checkout_allowed(self) -> bool:
        """Checkout stays gated until readiness (section 10)."""
        return self.reconciled

    def stop(self) -> None:
        """Cancel ONLY extension-owned handles via cancel_task.

        ``cancel_all_tasks()`` is forbidden (section 10): unrelated host
        tasks must survive the extension stop hook.
        """
        for handle in self.handles:
            self.task_manager.cancel_task(handle)
        self.handles.clear()
        self.reconciled = False


async def sdk_client_worker(client, stop_event) -> None:
    """A worker owning an SDK client with cancellation-safe cleanup.

    The ``finally`` runs whether the task is stopped via the stop hook or
    cancelled directly (process shutdown without the hook, section 10):
    the relay connection is closed either way.
    """
    try:
        await stop_event.wait()
    finally:
        await client.disconnect()
        await client.shutdown()


# --- topology refusal (section 14) ----------------------------------------------

SUPPORTED_DIALECTS = frozenset({"sqlite", "postgresql"})


@dataclass(frozen=True)
class TopologyDecision:
    allowed: bool
    reason: str


def evaluate_production_topology(dialect: str, workers: int) -> TopologyDecision:
    """Section 14: refuse production-ready mode for unsupported topologies.

    SQLite is single-process/worker only; PostgreSQL supports multiple
    workers; CockroachDB and multi-process SQLite are not v1 targets.
    """
    d = (dialect or "").lower()
    if d not in SUPPORTED_DIALECTS:
        return TopologyDecision(False, f"unsupported-dialect:{d or 'unknown'}")
    if workers < 1:
        return TopologyDecision(False, "invalid-worker-count")
    if d == "sqlite" and workers != 1:
        return TopologyDecision(False, "sqlite-multi-process-refused")
    return TopologyDecision(True, "supported")
