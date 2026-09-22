"""MerchantKeyStore — local key backend (spec section 11.1/11.2).

The merchant nsec exists only as an AES-256-GCM envelope in
``merchant_keys``; raw key material is decrypted inside a keystore
operation, used for the single signing/unwrap call, and never cached,
logged, or attached to a long-lived SDK client. Python cannot guarantee
physical memory zeroization — residual risk documented in section 11.2.

NIP-17/NIP-04 methods exist on the interface per section 11.1 but raise
``ReleaseNotAvailable`` — they are Release B/C scope.
"""

from __future__ import annotations

import time
import uuid

from nostr_sdk import Keys, NostrSigner, UnsignedEvent

from . import crypto
from .db import db, table
from .settings import ExtSettings

KEY_ORIGIN_GENERATED = "generated"
KEY_ORIGIN_IMPORTED = "imported"


class KeystoreError(RuntimeError):
    pass


class ReleaseNotAvailable(KeystoreError):
    """Interface member exists per section 11.1 but belongs to Release B/C."""


class MerchantKeyStore:
    def __init__(self, settings: ExtSettings) -> None:
        self._settings = settings

    # --- key lifecycle -------------------------------------------------------

    async def generate(self, merchant_id: str) -> str:
        """Generate a fresh keypair, persist the encrypted nsec, return pubkey.

        Refuses when a key row already exists — silent overwrite would
        orphan the old identity. Rotation goes through ``import_key`` (new
        material) or ``rewrap`` (same material, new master version).
        """
        async with db.connect() as conn:
            existing = await conn.fetchone(
                f"SELECT merchant_id FROM {table('merchant_keys')} "
                "WHERE merchant_id = :m",
                {"m": merchant_id},
            )
        if existing:
            raise KeystoreError(
                "merchant already has a key — use import_key or rewrap"
            )
        keys = Keys.generate()
        nsec = keys.secret_key().to_hex()
        try:
            await self._store(merchant_id, bytes.fromhex(nsec), KEY_ORIGIN_GENERATED)
            return keys.public_key().to_hex()
        finally:
            del keys, nsec

    async def import_key(self, merchant_id: str, nsec_bech32: str) -> str:
        """Decode a bech32 nsec, validate, encrypt into ``merchant_keys``.

        ``Keys.parse`` validates the nsec1 prefix + secp256k1 range; the raw
        secret lives only inside this call.
        """
        try:
            keys = Keys.parse(nsec_bech32)
        except Exception as exc:
            raise KeystoreError("invalid nsec") from exc
        nsec_hex = keys.secret_key().to_hex()
        try:
            await self._store(merchant_id, bytes.fromhex(nsec_hex), KEY_ORIGIN_IMPORTED)
            return keys.public_key().to_hex()
        finally:
            del keys, nsec_hex

    async def _store(self, merchant_id: str, nsec_bytes: bytes, origin: str) -> None:
        s = self._settings
        envelope = crypto.encrypt(
            nsec_bytes,
            s.master_keys[s.active_key_version],
            record_id=merchant_id,
            table="merchant_keys",
            column="ciphertext",
            key_version=s.active_key_version,
        )
        nonce = envelope[crypto.VERSION_LEN : crypto.VERSION_LEN + crypto.NONCE_LEN]
        body = envelope[crypto.VERSION_LEN + crypto.NONCE_LEN :]
        async with db.connect() as conn:
            await conn.execute(
                f"""
                INSERT INTO {table('merchant_keys')}
                    (merchant_id, key_origin, key_version, nonce, ciphertext,
                     created_at)
                VALUES (:m, :o, :v, :n, :c, :t)
                ON CONFLICT (merchant_id) DO UPDATE SET
                    key_origin = :o, key_version = :v, nonce = :n,
                    ciphertext = :c, rotated_at = :t
                """,
                {
                    "m": merchant_id,
                    "o": origin,
                    "v": s.active_key_version,
                    "n": nonce,
                    "c": body,
                    "t": int(time.time()),
                },
            )

    async def _load_nsec(self, merchant_id: str) -> bytes:
        """Decrypt the merchant nsec inside the operation; caller releases."""
        async with db.connect() as conn:
            row = await conn.fetchone(
                f"SELECT key_version, nonce, ciphertext FROM {table('merchant_keys')} "
                "WHERE merchant_id = :m",
                {"m": merchant_id},
            )
        if not row:
            raise KeystoreError("merchant key not found")
        version = row["key_version"]
        key = self._settings.master_keys.get(version)
        if key is None:
            raise KeystoreError("key version absent from keyring")
        envelope = (
            version.encode().ljust(crypto.VERSION_LEN, b"\x00")
            + bytes(row["nonce"])
            + bytes(row["ciphertext"])
        )
        return crypto.decrypt(
            envelope,
            key,
            record_id=merchant_id,
            table="merchant_keys",
            column="ciphertext",
            key_version=version,
        )

    async def _keys(self, merchant_id: str) -> Keys:
        nsec = await self._load_nsec(merchant_id)
        try:
            return Keys.parse(nsec.hex())
        finally:
            del nsec

    async def public_key(self, merchant_id: str) -> str:
        keys = await self._keys(merchant_id)
        try:
            return keys.public_key().to_hex()
        finally:
            del keys

    async def sign_event(self, merchant_id: str, unsigned: UnsignedEvent):
        """Sign ``unsigned`` with the merchant key; key is released on exit."""
        keys = await self._keys(merchant_id)
        try:
            signer = NostrSigner.keys(keys)
            return await signer.sign_event(unsigned)
        finally:
            del keys

    async def delete(self, merchant_id: str) -> None:
        """Erase key material (deactivation final step — see section 6.7)."""
        async with db.connect() as conn:
            await conn.execute(
                f"DELETE FROM {table('merchant_keys')} WHERE merchant_id = :m",
                {"m": merchant_id},
            )

    # --- rotation (resumable, section 11.2) -----------------------------------

    async def rewrap(self, merchant_id: str) -> bool:
        """Re-encrypt one merchant key under the active version.

        Returns True when the row already uses the active version or was
        rewrapped; False when the row's version is absent from the keyring
        (operator must restore the old key before rotation can finish).
        Bounded: one row per call — the rotation job loops over stale rows.
        """
        async with db.connect() as conn:
            row = await conn.fetchone(
                f"SELECT key_version, key_origin FROM {table('merchant_keys')} "
                "WHERE merchant_id = :m",
                {"m": merchant_id},
            )
        if not row:
            raise KeystoreError("merchant key not found")
        active = self._settings.active_key_version
        if row["key_version"] == active:
            return True
        if row["key_version"] not in self._settings.master_keys:
            return False
        nsec = await self._load_nsec(merchant_id)
        try:
            await self._store(merchant_id, nsec, row["key_origin"])
        finally:
            del nsec
        return True

    async def stale_versions(self) -> list[str]:
        """Key versions still present in merchant_keys — for the rotation
        job's 'zero old-version rows' gate."""
        async with db.connect() as conn:
            rows = await conn.fetchall(
                f"SELECT DISTINCT key_version AS v FROM {table('merchant_keys')}"
            )
        return [r["v"] for r in rows]

    async def stale_merchants(self) -> list[str]:
        """merchant_ids whose key rows are NOT on the active version — the
        rotation job's work list."""
        async with db.connect() as conn:
            rows = await conn.fetchall(
                f"SELECT merchant_id AS m FROM {table('merchant_keys')} "
                "WHERE key_version != :v ORDER BY merchant_id",
                {"v": self._settings.active_key_version},
            )
        return [r["m"] for r in rows]

    # --- backup/restore (envelope only — never plaintext) ---------------------

    async def export_encrypted(self, merchant_id: str) -> str:
        """Serialize the encrypted key row to a portable JSON blob.

        The blob stays ciphertext end-to-end — backup safety reduces to
        protecting the master keyring, not the export file.
        """
        import base64
        import json

        async with db.connect() as conn:
            row = await conn.fetchone(
                "SELECT key_origin, key_version, nonce, ciphertext,"
                " created_at FROM " + table("merchant_keys") +
                " WHERE merchant_id = :m",
                {"m": merchant_id},
            )
        if not row:
            raise KeystoreError("merchant key not found")
        return json.dumps(
            {
                "merchant_id": merchant_id,
                "key_origin": row["key_origin"],
                "key_version": row["key_version"],
                "nonce": base64.b64encode(bytes(row["nonce"])).decode(),
                "ciphertext": base64.b64encode(
                    bytes(row["ciphertext"])
                ).decode(),
                "created_at": row["created_at"],
            }
        )

    async def restore_encrypted(self, merchant_id: str, blob: str) -> None:
        """Restore an ``export_encrypted`` blob; refuses to overwrite an
        existing row."""
        import base64
        import json

        try:
            record = json.loads(blob)
            nonce = base64.b64decode(record["nonce"], validate=True)
            ciphertext = base64.b64decode(
                record["ciphertext"], validate=True
            )
            version = record["key_version"]
            origin = record["key_origin"]
        except (KeyError, ValueError, TypeError) as exc:
            raise KeystoreError("malformed key backup") from exc
        async with db.connect() as conn:
            existing = await conn.fetchone(
                f"SELECT merchant_id FROM {table('merchant_keys')} "
                "WHERE merchant_id = :m",
                {"m": merchant_id},
            )
            if existing:
                raise KeystoreError("merchant key already exists")
            await conn.execute(
                f"INSERT INTO {table('merchant_keys')} "
                "(merchant_id, key_origin, key_version, nonce, ciphertext,"
                " created_at) VALUES (:m, :o, :v, :n, :c, :t)",
                {
                    "m": merchant_id,
                    "o": origin,
                    "v": version,
                    "n": nonce,
                    "c": ciphertext,
                    "t": int(time.time()),
                },
            )

    # --- Release B/C interface members (section 11.1) -------------------------

    async def nip17_wrap(self, merchant_id, unsigned_rumor, recipient_pubkey):
        raise ReleaseNotAvailable("NIP-17 gift wrap is Release B scope")

    async def nip17_unwrap(self, merchant_id, signed_gift_wrap):
        raise ReleaseNotAvailable("NIP-17 unwrap is Release B scope")

    async def nip04_decrypt(self, merchant_id, peer_pubkey, ciphertext):
        raise ReleaseNotAvailable("NIP-04 compat is Release C scope")

    async def nip04_encrypt(self, merchant_id, peer_pubkey, plaintext):
        raise ReleaseNotAvailable("NIP-04 compat is Release C scope")


def key_store(settings: ExtSettings | None = None) -> MerchantKeyStore:
    from .settings import ext_settings

    return MerchantKeyStore(settings or ext_settings())


def new_id() -> str:
    return uuid.uuid4().hex
