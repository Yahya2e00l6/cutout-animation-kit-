# Rear drawing: appearance before animation

The author rejected the drawing in the first [rear run study](rear-run-study.md).
Matching the palette and projecting joint chains did not produce acceptable
clothing, hair, hands or shoe contours. That study remains intact for rollback;
do not refine its motion or register it to sidestep the drawing problem.

## Current task

Review **one complete, static rear drawing** beside the original front identity
and saved side artwork. No running poses, limb segmentation or animation edits
are part of this drawing pass. A drawing candidate is not visual approval.

References:

- [Original front identity](../lastpic.jpeg): character, outfit and proportion.
- [Saved side SVG](../characters/hoodie-side/character.svg): ink, palette,
  garment volume, curled hands and sneaker design.
- The existing local rear reference sheet supplies hood/nape construction,
  not a new timing or pose baseline.

The new visual candidate is AI-generated raster artwork (`openai/gpt-image-2`), **not an editable SVG,
rig or engine asset**. It is saved locally under `renders/rear-drawing/v01/`.
There is no automatic tracing or claim that a generated drawing can be animated
as-is. Obtain likeness/contour approval before drawing editable parts or rigging.
Generated review images are excluded from Git.
Latest comparison: `renders/rear-drawing/v01/review-v02/front-side-back.png`.

## Drawing brief

One straight rear-view, full-body character, standing naturally with both feet
on one baseline, arms relaxed and hands loosely curled. Retain the front
character's tall/slender proportions, modest head size and dark tousled hair.
Use dark organic ink contours and flat muted olive, charcoal, warm skin and
pale blue-grey sneaker rubber. No gradients, texture, text, panel sheet or
cast shadow.

Draw long continuous loose sleeves, rounded shoulders, wrist cuffs and small
hands; a hood with folded fabric thickness and a natural seam rather than a
rigid triangle; gathered hoodie hem; trousers with cloth volume and sparse
knee/ankle folds rather than straight trapezoids. Sneakers show rounded rear
heel counters and narrow soles. No exposed tread on the standing rear heels,
front pocket, drawstrings or face on the back of the figure.

## Compare without changing proportions

The [review tool](../tools/rear_drawing_review.py) arranges existing pictures;
it does not draw, animate or change source assets. From the toolkit root, choose
a fresh output directory:

```sh
TMPDIR=/tmp/opencode python3 -B -m tools.rear_drawing_review --drawing renders/rear-drawing/v01/back-drawing.png --out renders/rear-drawing/v01/review-v03
```

`front-side-back.png` uses a common displayed head-to-heel height, aligned
baselines and uniform scale only. This is a visual proportion comparison, not
evidence that the three silhouettes have identical anatomy. `back-isolated.png`
is a margin-cropped copy of the candidate, not a traced or segmented asset.

The saved front and side actions, rear motion sampler and all earlier rear
artwork are unchanged. The next decision is whether this complete drawing
belongs to the same character and drawing style.
