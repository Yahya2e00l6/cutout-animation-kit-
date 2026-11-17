# Rear-view run study

**Status: drawing rejected; retained for rollback, not a registered engine action.**
The author rejected the rear artwork after reviewing the preview. Work now moves
to [one static rear drawing](rear-drawing.md) before more motion or rigging.
The front
`front-run` and both approved side actions remain unchanged. Review the rear
artwork and playback before registering a back view or treating it as approved.

## Shared motion, separate drawing

[RearStudy](../tools/rear_run_study.py) reads the saved
[front-run settings](../motions/front-run.json) and the same prepared CMU 09_01
cycle as [Astra's front run](front-run.md). It rotates the resulting 3D positions
and body axes 180 degrees about world Y before projection. This changes camera
orientation, not action timing, joint lengths or limb directions relative to the
body. Anatomical left appears on the viewer's left in the rear view.

The [rear identity SVG](../characters/hoodie-rear-study/identity.svg) is separate
editable artwork: back-of-head hair, ears, rear hood/seam, plain hoodie back and
rear pelvis. It matches the existing front-study dimensions and palette; it has
no face, drawstrings or front pocket. This is a likeness proposal, not a claim
that changing cameras automatically creates the correct artwork.

Joined garments and the sneaker surface mesh reuse the front study's drawing
helpers. Rear shoes need a full local frame: the shin and toe direction define
their dorsal side, avoiding the world-up construction's flipped sole during heel
recovery. Laces and sole tread follow this frame's camera-facing test. The shoe
proxy is grounded again after this orientation change; any extra whole-body Y
correction is recorded separately as `rearGroundCorrection`. The pose otherwise
matches the rotated front exactly. This is not a planted-foot or pixel-grounding
solver. Camera projection means feet at different depths need not touch the
same single screen-space floor line.

The older `hoodie-back` and `hoodie-back-animation` assets, hand-keyed rear
motions, tools and tests already present locally are preserved, not overwritten,
loaded or committed as part of this study. No DICE assets are involved.

## Preview and reproduction

From the toolkit root, choose a fresh directory:

```sh
TMPDIR=/tmp/opencode python3 -B -m tools.rear_run_study --out renders/rear-run-study/v01 --encode
```

The preview is three complete strides: 2.3 seconds, 69 frames, 1280×720, native
30 fps, silent H.264. Outputs include eight editable SVG poses, `pose-study.png`,
`front-rear-comparison.png`, `study.mp4`, per-frame SVG/PNG files, encoder evidence
and `study-report.json`. Generated previews are not committed. The comparison
uses identical phases, crop and display size for both views, not independent
height fitting. `RearStudy.frame(t, clean=True)` returns transparent character
artwork without the study background or floor guide.

## Checks and review boundary

```sh
TMPDIR=/tmp/opencode python3 -B -m unittest discover -s tests -p test_rear_run_study.py
```

Tests cover proper camera rotation, equality to the shared front joint motion
apart from recorded grounding, fixed bone lengths, continuous shoe frames,
periodic poses/velocities, deterministic random access, valid SVG references,
rear-only identity, transparent export and read-only source files.

Still inspect hair/head likeness, hood silhouette, sleeve overlap, folded shoes,
sole perspective and whether the run reads clearly in playback. Painter ordering
is not a depth buffer; no travel, turns or standing transitions are implemented.
The floor line marks the camera's reference depth, not every projected shoe:
ground points at different depths can appear above or below that screen line.
Geometry tests and successful encoding do not establish visual approval.
