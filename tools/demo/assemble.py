#!/usr/bin/env python3
"""Assemble the final demo mp4: main recording (trimmed), tail segment,
and a TTS narration track aligned to the on-screen captions."""

import asyncio
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
CUT = 199.4          # main video cut point (s) — before the old verify scene
VOICE = "en-GB-RyanNeural"

def ffprobe(path, field="duration"):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", f"format={field}",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True).stdout.strip()
    return float(out)


def narration():
    lines = []
    for ln in (HERE / "narration.log").read_text().splitlines():
        m = re.match(r"\s*([\d.]+)\s+(.*)", ln)
        if m:
            t, text = float(m.group(1)), m.group(2).strip()
            if t < CUT and not text.startswith("WARN"):
                lines.append({"t": t, "text": text})
    tail = json.loads((HERE / "narr_tail.json").read_text())
    for item in tail:
        lines.append({"t": round(CUT + item["t"], 2), "text": item["text"]})
    return lines


async def tts(lines):
    import edge_tts
    tts_dir = HERE / "tts"
    tts_dir.mkdir(exist_ok=True)
    for i, ln in enumerate(lines):
        out = tts_dir / f"{i:02d}.mp3"
        if out.exists() and out.stat().st_size > 0:
            continue
        c = edge_tts.Communicate(ln["text"], VOICE, rate="+0%")
        await c.save(str(out))
        ln["mp3"] = str(out)
        ln["dur"] = ffprobe(out)


def build_video():
    main = next(HERE.glob("video/page@*.webm"))
    tail = next(HERE.glob("video_tail/page@*.webm"))
    tmp = HERE / "video_joined.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-i", str(main), "-i", str(tail),
        "-filter_complex",
        f"[0:v]trim=0:{CUT},setpts=PTS-STARTPTS[v0];"
        "[1:v]setpts=PTS-STARTPTS[v1];"
        "[v0][v1]concat=n=2:v=1:a=0[v]",
        "-map", "[v]", "-c:v", "libx264", "-preset", "medium",
        "-crf", "20", "-pix_fmt", "yuv420p", "-r", "25",
        str(tmp)], check=True)
    return tmp


def build_audio(lines):
    # placement: each line at its timestamp, pushed forward if it would overlap
    placed = []
    prev_end = 0.0
    for ln in lines:
        start = max(ln["t"], prev_end + 0.35)
        placed.append({"start": start, "mp3": ln["mp3"], "text": ln["text"]})
        prev_end = start + ln["dur"]
    dur_total = prev_end + 1.0
    # ffmpeg: silence base + adelay each clip + amix
    parts = ["-f", "lavfi", "-i", f"anullsrc=r=48000:cl=mono:d={dur_total}"]
    for i, p in enumerate(placed):
        parts += ["-i", p["mp3"]]
    n = len(placed)
    mix = "".join(
        f"[{i+1}:a]adelay={int(p['start']*1000)}|{int(p['start']*1000)}[d{i}];"
        for i, p in enumerate(placed))
    mix += "[0:a]" + "".join(f"[d{i}]" for i in range(n)) + \
        f"amix=inputs={n+1}:normalize=0:dropout_transition=0[a]"
    out = HERE / "narration_audio.m4a"
    subprocess.run(["ffmpeg", "-y", "-v", "error", *parts,
                    "-filter_complex", mix, "-map", "[a]",
                    "-c:a", "aac", "-b:a", "160k", str(out)], check=True)
    return out, placed


def mux(video, audio):
    out = HERE / "infinitemarkets_demo.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(audio),
        "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
        "-shortest", str(out)], check=True)
    return out


async def main():
    lines = narration()
    print(f"{len(lines)} narration lines")
    await tts(lines)
    v = build_video()
    a, placed = build_audio(lines)
    final = mux(v, a)
    print("final:", final, f"{ffprobe(final):.1f}s")
    (HERE / "narration_final.json").write_text(json.dumps(placed, indent=1))
    for p in placed:
        print(f"  {p['start']:7.1f}s  {p['text'][:80]}")


asyncio.run(main())
