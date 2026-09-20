"""Deterministic local Nostr relay fixture (NIP-01 subset) over websockets.

This is the authoritative relay test surface per spec section 9.1: a small
asyncio server bound to 127.0.0.1 on an ephemeral port (T-01-04), speaking
the subset of NIP-01 the qualification probes need:

- ``ACCEPTING``: reply ``["OK", id, true, ...]`` to every EVENT.
- ``REJECTING``: reply ``["OK", id, false, message]``.
- ``SILENT``: accept the connection, never reply (produces client timeout).
- ``AUTH_FLOOD``: send repeated AUTH challenges (configurable count) and no
  OK — for the paused-signing AUTH-boundedness probe (P0-02).

The fixture records every received message (parsed EVENT payloads included)
and every connection/disconnection for later assertions, e.g. proving the
client never sent an EVENT to an unlisted relay.

The optional ``wss://nostr.net`` smoke test is out of scope here and
non-authoritative by policy (spec section 21.27).
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from enum import Enum

from websockets.asyncio.server import serve


class RelayMode(str, Enum):
    ACCEPTING = "accepting"
    REJECTING = "rejecting"
    SILENT = "silent"
    AUTH_FLOOD = "auth_flood"


@dataclass
class _ConnectionRecord:
    remote: str
    event: str  # "connect" | "disconnect"


@dataclass
class LocalRelay:
    """A deterministic local relay bound to 127.0.0.1 on an ephemeral port."""

    mode: RelayMode = RelayMode.ACCEPTING
    auth_challenge_count: int = 50
    auth_challenge_interval_s: float = 0.005
    reject_message: str = "restricted: this relay is rejecting (qualification fixture)"

    received_messages: list[str] = field(default_factory=list)
    received_events: list[dict] = field(default_factory=list)
    connections: list[_ConnectionRecord] = field(default_factory=list)
    auth_challenges_sent: int = 0

    def __post_init__(self) -> None:
        self._server = None
        self._port: int | None = None

    @property
    def url(self) -> str:
        if self._port is None:
            raise RuntimeError("relay not started")
        return f"ws://127.0.0.1:{self._port}"

    @property
    def port(self) -> int:
        if self._port is None:
            raise RuntimeError("relay not started")
        return self._port

    async def start(self) -> "LocalRelay":
        self._server = await serve(self._handler, "127.0.0.1", 0)
        # websockets serves on an ephemeral port when port=0.
        self._port = self._server.sockets[0].getsockname()[1]
        return self

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            self._port = None

    async def __aenter__(self) -> "LocalRelay":
        return await self.start()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.stop()

    async def _send_auth_challenges(self, websocket, count: int | None = None) -> None:
        for _ in range(self.auth_challenge_count if count is None else count):
            await websocket.send(
                json.dumps(
                    ["AUTH", "qualification-fixture-challenge-not-a-real-challenge"]
                )
            )
            self.auth_challenges_sent += 1
            await asyncio.sleep(self.auth_challenge_interval_s)

    async def _handler(self, websocket) -> None:
        self.connections.append(_ConnectionRecord(str(websocket.remote_address), "connect"))
        try:
            if self.mode is RelayMode.AUTH_FLOOD:
                # Flood immediately on connect: paused-signing clients see a
                # large bounded number of challenges without any OK.
                await self._send_auth_challenges(websocket)
            async for raw in websocket:
                self.received_messages.append(raw)
                try:
                    message = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                if not isinstance(message, list) or not message:
                    continue
                kind = message[0]
                # NIP-01 client->relay EVENT is ["EVENT", <event>] (2 elements).
                if kind == "EVENT" and len(message) >= 2:
                    event = message[1] if isinstance(message[1], dict) else {}
                    self.received_events.append({"event": event})
                    if self.mode is RelayMode.ACCEPTING:
                        await websocket.send(
                            json.dumps(["OK", event.get("id"), True, ""])
                        )
                    elif self.mode is RelayMode.REJECTING:
                        await websocket.send(
                            json.dumps(
                                ["OK", event.get("id"), False, self.reject_message]
                            )
                        )
                    elif self.mode is RelayMode.AUTH_FLOOD:
                        # Answer every EVENT with another bounded flood.
                        await self._send_auth_challenges(websocket)
                    # SILENT: never reply.
                elif kind == "REQ" and self.mode is RelayMode.ACCEPTING:
                    # Minimal NIP-01 courtesy: immediately close the query.
                    await websocket.send(json.dumps(["CLOSED", message[1], "fixture"]))
        finally:
            self.connections.append(
                _ConnectionRecord(str(websocket.remote_address), "disconnect")
            )
