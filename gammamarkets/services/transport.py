"""Extension-owned nostr-sdk transport — spec section 9.1/9.5/10.

One ``Client`` per worker process, created with bounded connection
parameters, connected only to validated configured relays, shared by the
outbox publisher, and closed inside ``gammamarkets_stop``. No signer is ever
attached — signing happens per event through ``keystore.sign_event`` so raw
nsecs never reach the transport.

``GAMMAMARKETS_ALLOW_INSECURE_RELAYS=1`` is a TEST-ONLY escape hatch:
it permits ``ws://`` loopback targets so runtime tests can point the
transport at ``harness.relay.LocalRelay``. It is rejected (startup failure)
when the host is not in test mode… documented residual: qualified
deployments never set it.
"""

from __future__ import annotations

import os

from nostr_sdk import Client, ClientBuilder, ClientOptions, RelayUrl

from ..security import unprocessable, validate_relay_url
from ..settings import ext_settings

# §9.5 bounds
CONNECT_TIMEOUT_S = 10
MAX_RELAYS = 32


def insecure_relays_allowed() -> bool:
    return os.environ.get("GAMMAMARKETS_ALLOW_INSECURE_RELAYS") == "1"


def relay_io_enabled() -> bool:
    """TEST-ONLY kill switch: ``GAMMAMARKETS_RELAY_IO=off`` builds the
    client but never dials — runtime host boots must not publish test
    events to real public relays."""
    return os.environ.get("GAMMAMARKETS_RELAY_IO", "on") != "off"


def validate_relay_target(raw: str) -> str:
    """§9.5 relay target validation; the test-only insecure allowance admits
    ``ws://`` loopback targets (LocalRelay fixtures) and nothing else."""
    if insecure_relays_allowed():
        url = raw.strip()
        if url.startswith("ws://"):
            try:
                parsed = RelayUrl.parse(url)
            except Exception as exc:
                raise unprocessable(
                    "invalid-relay", "Invalid relay URL"
                ) from exc
            if parsed.is_local_addr():
                return url
            raise unprocessable(
                "invalid-relay",
                "ws:// relay targets are test-only and must be loopback",
            )
    return validate_relay_url(raw)


class RelayTransport:
    """Owned client lifecycle — no signer, bounded options, validated set."""

    def __init__(self) -> None:
        self._client: Client | None = None
        self._targets: set[str] = set()

    @property
    def client(self) -> Client | None:
        return self._client

    async def start(self, relay_urls: list[str]) -> None:
        """Create the client and connect to the validated relay set."""
        if self._client is not None:
            return
        opts = (
            ClientOptions()
            # Bound message/event sizes the relay will accept from us.
            .relay_limits(_relay_limits())
            # Do not auto-retry forever on unreachable relays — the
            # relay_manager tick owns reconnection cadence.
            .autoconnect(False)
        )
        self._client = ClientBuilder().opts(opts).build()
        if not relay_io_enabled():
            return
        await self.sync_relays(relay_urls)
        await self._client.connect()

    async def sync_relays(self, relay_urls: list[str]) -> None:
        """Converge the client's relay set to the validated target list."""
        if self._client is None or not relay_io_enabled():
            return
        validated = {validate_relay_target(u) for u in relay_urls}
        for url in validated - self._targets:
            if await self._client.add_relay(RelayUrl.parse(url)):
                await self._client.connect_relay(RelayUrl.parse(url))
        for url in self._targets - validated:
            await self._client.remove_relay(RelayUrl.parse(url))
        self._targets = validated

    async def send_to(self, urls: list[str], event):
        """Send an already-signed event to an explicit validated subset.

        OQ6 finding: ``send_event_to`` does not connect on demand — a
        target the client never connected lands in ``failed`` as 'relay is
        initialized but not ready'. Ensure every target is connected first.
        """
        if self._client is None:
            raise RuntimeError("transport not started")
        if not relay_io_enabled():
            raise RuntimeError("relay io disabled")
        targets = [RelayUrl.parse(validate_relay_target(u)) for u in urls]
        for target in targets:
            if target not in await self._client.relays():
                await self._client.add_relay(target)
            await self._client.connect_relay(target)
        return await self._client.send_event_to(targets, event)

    async def connected_urls(self) -> list[str]:
        if self._client is None:
            return []
        return [str(u) for u in (await self._client.relays()).keys()]

    async def close(self) -> None:
        client, self._client = self._client, None
        self._targets = set()
        if client is not None:
            try:
                await client.disconnect()
            finally:
                await client.shutdown()


def _relay_limits():
    from nostr_sdk import RelayLimits

    limits = RelayLimits.disable()
    # keep generous-but-bounded message size (catalog events are small)
    limits.message_max_size = 256 * 1024
    limits.event_max_size = 128 * 1024
    return limits


_transport: RelayTransport | None = None


def transport() -> RelayTransport:
    """Process-wide owned transport (per-worker on multi-worker hosts)."""
    global _transport
    if _transport is None:
        _transport = RelayTransport()
    return _transport


async def start_transport() -> None:
    """gammamarkets_start hook step — connect to the server-wide default +
    all configured public relay targets."""
    from . import relay as relay_service

    ext_settings()
    urls = await relay_service.all_public_targets()
    await transport().start(urls)
