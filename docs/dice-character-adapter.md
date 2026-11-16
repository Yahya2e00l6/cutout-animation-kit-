# Dongtae side-run adapter

Use `character: "dice-dongtae-upgraded"` to render Dongtae's saved DICE design
with shared side-run timing. This is a motion test, not a DICE story shot or an
approved DICE action. Future-movie illustrated characters remain separate.

The [courtyard example](../scenes/examples/dice-dongtae-courtyard.json) has a
standing hold, start, two seconds of running, stop, and final hold. It uses the
same cadence, distance and background as the approved hoodie technical test.
From `engine/`, export to a fresh folder:

```sh
TMPDIR=/tmp/opencode npm run scene -- export ../scenes/examples/dice-dongtae-courtyard.json ../renders/scenes/dice-dongtae-courtyard/v02
```

Both side views work; left-facing playback mirrors the right-facing drawing.
Other DICE cast members, front views, turns, dialogue, props and expression
tracks are not registered. Do not substitute upgraded Dongtae for his original
story appearance without checking the script.

## Artwork and motion stay separate

[The DICE asset directory](../characters/dice-dongtae-upgraded-side/) contains
byte-identical copies of `dongtae_upgraded_side_puppet.svg` and its existing
`puppet_rig.py` controller. `provenance.json` records original paths and hashes.
Export does not need the sibling DICE project. Validation and rendering reject
snapshots that no longer match those hashes.

[The adapter](../tools/dice_adapter.py) shares the selected side action's
cadence, standing blends, toe-X paths, planted shoe clearances and earlier
airborne recovery. It solves ankle targets using Dongtae's native segment
lengths, with uniform display scaling and reach-aware hip lowering. Arms use
the shared angles after compensating for their native rest directions. Hands
select Dongtae's saved fist state; the face retains its saved expression.

Dongtae's own rotating shoe drawings are measured at 4× resolution, rather than
assuming the hoodie sole has the same shape. The original SVG root remains
inside the rendered document so its root-scoped CSS keeps the saved palette.
Paths, polygons, colors, pivots, proportions and layer order are not redrawn.

Native ankle-to-sole depths are aligned by one constant vertical offset. This
avoids a repeated body drop when the shorter DICE shoe plants. During swing,
ankle height can lift farther to retain the donor's prompt knee recovery;
preserving the differently drawn shoe's clearance throughout flight would hold
Dongtae's knee nearly straight again. This adjustment eases in after toe-off
(phase `.26` to `.29`) and eases out before touchdown (`.88` to `1`). Planted
contact stays measured from Dongtae's shoe. `soleAlignment` and per-leg
`swingHeightAdjustment` record these changes in source-canvas pixels.

This does **not** make Dongtae's poses identical to the hoodie runner. His body
height, joint angles and reach adjustment differ. Shared timing does not carry
the hoodie's visual approval over to DICE. Review the start/stop, leg exchange,
silhouette and courtyard placement before building a longer scene.

## Checks and reports

`DICE_RETARGET_TRIAL` remains in validation/export warnings. Per-frame
`sourceContacts.diceRetarget` records the artwork hash, ankle-target error,
extra hip lowering and shoe-measurement mode. Its distances are in the shared
source canvas, before scene actor scaling. `render.maxDiceAnkleError` and
`render.maxDiceAdditionalHipDrop` summarize the two distances. The other source contact and support-IK metrics describe the
motion donor, **not** measured DICE joint angles.

Tests evaluate delivered SVG joint transforms, unchanged segment lengths,
toe-X matching in both directions, prompt delivered knee recovery, raster shoe grounding, preserved navy
colors, unchanged drawing attributes and snapshot hashes. These checks do not
establish likeness, acting or motion approval. Shoe roll is not full-sole
pinning; 4× raster contact measurement has quarter-source-unit resolution.

The approved DICE corridor benchmark and original cast/recordings are read-only
references. This adapter does not alter or replace them.

The revised four-second courtyard export measured 3.45 source-canvas pixels of
extra hip lowering, beyond the constant sole-depth alignment, and ankle-target
error below 0.001 pixels. Its outgoing knee exceeds 30° of flexion by local
phase `.30` in both legs/directions. These are technical checks; the DICE
performance still needs the author's playback approval.
