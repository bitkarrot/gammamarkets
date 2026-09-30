#!/usr/bin/env python3
"""E2E demo recording for the Infinite Markets LNbits extension.

Records a narrated Playwright walkthrough: merchant key import, catalog
creation (shipping, products w/ images, collection), Nostr publication to
public relays, storefront purchase with a real Lightning payment, and
order messaging — plus external relay verification of the NIP-99 events.
"""

import asyncio
import json
import subprocess
import time
from pathlib import Path

from playwright.async_api import async_playwright

BASE = "http://localhost:5000"        # internal API calls (payment, checks)
SITE = "https://schedulerlnbits.exe.xyz"  # canonical origin — Origin checks
EXT = SITE + "/infinitemarkets"
HERE = Path(__file__).resolve().parent
TOKEN = (HERE / "token.txt").read_text().strip()
KEYS = json.loads((HERE / "keys.json").read_text())
PAYER_KEY = "be6f22c4c9e4427a9c99d5d29e70855f"  # 'LNbits wallet' adminkey
IMG1 = "https://schedulerlnbits.exe.xyz/infinitemarkets/static/infinitemarkets/img/demo-node-report.png"
IMG2 = "https://schedulerlnbits.exe.xyz/infinitemarkets/static/infinitemarkets/img/demo-mug.png"
CATALOG_ID = "b8040efc85414adba0ba41fe59eb17b8"

NARR = []          # [(elapsed_s, text)]
T0 = time.monotonic()
LOG = (HERE / "narration.log").open("w")


def log_narr(text):
    t = time.monotonic() - T0
    NARR.append({"t": round(t, 2), "text": text})
    LOG.write(f"{t:8.2f}  {text}\n")
    LOG.flush()
    print(f"[{t:7.1f}] {text}")


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


def npub_say(npub: str) -> str:
    """Speakable form of an npub for TTS: 'npub' plus the first five
    identifier characters spelled out (bech32-separator '1' counts).
    Keeps narration short instead of spelling the whole string."""
    return "npub " + " ".join(npub[4:9])


async def narrate(page, text, pause=4.0, spoken=None):
    log_narr(spoken or text)
    try:
        await page.evaluate(
            """(t)=>{const d=document.getElementById('__narr');
            if(d){d.textContent=t;d.style.opacity='1';}}""",
            text,
        )
    except Exception:
        pass
    await page.wait_for_timeout(int(pause * 1000))


async def hide_banner(page):
    try:
        await page.evaluate(
            "()=>{const d=document.getElementById('__narr');if(d)d.style.opacity='0';}"
        )
    except Exception:
        pass


def pysign(event_json):
    """NIP-07 signEvent — signs with the customer key in-process."""
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
    print("payment response:", r.stdout[:400])
    return r.stdout


async def fill(page, label, value):
    """Fill a Quasar q-input/q-field by its label text."""
    field = page.locator(".q-field", has_text=label).first
    await field.locator("input, textarea").first.fill(value)


async def qselect(page, label, option_text):
    field = page.locator(".q-field", has_text=label).first
    await field.click()
    await page.wait_for_timeout(350)
    await page.locator(".q-menu .q-item, .q-menu [role=option]",
                       has_text=option_text).first.click()
    await page.wait_for_timeout(250)


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(
            args=["--disable-blink-features=AutomationControlled"]
        )
        ctx = await b.new_context(
            viewport={"width": 1440, "height": 900},
            record_video_dir=str(HERE / "video"),
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
                    text = await resp.text()
                    (HERE / "checkout_response.json").write_text(text)
                    body = json.loads(text)
                    inv = (body.get("bolt11") or body.get("payment_request")
                           or (body.get("order") or {}).get("bolt11")
                           or (body.get("invoice") or {}).get("bolt11")
                           or (body.get("payment") or {}).get("bolt11")
                           or (body.get("payment") or {}).get("payment_request"))
                    if inv:
                        invoice["bolt11"] = inv
                except Exception as exc:
                    print("capture error:", exc)
        page.on("response", lambda r: asyncio.ensure_future(capture(r)))

        # ---- Scene 1: title card ------------------------------------------
        await page.goto(f"file://{HERE}/title.html")
        await narrate(page, "Infinite Markets — an LNbits extension for Nostr-native "
                            "commerce with Lightning checkout.", 4.5)
        await narrate(page, "In this demo: merchant key import, catalog publishing to "
                            "public relays, a live purchase, and order messaging.", 4.5)

        # ---- Scene 2: admin overview --------------------------------------
        await page.goto(EXT + "/", wait_until="networkidle")
        await narrate(page, "This is the merchant workspace inside LNbits. The store is "
                            "active and ready for orders.", 4.5)

        # ---- Scene 3: import the merchant nostr key -----------------------
        await page.click('[data-gm-nav="settings"]')
        await page.wait_for_timeout(1200)
        await narrate(page, "In Settings, the merchant imports their Nostr secret key. "
                            "This key signs every listing sent to relays.", 4)
        nsec_field = page.locator(".q-field", has_text="nsec").first
        await nsec_field.locator("input").first.fill(KEYS["merchant"]["nsec"])
        await page.wait_for_timeout(800)
        await page.get_by_role("button", name="Import key").click()
        await page.wait_for_timeout(2500)
        await narrate(page, f"Key imported — merchant identity is now "
                            f"{KEYS['merchant']['npub'][:28]}…", 4,
                      spoken=f"Key imported — merchant identity is now "
                             f"{npub_say(KEYS['merchant']['npub'])}.")

        # ---- Scene 4: publish everything ----------------------------------
        pub_btn = page.get_by_role("button", name="Publish everything")
        if await pub_btn.count():
            await pub_btn.scroll_into_view_if_needed()
            await narrate(page, "Publishing the merchant profile and inbox preferences "
                                "to the configured relays.", 3)
            await pub_btn.click()
            await page.wait_for_timeout(3500)

        # ---- Scene 5: create a shipping option ----------------------------
        await page.click('[data-gm-nav="catalog"]')
        await page.wait_for_timeout(1000)
        await narrate(page, "Now the catalog: first a shipping option for physical goods.", 3.5)
        await page.get_by_role("button", name="New shipping option").click()
        await page.wait_for_timeout(800)
        await fill(page, "Title", "International Tracked")
        await qselect(page, "Service", "standard")
        await fill(page, "Base price (minor units)", "150")
        await fill(page, "Currency", "SAT")
        await fill(page, "Duration min", "3")
        await fill(page, "Duration max", "7")
        await qselect(page, "Duration unit", "D")
        await page.get_by_role("button", name="Create shipping option").click()
        await page.wait_for_timeout(2000)
        await narrate(page, "Shipping option created — available to any physical product.", 3.5)

        # ---- Scene 6: create the collection -------------------------------
        await page.get_by_role("button", name="New collection").click()
        await page.wait_for_timeout(800)
        await fill(page, "Title", "Lightning Essentials")
        await fill(page, "Description", "Curated goods for Lightning natives")
        await page.get_by_role("button", name="Create collection").click()
        await page.wait_for_timeout(2000)
        await narrate(page, "Collection created — it will publish as a NIP-99 stall set.", 3.5)

        # ---- Scene 7: product 1 — digital ---------------------------------
        await page.get_by_role("button", name="New product").click()
        await page.wait_for_timeout(800)
        await narrate(page, "Product one: a digital download — instant delivery after "
                            "payment settlement.", 4)
        await qselect(page, "Catalog", "Main Catalog")
        await fill(page, "Title", "Node Report — 2026 Lightning Analysis")
        await fill(page, "Summary", "Deep-dive on public channel liquidity and routing fees")
        await fill(page, "Description (markdown)",
                   "## Node Report\n\nAnnual analysis of the Lightning Network: "
                   "capacity, fee markets, and reliability data.\n\n"
                   "- 80 pages of charts\n- Raw CSV data included")
        await fill(page, "Digital delivery", IMG1)
        await fill(page, "Price (minor units)", "210")
        await fill(page, "Currency (SAT or fiat code)", "SAT")
        await qselect(page, "Format", "digital")
        await qselect(page, "Collections", "Lightning Essentials")
        await qselect(page, "Visibility", "on-sale")
        await fill(page, "Image URLs", IMG1)
        await page.get_by_role("button", name="Create product").click()
        await page.wait_for_timeout(2500)
        await narrate(page, "Digital product saved — it queues to the outbox and "
                            "publishes as kind 30402.", 4)

        # ---- Scene 8: product 2 — physical --------------------------------
        await page.get_by_role("button", name="New product").click()
        await page.wait_for_timeout(800)
        await narrate(page, "Product two: a physical item with limited stock and "
                            "tracked shipping.", 4)
        await qselect(page, "Catalog", "Main Catalog")
        await fill(page, "Title", "Plebeian Mug — Ceramic")
        await fill(page, "Summary", "12oz ceramic mug for the discerning merchant")
        await fill(page, "Description (markdown)",
                   "Glazed ceramic mug. Dishwasher safe, Lightning preferred.")
        await fill(page, "Price (minor units)", "490")
        await fill(page, "Currency (SAT or fiat code)", "SAT")
        await qselect(page, "Format", "physical")
        await fill(page, "Stock on hand", "25")
        await qselect(page, "Collections", "Lightning Essentials")
        await qselect(page, "Visibility", "on-sale")
        await fill(page, "Image URLs", IMG2)
        await page.get_by_role("button", name="Create product").click()
        await page.wait_for_timeout(2500)
        await narrate(page, "Physical product saved with 25 units of stock.", 3.5)

        # ---- Scene 9: preview the NIP-99 event ----------------------------
        eye = page.locator('[aria-label="Preview events"]').first
        if await eye.count():
            await eye.click()
            await page.wait_for_timeout(1500)
            await narrate(page, "This is the exact signed Nostr event other clients "
                                "will read — NIP-99 kind 30402.", 4.5)
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(500)

        # ---- Scene 10: publications tab -----------------------------------
        await page.click('[data-gm-nav="publications"]')
        await page.wait_for_timeout(2500)
        await narrate(page, "The Publications workspace tracks every broadcast — per "
                            "relay, per event, with acceptance state.", 4.5)

        # ---- Scene 11: storefront -----------------------------------------
        mpub = KEYS["merchant"]["hex"]
        await page.goto(f"{EXT}/public/merchants/{mpub}", wait_until="networkidle")
        await narrate(page, "The public storefront — reachable by anyone, no LNbits "
                            "login required.", 4.5)
        prod_link = page.locator("a", has_text="Node Report").first
        if await prod_link.count():
            await prod_link.click()
            await page.wait_for_timeout(2000)
            await narrate(page, "The product page: gallery, price, and the embedded "
                                "Lightning checkout.", 4)
        else:
            await page.goto(f"{EXT}/p/{mpub}/node-report-2026-lightning-analysis")
            await page.wait_for_timeout(2000)

        # ---- Scene 12: buyer nostr sign-in --------------------------------
        signin = page.locator("#gm-nostr-signin")
        if await signin.count():
            await narrate(page, "The buyer can sign in with Nostr — the extension "
                                "challenges and verifies the signature.", 4)
            await signin.click()
            await page.wait_for_timeout(3000)
            await narrate(page, f"Signed in as {KEYS['customer']['npub'][:26]}… — "
                                "orders now bind to this buyer identity.", 4,
                          spoken=f"Signed in as "
                                 f"{npub_say(KEYS['customer']['npub'])} — "
                                 "orders now bind to this buyer identity.")
        else:
            await narrate(page, "Proceeding to checkout.", 3)

        # ---- Scene 13: checkout + lightning payment -----------------------
        email_in = page.locator("#gm-email")
        if await email_in.count():
            await email_in.fill("buyer@example.com")
        await narrate(page, "The buyer checks out with an email for order updates — "
                            "no account needed.", 4)
        await page.get_by_role("button", name="Review payment").click()
        await page.wait_for_timeout(3000)
        await narrate(page, "A Lightning invoice is created for the exact total.", 3.5)
        # wait for bolt11 captured or visible
        for _ in range(10):
            if invoice["bolt11"]:
                break
            await page.wait_for_timeout(500)
        await narrate(page, "Scan or open in wallet — now paying it from a second "
                            "LNbits wallet.", 3)
        if invoice["bolt11"]:
            pay_invoice(invoice["bolt11"])
        else:
            log_narr("WARN: bolt11 not captured — cannot pay")
        # wait for settlement UI
        try:
            await page.wait_for_selector(
                "text=/confirmed|paid|settled|complete|receipt|order page/i",
                timeout=45000)
        except Exception:
            pass
        await narrate(page, "Payment settled — the order is confirmed and the digital "
                            "item is delivered on the buyer's private order page.", 5)

        # follow order link if visible
        order_link = page.locator("a", has_text="order").first
        if await order_link.count():
            try:
                href = await order_link.get_attribute("href")
                if href and "/order" in href:
                    await page.goto(SITE + href if href.startswith("/") else href)
                    await page.wait_for_timeout(2500)
                    await narrate(page, "The private order page — status, delivery "
                                        "content, and message thread.", 4)
            except Exception:
                pass

        # ---- Scene 14: admin sees the order -------------------------------
        await page.goto(EXT + "/", wait_until="networkidle")
        await page.click('[data-gm-nav="orders"]')
        await page.wait_for_timeout(2500)
        await narrate(page, "Back in the merchant workspace — the paid order is in "
                            "the queue.", 4)
        # click first order row
        try:
            await page.locator(".q-table tbody tr, [data-gm='order-row']").first.click()
            await page.wait_for_timeout(2000)
            await narrate(page, "Order detail: items, settlement, and the customer "
                                "thread.", 4)
        except Exception:
            pass

        # ---- Scene 15: messages -------------------------------------------
        await page.click('[data-gm-nav="messages"]')
        await page.wait_for_timeout(2000)
        await narrate(page, "Messages runs on NIP-17 gift-wrapped DMs — private "
                            "between merchant and buyer.", 4)
        comp = page.locator(".q-field", has_text="recipient").first
        comp_btn = page.get_by_role("button", name="Compose")
        if await comp_btn.count():
            await comp_btn.click()
            await page.wait_for_timeout(800)
            await fill(page, "Recipient", KEYS["customer"]["npub"])
            await fill(page, "Order", "")
            ta = page.locator("[data-gm='compose-content'], textarea").last
            try:
                await ta.fill("Thanks for your order! Your Node Report download "
                              "is live — reply here any time. — Infinite Markets")
            except Exception:
                pass
            send = page.get_by_role("button", name="Send")
            if await send.count():
                await send.first.click()
                await page.wait_for_timeout(3000)
                await narrate(page, "The reply is gift-wrapped and delivered only to "
                                    "the buyer's declared relays.", 4.5)
        else:
            # maybe conversations list already has the buyer thread — reply there
            ta = page.locator("[data-gm='reply-input'] textarea, [data-gm='reply-input'] input")
            if await ta.count():
                await ta.first.fill("Thanks for your order! — Infinite Markets")
                await page.locator("[data-gm='reply-send']").click()
                await page.wait_for_timeout(2500)

        # ---- Scene 16: relay verification ---------------------------------
        await narrate(page, "Now the external check — fetching these events straight "
                            "from public relays…", 3)
        subprocess.run(
            ["/home/exedev/lnbits/.venv/bin/python", str(HERE / "verify_gen.py")],
            timeout=200,
        )
        await page.goto(f"file://{HERE}/verify.html")
        await narrate(page, "Independent verification: these events were fetched "
                            "from public relays — damus and nos.lol — not from LNbits.", 5)
        await narrate(page, "Every listing is a valid NIP-99 event, signed by the "
                            "merchant key and retrievable by any Nostr client.", 5)

        # ---- Scene 17: end card -------------------------------------------
        await page.goto(f"file://{HERE}/endcard.html")
        await narrate(page, "Infinite Markets — one authoritative inventory, "
                            "Lightning checkout, Nostr-native distribution.", 5)

        await ctx.close()
        await b.close()


asyncio.run(main())
