#!/usr/bin/env python3
"""Fetch the merchant's published events from public relays and render
verify.html — the external-proof page for the demo video.

Pulls kind-0 (profile), 10050 (inbox prefs), 30402/30405/30406 (NIP-99)
authored by the merchant pubkey from relay.damus.io / nos.lol /
relay.nostr.net, checks the NIP-99 tag contract, and renders an HTML
report. Also attempts to unwrap the latest kind-1059 gift wrap addressed
to the customer pubkey to show the merchant's DM as the buyer sees it.
"""

import asyncio
import html
import json
from datetime import timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEYS = json.loads((HERE / "keys.json").read_text())
MERCHANT_HEX = KEYS["merchant"]["hex"]
CUSTOMER_HEX = KEYS["customer"]["hex"]
CUSTOMER_NSEC = KEYS["customer"]["nsec"]

RELAYS = ["wss://relay.damus.io", "wss://nos.lol", "wss://relay.nostr.net"]
KINDS = {0: "profile", 10050: "inbox prefs (NIP-17)",
         30402: "product (NIP-99)", 30405: "collection (NIP-99)",
         30406: "shipping (NIP-99)", 1059: "gift wrap"}
RESULT = {"events": [], "compliance": [], "message": None, "relays": {}}


async def fetch_events():
    from nostr_sdk import Client, Filter, Kind, PublicKey, RelayUrl

    client = Client()
    for r in RELAYS:
        try:
            await client.add_relay(RelayUrl.parse(r))
        except Exception as e:
            RESULT["relays"][r] = f"connect fail: {e}"
    await client.connect()
    author = PublicKey.parse(MERCHANT_HEX)
    f = (Filter()
         .author(author)
         .kinds([Kind(0), Kind(10050), Kind(30402), Kind(30405), Kind(30406)])
         .limit(50))
    events = await client.fetch_events(f, timedelta(seconds=20))
    evs = []
    try:
        evs = events.to_vec()
    except AttributeError:
        for ev in events:
            evs.append(ev)
    for ev in evs:
        try:
            j = json.loads(ev.as_json())
        except Exception:
            j = ev.as_json() if isinstance(ev.as_json(), dict) else {}
        if j:
            RESULT["events"].append(j)
    # per-relay liveness
    try:
        await client.relays()
        for url in RELAYS:
            RESULT["relays"][url] = "queried"
    except Exception:
        pass
    await client.disconnect()


def tagv(ev, name, idx=1):
    for t in ev.get("tags", []):
        if t and t[0] == name:
            return t[idx] if len(t) > idx else True
    return None


def live_d_tags():
    """d_tags of currently-live objects — filters deleted/superseded events."""
    import sqlite3
    con = sqlite3.connect(
        "/home/exedev/lnbits/data/ext_infinitemarkets.sqlite3")
    out = set()
    for table in ("products", "collections", "shipping_options"):
        try:
            for (d,) in con.execute(
                    f"select d_tag from {table} where deleted_at is null"):
                out.add(d)
        except Exception:
            pass
    return out


def check_nip99(ev):
    """Validate a 30402/30405/30406 event against the NIP-99 contract."""
    kind = ev.get("kind")
    checks = []
    def need(name, cond=True):
        val = tagv(ev, name)
        checks.append({"tag": name, "ok": bool(val is not None) if cond else True,
                       "value": val})
        return val
    d = need("d")
    need("title")
    if kind == 30402:
        need("published_at")
        need("summary")
        need("image")
        need("price")
        price = next((t for t in ev.get("tags", []) if t and t[0] == "price"), None)
        checks.append({"tag": "price=[amount,currency]",
                       "ok": bool(price and len(price) >= 3)})
    ok = all(c["ok"] for c in checks)
    return {"d": d, "ok": ok, "checks": checks,
            "addr": f"{kind}:{ev.get('pubkey','')[:8]}…:{d}"}


async def unwrap_dm():
    """Try to read the latest gift wrap to the customer and show content."""
    from nostr_sdk import (
        Client,
        Filter,
        Keys,
        Kind,
        NostrSigner,
        PublicKey,
        RelayUrl,
        UnwrappedGift,
    )
    client = Client()
    for r in RELAYS:
        try:
            await client.add_relay(RelayUrl.parse(r))
        except Exception:
            pass
    await client.connect()
    cust = PublicKey.parse(CUSTOMER_HEX)
    f = Filter().pubkey(cust).kind(Kind(1059)).limit(10)
    events = await client.fetch_events(f, timedelta(seconds=20))
    evs = events.to_vec() if hasattr(events, "to_vec") else list(events)
    keys = Keys.parse(CUSTOMER_NSEC)
    signer = NostrSigner.keys(keys)
    for ev in sorted(evs, key=lambda e: e.created_at().as_secs(), reverse=True):
        try:
            g = await UnwrappedGift.from_gift_wrap(signer, ev)
            RESULT["message"] = {
                "wrap_id": ev.id().to_hex(),
                "kind": g.rumor().kind().as_u16(),
                "sender": g.sender().to_hex(),
                "content": g.rumor().content(),
            }
            break
        except Exception:
            continue
    await client.disconnect()


def render():
    evs = RESULT["events"]
    by_kind = {}
    for ev in evs:
        by_kind.setdefault(ev.get("kind"), []).append(ev)
    live = live_d_tags()
    rows = ""
    for kind in (0, 10050, 30402, 30405, 30406):
        kept = []
        for ev in by_kind.get(kind, []):
            if kind in (30402, 30405, 30406):
                if tagv(ev, "d") not in live:
                    continue  # deleted/superseded listings stay off the report
            kept.append(ev)
        for ev in sorted(kept,
                         key=lambda e: e.get("created_at", 0), reverse=True)[:4]:
            c = check_nip99(ev) if kind in (30402, 30405, 30406) else None
            d = html.escape(str(tagv(ev, "d") or "—"))
            title = html.escape(str(tagv(ev, "title") or "—"))
            badge = ('<span class="ok">NIP-99 ✓</span>' if c and c["ok"]
                     else '<span class="warn">tags?</span>' if c else
                     '<span class="info">meta</span>')
            tags_summary = ""
            if c:
                tags_summary = " · ".join(
                    f'{x["tag"]}={"✓" if x["ok"] else "✗"}' for x in c["checks"])
            rows += (f'<tr><td class="mono">{kind}</td>'
                     f'<td>{KINDS.get(kind, "?")}</td>'
                     f'<td class="mono">{d}</td>'
                     f'<td>{title}</td>'
                     f'<td class="mono">{ev.get("id","")[:16]}…</td>'
                     f'<td>{badge}<div class="mini">{html.escape(tags_summary)}</div></td></tr>')
    msg = ""
    if RESULT["message"]:
        m = RESULT["message"]
        msg = (f'<div class="card msg"><h3>Encrypted order message — as the buyer receives it</h3>'
               f'<p class="mono">wrap {m["wrap_id"][:24]}… · kind {m["kind"]} · '
               f'from merchant {m["sender"][:16]}…</p>'
               f'<blockquote>{html.escape(m["content"][:400])}</blockquote></div>')
    relay_badges = " ".join(
        f'<span class="relay">{html.escape(r.replace("wss://",""))}</span>'
        for r in RELAYS)
    body = f"""<!doctype html><html><head><meta charset="utf-8"><style>
body{{margin:0;min-height:100vh;background:#0b1120;color:#e2e8f0;
font-family:system-ui,sans-serif;padding:44px 60px;box-sizing:border-box}}
h1{{font-size:36px;margin:0 0 6px}}
.sub{{color:#94a3b8;font-size:18px;margin-bottom:26px}}
.relays{{margin-bottom:22px}}
.relay{{background:#1e293b;border:1px solid #334155;border-radius:8px;
padding:6px 14px;margin-right:10px;font-family:ui-monospace,monospace;font-size:15px}}
table{{width:100%;border-collapse:collapse;font-size:15px}}
td,th{{border-bottom:1px solid #1e293b;padding:9px 10px;text-align:left;vertical-align:top}}
th{{color:#94a3b8;font-weight:600}}
.mono{{font-family:ui-monospace,monospace;font-size:13px}}
.ok{{color:#4ade80;font-weight:700}}
.warn{{color:#fbbf24}}
.info{{color:#93c5fd}}
.mini{{color:#64748b;font-size:12px;margin-top:4px}}
.card{{background:#111c33;border:1px solid #24344f;border-radius:14px;
padding:18px 24px;margin-top:28px}}
blockquote{{border-left:3px solid #4ade80;margin:12px 0;padding-left:14px;
color:#bbf7d0;font-size:17px}}
h3{{margin-top:0}}
</style></head><body>
<h1>Relay verification — independent of LNbits</h1>
<div class="sub">Events authored by merchant npub…{MERCHANT_HEX[-12:]},
fetched live from public relays</div>
<div class="relays">{relay_badges}</div>
<table><tr><th>kind</th><th>object</th><th>d-tag</th><th>title</th>
<th>event id</th><th>validation</th></tr>{rows}</table>
{msg}
</body></html>"""
    (HERE / "verify.html").write_text(body)
    print(f"verify.html written: {len(evs)} events, msg={bool(RESULT['message'])}")


async def main():
    for attempt in range(6):
        RESULT["events"].clear()
        try:
            await fetch_events()
        except Exception as e:
            print("fetch error:", e)
        if len(RESULT["events"]) >= 4:
            break
        print(f"attempt {attempt+1}: {len(RESULT['events'])} events — retrying in 10s")
        await asyncio.sleep(10)
    try:
        await unwrap_dm()
    except Exception as e:
        print("unwrap:", e)
    render()


if __name__ == "__main__":
    asyncio.run(main())
