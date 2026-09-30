#!/usr/bin/env python3
"""Reshoot: product page -> nostr sign-in -> checkout -> invoice -> pay ->
order page -> admin Orders, with the 'My orders' panel CLOSED after sign-in
so it doesn't cover the checkout/invoice view.

Records into video_reshoot/ (1440x900) and writes reshoot_beats.json with
clip-relative timestamps so narration can be re-placed onto the splice.
"""

import asyncio
import json
import subprocess
import time
from pathlib import Path

from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
KEYS = json.loads((HERE / "keys.json").read_text())
SITE = "https://schedulerlnbits.exe.xyz"
EXT = SITE + "/infinitemarkets"
BASE = "http://localhost:5000"
PAYER_KEY = "be6f22c4c9e4427a9c99d5d29e70855f"
TOKEN = (HERE / "token_fresh.txt").read_text().strip()
MPUB = KEYS["merchant"]["hex"]
PRODUCT = f"{EXT}/p/{MPUB}/8ac4ffff390d405198d1a71c64647853"

BEATS = {}
T0 = None


def mark(name):
    BEATS[name] = round(time.monotonic() - T0, 2)
    print(f"  [{BEATS[name]:6.1f}s] {name}")


BANNER_JS = """
(() => {
  const inject = () => {
    if (document.getElementById('__narr')) return;
    const d = document.createElement('div');
    d.id = '__narr';
    d.style.cssText = 'position:fixed;left:50%;bottom:24px;transform:translateX(-50%);'
      + 'max-width:1150px;background:rgba(10,10,20,.92);color:#fff;'
      + 'font:500 20px/1.45 system-ui,sans-serif;padding:14px 28px;'
      + 'border-radius:12px;z-index:2147483647;'
      + 'box-shadow:0 6px 30px rgba(0,0,0,.6);text-align:center;'
      + 'pointer-events:none;opacity:0;transition:opacity .35s;';
    document.body.appendChild(d);
  };
  if (document.body) inject();
  else document.addEventListener('DOMContentLoaded', inject);
})();
"""

NOSTR_STUB_JS = """
window.nostr = {
  getPublicKey: async () => '__CUST_HEX__',
  signEvent: async (ev) => JSON.parse(await window.__pySign(JSON.stringify(ev)))
};
""".replace("__CUST_HEX__", KEYS["customer"]["hex"])


def pysign(event_json):
    from nostr_sdk import EventBuilder, Kind, Tag, Timestamp, Keys

    ev = json.loads(event_json)
    keys = Keys.parse(KEYS["customer"]["nsec"])
    b = EventBuilder(Kind(int(ev["kind"])), ev.get("content", ""))
    tags = ev.get("tags") or []
    if tags:
        b = b.tags([Tag.parse(t) for t in tags])
    if ev.get("created_at"):
        b = b.custom_created_at(Timestamp.from_secs(int(ev["created_at"])))
    return b.finalize_unsigned(keys.public_key()).sign(keys).as_json()


def pay_invoice(bolt11):
    r = subprocess.run(
        [
            "curl", "-s", "--max-time", "60", "-X", "POST",
            f"{BASE}/api/v1/payments",
            "-H", f"X-Api-Key: {PAYER_KEY}",
            "-H", "Content-Type: application/json",
            "-d", json.dumps({"out": True, "bolt11": bolt11}),
        ],
        capture_output=True, text=True,
    )
    print("payment response:", r.stdout[:300])
    return r.stdout


async def caption(page, text):
    try:
        await page.evaluate(
            """(t)=>{const d=document.getElementById('__narr');
            if(d){d.textContent=t;d.style.opacity='1';}}""",
            text,
        )
    except Exception:
        pass


async def close_orders_panel(page):
    """Toggle the 'My orders' nav button if the orders panel is open."""
    try:
        hidden = await page.evaluate(
            "(()=>{const p=document.getElementById('gm-nostr-panel');"
            "return p ? p.hidden : true;})()"
        )
        if not hidden:
            await page.locator("#gm-nostr-signin").click()
            await page.wait_for_timeout(600)
            print("   (orders panel closed)")
            return True
    except Exception as e:
        print("   close panel err:", e)
    return False


async def main():
    global T0
    async with async_playwright() as pw:
        b = await pw.chromium.launch(
            args=["--disable-blink-features=AutomationControlled"]
        )
        ctx = await b.new_context(
            viewport={"width": 1440, "height": 900},
            record_video_dir=str(HERE / "video_reshoot"),
            record_video_size={"width": 1440, "height": 900},
            ignore_https_errors=True,
        )
        await ctx.add_cookies([{
            "name": "cookie_access_token",
            "value": TOKEN,
            "domain": "schedulerlnbits.exe.xyz",
            "path": "/",
        }])
        await ctx.expose_function("__pySign", pysign)
        await ctx.add_init_script(BANNER_JS)
        await ctx.add_init_script(NOSTR_STUB_JS)
        page = await ctx.new_page()

        invoice = {"bolt11": None}

        async def capture(resp):
            if "/checkout" in resp.url and resp.request.method == "POST":
                try:
                    body = json.loads(await resp.text())
                    for k in ("bolt11", "payment_request"):
                        if body.get(k):
                            invoice["bolt11"] = body[k]
                    for k in ("order", "invoice", "payment"):
                        sub = body.get(k) or {}
                        for kk in ("bolt11", "payment_request"):
                            if sub.get(kk):
                                invoice["bolt11"] = sub[kk]
                except Exception as exc:
                    print("capture error:", exc)
        page.on("response", lambda r: asyncio.ensure_future(capture(r)))

        # ---- product page ------------------------------------------------
        await page.goto(PRODUCT, wait_until="networkidle")
        T0 = time.monotonic()
        await caption(page, "The buyer can sign in with Nostr — the extension "
                            "challenges and verifies the signature.")
        mark("beat_signin_caption")
        await page.wait_for_timeout(1500)

        # ---- sign in ------------------------------------------------------
        await page.locator("#gm-nostr-signin").click()
        mark("beat_signin_click")
        try:
            await page.wait_for_selector(
                "[data-gm='nostr-signed-in']", timeout=15000)
        except Exception:
            print("WARN: signed-in panel not seen")
        await page.wait_for_timeout(500)
        mark("beat_signedin")
        await caption(page, f"Signed in as {KEYS['customer']['npub'][:26]}\u2026 \u2014 "
                            "orders now bind to this buyer identity.")
        await page.wait_for_timeout(3500)

        # ---- close the orders panel (the fix) -----------------------------
        await close_orders_panel(page)
        mark("beat_panel_closed")
        await page.wait_for_timeout(1200)

        # ---- checkout ------------------------------------------------------
        email_in = page.locator("#gm-email")
        if await email_in.count():
            await email_in.scroll_into_view_if_needed()
            await page.wait_for_timeout(400)
            await email_in.fill("buyer@example.com")
        await caption(page, "The buyer checks out with an email for order updates \u2014 "
                            "no account needed.")
        mark("beat_email")
        await page.wait_for_timeout(2000)
        await page.get_by_role("button", name="Review payment").click()
        mark("beat_review_click")
        await page.wait_for_timeout(3000)
        await close_orders_panel(page)
        await caption(page, "A Lightning invoice is created for the exact total.")
        mark("beat_invoice")
        # wait for bolt11 capture
        for _ in range(14):
            if invoice["bolt11"]:
                break
            await page.wait_for_timeout(500)
        await page.wait_for_timeout(2000)

        # ---- pay -----------------------------------------------------------
        await caption(page, "Scan or open in wallet \u2014 now paying it from a "
                            "second LNbits wallet.")
        mark("beat_pay")
        await page.wait_for_timeout(1000)
        if invoice["bolt11"]:
            pay_invoice(invoice["bolt11"])
        else:
            print("WARN: bolt11 not captured")
        try:
            await page.wait_for_selector(
                "text=/confirmed|paid|settled|complete|receipt|order page/i",
                timeout=45000)
        except Exception:
            pass
        mark("beat_settled")
        await caption(page, "Payment settled \u2014 the order is confirmed and the "
                            "digital item is delivered on the buyer's private order page.")
        await page.wait_for_timeout(4500)

        # ---- private order page --------------------------------------------
        order_link = page.locator("a", has_text="order").first
        if await order_link.count():
            try:
                href = await order_link.get_attribute("href")
                if href and "/order" in href:
                    await page.goto(SITE + href if href.startswith("/") else href)
                    await page.wait_for_timeout(2000)
            except Exception:
                pass
        await close_orders_panel(page)
        await caption(page, "The private order page \u2014 status, delivery content, "
                            "and message thread.")
        mark("beat_orderpage")
        await page.wait_for_timeout(3500)

        # ---- admin orders workspace ----------------------------------------
        await page.goto(EXT + "/", wait_until="networkidle")
        await page.click('[data-gm-nav="orders"]')
        await page.wait_for_timeout(2500)
        mark("beat_admin")
        await caption(page, "Back in the merchant workspace \u2014 the paid order is "
                            "in the queue.")
        await page.wait_for_timeout(3000)
        mark("end")

        await ctx.close()
        await b.close()

    (HERE / "reshoot_beats.json").write_text(json.dumps(BEATS, indent=1))
    print("beats:", BEATS)


asyncio.run(main())
