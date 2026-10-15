#!/usr/bin/env python3
"""Render a video-composite Reel: text card over a background video.

usage: render-video.py spec.json out.mp4 [options]

spec.json fields:
  text         (required) the card text
  handle       (optional) defaults to @iamjoshauld
  background   (required) path to background video file
  paneOpacity  (optional) dark pane opacity 0.0-1.0, default 0.55
  tint         (optional) darken the background 0.0-1.0, default 0 (none)

options:
  --duration N    override duration in seconds (default: auto from reading time
                  at 18.5 characters per second + 1.5s settle). Warns if
                  override is too short to read.
  --no-slow       never slow the background; cut the video at the clip's end.
                  By default a clip shorter than the reading time is slowed
                  down, but only where retime.py judges it will stay smooth
                  (max 1.5x; 60fps clips spread real frames; calm clips get
                  generated in-between frames; fast motion is refused).
  --tint N        override background darkening (0.0=none, 1.0=black)
  --pane N        override dark pane opacity behind text

The engine:
1. Renders the text overlay as a transparent PNG via Playwright
2. Scales/crops the background video to 1080x1920
3. Optionally tints the background (off by default)
4. Composites the text overlay on top
5. Adds silent audio track for Instagram Reel compatibility
"""
import json
import re
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from clip_path import resolve_background
import hook
import retime

HERE = Path(__file__).parent
FPS = 30
CPS = 18.5          # reading rate in characters per second (spaces included)
SETTLE = 1.5        # seconds for the eye to land before reading starts


def reading_duration(html_text):
    """Calculate how long a viewer needs to read the text at CPS rate.
    Strips HTML tags to count only readable characters."""
    readable = re.sub(r"<[^>]+>", "", html_text)
    return SETTLE + len(readable) / CPS


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


def render(spec_path, out_path, duration=None, tint_override=None, pane_override=None,
           allow_slow=True):
    spec = json.loads(Path(spec_path).read_text())
    if not spec.get("text"):
        raise SystemExit("missing field: text")
    if not spec.get("background"):
        raise SystemExit("missing field: background")

    try:
        bg_path = resolve_background(spec["background"])
    except FileNotFoundError as e:
        raise SystemExit(str(e))

    tint = tint_override if tint_override is not None else spec.get("tint", 0.0)
    pane_opacity = pane_override if pane_override is not None else spec.get("paneOpacity", 0.55)

    # Auto-duration from reading time at 18.5 cps. If the clip is too short,
    # retime.py decides whether it can be slowed down smoothly.
    read_time = reading_duration(spec["text"])
    hook_line = hook.resolve_hook(spec)
    if hook_line:
        read_time = hook.total_duration(read_time, hook_line, CPS)
        print(f"  hook: {hook_line!r} for {hook.HOOK_HOLD}s, then full card")
    bg_duration = probe_duration(bg_path)
    target = read_time if duration is None else duration

    slow = {"method": "none", "stretch": 1.0}
    if target > bg_duration and allow_slow:
        slow = retime.plan(bg_path, target)
        print(f"  background: {retime.describe(slow)}")
        if slow["method"] == "refuse":
            raise SystemExit(f"{bg_path.name}: {slow['reason']} "
                             f"(or pass --no-slow to cut the video short)")
    if slow["method"] in ("spread", "interpolate"):
        duration = min(target, bg_duration * slow["stretch"])
    else:
        duration = min(target, bg_duration)

    if duration < read_time:
        print(f"  WARNING: video {duration:.1f}s but text needs {read_time:.1f}s at {CPS} cps")

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

        hook_png = None
        if hook_line:
            page.evaluate("d => window.setup(d)", {**setup_data, "text": hook_line, "hook": True})
            hook_png = page.screenshot(type="png", omit_background=True)
        browser.close()

    # Write overlays to temp files
    overlay_path = Path(str(out_path) + ".overlay.png")
    overlay_path.write_bytes(overlay_png)
    hook_path = Path(str(out_path) + ".hook.png")
    if hook_png:
        hook_path.write_bytes(hook_png)

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
        # Slow motion, only when retime.plan chose it
        f"{retime.filters(slow)}"
        # Optional tint/darken (off by default since Oct 2026: the text pane
        # already gives contrast, and tinted reels looked too dark)
        + (f"eq=brightness={-tint * 0.5}:contrast={darken + 0.1}:saturation=0.7,"
           if tint > 0 else "") +
        f"format=yuva420p[bg];"
    )
    if hook_line:
        h, f = hook.HOOK_HOLD, hook.FADE
        filter_complex += (
            # Hook shows first, then crossfades into the full card
            f"[3:v]format=yuva420p,fade=t=out:st={h}:d={f}:alpha=1[hk];"
            f"[1:v]format=yuva420p,fade=t=in:st={h}:d={f}:alpha=1[ovr];"
            f"[bg][hk]overlay=0:0:format=auto[b1];"
            f"[b1][ovr]overlay=0:0:format=auto,format=yuv420p[out]"
        )
    else:
        filter_complex += (
            f"[1:v]format=yuva420p[ovr];"
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
        # Input 3 (hook-first only): hook overlay PNG
        *(["-loop", "1", "-framerate", str(FPS), "-i", str(hook_path)] if hook_line else []),
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
    hook_path.unlink(missing_ok=True)

    if ff.returncode != 0:
        raise SystemExit(f"ffmpeg failed with exit code {ff.returncode}")

    if slow["method"] in ("spread", "interpolate"):
        unevenness, frozen, ok = retime.check_smoothness(out_path)
        verdict = "smooth" if ok else "WARNING: may look jittery, review before posting"
        print(f"  smoothness: unevenness {unevenness}, frozen frames {frozen:.0%} -> {verdict}")

    readable_chars = len(re.sub(r"<[^>]+>", "", spec["text"]))
    print(f"OK  {out_path}  {duration:.1f}s  font {info['fontSize']}px  "
          f"{readable_chars} readable chars  {readable_chars / max(0.1, duration - SETTLE):.1f} cps "
          f"(target {CPS})  tint={tint}  pane={pane_opacity}")
    return {"file": str(out_path), "duration": duration, "read_time": read_time,
            "slow": slow, **info}


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

    duration = pop_flag("--duration")
    if duration is not None:
        duration = int(duration)
    tint_override = pop_flag("--tint")
    pane_override = pop_flag("--pane")
    allow_slow = "--no-slow" not in args
    if not allow_slow:
        args.remove("--no-slow")

    render(args[0], args[1], duration, tint_override, pane_override, allow_slow)
