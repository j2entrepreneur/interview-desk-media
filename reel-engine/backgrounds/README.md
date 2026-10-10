# Background Videos

Vertical background clips (1080x1920 or 4K) for video-composite Reels.
Videos stored on Google Drive (`iamjoshauld-backgrounds` folder), synced locally at render time.
See `backgrounds.json` for metadata (duration, mood, themes, Drive file IDs).

## Storage

- **Google Drive folder**: `iamjoshauld-backgrounds` (ID: `1zpdUqNIsYSrqj2tzkXNcETkYVO9HgjWk`)
- **Git tracks**: only `backgrounds.json`, `README.md`, and `sync-backgrounds.py`
- **Video files**: gitignored, downloaded from Drive when needed for rendering
- **Clips needing probe**: entries with `_needs_probe: true` need duration/resolution after first download

## Mood categories

| Mood | Feeling | Best card types |
|---|---|---|
| raw | Gritty, focused, a single light | Recognition |
| relentless | Repetitive force, crashing | Recognition (endurance) |
| cerebral | Zoomed out, analytical | Recognition (overthinking) |
| heavy | Weight, pressure, dark texture | Recognition (burden) |
| intimate | Interior, private, behind doors | Recognition / Relief |
| performing | Urban, alone in a crowd | Recognition (mask) |
| obscured | Hidden summit, not yet visible | Recognition / Relief |
| turbulent | Restless, churning, storm | Recognition / Relief |
| transformation | Light emerging, shifting | Relief |
| vast | Open landscape, the long view | Relief |
| reflective | Warm, golden, contemplative | Relief / Lighter |
| primal | Fire, warmth, gathering | Relief / Recognition |
| expansive | Cosmic, wonder | Lighter |
| grounded | Nature, organic, growth | Lighter / Relief |
| clean | Rising, light, releasing | Lighter |

## Current library (36 clips)

16 original clips (probed, metadata complete) + 20 new clips (on Drive, need probe).

## Adding new clips

1. Upload `.mp4` or `.mov` files to the Google Drive folder (vertical, min 1080x1920)
2. Add a filename mapping to `sync-backgrounds.py` FILENAME_MAP
3. Add an entry to `backgrounds.json` with mood, themes, best_for tags, and Drive file ID
4. Set `_needs_probe: true` until the clip is downloaded and probed for duration/resolution

## Wanted clips (gaps still in the collection)

- City at dawn, empty streets (12-20s)

Previously wanted, now covered:
- ~~Fog or mist clearing~~ (smoke-fog-transition.mov)
- ~~Forest canopy or single tree~~ (alaska-forest-mystical.mov, alaska-forest-overgrown.mov)
- ~~Storm with lightning or clouds breaking~~ (storm-clouds-field.mov, dark-storm-golden-horizon.mov)
- ~~Ember/coal glow close-up~~ (fiery-smoke-particles.mp4)
- ~~Rain / wet urban night~~ (brooklyn-rainy-night.mp4)
- ~~Sunrise/dawn breaking~~ (dramatic-sunrise-urban.mov)
- ~~Rain on glass~~ (rain-droplets-glass.mov)
- ~~Empty road/street at night~~ (foggy-night-street.mov)
- ~~Underwater~~ (underwater-reef-sunlight.mov)
- ~~City at sunset/dusk~~ (aerial-sunset-city.mov)
