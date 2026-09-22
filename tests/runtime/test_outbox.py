"""OQ6 probes + section 8.6 outbox publisher tests.

Part 1 (OQ6): pin nostr-sdk ``send_event_to`` semantics the §8.6 worker
depends on — connection requirements, unreachable-relay outcomes, and the
exact SendEventOutput shape — against ``harness.relay.LocalRelay`` and a
dead loopback port. Findings are recorded in 02-02-SUMMARY.md.

Part 2: the publisher worker against the real schema (keystore_env tmp DB)
with ``GAMMAMARKETS_ALLOW_INSECURE_RELAYS=1`` admitting ws:// loopback
targets — the production ``validate_relay_url`` remains wss-only.
"""

from __future__ import annotations

import asyncio
import base64
import importlib
import json
import socket
import time
import uuid

import pytest
import pytest_asyncio

pytestmark = pytest.mark.runtime


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _signed_event(keys, text="oq6"):
    from nostr_sdk import EventBuilder

    return EventBuilder.text_note(text).sign_with_keys(keys)


# --- OQ6: raw SDK probes ----------------------------------------------------------


async def test_oq6_send_to_unconnected_client_times_out():
    """Does send_event_to require a prior connect()? Add the relay but never
    call connect() — pin the observed behavior."""
    from nostr_sdk import ClientBuilder, RelayUrl

    from harness import relay as relay_module
    from harness import sdk

    async with relay_module.LocalRelay(
        mode=relay_module.RelayMode.ACCEPTING
    ) as accepting:
        keys = sdk.generate_keys()
        client = ClientBuilder().build()
        try:
            await client.add_relay(RelayUrl.parse(accepting.url))
            event = _signed_event(keys, "oq6-no-connect")
            # Bound the wait regardless of which behavior the SDK pins.
            output = await asyncio.wait_for(
                client.send_event_to(
                    [RelayUrl.parse(accepting.url)], event
                ),
                timeout=30,
            )
            relay_url = RelayUrl.parse(accepting.url)
            # PINNED: send_event_to does NOT connect on demand — a relay
            # that was added but never connected lands in ``failed`` with
            # 'relay is initialized but not ready', no exception, and the
            # relay sees no EVENT. OQ6 finding A: the transport MUST
            # connect targets before send (RelayTransport.send_to does).
            assert relay_url not in output.success
            assert relay_url in output.failed
            assert "not ready" in str(output.failed[relay_url])
            assert accepting.received_events == []
        finally:
            await client.shutdown()


async def test_oq6_send_to_dead_relay_is_timeout_not_exception():
    """An unreachable target must surface in ``output.failed`` (or timeout),
    never as an exception that kills the batch."""
    from nostr_sdk import ClientBuilder, RelayUrl

    from harness import sdk

    dead_url = f"ws://127.0.0.1:{_free_port()}"
    keys = sdk.generate_keys()
    client = ClientBuilder().build()
    try:
        await client.add_relay(RelayUrl.parse(dead_url))
        # connect() swallows connection-refused — no exception.
        await client.connect()
        event = _signed_event(keys, "oq6-dead")
        output = await asyncio.wait_for(
            client.send_event_to([RelayUrl.parse(dead_url)], event),
            timeout=30,
        )
        relay_url = RelayUrl.parse(dead_url)
        # PINNED: connection-refused lands in ``failed`` with reason
        # 'relay not connected' — never an exception, never in
        # ``success``. OQ6 finding B: transient transport failures share
        # the failed-map with real rejections, so the worker classifies
        # the known transient vocabulary as timeout.
        assert relay_url in output.failed
        assert str(output.failed[relay_url]) == "relay not connected"
        assert output.success == []
    finally:
        await client.shutdown()


async def test_oq6_send_to_unregistered_relay_is_safe():
    """send_event_to a URL the client never added: pin the outcome — the
    worker must treat every non-accepted classification as evidence."""
    from nostr_sdk import ClientBuilder, RelayUrl

    from harness import relay as relay_module
    from harness import sdk

    async with relay_module.LocalRelay(
        mode=relay_module.RelayMode.ACCEPTING
    ) as accepting:
        keys = sdk.generate_keys()
        client = ClientBuilder().build()
        try:
            event = _signed_event(keys, "oq6-unregistered")
            # PINNED (OQ6 finding C): an unregistered target raises —
            # 'no relays' — rather than landing in the failed map. The
            # transport therefore add_relay+connect's validated targets
            # inside send_to, and the worker converts any residual
            # exception into timeout evidence rather than crashing.
            with pytest.raises(Exception, match="no relays"):
                await asyncio.wait_for(
                    client.send_event_to(
                        [RelayUrl.parse(accepting.url)], event
                    ),
                    timeout=30,
                )
            assert accepting.received_events == []
        finally:
            await client.shutdown()


# --- worker tests ---------------------------------------------------------------


@pytest_asyncio.fixture
async def worker_env(keystore_env, monkeypatch):
    """Extension modules bound to the tmp DB + insecure-relay allowance."""
    env = {
        "GAMMAMARKETS_MASTER_KEYS": json.dumps(
            {"v1": base64.b64encode(bytes(32)).decode()}
        ),
        "GAMMAMARKETS_ACTIVE_KEY_VERSION": "v1",
        "GAMMAMARKETS_PRIVACY_KEY": base64.b64encode(bytes([9]) * 32).decode(),
        "GAMMAMARKETS_PUBLIC_BASE_URL": "https://x.example",
        "GAMMAMARKETS_ALLOW_INSECURE_RELAYS": "1",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    # worker tests DO dial — ensure no leaked kill switch from a host boot
    monkeypatch.delenv("GAMMAMARKETS_RELAY_IO", raising=False)
    gdb = keystore_env["db"]
    outbox = importlib.import_module("gammamarkets.services.outbox")
    relay_service = importlib.import_module("gammamarkets.services.relay")
    transport_mod = importlib.import_module(
        "gammamarkets.services.transport"
    )
    yield {
        "db": gdb,
        "outbox": outbox,
        "relay": relay_service,
        "transport": transport_mod.transport(),
        "keystore": keystore_env["keystore"],
    }
    await transport_mod.transport().close()


async def _merchant(worker_env, merchant_id: str | None = None) -> str:
    """Merchants row + generated key so keystore.sign_event works."""
    mid = merchant_id or uuid.uuid4().hex
    db = worker_env["db"]
    from gammamarkets.db import table

    async with db.connect() as conn:
        await conn.execute(
            f"INSERT INTO {table('merchants')} "
            "(id, user_id, pubkey, key_ref, display_name, wallet_id_enc,"
            " wallet_id_hash, state, created_at, updated_at) "
            "VALUES (:i, :u, :p, 'v1', 'Test Shop', :w, 'h', 'active',"
            " :t, :t)",
            {
                "i": mid,
                "u": uuid.uuid4().hex,
                "p": uuid.uuid4().hex,  # overwritten by keystore.generate
                "w": b"x",
                "t": int(time.time()),
            },
        )
    pubkey = await worker_env["keystore"].key_store().generate(mid)
    async with db.connect() as conn:
        await conn.execute(
            f"UPDATE {table('merchants')} SET pubkey = :p WHERE id = :i",
            {"p": pubkey, "i": mid},
        )
    return mid


async def _relay_config(db, merchant_id: str, url: str,
                        direction: str = "public", enabled: bool = True):
    from gammamarkets.db import table

    async with db.connect() as conn:
        await conn.execute(
            f"INSERT INTO {table('relay_configs')} "
            "(id, merchant_id, relay_url, direction, enabled, created_at,"
            " updated_at) VALUES (:i, :m, :u, :d, :e, :t, :t)",
            {
                "i": uuid.uuid4().hex,
                "m": merchant_id,
                "u": url,
                "d": direction,
                "e": enabled,
                "t": int(time.time()),
            },
        )


async def _intent(db, merchant_id: str, kind: int = 0) -> str:
    """merchant_profile intent — renderable from the merchants row alone."""
    from gammamarkets.db import DomainTransaction
    from gammamarkets.services.outbox import enqueue_intent

    async with DomainTransaction() as tx:
        return await enqueue_intent(
            tx, merchant_id, "merchant_profile", merchant_id, kind
        )


async def _state(db, intent_id: str) -> dict:
    from gammamarkets.db import table

    async with db.connect() as conn:
        row = await conn.fetchone(
            f"SELECT * FROM {table('outbox_events')} WHERE id = :i",
            {"i": intent_id},
        )
        pubs = await conn.fetchall(
            f"SELECT * FROM {table('relay_publications')} "
            "WHERE outbox_event_id = :i",
            {"i": intent_id},
        )
    return {"row": dict(row), "pubs": [dict(p) for p in pubs]}


async def test_publish_accepted_marks_published_and_records_evidence(
    worker_env,
):
    """Happy path: claimed -> signed -> sent -> accepted -> published."""
    from harness import relay as relay_module

    async with relay_module.LocalRelay(
        mode=relay_module.RelayMode.ACCEPTING
    ) as accepting:
        mid = await _merchant(worker_env)
        await _relay_config(worker_env["db"], mid, accepting.url)
        intent = await _intent(worker_env["db"], mid)
        await worker_env["transport"].start([accepting.url])

        result = await worker_env["outbox"].worker_tick("w-test")
        assert result["claimed"] == 1
        state = await _state(worker_env["db"], intent)
        assert state["row"]["state"] == "published"
        assert [p["result"] for p in state["pubs"]] == ["accepted"]
        assert state["pubs"][0]["relay_url"] == accepting.url
        # the relay received exactly one signed EVENT with this id
        assert len(accepting.received_events) == 1
        assert (
            accepting.received_events[0]["event"]["id"]
            == state["pubs"][0]["event_id"]
        )


async def test_rejected_and_timeout_relays_leave_intent_pending(worker_env):
    """Zero positive ACKs -> pending + backoff; both evidence rows persist
    verbatim, and the batch itself does not crash."""
    from harness import relay as relay_module

    async with relay_module.LocalRelay(
        mode=relay_module.RelayMode.REJECTING
    ) as rejecting, relay_module.LocalRelay(
        mode=relay_module.RelayMode.SILENT
    ) as silent:
        mid = await _merchant(worker_env)
        await _relay_config(worker_env["db"], mid, rejecting.url)
        await _relay_config(worker_env["db"], mid, silent.url)
        intent = await _intent(worker_env["db"], mid)
        await worker_env["transport"].start([rejecting.url, silent.url])

        result = await worker_env["outbox"].worker_tick("w-test")
        assert result["claimed"] == 1
        state = await _state(worker_env["db"], intent)
        assert state["row"]["state"] == "pending"
        assert state["row"]["attempts"] == 1
        assert state["row"]["next_attempt_at"] > int(time.time())
        results = {p["relay_url"]: p["result"] for p in state["pubs"]}
        assert results[rejecting.url] == "rejected"
        assert results[silent.url] == "timeout"
        # the rejecting relay's verbatim message is preserved
        msg = [p["message"] for p in state["pubs"]
               if p["relay_url"] == rejecting.url][0]
        assert "rejecting" in msg


async def test_dead_relay_isolated_one_failure_never_crashes_batch(
    worker_env,
):
    """A dead target yields timeout evidence; a healthy target in the same
    batch still accepts -> published via quorum."""
    from harness import relay as relay_module

    dead = f"ws://127.0.0.1:{_free_port()}"
    async with relay_module.LocalRelay(
        mode=relay_module.RelayMode.ACCEPTING
    ) as accepting:
        mid = await _merchant(worker_env)
        await _relay_config(worker_env["db"], mid, accepting.url)
        await _relay_config(worker_env["db"], mid, dead)
        intent = await _intent(worker_env["db"], mid)
        await worker_env["transport"].start([accepting.url, dead])

        result = await worker_env["outbox"].worker_tick("w-test")
        assert result["claimed"] == 1
        state = await _state(worker_env["db"], intent)
        # quorum = >=1 positive ACK -> published even with a dead target
        assert state["row"]["state"] == "published"
        results = {p["relay_url"]: p["result"] for p in state["pubs"]}
        assert results[accepting.url] == "accepted"
        assert results[dead] == "timeout"


async def test_accepted_targets_are_never_resent(worker_env):
    """Durable accepted evidence is subtracted before each send — a retry
    after a partial batch sends only to outstanding relays."""
    from harness import relay as relay_module

    async with relay_module.LocalRelay(
        mode=relay_module.RelayMode.ACCEPTING
    ) as accepting, relay_module.LocalRelay(
        mode=relay_module.RelayMode.SILENT
    ) as silent:
        mid = await _merchant(worker_env)
        await _relay_config(worker_env["db"], mid, accepting.url)
        await _relay_config(worker_env["db"], mid, silent.url)
        intent = await _intent(worker_env["db"], mid)
        await worker_env["transport"].start([accepting.url, silent.url])

        await worker_env["outbox"].worker_tick("w-test")
        assert len(accepting.received_events) == 1

        # Force a second attempt without waiting for backoff.
        from gammamarkets.db import table

        async with worker_env["db"].connect() as conn:
            await conn.execute(
                f"UPDATE {table('outbox_events')} "
                "SET state = 'pending', next_attempt_at = 0 WHERE id = :i",
                {"i": intent},
            )
        await worker_env["outbox"].worker_tick("w-test")
        state = await _state(worker_env["db"], intent)
        # silent still times out -> pending, but the accepted relay saw no
        # second EVENT frame.
        assert len(accepting.received_events) == 1, (
            "accepted relay target was resent"
        )
        accepted_pubs = [
            p for p in state["pubs"]
            if p["relay_url"] == accepting.url and p["result"] == "accepted"
        ]
        assert len(accepted_pubs) == 1


async def test_newer_live_revision_supersedes_stale_intent(worker_env):
    """A newer live intent for the same aggregate+kind marks the stale one
    superseded — stale content is never published."""
    from harness import relay as relay_module

    async with relay_module.LocalRelay(
        mode=relay_module.RelayMode.ACCEPTING
    ) as accepting:
        mid = await _merchant(worker_env)
        await _relay_config(worker_env["db"], mid, accepting.url)
        from gammamarkets.db import DomainTransaction
        from gammamarkets.services.outbox import enqueue_intent

        async with DomainTransaction() as tx:
            old = await enqueue_intent(
                tx, mid, "merchant_profile", mid, 0, revision=1
            )
            await enqueue_intent(
                tx, mid, "merchant_profile", mid, 0, revision=2
            )
        await worker_env["transport"].start([accepting.url])
        await worker_env["outbox"].worker_tick("w-test")

        state = await _state(worker_env["db"], old)
        assert state["row"]["state"] == "superseded"
        # only the newer intent published an EVENT
        assert len(accepting.received_events) == 1


async def test_dependency_gate_blocks_until_published(worker_env):
    """An intent whose dependency isn't published is requeued, not sent."""
    from harness import relay as relay_module

    async with relay_module.LocalRelay(
        mode=relay_module.RelayMode.ACCEPTING
    ) as accepting:
        mid = await _merchant(worker_env)
        await _relay_config(worker_env["db"], mid, accepting.url)
        from gammamarkets.db import DomainTransaction
        from gammamarkets.services.outbox import enqueue_intent

        async with DomainTransaction() as tx:
            cid = uuid.uuid4().hex
            await enqueue_intent(tx, mid, "collections", cid, 30405)
            child = await enqueue_intent(
                tx, mid, "merchant_profile", mid, 0,
                depends_on=[("collections", cid)],
            )
        # The collection row doesn't exist -> dep intent will be
        # superseded by the worker, leaving the child blocked forever.
        # First tick: child claimed but dependency not published -> requeue.
        await worker_env["transport"].start([accepting.url])
        await worker_env["outbox"].worker_tick("w-test")
        state = await _state(worker_env["db"], child)
        assert state["row"]["state"] == "pending"
        assert state["pubs"] == []
        assert accepting.received_events == []


async def test_retry_intent_resets_failed_and_skips_accepted(worker_env):
    """Admin retry: failed/partial -> pending, attempts reset, accepted
    targets still never resent."""
    from harness import relay as relay_module

    async with relay_module.LocalRelay(
        mode=relay_module.RelayMode.ACCEPTING
    ) as accepting:
        mid = await _merchant(worker_env)
        await _relay_config(worker_env["db"], mid, accepting.url)
        intent = await _intent(worker_env["db"], mid)
        db = worker_env["db"]
        from gammamarkets.db import table

        async with db.connect() as conn:
            await conn.execute(
                f"UPDATE {table('outbox_events')} SET state = 'failed',"
                " attempts = 20 WHERE id = :i",
                {"i": intent},
            )
        result = await worker_env["relay"].retry_intent(mid, intent)
        assert result["state"] == "pending"
        state = await _state(db, intent)
        assert state["row"]["state"] == "pending"
        assert state["row"]["attempts"] == 0

        # a published intent cannot be retried
        async with db.connect() as conn:
            await conn.execute(
                f"UPDATE {table('outbox_events')} SET state = 'published'"
                " WHERE id = :i",
                {"i": intent},
            )
        from gammamarkets.security import ProblemError

        with pytest.raises(ProblemError):
            await worker_env["relay"].retry_intent(mid, intent)


async def test_stale_claim_recovery_requeues_with_evidence(worker_env):
    """Lease-expired claims return to the queue — partially_published when
    durable accepted evidence exists, pending otherwise."""
    mid = await _merchant(worker_env)
    db = worker_env["db"]
    intent = await _intent(db, mid)
    from gammamarkets.db import table

    async with db.connect() as conn:
        await conn.execute(
            f"UPDATE {table('outbox_events')} SET state = 'claimed',"
            " claimed_by = 'dead-worker', claimed_until = 0 WHERE id = :i",
            {"i": intent},
        )
    recovered = await worker_env["outbox"].recover_stale_claims(
        int(time.time())
    )
    assert recovered == 1
    state = await _state(db, intent)
    assert state["row"]["state"] == "pending"


async def test_relay_targets_direction_and_defaults(worker_env):
    """Target resolution: public set = direction public|both + enabled;
    server-wide defaults (merchant_id NULL) apply to every merchant."""
    mid = await _merchant(worker_env)
    db = worker_env["db"]
    await _relay_config(db, mid, "wss://public.example", "public")
    await _relay_config(db, mid, "wss://inbox.example", "inbox")
    await _relay_config(db, mid, "wss://both.example", "both")
    await _relay_config(db, mid, "wss://off.example", "public",
                        enabled=False)
    targets = await worker_env["relay"].relay_targets(mid, "public")
    assert targets == ["wss://both.example", "wss://public.example"]
    inbox = await worker_env["relay"].relay_targets(mid, "inbox")
    assert inbox == ["wss://both.example", "wss://inbox.example"]

    # server-wide default rows (merchant_id NULL) supplement
    await _relay_config(db, None, "wss://default.example", "public")
    targets = await worker_env["relay"].relay_targets(mid, "public")
    assert "wss://default.example" in targets

    # starter seeding: a merchant with zero configs gets the visible set
    mid2 = uuid.uuid4().hex
    from gammamarkets.db import table

    async with db.connect() as conn:
        await conn.execute(
            f"INSERT INTO {table('merchants')} "
            "(id, user_id, pubkey, key_ref, display_name, wallet_id_enc,"
            " wallet_id_hash, state, created_at, updated_at) "
            "VALUES (:i, :u, :p, 'v1', 'S2', :w, 'h', 'active', 0, 0)",
            {"i": mid2, "u": uuid.uuid4().hex,
             "p": uuid.uuid4().hex, "w": b"x"},
        )
    await worker_env["relay"].ensure_default_relays(mid2)
    targets = await worker_env["relay"].relay_targets(mid2, "public")
    assert "wss://relay.damus.io" in targets
