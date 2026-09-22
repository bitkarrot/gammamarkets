"""Extension migrations — run by the host's ``run_migration`` (mNNN_ prefix).

m001 covers the merchant/catalog/outbox-intent schema subset (spec section 4):
merchants, merchant_keys, settings, catalogs, products + section-4.4 detail
tables, collections + collection_shipping, shipping_options,
protocol_addresses, relay_configs, outbox_events, outbox_dependencies,
relay_publications, task_leases, rate_limit_buckets — plus the section-4.19
indexes that touch these tables.

m002 (plan 02-03) adds the orders/payments/inventory/idempotency/email
cluster plus schema-only inbox_events/order_messages. peer_relays,
relay_cursors, and migration_jobs defer to Phase 3/4 migrations.

Conventions: table names and FK targets use ``db.references_schema``
(``gammamarkets.`` on PostgreSQL, unqualified on SQLite — the extension
file's ``main`` schema). Timestamps are integer epoch seconds. DDL runs
through ``db.execute`` (auto-commit is legal outside domain transactions).
"""

from __future__ import annotations

from lnbits.db import Connection


async def m001_initial(db: Connection):
    s = db.references_schema
    int_t = db.big_int
    blob_t = db.blob

    # --- 4.1 merchants -------------------------------------------------------
    await db.execute(
        f"""
        CREATE TABLE {s}merchants (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL UNIQUE,
            pubkey TEXT NOT NULL UNIQUE,
            key_ref TEXT NOT NULL,
            display_name TEXT,
            profile_json TEXT,
            payment_preference TEXT NOT NULL DEFAULT 'manual',
            recommended_app_d TEXT,
            wallet_id_enc {blob_t} NOT NULL,
            wallet_id_hash TEXT NOT NULL,
            notify_emails TEXT,
            notify_events TEXT,
            theme TEXT,
            state TEXT NOT NULL DEFAULT 'draft',
            created_at {int_t} NOT NULL DEFAULT 0,
            updated_at {int_t} NOT NULL DEFAULT 0
        )
        """
    )

    # --- 4.14 merchant_keys --------------------------------------------------
    await db.execute(
        f"""
        CREATE TABLE {s}merchant_keys (
            merchant_id TEXT PRIMARY KEY
                REFERENCES {s}merchants(id) ON DELETE RESTRICT,
            key_origin TEXT NOT NULL,
            key_version TEXT NOT NULL,
            nonce {blob_t} NOT NULL,
            ciphertext {blob_t} NOT NULL,
            created_at {int_t} NOT NULL DEFAULT 0,
            rotated_at {int_t}
        )
        """
    )

    # --- 4.17 settings -------------------------------------------------------
    await db.execute(
        f"""
        CREATE TABLE {s}settings (
            merchant_id TEXT NOT NULL
                REFERENCES {s}merchants(id) ON DELETE RESTRICT,
            key TEXT NOT NULL,
            value TEXT,
            UNIQUE (merchant_id, key)
        )
        """
    )

    # --- 4.2 catalogs --------------------------------------------------------
    await db.execute(
        f"""
        CREATE TABLE {s}catalogs (
            id TEXT PRIMARY KEY,
            merchant_id TEXT NOT NULL
                REFERENCES {s}merchants(id) ON DELETE RESTRICT,
            name TEXT,
            description TEXT,
            default_currency TEXT,
            default_location TEXT,
            nip15_stall_d TEXT,
            publish_gamma BOOLEAN NOT NULL DEFAULT TRUE,
            publish_nip15 BOOLEAN NOT NULL DEFAULT FALSE,
            deleted_at {int_t},
            created_at {int_t} NOT NULL DEFAULT 0,
            updated_at {int_t} NOT NULL DEFAULT 0
        )
        """
    )

    # --- 4.3 products --------------------------------------------------------
    await db.execute(
        f"""
        CREATE TABLE {s}products (
            id TEXT PRIMARY KEY,
            merchant_id TEXT NOT NULL
                REFERENCES {s}merchants(id) ON DELETE RESTRICT,
            catalog_id TEXT NOT NULL
                REFERENCES {s}catalogs(id) ON DELETE RESTRICT,
            d_tag TEXT NOT NULL,
            parent_product_id TEXT REFERENCES {s}products(id),
            product_type TEXT NOT NULL,
            format TEXT NOT NULL,
            title TEXT,
            summary TEXT,
            description_md TEXT,
            amount_minor {int_t},
            currency TEXT,
            currency_decimals {int_t},
            recurring_frequency TEXT,
            visibility TEXT NOT NULL DEFAULT 'hidden',
            nip99_status TEXT NOT NULL DEFAULT 'active',
            draft BOOLEAN NOT NULL DEFAULT FALSE,
            stock_on_hand {int_t},
            stock_reserved {int_t} NOT NULL DEFAULT 0,
            location TEXT,
            geohash TEXT,
            weight_value REAL,
            weight_unit TEXT,
            dim_l REAL,
            dim_w REAL,
            dim_h REAL,
            dim_unit TEXT,
            nip15_product_id TEXT,
            published_at {int_t},
            revision {int_t} NOT NULL DEFAULT 0,
            deleted_at {int_t},
            created_at {int_t} NOT NULL DEFAULT 0,
            updated_at {int_t} NOT NULL DEFAULT 0,
            UNIQUE (merchant_id, d_tag),
            CHECK (amount_minor IS NULL OR amount_minor >= 0),
            -- ^[A-Z0-9]{3,8}$ charset is asserted in the service layer;
            -- SQLite has no portable REGEXP.
            CHECK (currency IS NULL OR length(currency) BETWEEN 3 AND 8),
            CHECK (
                currency_decimals IS NULL
                OR (currency_decimals >= 0 AND currency_decimals <= 18)
            ),
            CHECK (stock_on_hand IS NULL OR stock_on_hand >= 0),
            CHECK (stock_reserved >= 0),
            CHECK (stock_on_hand IS NULL OR stock_reserved <= stock_on_hand),
            CHECK ((product_type = 'variation') = (parent_product_id IS NOT NULL))
        )
        """
    )

    # --- 4.4 product detail tables -------------------------------------------
    await db.execute(
        f"""
        CREATE TABLE {s}product_images (
            id TEXT PRIMARY KEY,
            product_id TEXT NOT NULL
                REFERENCES {s}products(id) ON DELETE RESTRICT,
            url TEXT NOT NULL,
            dimensions TEXT,
            sort_order {int_t} NOT NULL DEFAULT 0
        )
        """
    )
    await db.execute(
        f"""
        CREATE TABLE {s}product_specs (
            id TEXT PRIMARY KEY,
            product_id TEXT NOT NULL
                REFERENCES {s}products(id) ON DELETE RESTRICT,
            key TEXT NOT NULL,
            value TEXT NOT NULL
        )
        """
    )
    await db.execute(
        f"""
        CREATE TABLE {s}product_categories (
            id TEXT PRIMARY KEY,
            product_id TEXT NOT NULL
                REFERENCES {s}products(id) ON DELETE RESTRICT,
            category TEXT NOT NULL
        )
        """
    )
    await db.execute(
        f"""
        CREATE TABLE {s}product_collections (
            id TEXT PRIMARY KEY,
            product_id TEXT NOT NULL
                REFERENCES {s}products(id) ON DELETE RESTRICT,
            collection_id TEXT NOT NULL
                REFERENCES {s}collections(id) ON DELETE RESTRICT,
            UNIQUE (product_id, collection_id)
        )
        """
    )

    # --- 4.5 collections + collection_shipping -------------------------------
    await db.execute(
        f"""
        CREATE TABLE {s}collections (
            id TEXT PRIMARY KEY,
            merchant_id TEXT NOT NULL
                REFERENCES {s}merchants(id) ON DELETE RESTRICT,
            d_tag TEXT NOT NULL,
            title TEXT,
            description TEXT,
            image TEXT,
            location TEXT,
            geohash TEXT,
            revision {int_t} NOT NULL DEFAULT 0,
            deleted_at {int_t},
            created_at {int_t} NOT NULL DEFAULT 0,
            updated_at {int_t} NOT NULL DEFAULT 0,
            UNIQUE (merchant_id, d_tag)
        )
        """
    )
    await db.execute(
        f"""
        CREATE TABLE {s}collection_shipping (
            id TEXT PRIMARY KEY,
            collection_id TEXT NOT NULL
                REFERENCES {s}collections(id) ON DELETE RESTRICT,
            shipping_option_id TEXT NOT NULL,
            UNIQUE (collection_id, shipping_option_id)
        )
        """
    )

    # --- 4.6 shipping_options -------------------------------------------------
    await db.execute(
        f"""
        CREATE TABLE {s}shipping_options (
            id TEXT PRIMARY KEY,
            merchant_id TEXT NOT NULL
                REFERENCES {s}merchants(id) ON DELETE RESTRICT,
            d_tag TEXT NOT NULL,
            title TEXT,
            description TEXT,
            base_price_minor {int_t},
            currency TEXT,
            service TEXT NOT NULL,
            carrier TEXT,
            countries TEXT,
            regions TEXT,
            duration_min {int_t},
            duration_max {int_t},
            duration_unit TEXT,
            weight_min REAL,
            weight_max REAL,
            weight_unit TEXT,
            dim_min_l REAL,
            dim_min_w REAL,
            dim_min_h REAL,
            dim_max_l REAL,
            dim_max_w REAL,
            dim_max_h REAL,
            dim_unit TEXT,
            price_weight_minor {int_t},
            price_weight_unit TEXT,
            price_volume_minor {int_t},
            price_volume_unit TEXT,
            location TEXT,
            geohash TEXT,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            revision {int_t} NOT NULL DEFAULT 0,
            deleted_at {int_t},
            created_at {int_t} NOT NULL DEFAULT 0,
            updated_at {int_t} NOT NULL DEFAULT 0,
            UNIQUE (merchant_id, d_tag)
        )
        """
    )

    # --- 4.4 continued: shipping reference tables (need shipping_options) -----
    await db.execute(
        f"""
        CREATE TABLE {s}product_shipping_options (
            id TEXT PRIMARY KEY,
            product_id TEXT NOT NULL
                REFERENCES {s}products(id) ON DELETE RESTRICT,
            shipping_option_id TEXT NOT NULL
                REFERENCES {s}shipping_options(id) ON DELETE RESTRICT,
            extra_cost_minor {int_t},
            UNIQUE (product_id, shipping_option_id)
        )
        """
    )
    await db.execute(
        f"""
        CREATE TABLE {s}product_shipping_collections (
            id TEXT PRIMARY KEY,
            product_id TEXT NOT NULL
                REFERENCES {s}products(id) ON DELETE RESTRICT,
            collection_id TEXT NOT NULL
                REFERENCES {s}collections(id) ON DELETE RESTRICT,
            extra_cost_minor {int_t},
            UNIQUE (product_id, collection_id)
        )
        """
    )

    # --- 4.13 protocol_addresses ----------------------------------------------
    await db.execute(
        f"""
        CREATE TABLE {s}protocol_addresses (
            id TEXT PRIMARY KEY,
            domain_type TEXT NOT NULL,
            domain_id TEXT NOT NULL,
            protocol TEXT NOT NULL,
            event_kind {int_t} NOT NULL,
            author_pubkey TEXT NOT NULL,
            d_tag TEXT NOT NULL DEFAULT '',
            latest_event_id TEXT,
            latest_created_at {int_t},
            UNIQUE (protocol, event_kind, author_pubkey, d_tag)
        )
        """
    )

    # --- 4.11 relay_configs ----------------------------------------------------
    await db.execute(
        f"""
        CREATE TABLE {s}relay_configs (
            id TEXT PRIMARY KEY,
            merchant_id TEXT REFERENCES {s}merchants(id) ON DELETE RESTRICT,
            relay_url TEXT NOT NULL,
            direction TEXT NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at {int_t} NOT NULL DEFAULT 0,
            updated_at {int_t} NOT NULL DEFAULT 0
        )
        """
    )

    # --- 4.10 outbox_events + dependencies + relay_publications -----------------
    await db.execute(
        f"""
        CREATE TABLE {s}outbox_events (
            id TEXT PRIMARY KEY,
            merchant_id TEXT NOT NULL,
            aggregate_type TEXT NOT NULL,
            aggregate_id TEXT NOT NULL,
            aggregate_revision {int_t} NOT NULL DEFAULT 0,
            event_kind {int_t} NOT NULL,
            event_address TEXT,
            payload_json TEXT,
            payload_enc {blob_t},
            state TEXT NOT NULL,
            attempts {int_t} NOT NULL DEFAULT 0,
            next_attempt_at {int_t} NOT NULL DEFAULT 0,
            claimed_by TEXT,
            claimed_at {int_t},
            claimed_until {int_t},
            claim_token {int_t} NOT NULL DEFAULT 0,
            last_error TEXT,
            created_at {int_t} NOT NULL DEFAULT 0,
            updated_at {int_t} NOT NULL DEFAULT 0
        )
        """
    )
    await db.execute(
        f"""
        CREATE TABLE {s}outbox_dependencies (
            outbox_event_id TEXT NOT NULL
                REFERENCES {s}outbox_events(id) ON DELETE RESTRICT,
            depends_on_outbox_event_id TEXT NOT NULL
                REFERENCES {s}outbox_events(id) ON DELETE RESTRICT,
            UNIQUE (outbox_event_id, depends_on_outbox_event_id)
        )
        """
    )
    await db.execute(
        f"""
        CREATE TABLE {s}relay_publications (
            id TEXT PRIMARY KEY,
            outbox_event_id TEXT NOT NULL
                REFERENCES {s}outbox_events(id) ON DELETE RESTRICT,
            delivery_copy TEXT NOT NULL,
            relay_url TEXT NOT NULL,
            event_id TEXT NOT NULL,
            attempt_no {int_t} NOT NULL,
            result TEXT NOT NULL,
            message TEXT,
            attempted_at {int_t} NOT NULL,
            UNIQUE (
                outbox_event_id, delivery_copy, relay_url, event_id, attempt_no
            )
        )
        """
    )

    # --- 4.16 task_leases + rate_limit_buckets ---------------------------------
    await db.execute(
        f"""
        CREATE TABLE {s}task_leases (
            name TEXT PRIMARY KEY,
            holder_id TEXT,
            fencing_token {int_t} NOT NULL DEFAULT 0,
            leased_until {int_t} NOT NULL DEFAULT 0,
            updated_at {int_t} NOT NULL DEFAULT 0
        )
        """
    )
    await db.execute(
        f"""
        CREATE TABLE {s}rate_limit_buckets (
            scope_hash TEXT NOT NULL,
            bucket TEXT NOT NULL,
            window_start {int_t} NOT NULL,
            count {int_t} NOT NULL DEFAULT 0,
            expires_at {int_t} NOT NULL,
            UNIQUE (scope_hash, bucket, window_start)
        )
        """
    )

    # --- 4.19 indexes touching m001 tables --------------------------------------
    await db.execute(
        f"CREATE INDEX ix_products_merchant_catalog "
        f"ON {s}products(merchant_id, catalog_id)"
    )
    await db.execute(
        f"CREATE UNIQUE INDEX ix_products_nip15_id "
        f"ON {s}products(merchant_id, nip15_product_id) "
        f"WHERE nip15_product_id IS NOT NULL"
    )
    await db.execute(
        f"CREATE INDEX ix_outbox_events_state_next "
        f"ON {s}outbox_events(state, next_attempt_at)"
    )
    await db.execute(
        f"CREATE INDEX ix_outbox_events_aggregate "
        f"ON {s}outbox_events(aggregate_type, aggregate_id, aggregate_revision)"
    )
