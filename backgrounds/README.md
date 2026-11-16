# Background plates

Scenes can use registered PNG/JPEG plates without changing animation code:

```json
"stage": {
  "background": "#e5e6dd",
  "groundY": 970,
  "image": {"asset": "dice-school-courtyard", "fit": "contain"}
}
```

`contain` centers the whole image, preserving its aspect ratio. The solid
background color fills any margins. `cover` fills the canvas and crops the
edges; differing aspect ratios emit `BACKGROUND_CROP`. Neither mode stretches
the image or moves the camera. Ground Y and actor scale still need visual review
against the actual pavement/floor, not just a numeric contact check.

## Register a plate

Copy an authorized source image into this directory with a simple basename.
Keep the original untouched. Add an ID under `assets` in
[registry.json](registry.json), recording `file`, pixel `width`/`height`, `mime`
(`image/jpeg` or `image/png`), and the file's `sha256`. `source` records provenance
for readers; it is never opened by the renderer. Asset IDs are lower-case names
with hyphens. Registry filenames cannot include paths or URLs.

Limits: regular files only, no symlinks, at most 20 MiB, 8192 pixels per dimension,
and 16,777,216 decoded pixels. Validation checks the registry, file signature and
hash. Rendering rechecks the hash, decodes the image, checks actual dimensions
and format, then caches a data URI for that render. Source changes before the
first frame fail instead of silently producing a different background.

Scene JSON refers only to registered IDs. Arbitrary local paths, SVG backgrounds
and remote URLs are unsupported. Existing solid-background scenes are unchanged.
Each exported SVG embeds the background and remains standalone.

## DICE courtyard technical test

[The scene](../scenes/examples/dice-courtyard-background-test.json) uses the
author-selected background-test option: the approved **hoodie test runner** on
the copied DICE school courtyard. It is not Dongtae, a cast redesign, a narrative
beat, or a finished DICE shot. The source picture, saved DICE cast, recordings
and approved corridor benchmark are unchanged. No generative image/video service
was used.

The four-second scene uses native 30 fps at 1920×1080. `contain` preserves the
1376×768 plate with approximately four-pixel top/bottom margins. The runner stands and travels on
foreground pavement at Y=970. There is no added contact shadow, foreground mask,
dialogue, sound or depth-dependent scaling. These are production limits, not
evidence of cast or story approval.

From `engine/`, export to a fresh version:

```sh
TMPDIR=/tmp/opencode npm run scene -- export ../scenes/examples/dice-courtyard-background-test.json ../renders/scenes/dice-courtyard-background-test/v02
```

This test required a one-time reusable background adapter. The scene itself is
JSON and reuses the saved run/standing transitions without a scene-specific
animation script. Time/token savings have not been measured.
