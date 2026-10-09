#!/usr/bin/env python3
"""Render single-frame previews: text card composited over one frame of background video.

usage: render-preview.py specs.json [outdir]

For each card spec, this script:
1. Extracts one frame from the background video (at 2s or midpoint)
2. Renders the text overlay as a transparent PNG via Playwright
3. Composites the two into a still 1080x1920 preview PNG

This is much cheaper than full video renders and lets you catch
layout or readability issues before committing to video.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
CPS = 18.5
SETTLE = 1.5


def reading_duration(html_text):
    """Calculate how long a viewer needs to read the text at CPS rate."""
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


def extract_frame(video_path, out_path, seek=2.0):
    """Extract a single frame from a video at the given time."""
    duration = probe_duration(video_path)
    # If video is shorter than seek time, grab from midpoint
    if seek >= duration:
        seek = duration / 2

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", str(seek),
        "-i", str(video_path),
        "-frames:v", "1",
        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
        str(out_path),
    ]
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg frame extraction failed for {video_path}")
    return out_path


def render_text_overlay(text, handle="@iamjoshauld", pane_opacity=0.55):
    """Render text as a transparent PNG overlay using Playwright."""
    template = HERE / "video-card-template.html"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": 1080, "height": 1920},
            device_scale_factor=1,
        )
        page.goto(template.as_uri())
        page.evaluate("document.fonts.ready")

        setup_data = {
            "text": text,
            "handle": handle,
            "paneOpacity": pane_opacity,
        }
        info = page.evaluate("d => window.setup(d)", setup_data)
        overlay_bytes = page.screenshot(type="png", omit_background=True)
        browser.close()

    return overlay_bytes, info


def composite_preview(frame_path, overlay_bytes, out_path, tint=0.35):
    """Composite text overlay onto extracted frame with tinting."""
    # Write overlay to temp file
    overlay_path = Path(str(out_path) + ".overlay.png")
    overlay_path.write_bytes(overlay_bytes)

    darken = 1.0 - tint

    filter_complex = (
        f"[0:v]eq=brightness={-tint * 0.5}:contrast={darken + 0.1}:saturation=0.7,"
        f"format=yuva420p[bg];"
        f"[1:v]format=yuva420p[ovr];"
        f"[bg][ovr]overlay=0:0:format=auto,format=yuv420p[out]"
    )

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(frame_path),
        "-i", str(overlay_path),
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-frames:v", "1",
        str(out_path),
    ]
    r = subprocess.run(cmd)
    overlay_path.unlink(missing_ok=True)

    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg composite failed for {out_path}")


def render_preview(spec, out_dir):
    """Render a single preview from a card spec dict."""
    card_id = spec["id"]
    text = spec["text"]
    bg_path = spec["background"]

    # Calculate reading time
    readable = re.sub(r"<[^>]+>", "", text)
    read_time = reading_duration(text)
    char_count = len(readable)

    # Check background exists
    if not Path(bg_path).exists():
        print(f"  SKIP {card_id}: background not found: {bg_path}")
        return None

    bg_duration = probe_duration(bg_path)

    # Duration warning
    warning = ""
    if read_time > bg_duration:
        warning = f" WARNING: needs {read_time:.1f}s but clip is {bg_duration:.1f}s"

    print(f"\n--- {card_id} ({spec['type']}, {spec['voice']}) ---")
    print(f"  chars: {char_count}  read_time: {read_time:.1f}s  clip: {bg_duration:.1f}s{warning}")

    # Step 1: Extract frame
    frame_path = Path(out_dir) / f"{card_id}.frame.png"
    extract_frame(bg_path, frame_path)

    # Step 2: Render text overlay
    overlay_bytes, info = render_text_overlay(text)
    print(f"  font: {info['fontSize']}px")

    # Step 3: Composite
    preview_path = Path(out_dir) / f"{card_id}.png"
    composite_preview(frame_path, overlay_bytes, preview_path)

    # Clean up frame
    frame_path.unlink(missing_ok=True)

    print(f"  OK  {preview_path}")
    return {
        "id": card_id,
        "file": str(preview_path),
        "read_time": round(read_time, 1),
        "char_count": char_count,
        "bg_duration": round(bg_duration, 1),
        "font_size": info["fontSize"],
        "warning": warning.strip() if warning else None,
    }


def main():
    specs_path = sys.argv[1] if len(sys.argv) > 1 else "batch3-specs.json"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "batch3-previews"

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    specs = json.loads(Path(specs_path).read_text())

    results = []
    for spec in specs:
        result = render_preview(spec, out_dir)
        if result:
            results.append(result)

    print("\n\n=== SUMMARY ===")
    print(f"{'ID':<30} {'Type':<12} {'Chars':>5} {'Read':>6} {'Clip':>6} {'Font':>5} {'Status'}")
    print("-" * 95)
    for i, (spec, res) in enumerate(zip(specs, results)):
        status = "WARNING" if res.get("warning") else "OK"
        print(f"{res['id']:<30} {spec['type']:<12} {res['char_count']:>5} "
              f"{res['read_time']:>5.1f}s {res['bg_duration']:>5.1f}s "
              f"{res['font_size']:>4}px {status}")

    # Write results
    results_path = Path(out_dir) / "results.json"
    results_path.write_text(json.dumps(results, indent=2))
    print(f"\nResults written to {results_path}")


if __name__ == "__main__":
    main()
