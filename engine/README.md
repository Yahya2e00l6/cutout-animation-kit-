# Scene engine

This package validates [scene v1](../docs/scene-format.md), samples scheduling
and placement, and exports scenes through the existing saved action loaders.
It produces standalone SVG frames, PNG frames, and silent H.264 video. Approved
action loaders and artwork remain in the parent toolkit, unchanged.

## Run

Use Node.js 22.18 or newer with native TypeScript stripping. From `engine/`:

```sh
npm ci --ignore-scripts
npm run check
TMPDIR=/tmp/opencode npm test
npm run scene -- validate ../scenes/examples/side-run-across.json
npm run scene -- sample ../scenes/examples/side-run-across.json 75
npm run scene -- render ../scenes/examples/side-run-across.json ../renders/scenes/frames-only/v01
npm run scene -- export ../scenes/examples/side-run-across.json ../renders/scenes/side-run-across/v01
```

`validate` checks strict JSON, the Draft 7 schema through Ajv, semantic rules,
and registered asset paths. It returns JSON diagnostics and a frame count.
`sample` takes a **zero-based frame index**, validates first, then returns visible
actors in draw order. Both commands exit 1 on errors. Warnings do not block a
scene and remain in both validation and sample output. File arguments resolve
from the shell's working directory; registered assets resolve from the toolkit.

`render` writes SVG/PNG frames without video. `export` writes those frames and
`scene.mp4`. Both require a **new output directory** and refuse existing files,
directories, or symlinks at that location. Choose a new version for every run;
there is no overwrite or resume flag. All commands exit 1 on errors.

Rendering requires the toolkit's existing Python Cairo, PyGObject/librsvg, and
Pillow environment. Video export also requires FFmpeg/ffprobe and the installed
FFmpeg skill at `~/.config/opencode/skills/ffmpeg/scripts/`. It reuses
`tools/encode_sequence.py` to preserve native PNG timestamps and the skill's
overwrite/probe checks. Export calls the encoder's dry run before encoding.

Initial exporter limits: each dimension at most 4096 pixels, 3600 frames
(two minutes at 30 fps), and 16 actors. Each child process has a ten-minute
timeout. These are exporter limits, not schema restrictions. `npm test` includes
real Python and FFmpeg integration tests, so it needs those dependencies too.

The example has 150 frames. Frame 75 places the ground anchor at `(640, 620)`
and reports action-local time `2.5` seconds. Its travel warning must not be
interpreted as successful contact correction or visual approval.

## API

```ts
import { readFileSync } from 'node:fs';
import { loadScene, sampleFrame, sampleScene } from './src/scene.ts';

const result = loadScene(readFileSync('../scenes/examples/side-run-across.json', 'utf8'));
if (!result.valid) throw new Error(JSON.stringify(result.diagnostics));
const frame = sampleFrame(result.scene!, 75);
const subframe = sampleScene(result.scene!, 2.51);
```

- `parseScene(text)` rejects invalid JSON and duplicate keys, including escaped
  spellings of the same name. It returns data, not executable code.
- `validateScene(value, toolkitRoot?)` validates an already parsed object. Use
  `loadScene(text, toolkitRoot?)` when duplicate-key detection is needed.
- A successful result contains an opaque `PreparedScene` snapshot. Changing
  input data, returned samples, or diagnostics cannot alter it.
- `sampleScene(prepared, seconds)` allows subframe requests inside the half-open
  scene duration. Frame-boundary roundoff within eight scaled machine epsilons
  is snapped to the nearest integer frame, without snapping to the excluded
  scene endpoint.
- `sampleFrame(prepared, index)` is the export-facing exact-frame entry point.
- Invalid handles, times, and indices throw. Failed validation never produces
  a sampleable handle.

Each sampled actor includes the existing action name, duration, unscaled local
time, cadence speed, view, scale, ground position, source anchor, and SVG affine
matrix `[a,b,c,d,e,f]`. The rendering adapter loads the saved action with that
duration and speed, call it with **unscaled** local time, then apply placement.
Do not mirror again or multiply local time by cadence speed again.

The validator reads the saved side-run config to obtain the source anchor;
it checks file presence and basic config compatibility, not rig integrity or
renderability. Existing Python regressions remain responsible for the saved
actions. Export validates again before sampling, and the Python bridge checks
its loaded anchor against each sample. Do not edit assets during a render.

## Rendering and reports

`src/render.ts` validates and samples all frames, then starts one Python process
running `tools.render_scene`. That bridge retains one action instance per clip,
calls `frame(localTime, frameNumber, clean=True)`, and embeds each actor SVG as
an SVG image data URI. Each image is an isolated SVG document, preventing IDs,
gradient references, and global CSS from colliding between actors. The outer
SVG applies placement and scale, draws the background, and clips to the canvas.
An optional [registered PNG/JPEG plate](../backgrounds/README.md) is embedded
behind the actors with contain/cover fitting. The bridge verifies and caches it
once per render; reports retain its asset ID and fit. No image means the previous
solid-color behavior.
The existing librsvg rasterizer produces PNGs from that composite SVG.

An export directory contains:

- `scene.json`: validated input text for reproduction.
- `samples.json`: internal engine-to-Python manifest, not another public scene format.
- `svg/` and `frames/`: exact numbered SVG/PNG frames, starting at zero.
- `contacts.json`: `sourceContacts` in source coordinates and optional
  `horizontalLock` toe-anchor/correction records. Neither is an independent
  delivered-pixel contact measurement; the applied transform is recorded too.
- `render-result.json`: frame count, size, loaded action-instance count, and
  `maxRootOffsetX` (zero for legacy unlocked rendering).
  Reports also include `maxRunRootOffsetX` (excluding standing transitions),
  `maxHipDrop`, `maxRecoveryLift`, and `maxLegJointChangeDegrees` for the opt-in leg solver.
- `report.json`: status, warnings, limitations, and any failure.
- With video: `encode-plan.json`, `encode-result.json`, `probe.json`, and `scene.mp4`.

`frames-complete` means frame rendering finished without video. `complete` means
video export also passed the independent probe check for dimensions, duration,
frame count, constant fps, H.264/yuv420p, and absence of audio. `failed` keeps the
partial directory and error report for inspection; it must not be treated as a
successful export or reused as output. Reports always retain travel warnings.

For code callers, `renderScene(text, newDirectory, options)` in `src/render.ts`
supports `{encode: false}` for frames only, `python` for the Python executable,
and `skillDir` for a different FFmpeg skill scripts directory.

Review a video with the installed skill, then inspect the resulting PNG:

```sh
TMPDIR=/tmp/opencode python3 ~/.config/opencode/skills/ffmpeg/scripts/look.py ../renders/scenes/side-run-across/v01/scene.mp4 --tiles 3x2 --json
```

## Boundaries

Only the registered hoodie side-left and side-right actions are supported.
Front actions are unchanged but not bound to this scene format yet. Registered
background images are supported; this does not register the DICE cast. Travel is
linear unless experimental root correction is enabled; gaps hide actors and clip starts reset
phase. Multiple actors are composited in actor-array order, last on top.
The [opt-in travel adapter](../docs/travel-foot-lock.md) uses `footLock: true`
and `speed: "auto"` for pose-preserving toe-X anchoring. It alters root travel,
not limb angles, and reports its maximum root offset. Legacy scenes are unchanged.
An optional [standing-transition trial](../docs/standing-transitions.md) adds
holds and pose blends around a locked run, with a `TRANSITION_TRIAL` warning.
Blends match joint velocity at the run joins while retaining the accepted
standing pose and middle run. Grounding and natural acting still need review.
Optional [support-leg travel](../docs/support-leg-travel.md) keeps middle-run body X
linear by solving both leg chains while retaining planted contacts and horizontal
foot paths. Released heels lift earlier to avoid an extension hold. Short
boundary ramps retain the approved standing transitions. It
changes leg poses and may lower the hips slightly; it is not the default.
There is no camera animation, audio, force-based physics, or general rig solver.

The separate [DICE character adapter](../docs/dice-character-adapter.md) registers
`dice-dongtae-upgraded` for both side views. Its unchanged SVG/controller snapshot
uses the shared motion through proportion-specific IK; it emits
`DICE_RETARGET_TRIAL` and still needs visual approval.

The project-local [cutout-scene skill](../.opencode/skills/cutout-scene/SKILL.md)
guides JSON authoring, validation, export, and inspection without scene-specific
scripts. Work inside this toolkit for OpenCode to discover it; invoke it with
`@cutout-scene`. Other agents can read the same file directly. Passing technical
checks is not natural-motion, horizontal-contact, or likeness approval.
