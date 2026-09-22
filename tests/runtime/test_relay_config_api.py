"""Relay/blossom endpoint configurability + outbox admin routes — API level.

Owner directive (2026-09-22): merchants configure their own publication,
inbox, and blossom media endpoints with starter defaults surfaced by the
health route. Relay ``direction`` is the normative ``public|inbox|both``
vocabulary; blossom endpoints are https:// media servers validated under
the same SSRF posture (spec delta, recorded in 02-02-SUMMARY.md).
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.runtime


def _headers(env: dict, csrf: str | None = None) -> dict:
    # Real cookie jar semantics: auth + double-submit cookie travel together.
    cookie = f"cookie_access_token={env['token']}"
    if csrf:
        cookie += f"; gm_csrf={csrf}"
    h = {"Cookie": cookie, "Origin": "https://shop.example"}
    if csrf:
        h["X-CSRF-Token"] = csrf
    return h


async def _merchant_id(env: dict) -> tuple[str, str]:
    """Create a merchant; return (merchant_id, csrf)."""
    client = env["client"]
    # the boundary issues gm_csrf on any authenticated request — seed it;
    # the shared user gets exactly one merchant (user_id UNIQUE).
    existing = await client.get(
        "/gammamarkets/api/v1/merchants/current", headers=_headers(env)
    )
    if existing.status_code == 200:
        return existing.json()["id"], _csrf(client)
    resp = await client.post(
        "/gammamarkets/api/v1/merchants",
        json={"wallet_id": env["wallet"].id},
        headers=_headers(env, _csrf(client)),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"], _csrf(client)


def _csrf(client) -> str:
    return client.cookies.get("gm_csrf") or ""


async def test_relay_config_accepts_public_inbox_both(runtime_env):
    client, env = runtime_env["client"], runtime_env
    mid, csrf = await _merchant_id(env)
    resp = await client.patch(
        f"/gammamarkets/api/v1/merchants/{mid}",
        json={
            "relay_configs": [
                {"relay_url": "wss://relay-a.example", "direction": "public"},
                {"relay_url": "wss://relay-b.example", "direction": "inbox"},
                {"relay_url": "wss://relay-c.example", "direction": "both"},
                {
                    "relay_url": "wss://relay-d.example",
                    "direction": "public",
                    "enabled": False,
                },
            ]
        },
        headers=_headers(env, csrf),
    )
    assert resp.status_code == 200, resp.text

    health = await client.get(
        f"/gammamarkets/api/v1/merchants/{mid}/relay-health",
        headers=_headers(env),
    )
    assert health.status_code == 200, health.text
    body = health.json()
    relays = {r["relay_url"]: r for r in body["relays"]}
    assert relays["wss://relay-a.example"]["direction"] == "public"
    assert relays["wss://relay-b.example"]["direction"] == "inbox"
    assert relays["wss://relay-c.example"]["direction"] == "both"
    assert relays["wss://relay-d.example"]["enabled"] is False
    # starter defaults surface for the admin UI
    assert "wss://relay.damus.io" in body["defaults"]["relays"]
    assert body["defaults"]["blossom_servers"]


async def test_relay_config_rejects_invalid_and_duplicates(runtime_env):
    client, env = runtime_env["client"], runtime_env
    mid, csrf = await _merchant_id(env)
    for configs in (
        [{"relay_url": "http://relay.example"}],
        [{"relay_url": "wss://127.0.0.1:7777"}],
        [{"relay_url": "wss://localhost"}],
        [{"relay_url": "wss://user:pw@relay.example"}],
        [{"relay_url": "wss://a.example", "direction": "outbox"}],
        [
            {"relay_url": "wss://dup.example", "direction": "public"},
            {"relay_url": "wss://dup.example", "direction": "public"},
        ],
    ):
        resp = await client.patch(
            f"/gammamarkets/api/v1/merchants/{mid}",
            json={"relay_configs": configs},
            headers=_headers(env, csrf),
        )
        assert resp.status_code == 422, (configs, resp.status_code, resp.text)


async def test_blossom_servers_configurable_with_https_only(runtime_env):
    client, env = runtime_env["client"], runtime_env
    mid, csrf = await _merchant_id(env)
    resp = await client.patch(
        f"/gammamarkets/api/v1/merchants/{mid}",
        json={
            "blossom_servers": [
                "https://blossom.primal.net",
                "https://media.example.com",
            ]
        },
        headers=_headers(env, csrf),
    )
    assert resp.status_code == 200, resp.text

    health = await client.get(
        f"/gammamarkets/api/v1/merchants/{mid}/relay-health",
        headers=_headers(env),
    )
    assert health.json()["blossom_servers"] == [
        "https://blossom.primal.net",
        "https://media.example.com",
    ]

    for bad in ("http://media.example.com", "https://127.0.0.1:3000",
                "https://user:pw@media.example.com"):
        resp = await client.patch(
            f"/gammamarkets/api/v1/merchants/{mid}",
            json={"blossom_servers": [bad]},
            headers=_headers(env, csrf),
        )
        assert resp.status_code == 422, (bad, resp.status_code)


async def test_outbox_listing_and_retry_routes(runtime_env):
    """W-NEW-1 spec-delta routes: owner-scoped listing + retry."""
    client, env = runtime_env["client"], runtime_env
    mid, csrf = await _merchant_id(env)

    resp = await client.get(
        f"/gammamarkets/api/v1/merchants/{mid}/outbox",
        headers=_headers(env),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["intents"] == []

    # publishing enqueues intents (profile + handler pair) that surface here
    resp = await client.post(
        f"/gammamarkets/api/v1/merchants/{mid}/publish",
        headers=_headers(env, csrf),
    )
    assert resp.status_code == 200, resp.text
    listing = await client.get(
        f"/gammamarkets/api/v1/merchants/{mid}/outbox",
        headers=_headers(env),
    )
    intents = listing.json()["intents"]
    assert intents, "publish must enqueue intents"
    kinds = {i["event_kind"] for i in intents}
    assert {0, 31989, 31990} <= kinds
    for intent in intents:
        assert "relay_publications" in intent
        assert "depends_on" in intent

    # starter defaults are surfaced for the UI (this merchant already has
    # configured relays, so publish does not seed — seeding is pinned by
    # test_relay_targets_direction_and_defaults in test_outbox.py)
    health = await client.get(
        f"/gammamarkets/api/v1/merchants/{mid}/relay-health",
        headers=_headers(env),
    )
    assert "wss://relay.damus.io" in health.json()["defaults"]["relays"]

    # a published intent rejects retry
    intent_id = intents[0]["id"]
    resp = await client.post(
        f"/gammamarkets/api/v1/merchants/{mid}/outbox/{intent_id}/retry",
        headers=_headers(env, csrf),
    )
    assert resp.status_code == 409, resp.text

    # other-merchant access is forbidden
    resp = await client.get(
        f"/gammamarkets/api/v1/merchants/{uuid.uuid4().hex}/outbox",
        headers=_headers(env),
    )
    assert resp.status_code in (403, 404)
