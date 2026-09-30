#!/usr/bin/env python3
"""Record the tail segment: relay-verification page + end card."""
import asyncio
import json
import time
from pathlib import Path
from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
LOG = (HERE / "narration_tail.log").open("w")
T0 = time.monotonic()
NARR = []

BANNER_JS = """
(() => {
  const d = document.createElement('div');
  d.id = '__narr';
  d.style.cssText = 'position:fixed;left:50%;bottom:24px;transform:translateX(-50%);'
    + 'max-width:1150px;background:rgba(10,10,20,.92);color:#fff;'
    + 'font:500 20px/1.45 system-ui,sans-serif;padding:14px 28px;'
    + 'border-radius:12px;z-index:2147483647;'
    + 'box-shadow:0 6px 30px rgba(0,0,0,.6);text-align:center;'
    + 'pointer-events:none;opacity:0;transition:opacity .35s;';
  document.body.appendChild(d);
})();
"""

async def narrate(page, text, pause=5.0):
    NARR.append({"t": round(time.monotonic() - T0, 2), "text": text})
    LOG.write(f"{time.monotonic()-T0:8.2f}  {text}\n"); LOG.flush()
    await page.evaluate("""(t)=>{const d=document.getElementById('__narr');
        if(d){d.textContent=t;d.style.opacity='1';}}""", text)
    await page.wait_for_timeout(int(pause * 1000))

async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        ctx = await b.new_context(
            viewport={"width": 1440, "height": 900},
            record_video_dir=str(HERE / "video_tail"),
            record_video_size={"width": 1440, "height": 900},
        )
        await ctx.add_init_script(BANNER_JS)
        page = await ctx.new_page()
        await page.goto(f"file://{HERE}/verify.html")
        await narrate(page, "Independent verification: these events were fetched "
                            "live from public relays — damus and nos.lol — "
                            "not from LNbits.", 6)
        await narrate(page, "Every listing is a valid NIP-99 event, signed by the "
                            "merchant key and retrievable by any Nostr client.", 5)
        await page.evaluate("window.scrollTo(0, 300)")
        await narrate(page, "And the buyer's order message — gift-wrapped end to end, "
                            "decryptable only by the customer's key.", 6)
        await page.goto(f"file://{HERE}/endcard.html")
        await narrate(page, "Infinite Markets — one authoritative inventory, "
                            "Lightning checkout, Nostr-native distribution.", 6)
        await ctx.close()
        await b.close()
    (HERE / "narr_tail.json").write_text(json.dumps(NARR))

asyncio.run(main())
