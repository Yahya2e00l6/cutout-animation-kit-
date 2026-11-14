# Cutout Animation Kit

An editable 2D hoodie character reconstructed from
[the clean reference](lastpic.jpeg) and [the parts sheet](cutoutpic.jpeg).
This is an approximate vector reconstruction, not an automatic trace.

## Reuse the approved run

`reference-run` preserves the user-approved
`renders/reference-run/v02/reference-run.mp4`: a front-view, in-place hoodie
run, 4 seconds at 1280 × 720 / 30 fps. The reusable settings live in
[motions/reference-run.json](motions/reference-run.json); no cached frames or
original MP4 are needed. Keep this approved preset separate from experiments
in `motions/reference-run-candidate.json`.

From the repository directory, render a 10-second run:

```sh
python3 tools/animate.py --action reference-run --duration 10 --out renders/my-run/v01
TMPDIR=/tmp/opencode python3 tools/encode_sequence.py --dir renders/my-run/v01/frames --pattern 'frame_%04d.png' --fps 30 -o renders/my-run/v01/run.mp4 --json
```

Omit `--duration` for the approved 4-second clip. `--speed 1.25` makes the
cadence 25% faster; default `1` keeps the approved timing. Durations must be
whole frames at 30 fps. Choose a new output directory for each render.
`--keyframes` renders a small review selection instead of the full sequence.
Rendering needs Python Cairo, PyGObject/librsvg, and Pillow; encoding needs
FFmpeg and the local `ffmpeg` skill used by `tools/encode_sequence.py`.

Scene code can reuse the same action without running the CLI:

```python
from tools.actions import build_timeline
from tools.motion import sample

timeline = build_timeline("reference-run", duration=10, speed=1)
# model is a Humanoid built from the loaded rig and calibrated shoe soles.
state = sample(0.5, model, timeline)
```

This loop starts/ends mid-stride; it has no standing transition or travel
across the scene. The approved appearance applies to `characters/hoodie`;
another compatible rig still needs visual review. All 120 default frames were
checked pixel-for-pixel against the approved v02 PNGs when packaged. A test
locks the 120 motion states without depending on ignored render files.
The existing walk/jump/run demo and source artwork are unchanged.

## Side-view run construction

`characters/hoodie-side/` is separate, right-facing profile artwork inspired by
the approved side-view reference appearance. It reuses the pose loader, not the
front-view leg projection or motion adapter. Near/right limbs always stay in
front of far/left limbs; the limbs exchange their poses halfway through the
stride, not their depth order.

Review the eight editable construction poses:

```sh
python3 tools/side_review.py --png --out renders/side-run/rig/v01
```

Open `review-sheet.png` or `review-sheet.svg` in that output directory. Choose
a new directory for another review. The source SVG has a transparent background;
the review adds a ground guide. `poses/side-run.json` contains contact,
compression, push-off, and flight poses for each leg. Support poses align an
authored shoe marker with the guide; those markers are not raster-calibrated
shoe-contact guarantees.

These are **construction poses for visual review**, not an approved reusable
action. The front `reference-run` action is unchanged. The side-rig tests check
nesting, limb exchange, arm opposition,
depth order, support markers, flight clearance, and unclipped raster previews.

### Five-second side-run motion preview

```sh
python3 tools/side_run.py --out renders/side-run/motion/v02
TMPDIR=/tmp/opencode python3 tools/encode_sequence.py --dir renders/side-run/motion/v02/frames --pattern 'frame_%04d.png' --fps 30 -o renders/side-run/motion/v02/side-run.mp4 --json
```

`motions/side-run-preview.json` sets 5 seconds, 30 fps, 1280 × 720, and eight
full stride cycles. `tools/side_run.py` interpolates the revised construction
angles with periodic shape-preserving cubics and retains the side review's
vector limb outlines. The v02 correction keeps the artwork, leg angles, head,
torso, and authored root curve unchanged. Push-off/flight arms now oppose the
legs, rather than continuing to swing on the same side.

Opaque pixels from each rotated shoe are measured at 4× resolution to correct
vertical penetration. Ink bounds only size the calibration crop: their empty
corners are not sole contacts. Independent full-canvas raster tests compare
predicted clearances with actual shoe pixels throughout the five-second clip,
and check the previously floating stance frames. Other tests cover arm–leg
opposition at the keys and between them, plus untouched motion channels. This
does **not** lock horizontal foot contact or prove natural motion; foot slip,
arm timing, bounce, and stance transitions need playback review. No travel or
standing transitions are implemented. The output remains an unapproved motion
prototype, separate from the front action. Existing output folders are refused.

### Left-facing side run

Use the same corrected motion facing the other direction:

```sh
python3 tools/side_run.py --facing left --out renders/side-run-left/motion/v01
TMPDIR=/tmp/opencode python3 tools/encode_sequence.py --dir renders/side-run-left/motion/v01/frames --pattern 'frame_%04d.png' --fps 30 -o renders/side-run-left/motion/v01/side-run-left.mp4 --json
```

`--facing left` (or `"facing": "left"` in the config) reflects only the
character around the canvas centre. Ground, labels and time order are not
mirrored. It shares the right-facing artwork, arm timing and sole correction;
there is no second rig or motion sequence to maintain. Joint names remain in
the source rig's convention. `sample()` and `pose()` stay in source coordinates;
the facing transform is applied by `frame()`. Asymmetric character details are
mirrored too; this is not separately drawn artwork of the other anatomical side.

### Saved side-run actions for scenes

The named actions **`side-run-right`** and **`side-run-left`** use the saved
settings in [motions/side-run.json](motions/side-run.json), the side rig, and
`poses/side-run.json`. They do not read videos, render caches, or the experimental
`side-run-preview.json`. `tools/side_actions.py` is the Python entry point.

Export transparent PNG frames for a scene, from the repository directory:

```sh
python3 tools/side_run.py --action side-run-right --duration 10 --speed 1 --clean --out renders/my-scene/run-right
python3 tools/side_run.py --action side-run-left --duration 10 --speed 1 --clean --out renders/my-scene/run-left
```

`--clean` removes the background, ground guide, and review labels while keeping
the actor's pose and placement. Composite these alpha PNGs over the scene;
ordinary H.264 MP4 exports do not preserve transparency. Omit `--clean` for a
review video sequence. Choose a new output folder each time. Durations must
contain whole frames at 30 fps; `--speed` changes cadence, not body proportions.

Scene code can keep one action instance and render any point in its loop:

```python
from tools.side_actions import load_side_action
from tools.animate import raster

run = load_side_action("side-run-left", duration=10, speed=1)
svg, contacts = run.frame(0.5, 15, clean=True)
raster(svg, run.config["width"], run.config["height"]).write_to_png("runner.png")
```

The SVG is standalone; composite rasterized alpha frames rather than inlining
multiple rig SVGs with colliding IDs or style selectors. Position/scale the
result in the scene compositor. The movement remains an in-place loop, without
standing transitions or automatic scene travel. Another character needs a
compatible side rig and visual review. Tests pin representative saved frame
pixels in both directions and cover clean export, cadence, and duration.

## Review the puppet

Open [character.svg](characters/hoodie/character.svg) in a browser or Inkscape.
It has a transparent background, nested joint groups, and neutral, happy, and
open-mouth facial states. Left/right mean the character's own sides.

Generate four static review poses from the repository directory:

```sh
python3 tools/preview.py --png
python3 tools/preview.py --poses poses/checks.json --out renders/v03/checks --png
python3 tools/sweep.py --png
python3 -m unittest discover -s tests -v
```

Outputs go to `renders/v03/`, with a self-contained `review-sheet.svg` and
optional PNG sheet in each output folder. Earlier `renders/v01/` and `renders/v02/` previews are
left untouched. PNG export needs `rsvg-convert` (provided by
`librsvg` on Arch Linux); omit `--png` for SVG-only output with Python's
standard library. No cloud service, paid credits, or Blender is needed.
Repeated runs replace generated previews, not source artwork or references.

## Files to edit

- `characters/hoodie/character.svg`: vector artwork and joint rest transforms.
  Each joint's local origin is its pivot; child groups follow their parents.
- `characters/hoodie/rig.json`: joint names, limb chains, expressions, and
  initial grip/sole markers. These markers are not validated contact targets.
- `poses/review.json`: local rotation offsets in degrees, applied on top of
  the character's rest transforms. Positive rotation is clockwise on screen.
- `poses/checks.json`: pelvis tilt, forearm depth, leg depth, head tilts, and a
  mouth-only swap. These poses are construction checks, not approved acting.
- `tools/preview.py`: character-independent pose loader and renderer.
- `tools/sweep.py`: 35 sampled elbow, knee, and head poses, including foreground
  forearm variants, for visual inspection.

## Revision 3

The pelvis now carries both leg chains. The head pivots at the neck attachment
while a separate artwork offset preserves its neutral position. Neutral and
talk share the same eyes, eyebrows, and nose. Sleeves are slightly fuller and
the thigh is slightly longer relative to the shin. Relaxed hands have shorter,
curved fingers; lower-leg contours use smoother transitions into the ankles.

Overlapping sleeve/trouser fills are outlined as a combined silhouette using an
SVG filter, so there is no dark cap line at every elbow or knee. The border is
drawn inward, avoiding an extra outside border on already-stroked hands, cuffs
and shoes. Some importers rasterize SVG filters: the editable
vector paths are still present, but test import before adopting another app.

Pose-specific depth options:

```json
{
  "angles": {"elbow-left": 110},
  "layers": {"front_forearms": ["elbow-left"], "front_leg": "hip-right"}
}
```

Foreground forearms move above the torso while their upper arms remain behind.
The renderer preserves the forearm's position by combining its ancestor
transforms in a foreground wrapper. For filtered sleeves, that wrapper includes
upper-arm artwork when calculating the outline, then masks the result to the
forearm's coverage. This avoids a new cap line at the elbow. The generated mask
and outline context are derived artwork, not extra posing controls.
This flattens that chain in generated previews;
edit/pose the original SVG, not a generated pose, for further animation.
Foreground forearms are ordered back-to-front as listed. Leg ordering stays
under the pelvis artwork. Layer changes are explicit per pose; future animation
must choose when to switch them to avoid visible popping.

Use a new character directory with the same joint names to try another design.
Its artwork, rest transforms, limb lengths, and contact markers must be adapted.
The loader does not automatically trace images or retarget limb proportions.

## What this version proves—and does not

This version supports editable vector parts, nested joint rotations, facial
switches, depth overrides, and static pose previews. Tests check structure,
pivot positions, shared facial features, and position preservation during depth
changes. The sweep renders sample joint ranges; they are not a continuous
movement test or an automatic gap/artistic-quality detector.

There is no lip-sync, alternate view, gripping-hand swap, or finished movie
exporter yet. The talk preview is just an open mouth, not synchronized speech.
The bent-leg review pose is a construction test, not a balanced standing pose.
Full turns need additional artwork.

## Walk, jump, and run test

`motions/walk-jump-run.json` defines a 9.6-second silent test at 1280 × 720,
30 fps. It combines reusable idle, walk, jump, and run functions from
`tools/motion.py`; these read leg lengths from the character rather than using
the hoodie character's coordinates as animation presets.

This is a **front-view, in-place test**. A virtual stride goes into/out of the
picture; the renderer combines projected segment lengths with visible hip/knee
rotations and support-side root sway. In-plane IK compensates for the sway and
keeps declared shoe contacts fixed. It is not a side-view walk or a substitute for drawn
alternate views. No whole-character stretching or frame interpolation is used.
The run includes airborne phases, and the jump has anticipation, flight,
landing compression, and recovery.

The first video (`renders/motion-test/v02/`) had contact-boundary body jumps,
weak gait posing, overlapping running hands, and mismatched jump velocities.
It is not an approved motion benchmark. The revised test uses a root-height
curve independent of which shoe is supporting, matched compression/flight
velocities, separated running arm poses, and velocity-matched jump extension
and landing. New full-motion previews default to `renders/motion-test/v06/`; earlier outputs
are preserved for comparison. Passing the revised tests is not visual approval.

The current pose pass limits sideways knee bend: about 3 degrees at rest, with
more bend during swing and compression. Rounded knee overlaps keep the outer
contour connected. Stance and swing depth curves meet with matching velocity,
and the running hands alternate through a larger body-relative vertical range.

Render a small set of keyframes before a full sequence:

```sh
python3 tools/animate.py --keyframes --out renders/motion-test/my-test
python3 tools/animate.py --out renders/motion-test/my-test
```

The renderer needs Python GObject bindings, Cairo, librsvg, and Pillow. On Arch,
their packages are `python-gobject`, `python-cairo`, `librsvg`, and
`python-pillow`. It defaults to two render workers. Each output frame directory
must be empty; use a new output/version directory rather than replacing a test.
The supplied keyframe times are specific to the default test timeline.

At render time, each shoe's bottom outline is measured at 4× resolution using
bounds obtained from its actual vector geometry, not a fixed window. The
result goes in `motion-validation.json`, along with per-frame contact targets,
errors, planted-foot drift, artwork/code hashes, timing settings, and render time. These
measurements do not overwrite the initial attachment markers in `rig.json`.
Tests independently evaluate generated SVG transforms, walking support, run
clearance, hand separation and body-relative alternation, knee-angle bounds,
root and leg angular velocities at contact/action boundaries, and jump
takeoff/landing velocities. A synthetic fixture covers nonzero hip offsets,
unequal legs, and oversized shoes. It checks mechanics, not a second approved
character's appearance or continuous visual quality.

### Supported rig contract

This motion adapter does not work on arbitrary SVGs. It requires:

- Translation-only rest hip/knee/ankle controls with downward-aligned leg axes;
  hip vertical offsets are included in the solve.
- Identity torso/pelvis rest controls. The motion adapter owns leg rotations.
- An explicit `motion_geometry` mapping in `rig.json`. Each upper/lower segment
  is one direct-child path or group with an identity rest transform, containing
  all of that segment's art. Extra artwork outside it is rejected.
- Measurable shoe geometry within the calibration raster's 4096-pixel maximum.

Arm motion uses a tuned front-view reach model, measured arm lengths, and soft
forearm depth blending during walking/running. New body types may need different
reach targets, pivots, and artwork. No general-purpose
automatic retargeting or production savings are claimed yet.

### Arm-only pass

The walk/run arms now alternate opposite the actual eased leg trajectories.
Walking uses a restrained reach; running raises the forward hand further and
has more elbow bend. Limited per-segment projection suggests depth. Wrist follow-through stays close to forearm
alignment rather than forcing both hands to face down.

`arm_projection` in a pose scales the named upper/lower arm artwork and cuff
and updates elbow/wrist attachment positions before posing. Its supported
scales are 0.6–1.0, and the elbow/wrist rest joints must point downward. The
arm artwork IDs are declared in `rig.json` under `motion_geometry`.

`layers.forearm_blend` maps elbow IDs to weights between 0 (behind torso) and
1 (in front). It keeps the original arm hierarchy behind the torso and reveals
an opaque, aligned copy from its outside edge using a geometric clip. Weights
control foreground coverage, never opacity: torso lines must not show through
skin or sleeves. This is a front-view depth cue, not 3D occlusion.
Existing `front_forearms` poses
still use the original hard-foreground convention. Do not mix both conventions
for the same forearm.

The arm-only regression fixture locks all 288 leg/root states and idle/jump
states from v05. Update that fixture only for an intentional gait/jump change.
Other tests cover opposite-leg arm timing, body-relative hand movement, smooth
depth crossings, copy alignment, restrained running shoulder angles and elbow
spacing, raster opacity at partial depth coverage, and input validation.

For the local cached v05 comparison, `tools/arm_compare.py` renders only the
174 walking/running frames and reuses the previous PNGs for a 5.8-second
side-by-side result in `renders/arm-test/v02/comparison/`. That arm pass
removes the saturated swing extremes and keeps modest running elbow flexion
through the crossover. It requires the cached baseline video frames/report plus
the locally captured `before-states.json`; these ignored render files are not
part of a fresh clone. Without that cache, use `tools/animate.py` to render the
new motion directly. The comparison leaves the full sequence's legs and jump
unchanged and does not overwrite earlier previews.

### Bent-elbow running experiment

Running now eases into folded arms: settled elbow flexion stays around 81–99
degrees, with a shoulder-driven alternating pump and at most 3 degrees of wrist
follow-through. Walking, idle, jump, and every leg/root state are unchanged.
The original opaque depth-reveal technique remains in place.

Running hands ease into a loose curl instead of leaving the fingers extended.
`hand_curl` maps left/right to weights from 0 to 1. The renderer interpolates
the original SVG hand outline/crease paths toward matched-command targets in
`rig.json` under `hand_morph`. The original open-hand artwork remains unchanged
for non-running poses. Different character hands need compatible target paths;
incompatible command topology is rejected.

`tools/run_compare.py` reuses the right half of the latest cached arm comparison
and renders only 90 new running frames. Its 3-second side-by-side output goes
to `renders/run-arms/v01/comparison/`. It requires that cache and a locally
captured `before-states.json`; fresh clones can render the current full motion
with `tools/animate.py` instead. The experiment is a front-view pose option,
not an approval of realistic running or a new side-view rig.

To encode with the separately installed OpenCode FFmpeg skill:

```sh
python3 tools/encode_sequence.py --dir renders/motion-test/my-test/frames --pattern 'frame_%04d.png' --fps 30 -o renders/motion-test/my-test/walk-jump-run.mp4 --dry-run --json
python3 tools/encode_sequence.py --dir renders/motion-test/my-test/frames --pattern 'frame_%04d.png' --fps 30 -o renders/motion-test/my-test/walk-jump-run.mp4 --json
```

The wrapper preserves the skill encoder's output/probe safeguards and adds
native PNG frame-rate hints to prevent concat's default 25 Hz input cadence
from dropping/repeating exposures in a nominal 30 fps output. Pass
`--skill-dir /path/to/ffmpeg/scripts` for a different skill installation.
No DICE files or installed tool files are changed.

Next: watch the encoded test, refine actual movement defects, then test the
same motion functions on a second character with different proportions before
claiming production savings.
