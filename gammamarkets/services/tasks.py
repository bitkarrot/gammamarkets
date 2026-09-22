"""Worker registry — spec section 10.

``gammamarkets_start`` registers exactly the handles this module owns;
``gammamarkets_stop`` cancels them via ``register_owned_task`` tracking.
Every worker loop is cancellation-safe (try/finally, owned resources closed).

Release-A scope: ``outbox_publisher`` (5s) and ``relay_manager`` (30s health
tick — connect/reconnect the owned transport to the configured set).
Release-B subscription duties are deferred and documented.

§10 lease deviation (recorded in 02-02 summary): the relay_manager tick runs
UNLEASED per worker — each worker owns its own Client and manages only its
own connections, so per-worker ticks are correct on multi-worker PostgreSQL
topology; it writes no shared lease-fenced rows.
"""

from __future__ import annotations

import asyncio
import uuid

from loguru import logger

OUTBOX_INTERVAL_S = 5
RELAY_TICK_INTERVAL_S = 30

WORKER_ID = f"worker-{uuid.uuid4().hex[:8]}"


async def outbox_publisher() -> None:
    """§8.6 publisher loop — claim, build-from-current-state, sign, send,
    persist per-relay evidence."""
    from . import outbox

    while True:
        try:
            result = await outbox.worker_tick(WORKER_ID)
            if result["claimed"]:
                logger.debug(
                    f"gammamarkets outbox: claimed={result['claimed']} "
                    f"recovered={result['recovered']} "
                    f"outcomes={result['outcomes']}"
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"gammamarkets outbox tick failed: {exc}")
        await asyncio.sleep(OUTBOX_INTERVAL_S)


async def relay_manager() -> None:
    """Health tick — converge the owned transport's connection set to the
    configured public relays. Per-worker, unleased (see module docstring)."""
    from . import relay as relay_service
    from .transport import transport

    while True:
        try:
            targets = await relay_service.all_public_targets()
            tport = transport()
            if tport.client is None:
                await tport.start(targets)
            else:
                await tport.sync_relays(targets)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"gammamarkets relay tick failed: {exc}")
        await asyncio.sleep(RELAY_TICK_INTERVAL_S)


def start_workers() -> list[asyncio.Task]:
    """Register owned tasks through the host task manager; returns the
    handles so gammamarkets_start can track them for stop."""
    from lnbits.tasks import task_manager

    handles = []
    for func, name in (
        (outbox_publisher, "gammamarkets_outbox"),
        (relay_manager, "gammamarkets_relay_manager"),
    ):
        handle = task_manager.create_task(func(), name=name)
        handles.append(handle.task)
    return handles
