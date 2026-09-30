# Demo pipeline

Playwright + edge-tts pipeline that produces the narrated end-to-end demo
video (`docs/assets/infinitemarkets_demo.mp4`). Records real interactions
against a live host — merchant workspace, relay publishing, a paid
Lightning purchase, and NIP-17 order messaging.

## Setup

```bash
python -m venv .venv && .venv/bin/pip install playwright edge-tts nostr-sdk
.venv/bin/playwright install chromium
```

Copy `keys.example.json` → `keys.json` and fill in a merchant and a
customer keypair (`nsec`/`npub`/`hex`). The merchant key must be imported
into the target merchant account; the customer key becomes the buyer
identity.

`token.txt` (and `token_fresh.txt` for reshoots) must contain a valid
`cookie_access_token` JWT for the admin workspace scenes.

Set `SITE`/`EXT`/`BASE` at the top of the scripts for your host.

## Pipeline

```bash
python demo.py        # full walkthrough -> video/*.webm + narration.log
python demo_tail.py   # external-verification + end-card scenes -> video_tail/
python assemble.py    # joins footage, synthesizes tts/*.mp3, muxes final mp4
python reshoot.py     # checkout-section re-record -> video_reshoot/
python verify_gen.py  # rebuilds verify.html from live relay fetches
```

`assemble.py` skips TTS clips that already exist in `tts/` — delete a clip
to regenerate it. `reshoot.py` writes `reshoot_beats.json` (clip-relative
beat times) used to re-place narration onto a splice.

Secrets and generated artifacts are excluded via `.gitignore`.
