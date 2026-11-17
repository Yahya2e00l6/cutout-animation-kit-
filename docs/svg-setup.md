# One-time SVG setup: first working backend

**Status: CLI/data foundation, not a visual setup editor or automatic SVG
separator.** V1 supports separated, right-facing side-view humanoid artwork.
There is no new scene binding and no change to the approved front or side runs.

## What works

The same shared motion profile drives different SVG files through one generic
renderer. The setup file supplies all part IDs, pivot positions, proportions and
layer order. No per-character Python controller, custom animation function,
hoodie drawing or DICE adapter is loaded during playback.

- Inspect the SVG and list available part groups.
- Generate a setup template without guessing anatomy.
- Map fourteen parts, mark fourteen joints and order layers back to front.
- Validate and package a byte-identical artwork copy plus a hash-pinned rig JSON.
- Check the package and preview the shared run as transparent SVG/PNG frames.
- Optionally encode the preview as silent H.264. Video export is not required
  for using the package or sampler.

Transparent assets stay in `frames/` and `svg/`. MP4 previews use separate
opaque `review-frames/` with an off-white plate; H.264 does not preserve alpha.

`frames/` and `svg/` stay transparent. MP4 encoding uses separate opaque
`review-frames/` against a plain background because H.264 does not preserve alpha.

The two [technical fixtures](../examples/svg-setup/compact.svg) and
[long-limbed fixture](../examples/svg-setup/tall.svg) use different group IDs,
limb lengths and rest arm directions. Both use exactly the same playback code
and motion file. These deliberately simple figures test the rigging pipeline;
they are not proposed production character designs or visual approval.

The [ponytail hoodie girl](../characters/ponytail-hoodie-side-source/README.md)
is the first illustrated character reconstruction prepared from a user-supplied
picture. Only its source SVG and setup JSON differ; the same tool and motion
profile are used. Its likeness and retargeted run still need visual approval.

Local demonstration exports are under `renders/svg-setup/v04/compact-preview/`
and `renders/svg-setup/v04/tall-preview/`: each is 2.5 seconds, 75 native 30 fps
frames, silent H.264. The different 520×600 and 720×800 viewports retain each
fixture's fixed drawing margins. Both decoded-frame sheets were inspected;
delivery checks have no failures and expected missing-audio/subtitle warnings.
Generated media and test packages are not committed.

## Character preparation

SVG parts must be separate **top-level `<g id="...">` groups**, in viewBox-space
coordinates. Nested artwork inside a part may retain its own transforms. Keep
simple class/ID styles and definitions in the source SVG. Every top-level part
group must be mapped once; put no visible paths outside those groups.

Parts: torso, head; left/right upper arm, forearm, hand, thigh, shin and foot.
Joints: root/pelvis anchor, neck/head pivot; left/right shoulder, elbow, wrist,
hip, knee and ankle. Coordinates are absolute `[x,y]` in the source viewBox,
not pixels in a scaled preview. Feet should be drawn in their neutral,
right-facing standing orientation. A pivot marks attachment, not a shoe's sole.

Leave fixed margins around the artwork for full limb swings. Playback preserves
the viewport rather than shrinking individual frames to fit. Preview export
rejects clipped artwork. The long-limbed fixture demonstrates a negative viewBox
origin and extra rear margin. Set even viewport dimensions for MP4 export.

Flattened drawings are **not automatically segmented**. Existing nested rigs
must be flattened into these part groups first; that conversion is not provided
yet. Missing hidden surfaces and joint overlaps still need drawing work. V1
rejects scripts, raster images, `<use>`, active animation, external resources,
DTD/entities, and structural CSS selectors; it is not a general SVG sanitizer.
Use trusted artwork, not arbitrary untrusted downloads.

## Commands

From the toolkit root, choose fresh output paths:

```sh
python3 -B -m tools.svg_setup inspect --svg examples/svg-setup/compact.svg
python3 -B -m tools.svg_setup template --svg examples/svg-setup/compact.svg --out /tmp/opencode/my-character-setup.json
# Fill in parts, joints and layer order; compact.setup.json is a completed example.
python3 -B -m tools.svg_setup build --svg examples/svg-setup/compact.svg --map examples/svg-setup/compact.setup.json --out renders/svg-setup/demo/package
python3 -B -m tools.svg_setup check --rig renders/svg-setup/demo/package/rig.json
TMPDIR=/tmp/opencode python3 -B -m tools.svg_setup preview --rig renders/svg-setup/demo/package/rig.json --out renders/svg-setup/demo/preview --duration 2.5 --encode
```

`build` saves `character.svg` and `rig.json`. It never edits the input SVG or
overwrites an existing package. `check` verifies the hash, IDs, joint positions,
nonzero bone lengths and complete layer order. Rebuild after deliberate artwork
changes; stale artwork is an error, not a silent fallback. The rig's structural
contract is [svg-rig.schema.json](../schemas/svg-rig.schema.json); the setup CLI
also performs semantic checks against the actual SVG.

For a new character, only the SVG and setup JSON change. The CLI template still
requires a human/agent to identify parts and place pivots. A future visual editor
will write this same format; it has not been implemented in this checkpoint.

## Shared motion and what is not shared yet

[RunProfile](../tools/run_profile.py) reads
[shared-side-run.json](../motions/shared-side-run.json) without any character
artwork or legacy scene renderer. It samples angles and normalized flight height
with periodic shape-preserving cubic interpolation. Numeric cadence is applied
once. [SvgRig](../tools/svg_rig.py) computes forward kinematics using each new
character's own segment lengths and corrects authored rest bone directions.
Each source part receives a rigid transform; bones and artwork are not stretched.

The profile contains 96 equally spaced samples from the approved steady-state
`SupportRun` leg exchange, normalized by donor leg length, without its entry/exit
ramps. This is **baked motion data, not a port of the live support-leg solver**.
Source hashes and preparation provenance are recorded in the JSON. To regenerate
from unchanged original source assets, choose a fresh file:

```sh
TMPDIR=/tmp/opencode python3 -B -m tools.export_run_profile --out /tmp/opencode/shared-side-run-recheck.json
```

Generic playback measures each character's rotated shoe alpha and shifts the
whole body vertically to preserve clearance. That does not solve horizontal
foot planting, whole-sole constraints, standing transitions, extreme-proportion
IK, or dynamic layer swaps. Retargeting the sampled angles is not a guarantee of
natural motion on every body type. It does not reproduce the original motion's
travel/contact behavior exactly. Original production scenes keep their existing
loaders and approved live solvers.

## Checks and next step

```sh
TMPDIR=/tmp/opencode python3 -B -m unittest discover -s tests -p test_svg_setup.py -v
```

Tests cover read-only source preservation, arbitrary part-ID mapping, changed
limb proportions and rest directions, fixed bone lengths, independent raster
shoe grounding, playback without hoodie/DICE assets, deterministic scrubbing,
cadence/loop interpolation, malformed input and overwrite refusal. The JSON
schema is also compiled and tested with the engine's existing Ajv dependency.
These are technical checks, not visual approval of either test figure.

Next: use this format on one real new separated SVG, then add click-to-map parts
and drag-to-place joints. Automatic segmentation, front/back setups, arbitrary
nonhumanoid rigs, Godot export and production scene registration remain separate
work. Do not tell users this first backend already animates any SVG.
