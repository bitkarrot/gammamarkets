"""Runtime install fixtures — the REAL host discovery path.

Unlike the qualification probes (which mount fixture routers inside a host
app), these tests exercise the actual extension lifecycle:

    LNBITS_EXTENSIONS_PATH/extensions/gammamarkets/config.json
        -> build_all_installed_extensions_list (from_ext_dir)
        -> migrate_extension_database (m001)
        -> register_ext_routes (imports ``gammamarkets``)
        -> register_ext_tasks (calls ``gammamarkets_start`` synchronously)

The extension directory is a symlink to the repo package — same files, real
loader. ``GAMMAMARKETS_*`` env is set before the lifespan startup so the
sync start hook's strict validation passes.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest_asyncio

REPO_ROOT = Path(__file__).resolve().parents[2]
PKG_DIR = REPO_ROOT / "gammamarkets"

CANONICAL_ORIGIN = "https://shop.example"

_EXT_ENV = {
    "GAMMAMARKETS_MASTER_KEYS": json.dumps(
        {"v1": base64.b64encode(b"k" * 32).decode()}
    ),
    "GAMMAMARKETS_ACTIVE_KEY_VERSION": "v1",
    "GAMMAMARKETS_PRIVACY_KEY": base64.b64encode(b"p" * 32).decode(),
    "GAMMAMARKETS_PUBLIC_BASE_URL": CANONICAL_ORIGIN,
    # Never dial real relays from a host-boot test — workers stay live
    # (claim/evidence paths exercised) but the transport never connects.
    "GAMMAMARKETS_RELAY_IO": "off",
}

_RUNTIME_SETTINGS_KEYS = (
    "lnbits_data_folder",
    "lnbits_backend_wallet_class",
    "lnbits_extensions_path",
    "lnbits_extensions_deactivate_all",
    "lnbits_admin_ui",
    "first_install",
    # OQ3 qualified posture: audit capture off for gammamarkets tests
    "lnbits_audit_log_request_body",
    "lnbits_audit_log_query_params",
    "lnbits_audit_log_path_params",
)


@asynccontextmanager
async def _runtime_app(data_folder: Path, ext_root: Path):
    """Boot the pinned host with the real extension-discovery path.

    Mirrors harness.host.host_app (chdir into the checkout, FakeWallet,
    isolated data folder) but with ``lnbits_extensions_path`` pointed at a
    tmp dir whose ``extensions/gammamarkets`` is a symlink to the repo
    package, and ``lnbits_extensions_deactivate_all = False`` so the real
    restore/registration path activates the extension.
    """
    from asgi_lifespan import LifespanManager
    from lnbits.app import create_app
    from lnbits.core.models.users import UpdateSuperuserPassword
    from lnbits.core.views.auth_api import first_install
    from lnbits.settings import settings

    from tools.checkout_host import host_checkout_dir

    snapshot = {key: getattr(settings, key) for key in _RUNTIME_SETTINGS_KEYS}
    previous_cwd = Path.cwd()
    env_snapshot = {k: os.environ.get(k) for k in _EXT_ENV}

    extensions_dir = ext_root / "extensions"
    extensions_dir.mkdir(parents=True)
    link = extensions_dir / "gammamarkets"
    if not link.exists():
        link.symlink_to(PKG_DIR, target_is_directory=True)

    os.environ.update(_EXT_ENV)
    settings.lnbits_data_folder = str(data_folder)
    settings.lnbits_backend_wallet_class = "FakeWallet"
    settings.lnbits_extensions_path = str(ext_root)
    settings.lnbits_extensions_deactivate_all = False
    settings.lnbits_admin_ui = True
    settings.first_install = True
    # Qualified audit posture (OQ3): no path/query/body capture.
    settings.lnbits_audit_log_request_body = False
    settings.lnbits_audit_log_query_params = False
    settings.lnbits_audit_log_path_params = False

    # The extension module must not be pre-imported: ``Database.__init__``
    # binds the SQLite path at construction, and the host's migration loader
    # uses whatever module object is in sys.modules. Purge any earlier
    # import so the boot binds this run's data folder.
    for mod in [m for m in sys.modules if m == "gammamarkets" or m.startswith("gammamarkets.")]:
        del sys.modules[mod]

    # The core DB (.cache/qual-data) is shared across boots: prior runs leave
    # installed_extensions/dbversions/extensions rows for gammamarkets while
    # this boot's ext DB file is fresh. Reset BEFORE startup so the boot is
    # a real fresh install through the host's own restore path.
    from lnbits.core.db import db as core_db

    async with core_db.connect() as conn:
        await conn.execute(
            "DELETE FROM installed_extensions WHERE id = :id",
            {"id": "gammamarkets"},
        )
        await conn.execute(
            "DELETE FROM dbversions WHERE db = :id", {"id": "gammamarkets"}
        )
        await conn.execute(
            'DELETE FROM extensions WHERE extension = :id',
            {"id": "gammamarkets"},
        )
    settings.lnbits_installed_extensions_ids.discard("gammamarkets")
    settings.lnbits_deactivated_extensions.discard("gammamarkets")

    os.chdir(host_checkout_dir())
    try:
        app = create_app()
        async with LifespanManager(app, startup_timeout=30):
            superuser = f"gqadmin-{uuid.uuid4().hex[:8]}"
            await first_install(
                UpdateSuperuserPassword(
                    username=superuser,
                    password="secret1234",
                    password_repeat="secret1234",
                    first_install_token=settings.first_install_token,
                )
            )
            # If the persisted deactivate_all flag skipped the startup
            # registration pass, run it now — the same path admin
            # activation uses: scan -> migrate -> register routes -> start
            # hook. (deactivate_all is an editable admin setting reloaded
            # from the shared core DB at startup.)
            import importlib

            from lnbits.app import check_and_register_extensions
            from lnbits.core.crud import update_admin_settings
            from lnbits.core.services.settings import update_cached_settings
            from lnbits.settings import EditableSettings

            await update_admin_settings(
                EditableSettings(
                    lnbits_extensions_deactivate_all=False,
                    lnbits_audit_log_request_body=False,
                    lnbits_audit_log_query_params=False,
                    lnbits_audit_log_path_params=False,
                )
            )
            update_cached_settings(
                {
                    "lnbits_extensions_deactivate_all": False,
                    "lnbits_audit_log_request_body": False,
                    "lnbits_audit_log_query_params": False,
                    "lnbits_audit_log_path_params": False,
                }
            )
            ext_module = importlib.import_module("gammamarkets")
            if ext_module.started_at is None:
                await check_and_register_extensions(app)
            yield app
    finally:
        os.chdir(previous_cwd)
        for key, value in snapshot.items():
            setattr(settings, key, value)
        for key, value in env_snapshot.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def keystore_env(tmp_path_factory):
    """Fresh gammamarkets module set bound to a tmp data folder, m001 applied.

    ``Database.__init__`` binds ``settings.lnbits_data_folder`` at import
    time, so any ``gammamarkets`` module imported earlier (e.g. at test
    collection) holds a stale path. The fixture purges ``gammamarkets*``
    modules, sets the folder, then imports db/keystore fresh — tests MUST
    take ``MerchantKeyStore`` from the yielded namespace, not a module-level
    import.

    Yields ``{"db", "keystore", "crypto", "settings"}`` module objects.
    """
    import importlib

    from lnbits.settings import settings

    folder = tmp_path_factory.mktemp("keystore-db")
    previous = settings.lnbits_data_folder
    settings.lnbits_data_folder = str(folder)
    for mod in [
        m for m in sys.modules
        if m == "gammamarkets" or m.startswith("gammamarkets.")
    ]:
        del sys.modules[mod]
    try:
        gdb = importlib.import_module("gammamarkets.db")
        keystore = importlib.import_module("gammamarkets.keystore")
        crypto = importlib.import_module("gammamarkets.crypto")
        gsettings = importlib.import_module("gammamarkets.settings")
        from gammamarkets.migrations import m001_initial

        async with gdb.db.connect() as conn:
            await m001_initial(conn)
        yield {
            "db": gdb.db,
            "keystore": keystore,
            "crypto": crypto,
            "settings": gsettings,
        }
    finally:
        settings.lnbits_data_folder = previous


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def runtime_env(tmp_path_factory):
    """One real-loader host boot per module + an authenticated client.

    Yields ``{app, client, token, user_id, wallet, ext_module}`` where
    ``ext_module`` is the module object the host registered (imported AFTER
    registration so ``sys.modules`` reimport semantics are observed).
    """
    import importlib

    from lnbits.core.crud import create_wallet
    from lnbits.core.services import update_wallet_balance

    tmp = tmp_path_factory.mktemp("runtime")
    async with _runtime_app(tmp / "data", tmp / "extroot") as app:
        # Real account with password (same pattern as the P0-12 auth probes),
        # logged in through the host's own auth endpoint.
        from lnbits.core.crud.users import create_account
        from lnbits.core.models.users import Account

        username = f"gquser{uuid.uuid4().hex[:8]}"
        password = "runtime-pass-123"
        account = Account(
            id=uuid.uuid4().hex, username=username, email=None
        )
        account.hash_password(password)
        await create_account(account)

        wallet = await create_wallet(
            user_id=account.id, wallet_name="runtime-wallet"
        )
        await update_wallet_balance(wallet=wallet, amount=9999999)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url=CANONICAL_ORIGIN
        ) as client:
            resp = await client.post(
                "/api/v1/auth",
                json={"username": username, "password": password},
            )
            assert resp.status_code == 200, resp.text
            token = resp.json()["access_token"]

            # Per-user enablement: the host gates extension routes on the
            # user's active extension list (extension not enabled -> 403).
            resp = await client.put(
                "/api/v1/extension/gammamarkets/enable",
                headers={
                    "Cookie": f"cookie_access_token={token}",
                    "Origin": CANONICAL_ORIGIN,
                },
            )
            assert resp.status_code == 200, resp.text

            # The host reimports the extension during registration — import
            # now so tests observe the module object the host registered.
            sys.path.insert(
                0, str(tmp / "extroot" / "extensions")
            )
            try:
                ext_module = importlib.import_module("gammamarkets")
            finally:
                sys.path.remove(str(tmp / "extroot" / "extensions"))
            yield {
                "app": app,
                "client": client,
                "token": token,
                "user_id": account.id,
                "username": username,
                "wallet": wallet,
                "ext_module": ext_module,
                "tmp": tmp,
            }
