# Ponytail hoodie girl: source artwork and setup

**Status: first side-view reconstruction for visual review.** This is a new
character prepared from the middle panel of the author's uploaded three-view
picture, not a recolored hoodie boy or a new motion implementation.

`character.svg` is hand-reconstructed editable vector artwork. It does not embed
the picture, and it is not an exact automatic trace. The supplied front/back
panels informed identity and clothing but are not converted or rigged here.
Concealed far limbs and joint overlap areas are newly drawn approximations.

Preserved identity choices: brown ponytail with a pink hair tie, profile face,
dusty-rose hoodie, dark trousers, light rubber toe caps/soles and canvas sneakers.
Flat color replaces subtle shading in the picture. Fourteen top-level body-part
groups satisfy the generic setup contract. All coordinates use the same source
picture-like space; the expanded viewBox leaves fixed margins for limb swings.

## Data-only handoff

- `character.svg`: editable, separated source, transparent background.
- `setup.json`: part IDs, absolute joint pivots and fixed layer order.
- [Packaged artwork](../ponytail-hoodie-side/character.svg) and
  [rig](../ponytail-hoodie-side/rig.json): produced by `tools.svg_setup build`.

No character-specific Python controller exists. The package uses
`tools.svg_rig.SvgRig` and the unchanged `motions/shared-side-run.json`.
The ponytail remains attached to the head, and hands retain their drawn shape;
secondary hair motion and alternate fist drawings are not implemented.

From the toolkit root, reproduce into a **fresh** package directory:

```sh
python3 -B -m tools.svg_setup build --svg characters/ponytail-hoodie-side-source/character.svg --map characters/ponytail-hoodie-side-source/setup.json --out renders/ponytail-hoodie-side/rebuild/package
python3 -B -m tools.svg_setup check --rig renders/ponytail-hoodie-side/rebuild/package/rig.json
TMPDIR=/tmp/opencode python3 -B -m tools.svg_setup preview --rig renders/ponytail-hoodie-side/rebuild/package/rig.json --out renders/ponytail-hoodie-side/rebuild/run --duration 2.5 --encode
```

The original production front and side actions remain unchanged. This new
character is **not registered in the production scene engine**. Generic preview
grounding is vertical shoe-alpha measurement, not horizontal planted-foot IK.
Inspect likeness, joint overlap, fingers and garment silhouettes in playback
before treating the resulting run as approved.

Current local preview: `renders/ponytail-hoodie-side/run/v02/run.mp4`, 2.5 seconds,
75 frames, 900×1100, native 30 fps, silent H.264. Editable frames, transparent
PNGs and a pose sheet are alongside it. Delivery checks have no failures;
missing audio/subtitle warnings are expected. Generated renders are not committed.
