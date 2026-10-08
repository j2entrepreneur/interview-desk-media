#!/usr/bin/env python3
"""Render a video-composite Reel: text card over a background video.

usage: render-video.py spec.json out.mp4 [options]

spec.json fields:
  text         (required) the card text
  handle       (optional) defaults to @iamjoshauld
  background   (required) path to background video file
  paneOpacity  (optional) dark pane opacity 0.0-1.0, default 0.55
  tint         (optional) darken the background 0.0-1.0, default 0.35

options:
  --duration N    how many seconds (default 10, capped to background length)
  --tint N        override background darkening (0.0=none, 1.0=black)
  --pane N        override dark pane opacity behind text

The engine:
1. Renders the text overlay as a transparent PNG via Playwright
2. Scales/crops the background video to 1080x1920
3. Applies a dark tint to the background
4. Composites the text overlay on top
5. Adds silent audio track for Instagram Reel compatibility
"""
import json
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
FPS = 30


def probe_duration(video_path):
    """Get video duration in seconds."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 10.0


def render(spec_path, out_path, duration=10, tint_override=None, pane_override=None):
    spec = json.loads(Path(spec_path).read_text())
    if not spec.get("text"):
        raise SystemExit("missing field: text")
    if not spec.get("background"):
        raise SystemExit("missing field: background")

    bg_path = Path(spec["background"])
    if not bg_path.exists():
        raise SystemExit(f"background video not found: {bg_path}")

    tint = tint_override if tint_override is not None else spec.get("tint", 0.35)
    pane_opacity = pane_override if pane_override is not None else spec.get("paneOpacity", 0.55)

    # Cap duration to background video length
    bg_duration = probe_duration(bg_path)
    duration = min(duration, bg_duration)

    # --- Step 1: Render text overlay as transparent PNG ---
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": 1080, "height": 1920},
            device_scale_factor=1,
        )
        page.goto((HERE / "video-card-template.html").as_uri())
        page.evaluate("document.fonts.ready")

        setup_data = {
            "text": spec["text"],
            "handle": spec.get("handle", "@iamjoshauld"),
            "paneOpacity": pane_opacity,
        }
        info = page.evaluate("d => window.setup(d)", setup_data)

        # Screenshot with transparency
        overlay_png = page.screenshot(type="png", omit_background=True)
        browser.close()

    # Write overlay to temp file
    overlay_path = Path(str(out_path) + ".overlay.png")
    overlay_path.write_bytes(overlay_png)

    # --- Step 2: Composite with ffmpeg ---
    # Build the filter:
    # 1. Scale/crop background to 1080x1920
    # 2. Apply dark tint (multiply with dark color)
    # 3. Overlay the text PNG on top
    darken = 1.0 - tint  # tint=0.35 means keep 65% brightness

    filter_complex = (
        # Scale background to cover 1080x1920, center crop
        f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=1080:1920,"
        # Apply tint/darken
        f"eq=brightness={-tint * 0.5}:contrast={darken + 0.1}:saturation=0.7,"
        f"format=yuva420p[bg];"
        # Load overlay
        f"[1:v]format=yuva420p[ovr];"
        # Composite
        f"[bg][ovr]overlay=0:0:format=auto,format=yuv420p[out]"
    )

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        # Input 0: background video
        "-i", str(bg_path),
        # Input 1: text overlay PNG
        "-loop", "1", "-framerate", str(FPS), "-i", str(overlay_path),
        # Silent audio
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        # Filter
        "-filter_complex", filter_complex,
        "-map", "[out]", "-map", "2:a",
        # Encode
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
        "-c:a", "aac", "-b:a", "128k",
        "-t", str(duration),
        "-movflags", "+faststart",
        "-shortest",
        str(out_path),
    ]

    ff = subprocess.run(cmd)
    overlay_path.unlink(missing_ok=True)

    if ff.returncode != 0:
        raise SystemExit(f"ffmpeg failed with exit code {ff.returncode}")

    print(f"OK  {out_path}  {duration:.1f}s  font {info['fontSize']}px  "
          f"{info['chars']} chars  tint={tint}  pane={pane_opacity}")
    return {"file": str(out_path), "duration": duration, **info}


if __name__ == "__main__":
    args = sys.argv[1:]

    duration = 10
    tint_override = None
    pane_override = None

    def pop_flag(name):
        if name in args:
            i = args.index(name)
            val = float(args[i + 1])
            del args[i:i + 2]
            return val
        return None

    duration = pop_flag("--duration") or 10
    duration = int(duration)
    tint_override = pop_flag("--tint")
    pane_override = pop_flag("--pane")

    render(args[0], args[1], duration, tint_override, pane_override)
