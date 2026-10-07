#!/usr/bin/env python3
"""Render a still-card Reel (1080x1920 MP4) from a JSON spec.

usage: render-still.py spec.json out.mp4 [--duration 8]

spec.json fields:
  text     (required) the card text
  handle   (optional) defaults to @iamjoshauld

--duration  how many seconds the card stays on screen (default 8)

The card is a static image held for the duration, with a silent audio track
so Instagram treats it as a Reel.
"""
import json
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
FPS = 30


def render(spec_path, out_path, duration=8):
    spec = json.loads(Path(spec_path).read_text())
    if not spec.get("text"):
        raise SystemExit("missing field: text")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": 1080, "height": 1920},
            device_scale_factor=1,
        )
        page.goto((HERE / "still-card-template.html").as_uri())
        page.evaluate("document.fonts.ready")
        info = page.evaluate("d => window.setup(d)", spec)

        # Grab a single frame as PNG
        frame_png = page.screenshot(type="png")
        browser.close()

    # Use ffmpeg to hold the still frame for the duration, with silent audio
    ff = subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            # Loop the single image
            "-loop", "1", "-framerate", str(FPS),
            "-f", "image2pipe", "-c:v", "png", "-i", "-",
            # Silent audio
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            # Encode
            "-c:v", "libx264", "-preset", "medium", "-crf", "17",
            "-pix_fmt", "yuv420p",
            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
            "-c:a", "aac", "-b:a", "128k",
            "-t", str(duration),
            "-movflags", "+faststart",
            str(out_path),
        ],
        input=frame_png,
    )
    if ff.returncode != 0:
        raise SystemExit(f"ffmpeg failed with exit code {ff.returncode}")

    print(f"OK  {out_path}  {duration}s  font {info['fontSize']}px  {info['chars']} chars")
    return {"file": str(out_path), "duration": duration, **info}


if __name__ == "__main__":
    args = sys.argv[1:]

    duration = 8
    if "--duration" in args:
        i = args.index("--duration")
        duration = int(args[i + 1])
        del args[i:i + 2]

    render(args[0], args[1], duration)
