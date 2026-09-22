"""Worker registry — spec section 10.

``gammamarkets_start`` registers exactly the handles this module owns;
``gammamarkets_stop`` cancels them via ``register_owned_task`` tracking.
Every worker loop is cancellation-safe (try/finally, owned resources
closed).

Lease discipline (§10): ``reservation_expiry``, ``reconciliation``, and
``retention_pruner`` acquire/renew their ``task_leases`` row before each
pass; loss of lease stops work immediately, and every leased write carries
the fencing token. ``email_sender`` and ``outbox_publisher`` need no task
lease — the per-row claim-token CAS is their fencing. ``relay_manager``
runs per-worker unleased (each worker owns its own Client).

The invoice listener registers through
``task_manager.register_invoice_listener`` — an unfiltered fan-out, so the
callback self-filters (§8.3); delivery is memory-only, which is why the
leased reconciliation pass is mandatory for payment truth.
"""

from __future__ import annotations

import asyncio
import uuid

from loguru import logger

OUTBOX_INTERVAL_S = 5
RELAY_TICK_INTERVAL_S = 30
EMAIL_INTERVAL_S = 5
RESERVATION_EXPIRY_INTERVAL_S = 30
RECONCILE_INTERVAL_S = 60
RETENTION_INTERVAL_S = 86400

LEASE_TTL_S = 120

WORKER_ID = f"worker-{uuid.uuid4().hex[:8]}"


async def _acquire_lease(name: str, ttl: int = LEASE_TTL_S) -> int | None:
    """Acquire or renew a §4.16 task lease; returns the fencing token or
    None when another worker holds a live lease."""
    from ..db import DomainTransaction

    now = _now()
    async with DomainTransaction() as tx:
        rc = await tx.execute(
            f"UPDATE {tx.table('task_leases')} SET holder_id = :h,"
            " fencing_token = fencing_token + 1, leased_until = :u,"
            " updated_at = :n"
            " WHERE name = :name AND (leased_until <= :n OR holder_id = :h)",
            {
                "name": name, "h": WORKER_ID, "n": now, "u": now + ttl,
            },
        )
        if rc == 1:
            row = await tx.fetch_one(
                f"SELECT fencing_token FROM {tx.table('task_leases')}"
                " WHERE name = :name",
                {"name": name},
            )
            return int(row["fencing_token"]) if row else None
        try:
            await tx.execute(
                f"INSERT INTO {tx.table('task_leases')} "
                "(name, holder_id, fencing_token, leased_until, updated_at)"
                " VALUES (:name, :h, 1, :u, :n)",
                {"name": name, "h": WORKER_ID, "n": now, "u": now + ttl},
            )
            return 1
        except Exception:  # noqa: BLE001 — IntegrityError across dialects
            return None


def _now() -> int:
    import time

    return int(time.time())


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


async def email_sender() -> None:
    """§8.8 worker loop — claim-fenced rows; per-worker Database handle."""
    from ..db import worker_db
    from . import email as email_service

    wdb = worker_db()
    while True:
        try:
            await email_service.recover_stale_claims(database=wdb)
            result = await email_service.worker_tick(
                WORKER_ID, database=wdb
            )
            if result["claimed"]:
                logger.debug(
                    f"gammamarkets email: claimed={result['claimed']}"
                    f" outcomes={result['outcomes']}"
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"gammamarkets email tick failed: {exc}")
        await asyncio.sleep(EMAIL_INTERVAL_S)


async def reservation_expiry() -> None:
    """§8.4 expiry loop (30s, leased): expired held reservations release
    exactly once; expired invoices take the §8.4 path."""
    from . import settlement

    while True:
        try:
            token = await _acquire_lease("reservation_expiry")
            if token is not None:
                result = await settlement.reservation_expiry_pass()
                if result["released"] or result["expired_orders"]:
                    logger.debug(
                        f"gammamarkets reservation expiry:"
                        f" released={result['released']}"
                        f" expired_orders={result['expired_orders']}"
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                f"gammamarkets reservation expiry tick failed: {exc}"
            )
        await asyncio.sleep(RESERVATION_EXPIRY_INTERVAL_S)


async def reconciliation() -> None:
    """§8.7 pass — runs once immediately (startup reconciliation gates
    checkout readiness), then every 60s under the task lease."""
    from . import readiness, settlement

    first = True
    while True:
        try:
            token = await _acquire_lease("reconciliation")
            if token is not None:
                report = await settlement.reconcile()
                if any(report.values()):
                    logger.debug(f"gammamarkets reconcile: {report}")
                if first:
                    readiness.mark_reconciled()
                    first = False
            elif first:
                # Another worker holds the lease — readiness still flips
                # once that worker completes its first pass; poll again
                # quickly rather than waiting the full interval.
                await asyncio.sleep(5)
                continue
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"gammamarkets reconcile tick failed: {exc}")
            await asyncio.sleep(5)
            continue
        await asyncio.sleep(RECONCILE_INTERVAL_S)


async def retention_pruner() -> None:
    """§11.3 daily retention pass (leased)."""
    from . import settlement

    while True:
        try:
            token = await _acquire_lease("retention_pruner",
                                       ttl=LEASE_TTL_S * 4)
            if token is not None:
                report = await settlement.retention_prune()
                if any(report.values()):
                    logger.debug(f"gammamarkets retention: {report}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                f"gammamarkets retention tick failed: {exc}"
            )
        await asyncio.sleep(RETENTION_INTERVAL_S)


def start_workers() -> list[asyncio.Task]:
    """Register owned tasks through the host task manager; returns the
    handles so gammamarkets_start can track them for stop."""
    from lnbits.tasks import task_manager

    from . import settlement

    handles = []
    listener = task_manager.register_invoice_listener(
        settlement.invoice_listener, name="gammamarkets"
    )
    handles.append(listener.task)
    for func, name in (
        (outbox_publisher, "gammamarkets_outbox"),
        (relay_manager, "gammamarkets_relay_manager"),
        (email_sender, "gammamarkets_email_sender"),
        (reservation_expiry, "gammamarkets_reservation_expiry"),
        (reconciliation, "gammamarkets_reconciliation"),
        (retention_pruner, "gammamarkets_retention_pruner"),
    ):
        handle = task_manager.create_task(func(), name=name)
        handles.append(handle.task)
    return handles
