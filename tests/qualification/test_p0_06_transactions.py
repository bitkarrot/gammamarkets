"""P0-06 (tracer scope): the one real database transaction-model check.

Section 8.2 step 1 executable model, run inside ONE section-14 domain
transaction (BEGIN IMMEDIATE on SQLite / conn.begin() on PostgreSQL):

- conditional stock claim (guard: stock_on_hand - stock_reserved >= qty),
- compare-and-swap order transition (WHERE state = expected),
- insert of a `held` reservation.

Asserts:

(a) a lost CAS rolls back the ENTIRE transaction (stock_reserved unchanged,
    no reservation row);
(b) an orphan inventory_reservations insert violates the FK
    (SQLite FK enforcement enabled per connection);
(c) the winning path leaves exactly one held reservation and increments
    stock_reserved.

Runs on the selected profile dialect (SQLite locally; the four blocking
profiles run it in CI per D-03).
"""

from __future__ import annotations

import pytest

from harness import tx

pytestmark = pytest.mark.db

RESERVATION_EXPIRES_AT = 1_800_000_000


async def _seed(qual_db, *, product_id: str, on_hand: int, order_id: str, state: str):
    async with qual_db.connect() as conn:
        async with qual_db.transaction(conn) as t:
            await t.execute(
                f"INSERT INTO {qual_db.table('products')}"
                " (id, stock_on_hand, stock_reserved) VALUES (:id, :h, :r)",
                {"id": product_id, "h": on_hand, "r": 0},
            )
            await t.execute(
                f"INSERT INTO {qual_db.table('orders')}"
                " (id, merchant_id, state) VALUES (:id, :m, :s)",
                {"id": order_id, "m": "merchant-1", "s": state},
            )


async def _reservations(qual_db) -> list[dict]:
    return await qual_db.fetch_all(
        f"SELECT * FROM {qual_db.table('inventory_reservations')}"
    )


async def _product(qual_db, product_id: str) -> dict:
    rows = await qual_db.fetch_all(
        f"SELECT stock_on_hand, stock_reserved FROM {qual_db.table('products')}"
        " WHERE id = :id",
        {"id": product_id},
    )
    assert rows, "seeded product must exist"
    return rows[0]


async def test_winning_cas_leaves_one_held_reservation(qual_db_factory):
    async with qual_db_factory() as qual_db:
        await _seed(
            qual_db, product_id="p1", on_hand=5, order_id="o1", state="received"
        )
        await tx.claim_and_reserve(
            qual_db,
            product_id="p1",
            qty=2,
            order_id="o1",
            reservation_id="r1",
            expires_at=RESERVATION_EXPIRES_AT,
        )
        product = await _product(qual_db, "p1")
        assert product["stock_reserved"] == 2
        assert product["stock_on_hand"] == 5
        reservations = await _reservations(qual_db)
        assert len(reservations) == 1
        reservation = reservations[0]
        assert reservation["state"] == "held"
        assert reservation["quantity"] == 2
        assert reservation["expires_at"] == RESERVATION_EXPIRES_AT
        order_rows = await qual_db.fetch_all(
            f"SELECT state FROM {qual_db.table('orders')} WHERE id = :id",
            {"id": "o1"},
        )
        assert order_rows[0]["state"] == "invoice_pending"


async def test_lost_cas_rolls_back_the_entire_transaction(qual_db_factory):
    async with qual_db_factory() as qual_db:
        # Order already advanced past 'received' -> the CAS must lose.
        await _seed(
            qual_db,
            product_id="p1",
            on_hand=5,
            order_id="o1",
            state="invoice_pending",
        )
        with pytest.raises(tx.SagaConflict):
            await tx.claim_and_reserve(
                qual_db,
                product_id="p1",
                qty=2,
                order_id="o1",
                reservation_id="r1",
                expires_at=RESERVATION_EXPIRES_AT,
            )
        # The claim executed inside the transaction, but the CAS loss rolled
        # back EVERYTHING: stock_reserved unchanged, no reservation row.
        product = await _product(qual_db, "p1")
        assert product["stock_reserved"] == 0
        assert await _reservations(qual_db) == []


async def test_orphan_reservation_insert_violates_fk(qual_db_factory):
    async with qual_db_factory() as qual_db:
        await _seed(
            qual_db, product_id="p1", on_hand=5, order_id="o1", state="received"
        )
        with pytest.raises(Exception) as exc_info:
            async with qual_db.connect() as conn:
                async with qual_db.transaction(conn) as t:
                    await t.execute(
                        tx.insert_reservation_sql(
                            qual_db.table("inventory_reservations")
                        ),
                        {
                            "id": "orphan",
                            "product_id": "does-not-exist",
                            "order_id": "o1",
                            "qty": 1,
                            "state": "held",
                            "expires_at": RESERVATION_EXPIRES_AT,
                        },
                    )
        # sqlite3.IntegrityError and sqlalchemy.exc.IntegrityError both
        # surface the type name IntegrityError.
        assert "IntegrityError" in type(exc_info.value).__name__
        assert await _reservations(qual_db) == []
