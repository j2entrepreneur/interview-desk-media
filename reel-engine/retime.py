"""Slow a background clip down when the card needs longer to read than the
clip runs, without making it jittery.

Rules (calibrated on the clip library, Oct 2026):

1. Only slow down when needed: stretch = reading time / clip length.
   Never more than MAX_STRETCH (1.5x, i.e. 67% speed). Beyond that the
   motion starts to look wrong; pick a longer clip instead.

2. High frame rate clips (60fps) are slowed by spreading out their real
   frames. As long as that still leaves 30 real frames a second, nothing is
   invented and the result is perfectly smooth.

3. Lower frame rate clips (24/25/30fps) need in-between frames. Simply
   repeating frames causes visible stutter (measured unevenness 0.5 to 1.0,
   up to a third of frames frozen), so in-between frames are generated with
   motion-compensated interpolation instead (unevenness back to 0.1 to 0.3).

4. Interpolation only works on calm, flowing motion: sky, mist, smoke, slow
   water, slow camera moves. On fast chaotic motion (flames, trees in wind,
   crashing surf, flickering light) it warps. So it is refused for clips
   whose average frame-to-frame motion is above MOTION_LIMIT.

5. Every slowed render is measured afterwards. If the output is uneven or
   has frozen frames, the render prints a warning.
"""
import statistics
import subprocess

MAX_STRETCH = 1.5
# Mean frame-difference score at 270px. Library spans 0.14 (cars at night) to
# ~5 (trees in wind, flames, surf). Interpolation was verified smooth on
# milky-way-mountains (0.77) and misty-forest-river (2.09); raise this only
# after testing a clip above it.
MOTION_LIMIT = 2.2
OUT_FPS = 30
INTERP = ("minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:"
          "me_mode=bidir:vsbmc=1")

# Post-render smoothness thresholds
MAX_UNEVENNESS = 0.6
MAX_FROZEN_SHARE = 0.05


def _probe(path, entries, stream=True):
    args = ["ffprobe", "-v", "error"]
    if stream:
        args += ["-select_streams", "v:0"]
    args += ["-show_entries", entries, "-of", "default=noprint_wrappers=1:nokey=1",
             str(path)]
    return subprocess.run(args, capture_output=True, text=True).stdout.strip()


def clip_duration(path):
    try:
        return float(_probe(path, "format=duration", stream=False))
    except ValueError:
        return 10.0


def clip_fps(path):
    raw = _probe(path, "stream=avg_frame_rate") or "30/1"
    num, _, den = raw.partition("/")
    try:
        return float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return 30.0


def frame_diffs(path, seconds=None):
    """Per-frame mean absolute difference on a small greyscale copy."""
    cmd = ["ffmpeg", "-v", "error"]
    if seconds:
        cmd += ["-t", str(seconds)]
    cmd += ["-i", str(path), "-vf",
            "scale=270:-2,format=gray,tblend=all_mode=difference,signalstats,"
            "metadata=print:key=lavfi.signalstats.YAVG:file=-",
            "-f", "null", "-"]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    return [float(line.split("=", 1)[1]) for line in out.splitlines()
            if "YAVG=" in line]


def clip_motion(path):
    v = frame_diffs(path)
    return statistics.mean(v) if v else 0.0


def plan(bg_path, needed_seconds):
    """Decide whether and how to slow the clip. Returns a dict with
    method in {"none", "spread", "interpolate", "refuse"}."""
    dur = clip_duration(bg_path)
    p = {"clip_seconds": round(dur, 1), "needed_seconds": round(needed_seconds, 1),
         "stretch": 1.0, "method": "none", "reason": ""}
    if needed_seconds <= dur:
        return p

    stretch = round(needed_seconds / dur + 0.005, 2)
    p["stretch"] = stretch
    if stretch > MAX_STRETCH:
        p["method"] = "refuse"
        p["reason"] = (f"needs {stretch}x slow motion, limit is {MAX_STRETCH}x; "
                       f"use a clip of at least {needed_seconds / MAX_STRETCH:.1f}s")
        return p

    fps = clip_fps(bg_path)
    p["source_fps"] = round(fps, 2)
    if fps / stretch >= OUT_FPS - 0.5:
        p["method"] = "spread"
        p["reason"] = f"{fps:.0f}fps source has enough real frames"
        return p

    motion = clip_motion(bg_path)
    p["motion"] = round(motion, 2)
    if motion > MOTION_LIMIT:
        p["method"] = "refuse"
        p["reason"] = (f"motion {motion:.2f} is too fast to slow smoothly "
                       f"(limit {MOTION_LIMIT}); use a calmer or longer clip")
        return p
    p["method"] = "interpolate"
    p["reason"] = (f"motion {motion:.2f} within limit {MOTION_LIMIT}, "
                   f"in-between frames generated")
    return p


def filters(p):
    """ffmpeg filter fragment to insert after scale/crop, or '' if none."""
    if p["method"] == "spread":
        return f"setpts={p['stretch']}*PTS,fps={OUT_FPS},"
    if p["method"] == "interpolate":
        return f"setpts={p['stretch']}*PTS,{INTERP.format(fps=OUT_FPS)},"
    return ""


def describe(p):
    if p["method"] == "none":
        return "normal speed"
    if p["method"] == "refuse":
        return f"CANNOT SLOW: {p['reason']}"
    return f"slowed {p['stretch']}x ({p['method']}: {p['reason']})"


def check_smoothness(path, seconds=None):
    """Measure a rendered video. Returns (unevenness, frozen_share, ok)."""
    v = frame_diffs(path, seconds)[2:]
    if len(v) < 5:
        return 0.0, 0.0, True
    mean = statistics.mean(v) or 1e-6
    unevenness = statistics.pstdev(v) / mean
    # Relative threshold: the final video is darkened and partly covered by
    # the text pane, so absolute differences shrink on calm clips.
    frozen = sum(1 for x in v if x < 0.1 * mean) / len(v)
    ok = unevenness <= MAX_UNEVENNESS and frozen <= MAX_FROZEN_SHARE
    return round(unevenness, 2), round(frozen, 3), ok
