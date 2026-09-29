"""Provision and probe the LNbits ``nostrrelay`` extension — the
reference self-hosted gated-relay environment for Release-B §9.5
(locked D-33).

This is reference tooling, not a packaging decision: the nostrrelay
source is READ-ONLY under ``.cache/gsd-tmp/nostrrelay`` (or
``$NOSTRRELAY_SRC``); it is copied into a throwaway test-host extensions
dir next to a symlink of this repo's ``infinitemarkets`` package and the
pinned LNbits host is booted in-process with ``FakeWallet``.

Provisioned topology:

- ``gated`` — ``requireAuthFilter`` + paid join (costToJoin) + account
  allowlist containing ONLY the merchant pubkey. nostrrelay's native
  p-tag read gate is kind-4-only, so kind-1059 read privacy comes from
  NIP-42 auth + the account gate; reads by unauthenticated or
  non-allowlisted connections get nothing.
- ``open`` — free, no auth — proves open kind-1059 writes are accepted
  and carries the wrap intake leg of the extension-path probe.
- Both relays use ``createdAtDaysPast >= 2`` so NIP-59's backdated
  (≤ 2 days) gift-wrap timestamps are admitted.

Probe battery (each recorded with a bounded outcome):

- ``gated_anon_req``        — anonymous REQ {kinds:[1059], #p:[merchant]}
                              returns AUTH, no events, no EOSE.
- ``gated_stranger_req``    — NIP-42-authed non-allowlisted REQ returns
                              NOTICE "This is a paid relay", no events.
- ``gated_merchant_req``    — NIP-42-authed merchant REQ returns the
                              stored wraps + EOSE.
- ``open_write_accepted``   — anonymous kind-1059 write to ``open``
                              returns a positive OK.
- ``gated_paid_write``      — anonymous kind-1059 write to ``paid``-mode
                              gated relay returns the negative OK
                              ``"This is a paid relay: '<id>'"`` which
                              the extension classifies as
                              ``payment-required`` (D-27 — surfaced,
                              never paid).
- ``extension_gated_inbox`` — the REAL extension inbox session on the
                              gated relay answers AUTH and (post-auth
                              REQ re-issue) serves the stored wraps:
                              ``inbox_events`` rows are admitted with
                              ``source_relay_url = <gated>``.
- ``extension_open_inbox``  — a buyer wrap posted anonymously to
                              ``open`` is admitted by the extension.
- ``paid_publish_surface``  — the real outbox kind-10050 publish to the
                              paid gated relay produces a durable
                              ``relay_publications`` rejection carrying
                              the paid-relay reason (never paid).

Usage::

    uv run python tests/conformance/nostrrelay_env.py run [--json-out FILE]
    uv run python tests/conformance/nostrrelay_env.py serve --port 55123

``run`` exits 0 only when every probe reports ``pass``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PKG_DIR = REPO_ROOT / "infinitemarkets"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
NOSTRRELAY_SRC = Path(
    os.environ.get(
        "NOSTRRELAY_SRC", str(REPO_ROOT / ".cache" / "gsd-tmp" / "nostrrelay")
    )
)

# --- environment must be set BEFORE any lnbits/infinitemarkets import ---------

WORK = Path(tempfile.mkdtemp(prefix="conf-nostrrelay-"))
EXT_ROOT = WORK / "extroot"
DATA_DIR = WORK / "data"
EXT_DIR = EXT_ROOT / "extensions"
EXT_DIR.mkdir(parents=True)
DATA_DIR.mkdir()

(EXT_DIR / "infinitemarkets").symlink_to(PKG_DIR, target_is_directory=True)
if not NOSTRRELAY_SRC.exists():
    print(
        json.dumps(
            {
                "outcome": "error",
                "detail": (
                    f"nostrrelay source missing at {NOSTRRELAY_SRC} — clone "
                    "https://github.com/lnbits/nostrrelay and set NOSTRRELAY_SRC"
                ),
            }
        )
    )
    sys.exit(2)
shutil.copytree(
    NOSTRRELAY_SRC,
    EXT_DIR / "nostrrelay",
    ignore=shutil.ignore_patterns(".git", "node_modules", "__pycache__",
                                  ".venv", "dist"),
)

import base64  # noqa: E402

_DEFAULT_KEYS = base64.b64encode(b"k" * 32).decode()
os.environ.update(
    {
        "INFINITEMARKETS_MASTER_KEYS": json.dumps({"v1": _DEFAULT_KEYS}),
        "INFINITEMARKETS_ACTIVE_KEY_VERSION": "v1",
        "INFINITEMARKETS_PRIVACY_KEY": base64.b64encode(b"p" * 32).decode(),
        "INFINITEMARKETS_RELAY_IO": "on",
        "INFINITEMARKETS_ALLOW_INSECURE_RELAYS": "1",
        "LNBITS_DATA_FOLDER": str(DATA_DIR),
        "LNBITS_EXTENSIONS_PATH": str(EXT_ROOT),
        "LNBITS_EXTENSIONS_DEACTIVATE_ALL": "false",
        "LNBITS_BACKEND_WALLET_CLASS": "FakeWallet",
        "LNBITS_ADMIN_UI": "true",
        "LNBITS_AUDIT_LOG_REQUEST_BODY": "false",
        "LNBITS_AUDIT_LOG_QUERY_PARAMS": "false",
        "LNBITS_AUDIT_LOG_PATH_PARAMS": "false",
        "FIRST_INSTALL": "true",
    }
)


def _free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _derive_nsec(label: str) -> str:
    """Deterministic test-only merchant nsec — disposable envs only."""
    import hashlib

    from nostr_sdk import Keys

    secret = hashlib.sha256(
        f"infinitemarkets-conformance:{label}".encode()
    ).hexdigest()
    return Keys.parse(secret).secret_key().to_bech32()


def nostrrelay_revision() -> str:
    out = subprocess_run(["git", "-C", str(NOSTRRELAY_SRC),
                          "rev-parse", "HEAD"])
    return out.strip() if out else "unknown"


def subprocess_run(cmd: list[str]) -> str:
    import subprocess

    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=20, check=True
        ).stdout
    except Exception:  # noqa: BLE001 — provenance is best-effort
        return ""


# --- websocket probe helpers --------------------------------------------------


class WsProbe:
    """Minimal Nostr websocket probe client (JSON lines over one
    connection). Records every frame for post-hoc assertions."""

    def __init__(self, url: str):
        self.url = url
        self.frames: list[list] = []
        self._ws = None

    async def __aenter__(self) -> "WsProbe":
        from websockets.asyncio.client import connect

        self._ws = await connect(self.url, open_timeout=10)
        return self

    async def __aexit__(self, *exc) -> None:
        if self._ws is not None:
            await self._ws.close()

    async def send(self, frame: list) -> None:
        await self._ws.send(json.dumps(frame))

    async def req(self, sub_id: str, *filters: dict) -> None:
        await self.send(["REQ", sub_id, *filters])

    async def event(self, ev: dict) -> None:
        await self.send(["EVENT", ev])

    async def auth(self, ev: dict) -> None:
        await self.send(["AUTH", ev])

    async def collect(self, seconds: float = 5.0) -> list[list]:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                raw = await asyncio.wait_for(
                    self._ws.recv(),
                    timeout=max(0.05, deadline - time.monotonic()),
                )
            except (asyncio.TimeoutError, TimeoutError):
                break
            except Exception:  # noqa: BLE001 — connection closed mid-probe
                break
            try:
                self.frames.append(json.loads(raw))
            except ValueError:
                self.frames.append([raw])
        return self.frames

    def kinds(self) -> list[str]:
        return [f[0] for f in self.frames if isinstance(f, list) and f]

    def events(self) -> list[dict]:
        return [f[2] for f in self.frames
                if isinstance(f, list) and len(f) >= 3
                and f[0] == "EVENT" and isinstance(f[2], dict)]

    def notices(self) -> list[str]:
        return [f[1] for f in self.frames
                if isinstance(f, list) and len(f) >= 2 and f[0] == "NOTICE"]

    def oks(self) -> list[list]:
        return [f for f in self.frames
                if isinstance(f, list) and len(f) >= 3 and f[0] == "OK"]

    def challenges(self) -> list[str]:
        return [f[1] for f in self.frames
                if isinstance(f, list) and len(f) == 2 and f[0] == "AUTH"
                and isinstance(f[1], str)]


async def _auth_event(secret_nsec_or_hex: str, challenge: str,
                      relay_url: str) -> dict:
    from nostr_sdk import EventBuilder, Keys, NostrSigner, RelayUrl

    keys = Keys.parse(secret_nsec_or_hex)
    unsigned = EventBuilder.auth(
        challenge, RelayUrl.parse(relay_url)
    ).build(keys.public_key())
    signed = await unsigned.sign(NostrSigner.keys(keys))
    return json.loads(signed.as_json())


async def _wrap_to(secret_hex: str, merchant_pubkey: str, *,
                   order_id: str) -> dict:
    """Buyer-authored kind-16 type-1 rumor -> seal -> kind-1059 wrap."""
    from nostr_sdk import Keys, PublicKey

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from harness import sdk

    buyer = Keys.parse(secret_hex)
    merchant_pk = PublicKey.parse(merchant_pubkey)
    rumor = sdk.build_order_rumor(
        buyer,
        merchant_pk,
        order_external_id=order_id,
        amount_sat=700,
        items=[("30402:" + merchant_pubkey + ":conf-widget", 1)],
        created_at=int(time.time()),
    )
    seal = await sdk.seal_rumor(buyer, merchant_pk, rumor)
    wrap = sdk.wrap_seal(merchant_pk, seal)
    return json.loads(wrap.as_json())


# --- provisioning -------------------------------------------------------------


async def _admin_put(http, path: str, adminkey: str, body: dict):
    return await http.put(
        path, json=body, headers={"X-Api-Key": adminkey}
    )


async def _admin_post(http, path: str, adminkey: str, body: dict):
    return await http.post(
        path, json=body, headers={"X-Api-Key": adminkey}
    )


async def _admin_get(http, path: str, adminkey: str):
    return await http.get(path, headers={"X-Api-Key": adminkey})


async def provision(http, adminkey: str) -> dict:
    """Create the gated + open relays. The merchant account allowlist row
    is added separately (``allowlist``) once the merchant exists.

    Returns ``{"gated": {...}, "open": {...}}`` with ws URLs.
    """
    base = str(http.base_url).rstrip("/")

    gated_meta = {
        "requireAuthFilter": True,
        "isPaidRelay": True,
        "costToJoin": 21,
        # NIP-59 wraps are backdated up to two days — accept that window.
        "createdAtDaysPast": 3,
        "freeStorageValue": 8,
        "freeStorageUnit": "MB",
        "limitPerFilter": 1000,
    }
    resp = await _admin_post(http, "/nostrrelay/api/v1/relay", adminkey, {
        "id": "",
        "name": "gamma-gated-inbox",
        "description": "Release-B gated relay (auth + allowlist reads)",
        "active": False,
        "meta": gated_meta,
    })
    assert resp.status_code == 200, resp.text
    gated = resp.json()
    resp = await _admin_put(
        http, f"/nostrrelay/api/v1/relay/{gated['id']}", adminkey, {}
    )
    assert resp.status_code == 200, resp.text
    gated = resp.json()

    open_meta = {
        "requireAuthFilter": False,
        "isPaidRelay": False,
        "costToJoin": 0,
        "createdAtDaysPast": 3,
        "freeStorageValue": 8,
        "freeStorageUnit": "MB",
        "limitPerFilter": 1000,
    }
    resp = await _admin_post(http, "/nostrrelay/api/v1/relay", adminkey, {
        "id": "",
        "name": "gamma-open-inbox",
        "description": "Release-B open-write relay",
        "active": False,
        "meta": open_meta,
    })
    assert resp.status_code == 200, resp.text
    opened = resp.json()
    resp = await _admin_put(
        http, f"/nostrrelay/api/v1/relay/{opened['id']}", adminkey, {}
    )
    assert resp.status_code == 200, resp.text
    opened = resp.json()

    # A third relay: paid, no allowlisted account — the merchant's own
    # publish to it produces the durable negative-OK publication row
    # (D-27 surfaced, never paid).
    resp = await _admin_post(http, "/nostrrelay/api/v1/relay", adminkey, {
        "id": "",
        "name": "gamma-paywall",
        "description": "Release-B paid relay (no allowlist)",
        "active": False,
        "meta": {
            "requireAuthFilter": False,
            "isPaidRelay": True,
            "costToJoin": 21,
            "createdAtDaysPast": 3,
            "freeStorageValue": 8,
            "freeStorageUnit": "MB",
        },
    })
    assert resp.status_code == 200, resp.text
    paywall = resp.json()
    resp = await _admin_put(
        http, f"/nostrrelay/api/v1/relay/{paywall['id']}", adminkey, {}
    )
    assert resp.status_code == 200, resp.text
    paywall = resp.json()

    return {
        "gated": {
            "id": gated["id"],
            "ws": f"{base.replace('http', 'ws')}/nostrrelay/{gated['id']}",
            "meta": gated["meta"],
        },
        "open": {
            "id": opened["id"],
            "ws": f"{base.replace('http', 'ws')}/nostrrelay/{opened['id']}",
            "meta": opened["meta"],
        },
        "paywall": {
            "id": paywall["id"],
            "ws": f"{base.replace('http', 'ws')}/nostrrelay/{paywall['id']}",
            "meta": paywall["meta"],
        },
    }


async def allowlist(http, adminkey: str, relay_id: str,
                    merchant_pubkey: str) -> dict:
    """Allowlist the merchant account on the gated relay."""
    resp = await _admin_put(http, "/nostrrelay/api/v1/account", adminkey, {
        "relay_id": relay_id, "pubkey": merchant_pubkey, "allowed": True,
    })
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- the probe battery --------------------------------------------------------


async def probe_gated_anon_req(gated_ws: str, merchant_pubkey: str,
                               probes: list) -> None:
    async with WsProbe(gated_ws) as ws:
        await ws.req("s1", {"kinds": [1059], "#p": [merchant_pubkey]})
        await ws.collect(4.0)
        ok = (
            bool(ws.challenges())
            and not ws.events()
            and "EOSE" not in ws.kinds()
        )
        probes.append({
            "name": "gated_anon_req",
            "outcome": "pass" if ok else "fail",
            "detail": {
                "challenge": bool(ws.challenges()),
                "events": len(ws.events()),
                "eose": "EOSE" in ws.kinds(),
            },
        })


async def probe_gated_stranger_req(gated_ws: str, merchant_pubkey: str,
                                 stranger_hex: str, probes: list) -> None:
    async with WsProbe(gated_ws) as ws:
        await ws.req("s1", {"kinds": [1059], "#p": [merchant_pubkey]})
        await ws.collect(3.0)
        challenge = (ws.challenges() or [None])[0]
        authed = False
        if challenge:
            auth = await _auth_event(stranger_hex, challenge, gated_ws)
            await ws.auth(auth)
            await ws.collect(1.5)
            await ws.req("s1", {"kinds": [1059], "#p": [merchant_pubkey]})
            await ws.collect(3.0)
            authed = True
        paid_notice = any("paid relay" in n.lower() for n in ws.notices())
        ok = authed and paid_notice and not ws.events()
        probes.append({
            "name": "gated_stranger_req",
            "outcome": "pass" if ok else "fail",
            "detail": {
                "auth_sent": authed,
                "paid_notice": paid_notice,
                "events": len(ws.events()),
                "frames": [f[:2] for f in ws.frames],
            },
        })


async def probe_gated_merchant_req(gated_ws: str, merchant_nsec: str,
                                   merchant_pubkey: str,
                                   probes: list) -> list[dict]:
    """Authed merchant writes two wraps (allowed account -> free quota)
    then REQs — wraps + EOSE must be served. Returns stored wrap dicts."""
    wrap_events: list[dict] = []
    async with WsProbe(gated_ws) as ws:
        await ws.req("s0", {"kinds": [1059], "#p": [merchant_pubkey]})
        await ws.collect(2.5)
        challenge = (ws.challenges() or [None])[0]
        if not challenge:
            probes.append({
                "name": "gated_merchant_req",
                "outcome": "fail",
                "detail": {"reason": "no AUTH challenge issued"},
            })
            return wrap_events
        auth = await _auth_event(merchant_nsec, challenge, gated_ws)
        await ws.auth(auth)
        await ws.collect(1.5)

        # Allowed account can write — seed two merchant-directed wraps.
        buyer_hex = "aa" * 32
        wrap_ids: list[str] = []
        for i in range(2):
            ev = await _wrap_to(
                buyer_hex, merchant_pubkey, order_id=f"gated-{i}"
            )
            wrap_ids.append(ev["id"])
            await ws.event(ev)
        await ws.collect(2.5)
        # Match OKs by wrap event id — the AUTH event's own OK frame
        # must not be miscounted among the write acceptances.
        oks = {o[1]: o for o in ws.oks() if len(o) >= 3}
        wrote = [
            wid for wid in wrap_ids
            if wid in oks and oks[wid][2] is True
        ]

        ws.frames.clear()
        await ws.req("s1", {"kinds": [1059], "#p": [merchant_pubkey]})
        await ws.collect(4.0)
        wrap_events = ws.events()
        ok = (
            len(wrote) == 2
            and len(wrap_events) >= 2
            and "EOSE" in ws.kinds()
        )
        probes.append({
            "name": "gated_merchant_req",
            "outcome": "pass" if ok else "fail",
            "detail": {
                "write_oks": list(wrote),
                "events": len(wrap_events),
                "eose": "EOSE" in ws.kinds(),
            },
        })
    return wrap_events


async def probe_open_write(open_ws: str, merchant_pubkey: str,
                           buyer_hex: str, probes: list) -> dict | None:
    """Anonymous kind-1059 write to the open relay must be accepted.
    Returns the accepted wrap event (reused by the extension-path probe)."""
    ev = await _wrap_to(buyer_hex, merchant_pubkey, order_id="open-1")
    async with WsProbe(open_ws) as ws:
        await ws.event(ev)
        await ws.collect(3.0)
        accepted = any(len(o) >= 3 and o[2] is True for o in ws.oks())
        # read-back: REQ serves the stored event
        ws.frames.clear()
        await ws.req("s1", {"kinds": [1059], "#p": [merchant_pubkey]})
        await ws.collect(3.0)
        served = any(e.get("id") == ev["id"] for e in ws.events())
        ok = accepted and served
        probes.append({
            "name": "open_write_accepted",
            "outcome": "pass" if ok else "fail",
            "detail": {"ok": accepted, "served": served},
        })
    return ev if ok else None


async def probe_gated_paid_write(gated_ws: str, merchant_pubkey: str,
                                 stranger_hex: str, probes: list) -> None:
    ev = await _wrap_to(stranger_hex, merchant_pubkey, order_id="paid-1")
    async with WsProbe(gated_ws) as ws:
        await ws.event(ev)
        await ws.collect(3.0)
        oks = ws.oks()
        neg = [o for o in oks if len(o) >= 4 and o[2] is False]
        paid = neg and "paid relay" in str(neg[0][3]).lower()
        classified = None
        if paid:
            from infinitemarkets.services import nostr_auth

            state, _invoice = nostr_auth.classify_relay_ok(str(neg[0][3]))
            classified = state
        ok = bool(paid) and classified == "payment-required"
        probes.append({
            "name": "gated_paid_write",
            "outcome": "pass" if ok else "fail",
            "detail": {
                "ok_frames": oks,
                "classified": classified,
            },
        })


async def probe_extension_inbox(mid: str, gated_ws: str, open_ws: str,
                                probes: list) -> None:
    """Drive the REAL extension inbox runtime against both relays.

    Gated session: REQ -> AUTH challenge -> manual NIP-42 answer ->
    post-auth REQ re-issue -> served wraps -> admitted rows.
    Open session: plain REQ -> wraps admitted.
    """
    from infinitemarkets.db import db as ext_db
    from infinitemarkets.services.inbox import drain_received, inbox_runtime

    rt = inbox_runtime()
    await rt.reconcile()
    await asyncio.sleep(1.0)
    await rt.reconcile()
    await asyncio.sleep(2.5)

    async with ext_db.connect() as conn:
        auth_row = await conn.fetchone(
            "SELECT auth_state FROM infinitemarkets.relay_configs"
            " WHERE merchant_id = :m AND relay_url = :u",
            {"m": mid, "u": gated_ws},
        )
        rows = await conn.fetchall(
            "SELECT source_relay_url, processed_state FROM"
            " infinitemarkets.inbox_events WHERE merchant_id = :m",
            {"m": mid},
        )
    gated_rows = [r for r in rows if r["source_relay_url"] == gated_ws]
    open_rows = [r for r in rows if r["source_relay_url"] == open_ws]

    await drain_received()

    probes.append({
        "name": "extension_gated_inbox",
        "outcome": (
            "pass"
            if gated_rows
            and auth_row
            and auth_row["auth_state"] in ("auth-sent", "authenticated")
            else "fail"
        ),
        "detail": {
            "auth_state": auth_row["auth_state"] if auth_row else None,
            "admitted": len(gated_rows),
            "states": [r["processed_state"] for r in gated_rows],
        },
    })
    probes.append({
        "name": "extension_open_inbox",
        "outcome": "pass" if open_rows else "fail",
        "detail": {
            "admitted": len(open_rows),
            "states": [r["processed_state"] for r in open_rows],
        },
    })


async def probe_paid_publish_surface(mid: str, paywall_ws: str,
                                     account, probes: list) -> None:
    """Publish a kind-0 profile to a paid relay through the real outbox —
    the negative OK lands as a durable ``rejected`` relay_publications
    row with the paid-relay reason verbatim (surfaced, never paid)."""
    import time as _t

    from infinitemarkets.db import DomainTransaction, db
    from infinitemarkets.services import merchant as merchant_service
    from infinitemarkets.services import outbox

    async with DomainTransaction() as tx:
        await tx.execute(
            f"INSERT INTO {tx.table('relay_configs')} "
            "(id, merchant_id, relay_url, direction, enabled,"
            " created_at, updated_at) VALUES (:i, :m, :u, 'public', TRUE,"
            " :t, :t)",
            {"i": uuid.uuid4().hex, "m": mid, "u": paywall_ws,
             "t": int(_t.time())},
        )
    from types import SimpleNamespace

    user = SimpleNamespace(id=account.id)
    await merchant_service.publish(mid, user)
    for _ in range(25):
        await outbox.worker_tick(f"conf-{uuid.uuid4().hex[:6]}")
        async with db.connect() as conn:
            row = await conn.fetchone(
                "SELECT COUNT(*) AS n FROM infinitemarkets.relay_publications"
                " rp JOIN infinitemarkets.outbox_events oe"
                " ON oe.id = rp.outbox_event_id"
                " WHERE oe.merchant_id = :m AND rp.relay_url = :u"
                " AND rp.result = 'rejected'",
                {"m": mid, "u": paywall_ws},
            )
        if row and int(row["n"]) > 0:
            break
        await asyncio.sleep(0.3)
    async with db.connect() as conn:
        rows = await conn.fetchall(
            "SELECT rp.result, rp.message FROM"
            " infinitemarkets.relay_publications rp JOIN"
            " infinitemarkets.outbox_events oe"
            " ON oe.id = rp.outbox_event_id"
            " WHERE oe.merchant_id = :m AND rp.relay_url = :u",
            {"m": mid, "u": paywall_ws},
        )
    rejected = [
        r for r in rows
        if r["result"] == "rejected"
        and "paid relay" in str(r.get("message", "")).lower()
    ]
    probes.append({
        "name": "paid_publish_surface",
        "outcome": "pass" if rejected else "fail",
        "detail": {"publications": [dict(r) for r in rows]},
    })


# --- host boot + orchestration -------------------------------------------------


async def _wait_started(server, serve_task, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while not server.started:
        if serve_task.done():
            raise serve_task.exception() or RuntimeError("serve exited")
        if time.monotonic() > deadline:
            raise TimeoutError("uvicorn did not start")
        await asyncio.sleep(0.05)


async def boot(port: int | None = None) -> dict:
    """Boot the pinned LNbits host with nostrrelay + infinitemarkets."""
    import uvicorn

    port = port or _free_port()
    os.environ["INFINITEMARKETS_PUBLIC_BASE_URL"] = (
        f"https://localhost:{port}"
    )
    from tools.checkout_host import host_checkout_dir

    host_dir = host_checkout_dir()
    os.chdir(host_dir)
    from lnbits.app import check_and_register_extensions, create_app
    from lnbits.core.crud import create_wallet
    from lnbits.core.crud.users import create_account
    from lnbits.core.models.users import Account, UpdateSuperuserPassword
    from lnbits.core.services import update_wallet_balance
    from lnbits.core.views.auth_api import first_install
    from lnbits.settings import settings

    app = create_app()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port,
                       log_level="warning")
    )
    serve = asyncio.create_task(server.serve())
    await _wait_started(server, serve)

    # Purge any stale extension module (fresh process shouldn't have one)
    for mod in [m for m in sys.modules if m == "infinitemarkets"
                or m.startswith("infinitemarkets.")]:
        del sys.modules[mod]
    await first_install(
        UpdateSuperuserPassword(
            username="confadmin" + uuid.uuid4().hex[:8],
            password="secret1234",
            password_repeat="secret1234",
            first_install_token=settings.first_install_token,
        )
    )
    await check_and_register_extensions(app)

    account = Account(
        id=uuid.uuid4().hex, username="confuser" + uuid.uuid4().hex[:8],
        email=None,
    )
    account.hash_password("conf-pass-123")
    await create_account(account)
    wallet = await create_wallet(user_id=account.id, wallet_name="conf")
    await update_wallet_balance(wallet=wallet, amount=9_999_999)

    # Per-user extension enablement gates every extension API route.
    from lnbits.core.crud import (
        create_user_extension,
        get_user_extension,
        update_user_extension,
    )
    from lnbits.core.models.extensions import UserExtension

    for ext_id in ("infinitemarkets", "nostrrelay"):
        ue = await get_user_extension(account.id, ext_id)
        if ue is None:
            await create_user_extension(
                UserExtension(
                    user=account.id, extension=ext_id, active=True
                )
            )
        elif not ue.active:
            ue.active = True
            await update_user_extension(ue)

    return {
        "app": app, "server": server, "serve": serve, "port": port,
        "base": f"http://127.0.0.1:{port}", "account": account,
        "wallet": wallet,
    }


async def seed_merchant(account, wallet, gated_ws: str, open_ws: str) -> dict:
    """Create the extension merchant, import a deterministic test nsec,
    configure inbox relays [gated, open] + public [open], publish, and
    activate the Gamma inbox — all through the real service layer."""
    from types import SimpleNamespace

    from infinitemarkets.db import DomainTransaction, db
    from infinitemarkets.services import merchant as merchant_service
    from infinitemarkets.services import outbox

    user = SimpleNamespace(id=account.id)
    merchant = await merchant_service.create_merchant(
        user, wallet_id=wallet.id, display_name="conf shop"
    )
    mid = merchant["id"]
    nsec = _derive_nsec("nostrrelay-merchant")
    merchant = await merchant_service.import_nsec(mid, user, nsec)
    pubkey = merchant["pubkey"]

    now = int(time.time())
    async with DomainTransaction() as tx:
        for url, direction in (
            (gated_ws, "inbox"), (open_ws, "inbox"), (open_ws, "public"),
        ):
            await tx.execute(
                f"INSERT INTO {tx.table('relay_configs')} "
                "(id, merchant_id, relay_url, direction, enabled,"
                " created_at, updated_at) VALUES (:i, :m, :u, :d, TRUE,"
                " :t, :t)",
                {"i": uuid.uuid4().hex, "m": mid, "u": url,
                 "d": direction, "t": now},
            )

    await merchant_service.publish(mid, user)
    await merchant_service.enable_inbox(mid, user)

    # Drive the real outbox worker until the kind-10050 intent resolves.
    for _ in range(20):
        await outbox.worker_tick(f"conf-{uuid.uuid4().hex[:6]}")
        async with db.connect() as conn:
            row = await conn.fetchone(
                "SELECT inbox_state FROM infinitemarkets.merchants"
                " WHERE id = :i", {"i": mid}
            )
        if row and row["inbox_state"] == "active":
            break
        await asyncio.sleep(0.4)

    async with db.connect() as conn:
        state = await conn.fetchone(
            "SELECT inbox_state FROM infinitemarkets.merchants"
            " WHERE id = :i", {"i": mid}
        )
        pubs = await conn.fetchall(
            "SELECT rp.relay_url, rp.result, rp.message FROM"
            " infinitemarkets.relay_publications rp JOIN"
            " infinitemarkets.outbox_events oe"
            " ON oe.id = rp.outbox_event_id"
            " WHERE oe.event_kind = 10050 AND oe.merchant_id = :m",
            {"m": mid},
        )
    return {
        "mid": mid, "pubkey": pubkey, "nsec": nsec,
        "inbox_state": state["inbox_state"] if state else None,
        "kind10050_publications": [dict(r) for r in pubs],
    }


async def run(probes_out: Path | None = None,
              port: int | None = None) -> int:
    env = await boot(port)
    port, base = env["port"], env["base"]
    import httpx

    merchant_nsec = _derive_nsec("nostrrelay-merchant")
    merchant_pubkey = ""
    probes: list[dict] = []

    async with httpx.AsyncClient(base_url=base, timeout=15.0) as http:
        relays = await provision(http, env["wallet"].adminkey)
    # allowlist needs the merchant pubkey — seed merchant first, then
    # create the account row.
    seeded = await seed_merchant(
        env["account"], env["wallet"],
        relays["gated"]["ws"], relays["open"]["ws"],
    )
    merchant_pubkey = seeded["pubkey"]
    async with httpx.AsyncClient(base_url=base, timeout=15.0) as http:
        await allowlist(http, env["wallet"].adminkey,
                        relays["gated"]["id"], merchant_pubkey)

    buyer_hex = "bb" * 32
    stranger_hex = "cc" * 32
    gated_ws, open_ws = relays["gated"]["ws"], relays["open"]["ws"]
    paywall_ws = relays["paywall"]["ws"]

    try:
        await probe_gated_anon_req(gated_ws, merchant_pubkey, probes)
        await probe_gated_stranger_req(
            gated_ws, merchant_pubkey, stranger_hex, probes
        )
        await probe_gated_merchant_req(
            gated_ws, merchant_nsec, merchant_pubkey, probes
        )
        await probe_open_write(open_ws, merchant_pubkey, buyer_hex, probes)
        await probe_gated_paid_write(
            gated_ws, merchant_pubkey, stranger_hex, probes
        )
        # D-27 through the real outbox: add the paywall relay as a public
        # target, republish the kind-0 profile, and let a worker tick
        # record the paid-relay negative OK as a rejected publication.
        await probe_paid_publish_surface(
            seeded["mid"], paywall_ws, env["account"], probes
        )
        await probe_extension_inbox(
            seeded["mid"], gated_ws, open_ws, probes
        )
    except Exception as exc:  # noqa: BLE001 — report, never raise raw
        probes.append({
            "name": "probe_driver",
            "outcome": "fail",
            "detail": {"error": f"{type(exc).__name__}: {exc}"},
        })

    outcome = "pass" if all(p["outcome"] == "pass" for p in probes) else "fail"
    report = {
        "artifact": "nostrrelay-env",
        "generated_at": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
        ),
        "outcome": outcome,
        "host": {
            "port": port, "base": base,
            "data_dir": str(DATA_DIR),
        },
        "relays": {
            "gated": {"id": relays["gated"]["id"], "ws": gated_ws,
                      "requireAuthFilter": True, "paid": True,
                      "allowlist": [merchant_pubkey]},
            "open": {"id": relays["open"]["id"], "ws": open_ws,
                     "requireAuthFilter": False, "paid": False},
            "paywall": {"id": relays["paywall"]["id"], "ws": paywall_ws,
                        "requireAuthFilter": False, "paid": True},
        },
        "merchant": {
            "pubkey": merchant_pubkey,
            "inbox_state": seeded["inbox_state"],
        },
        "pins": {
            "nostrrelay_commit": nostrrelay_revision(),
            "nostrrelay_src": str(NOSTRRELAY_SRC),
        },
        "probes": probes,
    }
    if probes_out:
        probes_out.parent.mkdir(parents=True, exist_ok=True)
        probes_out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))

    env["server"].should_exit = True
    await asyncio.wait_for(env["serve"], timeout=10)
    return 0 if outcome == "pass" else 1


async def serve(port: int) -> None:
    env = await boot(port)
    import httpx

    async with httpx.AsyncClient(
        base_url=env["base"], timeout=15.0
    ) as http:
        relays = await provision(http, env["wallet"].adminkey)
    seeded = await seed_merchant(
        env["account"], env["wallet"],
        relays["gated"]["ws"], relays["open"]["ws"],
    )
    async with httpx.AsyncClient(
        base_url=env["base"], timeout=15.0
    ) as http:
        await allowlist(http, env["wallet"].adminkey,
                        relays["gated"]["id"], seeded["pubkey"])
    print(json.dumps({
        "base": env["base"],
        "gated": relays["gated"], "open": relays["open"],
        "merchant_pubkey": seeded["pubkey"],
        "inbox_state": seeded["inbox_state"],
    }, indent=2))
    try:
        await env["serve"]
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    run_p = sub.add_parser("run", help="boot, provision, probe, report")
    run_p.add_argument("--json-out", type=Path, default=None)
    run_p.add_argument("--port", type=int, default=None)
    serve_p = sub.add_parser("serve", help="boot and serve until killed")
    serve_p.add_argument("--port", type=int, default=0)
    args = parser.parse_args()

    if args.cmd == "run":
        raise SystemExit(asyncio.run(run(args.json_out, args.port)))
    raise SystemExit(asyncio.run(serve(args.port or _free_port())))


if __name__ == "__main__":
    main()
