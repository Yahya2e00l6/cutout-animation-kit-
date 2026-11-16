# Front run in the scene engine

## Saved Astra v04 run

Use `character: "hoodie"`, `view: "front"`, and `action: "front-run"` for Astra's
v04 revision (`6fc6134`), registered at the author's request. The
[example](../scenes/examples/front-run-v04.json) repeats three strides in
2.3 seconds at 1280×720, native 30 fps, with no audio.

From `engine/`, choose a fresh output directory:

```sh
TMPDIR=/tmp/opencode npm run scene -- export ../scenes/examples/front-run-v04.json ../renders/scenes/front-run-v04/v02
```

[The adapter](../tools/front_study_action.py) loads the
[saved settings](../motions/front-run.json) and the CMU-based
[study renderer](../tools/front_run_study.py). All 69 character SVGs and their
definitions match v04 exactly; only the study background, guide line and shadow
are removed for scene composition. Numeric `speed` changes cadence once. Clip
timing, placement, uniform scale, registered backgrounds and mixed-view layering
use the normal engine controls.

Travel endpoints must be identical and on `stage.groundY`. Side `footLock`,
`travelMode`, automatic cadence and standing transitions are rejected, as are
depth/lateral travel and DICE front retargeting. Do not simulate forward travel
by enlarging the loop. The fixed 1280×720 source camera has anchor `[640, 650]`;
scene output size and actor transforms remain independent of it.

`sourceContacts.frontRun` records phase and the native-unit shoe-proxy ground
correction. This is not a planted-foot solver or pixel-grounding measurement.
No `maxFrontContactError` / `maxFrontPlantedDrift` metrics are produced for this
action, because it does not supply verified planted contacts. Preserve
`FRONT_RUN_IN_PLACE` warnings. See [study history and limits](front-run-study.md).
The original artwork, rejected front preset and approved side motion are unchanged.

## Legacy reference-run: rollback only

**Motion rejected:** the author rejected this front loop after comparing it with
the approved side run. Its registration and preservation tests establish only
technical behavior. Do not use it as the basis for new front-run motion. It is
retained for rollback. The `front-run` action above is a separate implementation.

Use `character: "hoodie"`, `view: "front"`, and `action: "reference-run"` to
render the existing saved front-view loop through the scene engine. The
[plain-background example](../scenes/examples/front-run-in-place.json) exports
four seconds at 1280×720, native 30 fps, without story scenery or DICE assets.

From `engine/`, choose a fresh output directory:

```sh
TMPDIR=/tmp/opencode npm run scene -- export ../scenes/examples/front-run-in-place.json ../renders/scenes/front-run-in-place/v02
```

### Legacy supported controls

- Clip timing, numeric cadence `speed`, actor placement and uniform scale.
- Solid or registered-image backgrounds, actor layering and multiple actors.
- Front and side actors in one scene, each using its own action's source anchor.

Front travel endpoints must be identical and lie on `stage.groundY`. The loop
begins and ends mid-stride; it does not stand, launch or stop. `speed` changes
cadence once in the saved loader, not again in the scene sampler.

The front gait already solves its own image-plane contacts. Do not add side
`footLock`, `travelMode`, `speed: "auto"`, or `transitions`; validation rejects
them. Lateral travel, running toward the camera, turning, perspective scaling
and DICE front-view retargeting are not implemented. Do not fake depth travel
by translating or enlarging this loop.

### Legacy preservation

[The wrapper](../tools/front_run.py) loads the existing
[front action](../motions/reference-run.json) through `build_timeline` and
calls the existing `frame_svg` renderer. It removes only the review-stage
background, labels and shadow before composition. Artwork, expressions, pose
math, projected limb lengths, contact timing and saved settings are unchanged.
The original command-line renderer and its approved-frame fixtures stay intact.

The front gait uses axial foreshortening and in-plane articulation. It is not
the side solver projected onto a new drawing. Astra's approved side run remains
separate and unchanged.

### Legacy checks

`FRONT_RUN_IN_PLACE` discloses the projection and travel limits. Per-frame
`sourceContacts.contacts` contains the existing front-action landmarks.
`render.maxFrontContactError` and `render.maxFrontPlantedDrift` evaluate those
landmarks after scene placement/scaling. They are model checks, not independent
raster grounding or proof of convincing depth motion.

Tests compare all 120 clean actor SVGs and contact records with the unchanged
saved renderer. Existing approved motion-state and raster hashes remain checked.
Other tests cover source preservation, cadence, scrubbing, mixed-view isolation,
per-action anchors, real Python bridge export, and rejected unsupported options.

Inspect the plain loop in playback before changing its motion. Registering the
saved action does not approve new cadence, staging or future front-run edits.
