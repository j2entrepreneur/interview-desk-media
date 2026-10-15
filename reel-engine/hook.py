"""Hook-first card timing.

A hook-first Reel opens on one short line in large bold text for HOOK_HOLD
seconds, then fades to the full card. Reason (Oct 2026 data): only 23% to
56% of viewers stayed past 3 seconds and average watch time was 3 to 7
seconds, because the first frame was a 40 to 70 word block. One line can be
read in under a second; a paragraph cannot.

The hook comes from the spec's "hook" field. If a spec has hook: true, the
card's first sentence is used, provided it is short enough to read at a
glance (MAX_HOOK_WORDS). The full card still includes that sentence, so the
viewer reads it twice: once as the hook, once in context.
"""
import re

HOOK_HOLD = 1.8      # seconds the hook is on screen before the fade starts
FADE = 0.35          # crossfade from hook to full card
MAX_HOOK_WORDS = 10


def first_sentence(text):
    plain = re.sub(r"<[^>]+>", "", text).strip()
    m = re.match(r"(.+?[.?!:])(\s|$)", plain.split("\n")[0])
    return (m.group(1) if m else plain.split("\n")[0]).strip()


def resolve_hook(spec):
    """Return the hook line for a spec, or None if the card is not hook-first."""
    hook = spec.get("hook")
    if not hook:
        return None
    if hook is True:
        hook = first_sentence(spec["text"])
    if len(hook.split()) > MAX_HOOK_WORDS:
        raise SystemExit(f"hook too long to read at a glance ({len(hook.split())} words, "
                         f"max {MAX_HOOK_WORDS}): {hook!r}. Set an explicit short \"hook\".")
    return hook


def total_duration(read_time, hook, cps):
    """Hook hold, then enough time to read the rest of the card. The hook's
    own characters are already read, so they are not counted twice."""
    return HOOK_HOLD + max(read_time - len(hook) / cps, 2.0)
