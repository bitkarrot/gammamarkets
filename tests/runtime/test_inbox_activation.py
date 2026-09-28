"""Gamma inbox activation (GAM-01/D-16/D-17) — the kind-10050 vertical.

Enable -> kind-10050 intent -> durable outbox publish -> >=1 ``accepted``
``relay_publications`` row -> ``inbox_state='active'``. Deactivation emits
the ``10050:<pk>:`` kind-5 tombstone and lands at ``off``; exhausted
publishes land at ``error``.

The host boots with ``INFINITEMARKETS_RELAY_IO=off`` (fixture default);
the tests flip that env plus ``INFINITEMARKETS_ALLOW_INSECURE_RELAYS`` at
call time so the REAL running outbox worker dials ``harness.relay
.LocalRelay`` — the whole activation path is proven on live workers, not
a stubbed publisher.
"""

from __future__ import annotations

import asyncio
import time
import uuid

import pytest

pytestmark = pytest.mark.runtime


def _headers(env: dict, csrf: str | None = None) -> dict:
    cookie = f"cookie_access_token={env['token']}"
    if csrf:
        cookie += f"; gm_csrf={csrf}"
    h = {"Cookie": cookie, "Origin": "https://shop.example"}
    if csrf:
        h["X-CSRF-Token"] = csrf
    return h


def _csrf(client) -> str:
    return client.cookies.get("gm_csrf") or ""


async def _merchant_id(env: dict) -> tuple[str, str]:
    """Create (or fetch) the module merchant; return (id, csrf)."""
    client = env["client"]
    existing = await client.get(
        "/infinitemarkets/api/v1/merchants/current", headers=_headers(env)
    )
    if existing.status_code == 200:
        return existing.json()["id"], _csrf(client)
    resp = await client.post(
        "/infinitemarkets/api/v1/merchants",
        json={"wallet_id": env["wallet"].id},
        headers=_headers(env, _csrf(client)),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"], _csrf(client)


async def _set_relays(env: dict, mid: str, csrf: str, configs: list[dict]):
    client = env["client"]
    resp = await client.patch(
        f"/infinitemarkets/api/v1/merchants/{mid}",
        json={"relay_configs": configs},
        headers=_headers(env, csrf),
    )
    assert resp.status_code == 200, resp.text


async def _inbox_state(ext_module, mid: str) -> str:
    async with ext_module.db.connect() as conn:
        row = await conn.fetchone(
            "SELECT inbox_state FROM infinitemarkets.merchants WHERE id = :i",
            {"i": mid},
        )
    return row["inbox_state"]


async def _inbox_intents(ext_module, mid: str) -> list[dict]:
    async with ext_module.db.connect() as conn:
        rows = await conn.fetchall(
            "SELECT * FROM infinitemarkets.outbox_events "
            "WHERE merchant_id = :m AND aggregate_type = 'merchant' "
            "ORDER BY created_at, aggregate_revision",
            {"m": mid},
        )
    return [dict(r) for r in rows]


async def _publications(ext_module, intent_id: str) -> list[dict]:
    async with ext_module.db.connect() as conn:
        rows = await conn.fetchall(
            "SELECT * FROM infinitemarkets.relay_publications "
            "WHERE outbox_event_id = :i",
            {"i": intent_id},
        )
    return [dict(r) for r in rows]


async def _wait_state(ext_module, mid: str, state: str, timeout: float = 45.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = await _inbox_state(ext_module, mid)
        if current == state:
            return current
        await asyncio.sleep(0.5)
    raise AssertionError(
        f"inbox_state never reached {state!r} (last={current!r})"
    )


async def _order_count(ext_module, mid: str) -> int:
    async with ext_module.db.connect() as conn:
        row = await conn.fetchone(
            "SELECT COUNT(*) AS n FROM infinitemarkets.orders "
            "WHERE merchant_id = :m",
            {"m": mid},
        )
    return int(row["n"])


async def test_m006_schema_present(runtime_env):
    """peer_relays / relay_cursors / inbox_blocklist + the new columns all
    exist on the booted host's migrated schema."""
    from lnbits.db import POSTGRES

    db = runtime_env["ext_module"].db
    async with db.connect() as conn:
        if db.type == POSTGRES:
            rows = await conn.fetchall(
                "SELECT table_name AS name FROM information_schema.tables "
                "WHERE table_schema = 'infinitemarkets'"
            )
        else:
            rows = await conn.fetchall(
                "SELECT name FROM infinitemarkets.sqlite_master "
                "WHERE type = 'table'"
            )
    names = {r["name"] for r in rows}
    assert {"peer_relays", "relay_cursors", "inbox_blocklist"} <= names


async def test_enable_requires_inbox_relay(runtime_env):
    """Enable with zero enabled inbox-direction relays -> 422
    ``no-inbox-relays`` (a merchant with configs of its own is NOT seeded
    with inbox defaults)."""
    env, client = runtime_env, runtime_env["client"]
    mid, csrf = await _merchant_id(env)
    await _set_relays(
        env, mid, csrf,
        [{"relay_url": "wss://relay-public.example", "direction": "public"}],
    )
    resp = await client.post(
        f"/infinitemarkets/api/v1/merchants/{mid}/inbox/enable",
        headers=_headers(env, csrf),
    )
    assert resp.status_code == 422, resp.text
    assert "no-inbox-relays" in resp.text
    assert await _inbox_state(runtime_env["ext_module"], mid) == "off"


async def test_build_kind10050_deterministic(runtime_env, monkeypatch):
    """Identical inputs -> byte-identical unsigned dicts; >3 relays or a
    non-wss URL raises."""
    monkeypatch.delenv("INFINITEMARKETS_ALLOW_INSECURE_RELAYS", raising=False)
    from infinitemarkets.services import events

    urls = ["wss://b.example", "wss://a.example"]
    first = events.build_kind10050("ab" * 32, urls)
    second = events.build_kind10050("ab" * 32, list(urls))
    assert first == second
    assert first["kind"] == 10050
    assert first["content"] == ""
    assert first["tags"] == [["relay", "wss://b.example"],
                             ["relay", "wss://a.example"]]

    with pytest.raises(Exception):
        events.build_kind10050(
            "ab" * 32,
            ["wss://a.example", "wss://b.example",
             "wss://c.example", "wss://d.example"],
        )
    with pytest.raises(Exception):
        events.build_kind10050("ab" * 32, ["https://not-a-relay.example"])
    with pytest.raises(Exception):
        events.build_kind10050("ab" * 32, [])


async def test_activation_vertical(runtime_env, monkeypatch):
    """The tracer slice end to end on the live outbox worker:

    enable -> pending -> (accepted OK) -> active -> disable -> tombstone
    -> off -> re-enable -> active. Asserts durable evidence rows and the
    10050:<pk>: protocol address at each step.
    """
    from harness import relay as relay_module

    env, client = runtime_env, runtime_env["client"]
    ext_module = runtime_env["ext_module"]
    mid, csrf = await _merchant_id(env)
    pubkey_resp = await client.get(
        "/infinitemarkets/api/v1/merchants/current", headers=_headers(env)
    )
    pubkey = pubkey_resp.json()["pubkey"]

    # Let the real worker dial the deterministic local relay.
    monkeypatch.setenv("INFINITEMARKETS_RELAY_IO", "on")
    monkeypatch.setenv("INFINITEMARKETS_ALLOW_INSECURE_RELAYS", "1")

    async with relay_module.LocalRelay(
        mode=relay_module.RelayMode.ACCEPTING
    ) as accepting:
        await _set_relays(
            env, mid, csrf,
            [{"relay_url": accepting.url, "direction": "inbox"}],
        )

        # --- enable -> pending -> accepted -> active ---------------------
        resp = await client.post(
            f"/infinitemarkets/api/v1/merchants/{mid}/inbox/enable",
            headers=_headers(env, csrf),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["inbox_state"] == "pending"
        assert await _inbox_state(ext_module, mid) == "pending"

        await _wait_state(ext_module, mid, "active")

        intents = await _inbox_intents(ext_module, mid)
        publish_intent = [i for i in intents if i["event_kind"] == 10050]
        assert publish_intent, "kind-10050 intent missing"
        publish_intent = publish_intent[-1]
        assert publish_intent["state"] == "published"
        assert publish_intent["event_address"] == f"10050:{pubkey}:"

        pubs = await _publications(ext_module, publish_intent["id"])
        assert any(p["result"] == "accepted" for p in pubs), (
            "inbox_state=active without positive OK evidence"
        )
        assert accepting.received_events, "relay saw no EVENT"
        received = accepting.received_events[0]["event"]
        assert received["kind"] == 10050
        assert [t[0] for t in received["tags"]] == ["relay"]

        # §4.13: non-addressable replaceable -> empty d_tag row exists.
        async with ext_module.db.connect() as conn:
            addr = await conn.fetchone(
                "SELECT * FROM infinitemarkets.protocol_addresses "
                "WHERE event_kind = 10050 AND author_pubkey = :p AND d_tag = ''",
                {"p": pubkey},
            )
        assert addr and addr["latest_event_id"] == received["id"]

        # GET /inbox-state exposes the evidence surface.
        state = await client.get(
            f"/infinitemarkets/api/v1/merchants/{mid}/inbox-state",
            headers=_headers(env),
        )
        assert state.status_code == 200, state.text
        body = state.json()
        assert body["inbox_state"] == "active"
        assert accepting.url in body["inbox_relays"]
        assert any(e["result"] == "accepted"
                   for e in body["last_publication_evidence"])

        # --- disable -> tombstone -> off --------------------------------
        orders_before = await _order_count(ext_module, mid)
        resp = await client.post(
            f"/infinitemarkets/api/v1/merchants/{mid}/inbox/disable",
            headers=_headers(env, csrf),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["inbox_state"] == "deactivating"

        await _wait_state(ext_module, mid, "off")

        intents = await _inbox_intents(ext_module, mid)
        tombstones = [i for i in intents if i["event_kind"] == 5]
        assert tombstones, "kind-5 tombstone intent missing"
        tombstone = tombstones[-1]
        assert tombstone["state"] == "published"
        assert tombstone["event_address"] == f"10050:{pubkey}:"
        assert tombstone["aggregate_revision"] > publish_intent[
            "aggregate_revision"
        ]
        # in-flight orders untouched (none existed — none created).
        assert await _order_count(ext_module, mid) == orders_before

        # --- re-enable -> new revision -> active again -------------------
        resp = await client.post(
            f"/infinitemarkets/api/v1/merchants/{mid}/inbox/enable",
            headers=_headers(env, csrf),
        )
        assert resp.status_code == 200, resp.text
        await _wait_state(ext_module, mid, "active")

        intents = await _inbox_intents(ext_module, mid)
        latest = [i for i in intents if i["event_kind"] == 10050][-1]
        assert latest["state"] == "published"
        assert latest["aggregate_revision"] > tombstone[
            "aggregate_revision"
        ]


async def test_activation_error(runtime_env, monkeypatch):
    """Every target returning a negative OK can never yield ``active`` —
    the state machine lands at ``error`` when attempts exhaust."""
    from harness import relay as relay_module

    env, client = runtime_env, runtime_env["client"]
    ext_module = runtime_env["ext_module"]
    mid, csrf = await _merchant_id(env)

    monkeypatch.setenv("INFINITEMARKETS_RELAY_IO", "on")
    monkeypatch.setenv("INFINITEMARKETS_ALLOW_INSECURE_RELAYS", "1")
    # Bound the attempt budget so the error transition happens inside the
    # test window (module attribute is read at publish time).
    outbox_mod = __import__(
        "importlib"
    ).import_module("infinitemarkets.services.outbox")
    monkeypatch.setattr(outbox_mod, "OUTBOX_MAX_ATTEMPTS", 2)

    async with relay_module.LocalRelay(
        mode=relay_module.RelayMode.REJECTING
    ) as rejecting:
        await _set_relays(
            env, mid, csrf,
            [{"relay_url": rejecting.url, "direction": "inbox"}],
        )
        resp = await client.post(
            f"/infinitemarkets/api/v1/merchants/{mid}/inbox/enable",
            headers=_headers(env, csrf),
        )
        assert resp.status_code == 200, resp.text

        await _wait_state(ext_module, mid, "error", timeout=60)

        intents = await _inbox_intents(ext_module, mid)
        latest = [i for i in intents if i["event_kind"] == 10050][-1]
        assert latest["state"] == "failed"
        pubs = await _publications(ext_module, latest["id"])
        assert pubs and all(p["result"] != "accepted" for p in pubs)
        # A paid-relay style negative OK is evidence, never an ACK.
        assert any(p["result"] == "rejected" for p in pubs)


async def test_disable_off_is_noop(runtime_env):
    """Disabling a merchant that was never enabled is a quiet no-op."""
    env, client = runtime_env, runtime_env["client"]
    mid, csrf = await _merchant_id(env)
    async with env["ext_module"].db.connect() as conn:
        await conn.execute(
            "UPDATE infinitemarkets.merchants SET inbox_state = 'off' "
            "WHERE id = :i",
            {"i": mid},
        )
    resp = await client.post(
        f"/infinitemarkets/api/v1/merchants/{mid}/inbox/disable",
        headers=_headers(env, csrf),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["inbox_state"] == "off"
    intents = await _inbox_intents(env["ext_module"], mid)
    assert not [i for i in intents if i["state"] == "pending"
                and i["event_kind"] == 5]


async def test_inbox_routes_owner_scoped(runtime_env):
    """Foreign merchant ids get the 404-not-403 posture on every inbox
    route."""
    env, client = runtime_env, runtime_env["client"]
    foreign = uuid.uuid4().hex
    _, csrf = await _merchant_id(env)
    for method, path, headers in (
        ("post", f"/merchants/{foreign}/inbox/enable", _headers(env, csrf)),
        ("post", f"/merchants/{foreign}/inbox/disable", _headers(env, csrf)),
        ("get", f"/merchants/{foreign}/inbox-state", _headers(env)),
    ):
        resp = await getattr(client, method)(
            f"/infinitemarkets/api/v1{path}", headers=headers
        )
        assert resp.status_code == 404, (method, path, resp.status_code)
