# Front run in the scene engine

**Motion rejected:** the author rejected this front loop after comparing it with
the approved side run. Its registration and preservation tests establish only
technical behavior. Do not use it as the basis for new front-run motion. It is
retained for rollback; [the fresh front-run study](front-run-study.md) is separate
and is not an approved replacement or registered engine action yet.

Use `character: "hoodie"`, `view: "front"`, and `action: "reference-run"` to
render the existing saved front-view loop through the scene engine. The
[plain-background example](../scenes/examples/front-run-in-place.json) exports
four seconds at 1280×720, native 30 fps, without story scenery or DICE assets.

From `engine/`, choose a fresh output directory:

```sh
TMPDIR=/tmp/opencode npm run scene -- export ../scenes/examples/front-run-in-place.json ../renders/scenes/front-run-in-place/v02
```

## Supported controls

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

## What is preserved

[The wrapper](../tools/front_run.py) loads the existing
[front action](../motions/reference-run.json) through `build_timeline` and
calls the existing `frame_svg` renderer. It removes only the review-stage
background, labels and shadow before composition. Artwork, expressions, pose
math, projected limb lengths, contact timing and saved settings are unchanged.
The original command-line renderer and its approved-frame fixtures stay intact.

The front gait uses axial foreshortening and in-plane articulation. It is not
the side solver projected onto a new drawing. Astra's approved side run remains
separate and unchanged.

## Review and checks

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
