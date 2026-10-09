#!/usr/bin/env python3
"""Sync background videos from Google Drive to local backgrounds/ folder.

This script is meant to be run by Claude at the start of a session.
It reads the Drive folder, compares against backgrounds.json, and
reports what needs downloading. Claude then downloads new clips via
the Google Drive MCP tools and probes them for metadata.

Usage (by Claude, not standalone):
  1. Read the Drive folder listing
  2. Compare against backgrounds.json
  3. Download any new clips
  4. Probe duration/resolution
  5. Update backgrounds.json with new entries

Drive folder ID: 1zpdUqNIsYSrqj2tzkXNcETkYVO9HgjWk
Folder name: iamjoshauld-backgrounds
"""

import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
BG_DIR = HERE / "backgrounds"
BG_JSON = BG_DIR / "backgrounds.json"

# Mapping from long Envato filenames to clean short names
# Add new mappings here when new clips arrive
FILENAME_MAP = {
    "abstract-vertical-light-motion-background-with-tex": "abstract-light-motion",
    "abstract-vertical-space-nebula-background-animatio": "abstract-space-nebula",
    "aerial-view-of-waves-crashing-on-dark-beach": "aerial-waves-dark-beach",
    "aerial-waves-on-dark-sand-beach": "aerial-waves-dark-sand",
    "vertical-view-of-beautiful-mountain-hills-in-bali": "bali-mountain-hills",
    "brilliant-campfire-flames-illuminate-the-night": "campfire-flames",
    "cinematic-vertical-planet-view-with-drifting-cosmi": "cinematic-planet-cosmic",
    "dark-bookshelf-next-to-bed-with-decorations": "dark-bookshelf-bed",
    "dark-fluid-water-waves-seamless-loop-motion-backgr": "dark-fluid-water-waves",
    "dark-grunge-wood-texture-with-dynamic-spotlight-an": "dark-grunge-spotlight",
    "vertical-view-of-beautiful-mountains-hill-with-lan": "mountains-landscape",
    "mountain-peak-obscured-by-heavy-clouds": "mountain-peak-clouds",
    "nighttime-cityscape-people-walking-along-river": "nighttime-cityscape-river",
    "orange-sunset-over-lake-with-mountains-in-distance": "orange-sunset-lake",
    "slow-motion-dark-textured-surface-background": "slow-dark-texture",
    "white-smoke-rising-fluid-abstract-animation": "white-smoke-abstract",
    "abstract-dark-organic-textured-background-motion": "abstract-dark-organic",
    "storm-clouds-rolling-over-a-green-field": "storm-clouds-field",
    "vertical-milky-way-night-sky-over-snowy-mountains": "milky-way-mountains",
    "animated-vertical-grunge-black-texture-background": "grunge-black-texture",
    "dark-grungy-industrial-moving-light-background": "dark-industrial-light",
    "alaska-forest-background-mystical-wooded-route-clo": "alaska-forest-mystical",
    "dynamic-vertical-smoke-fog-transition-overlay-elem": "smoke-fog-transition",
    "dark-storm-clouds-rolling-across-golden-horizon-at": "dark-storm-golden-horizon",
    "intense-fiery-smoke-particles-abstract-motion-back": "fiery-smoke-particles",
    "trees-blowing-in-the-dark": "trees-blowing-dark",
    "urban-urban-video-of-brooklyn-on-a-rainy-night": "brooklyn-rainy-night",
    "indoor-workspace-at-night": "indoor-workspace-night",
    "cars-driving-through-dark-city-at-night": "cars-dark-city-night",
    "dramatic-clouds-at-sunrise-in-an-urban-setting": "dramatic-sunrise-urban",
    "alaska-forest-background-overgrown-woodland-trail": "alaska-forest-overgrown",
    "misty-forest-river-flowing-water-animated-backgrou": "misty-forest-river",
}


def clean_name(drive_filename):
    """Convert a long Envato filename to a clean short name."""
    # Strip the date suffix and extension
    stem = Path(drive_filename).stem
    # Remove date pattern like -2026-10-03-08-05-11-utc
    stem = re.sub(r"-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}-utc.*$", "", stem)

    # Check explicit mapping first
    if stem in FILENAME_MAP:
        return FILENAME_MAP[stem]

    # Fallback: truncate to reasonable length
    return stem[:40]


def probe_video(video_path):
    """Get duration and resolution of a video file."""
    path = str(video_path)

    # Duration
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    try:
        duration = round(float(r.stdout.strip()), 1)
    except ValueError:
        duration = 0.0

    # Resolution
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-of", "csv=p=0", path],
        capture_output=True, text=True,
    )
    try:
        w, h = r.stdout.strip().split(",")
        resolution = f"{w}x{h}"
    except ValueError:
        resolution = "unknown"

    return duration, resolution


def load_metadata():
    """Load the current backgrounds.json."""
    if BG_JSON.exists():
        return json.loads(BG_JSON.read_text())
    return []


def save_metadata(entries):
    """Save backgrounds.json."""
    BG_JSON.write_text(json.dumps(entries, indent=2) + "\n")


def list_local_clips():
    """List video files already in backgrounds/."""
    clips = {}
    for ext in ("*.mp4", "*.mov"):
        for f in BG_DIR.glob(ext):
            clips[f.name] = f
    return clips


def diff_report(drive_files, local_clips, metadata):
    """Compare Drive contents against local state.

    drive_files: list of dicts with {title, id, fileSize}
    Returns: {new: [...], existing: [...], missing_locally: [...]}
    """
    meta_files = {e["file"] for e in metadata}
    local_names = set(local_clips.keys())

    new = []
    existing = []
    missing_locally = []

    for df in drive_files:
        short = clean_name(df["title"])
        ext = Path(df["title"]).suffix
        local_file = f"{short}{ext}"

        if local_file in local_names:
            existing.append({"drive": df, "local": local_file, "short": short})
        elif local_file in meta_files:
            missing_locally.append({"drive": df, "local": local_file, "short": short})
        else:
            new.append({"drive": df, "local": local_file, "short": short})

    return {"new": new, "existing": existing, "missing_locally": missing_locally}


if __name__ == "__main__":
    # Standalone: just show what we have locally
    local = list_local_clips()
    meta = load_metadata()

    print(f"Local clips: {len(local)}")
    print(f"Metadata entries: {len(meta)}")

    for clip_name, clip_path in sorted(local.items()):
        dur, res = probe_video(clip_path)
        in_meta = any(e["file"] == clip_name for e in meta)
        print(f"  {clip_name:<40} {dur:>6.1f}s  {res:<12} {'OK' if in_meta else 'NO METADATA'}")
