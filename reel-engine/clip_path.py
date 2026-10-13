"""Resolve a card's background clip to a file on disk.

Cards store backgrounds as "backgrounds/<name>.<ext>". Clips now live in the
private iamjoshauld-clips repo as clips/<name>.mp4, synced from Google Drive.
Lookup order:
  1. the path as given (absolute, or relative to reel-engine/)
  2. the clips repo, matching on the short name and ignoring the extension

The clips repo location defaults to a sibling checkout and can be overridden
with the CLIPS_DIR environment variable.
"""
import os
from pathlib import Path

HERE = Path(__file__).parent
CLIPS_DIR = Path(os.environ.get(
    "CLIPS_DIR", HERE.parent.parent / "iamjoshauld-clips" / "clips"))


def resolve_background(background):
    p = Path(background)
    direct = p if p.is_absolute() else HERE / p
    if direct.exists():
        return direct
    synced = CLIPS_DIR / f"{p.stem}.mp4"
    if synced.exists():
        return synced
    raise FileNotFoundError(
        f"background '{background}' not found in reel-engine/ or {CLIPS_DIR} "
        f"(pull iamjoshauld-clips, or check the clip has synced from Drive)")
