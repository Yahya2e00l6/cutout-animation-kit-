---
name: cutout-scene
description: Assemble and export 2D hoodie animation scenes from story requests using the cutout-animation-kit scene engine. Use for scene JSON, saved side-run actions, multi-actor staging, SVG/PNG rendering, and silent MP4 export. Report unsupported actions rather than writing scene-specific animation scripts.
---

# Cutout scene authoring

Turn a supported request into scene JSON, validate it, export it, and inspect the
result. Reuse the saved artwork and actions. Do not write a Python/TypeScript
script for an individual scene or edit the engine, schema, rigs, poses, or saved
actions to make a request fit. Engine extensions need separate approval.

## Locate the toolkit and check support

Paths in this skill resolve from its directory. The toolkit root is `../../..`.
Read [a working example](../../../scenes/examples/side-run-across.json) before
the first scene. Consult [the scene rules](../../../docs/scene-format.md) for
timing/coordinate details or validation errors, and
[the engine guide](../../../engine/README.md) for dependencies or failures;
do not load the research reports or entire motion implementation for routine work.

Only these scene bindings exist:

| Character | View | Action |
| --- | --- | --- |
| `hoodie` | `side-right` | `side-run-right` |
| `hoodie` | `side-left` | `side-run-left` |

Multiple actors are instances of the same saved hoodie artwork, not newly drawn
characters. Left-facing art is mirrored. Front actions exist outside this scene
format; do not silently replace a requested front view with a side view. Rear
art is unapproved and not registered.

Supported: fixed camera, solid background, horizontal linear travel, scale,
cadence, timed clips, and actor-array draw order (last on top).
Optional experimental stand → run → stop: read
[the transition guide](../../../docs/standing-transitions.md) before using
`transitions`. It requires toe locking and a touchdown endpoint; it blends a
neutral pose rather than physically accelerating. Preserve `TRANSITION_TRIAL`
and request playback review. Do not silently adjust distance to fit touchdown.
Unsupported: standalone standing/idle, walk, jump, turns, view changes, expressions,
dialogue/audio, props, drawn scenery, camera moves, physical collision avoidance,
arbitrary action blends, and full sole/IK locking. Say what is missing and ask
whether a supported alternative is acceptable. Do not silently drop a story beat
or invent action names/fields. If the request explicitly asks for an engine
extension, stop scene production and plan that extension separately.

## Write the scene, not code

1. Identify actors, supported actions, timing, travel, and layering. Ask only for
   missing choices that materially change the requested result. For unspecified
   technical settings, state defaults: 1280×720, 30 fps, five seconds, white
   background, ground Y=620, scale=1, cadence speed=1. Duration overrides the
   default when the request names one.
2. Create a new descriptive JSON file under `scenes/`; inspect an existing file
   before editing it. Copy the example structure; use only schema fields. Consult
   [the schema](../../../schemas/scene.schema.json) for exact allowed values.
3. Use seconds aligned to whole frames. Each clip lies inside output duration;
   no same-actor overlap. Gaps hide an actor; they do not mean standing still.
   Each new clip restarts phase. Without explicit `transitions`, a run clip
   starts/ends mid-stride without a standing transition.
4. Place the ground anchor, not the SVG corner: both travel endpoint Y values
   equal `stage.groundY`. Right-facing travel goes right; left-facing travel goes
   left. Equal endpoints mean running in place, **not** idle. Scale=1 preserves
   the saved action's size. Leave room around the whole silhouette; the renderer
   clips rather than automatically fitting it.
5. Numeric cadence and travel are independent by default. Preserve
   `UNLOCKED_TRAVEL` warnings. An explicitly requested experimental alternative
   uses `footLock: true` with `speed: "auto"`; first read
   [the travel adapter's limits](../../../docs/travel-foot-lock.md). It anchors
   toe X by changing root travel, not limb poses. Disclose its
   `POSE_PRESERVING_TRAVEL` warning and measured root offset. Do not silently
   enable it, claim full sole pinning, or change travel/duration to bypass a
   cadence-range error without agreement.

Do not edit `samples.json` or generated SVGs to repair a scene. They are outputs,
not the authoring source. Use the scene JSON, then render to a new directory.

## Validate and export

Run commands from the toolkit's `engine/` directory. Below, `scene.json` means
the new file under `../scenes/`, and `new-version` means an unused version name.
Replace those placeholders with real paths; quote paths containing spaces.

```sh
npm run scene -- validate ../scenes/scene.json
npm run scene -- sample ../scenes/scene.json 0
npm run scene -- export ../scenes/scene.json ../renders/scenes/new-version
```

Validate first. Fix errors in the JSON, not by weakening the schema or suppressing
diagnostics. Sample the midpoint and clip boundaries too when scheduling several
clips. `sample` takes a zero-based frame index, not seconds. Export includes
validation and an encoder dry run. For frames only, use `render` instead of
`export`; do not separately render and then export to the same directory.

Output directories must be new. Never delete an old render to reuse its path.
Initial limits are 4096 pixels per dimension, 3600 frames, and 16 actors.
Dependencies missing? Report the exact error and follow the engine guide;
do not install globally, rewrite the renderer, or switch assets as a workaround.
Use `npm ci --ignore-scripts` in `engine/` when project dependency installation
is authorized and needed. No custom agent or model is required to use this skill.

## Inspect before delivery

1. Confirm command exit 0 and `report.json` status `complete` for video or
   `frames-complete` for frames only. A `failed` report is a failed job; retain
   its directory for diagnosis. Check that report warnings were retained.
2. For video, read `probe.json`: expected dimensions, duration, exact frame count,
   30 fps, H.264/yuv420p, and no audio. Frames use `[0, duration)`, so there is
   no extra endpoint frame. The exporter checks these independently of encoding.
3. Load the installed `ffmpeg` skill for video inspection. From `engine/`, run:

   ```sh
   python3 ~/.config/opencode/skills/ffmpeg/scripts/look.py ../renders/scenes/new-version/scene.mp4 --tiles 3x2 --json
   ```

   Open the generated PNG. Inspect first/last PNGs and frames around overlaps or
   clip changes when the sheet misses them. For frames-only output, open selected
   PNGs directly. Check actor visibility, facing, framing, layer order, background,
   and abrupt starts/ends. A contact sheet cannot establish motion quality; use
   playback when available and do not claim to have watched it unless you did.
4. If framing is wrong, revise JSON and use a new output version. If the defect
   belongs to a saved action or unsupported feature, report it rather than patching
   artwork/engine code or changing the requested story without approval.

Deliver links to the scene, video/frames, and inspected images. Report measured
duration, size, fps, audio, warnings, and whether playback was reviewed. Separate
technical checks from natural-motion/likeness approval. `contacts.json` contains
source-space metadata, not independent scene-space contact proof. The author has
authorized automatic commits and pushes for completed changes in this project.
Keep focused, tested checkpoints; stage only your work, leaving unrelated changes
untouched. Exclude renders, videos, caches, and archives. Report push failures;
never force-push or rewrite history to recover from a problem.
