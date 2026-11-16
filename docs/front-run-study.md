# Fresh front-run pose study

**Status: v04 saved into the engine at the author's request.** Use
`hoodie` / `front` / `front-run`; see [the engine action guide](front-run.md).
The adapter preserves v04 poses and character drawing, removing only the study
plate, guide line and shadow. This registration does not establish planted-foot
contact, approve future edits or enable depth travel. The rejected legacy front
loop and approved side run stay untouched. No DICE scenes are involved.

## Review candidate: v04 drawing revision

Preview: `renders/front-run-study/v04/study.mp4` (2.3 seconds, 30 fps).
Start with `character-style-comparison.png` for the side/front artwork comparison
and `before-after.png` for v03/v04 at identical poses. `reference-comparison.png`
and `sagittal-comparison.png` retain the motion diagnostics.
These local renders are excluded from Git. V01 remains available; its code
checkpoint is `3db14e5`. V02 is an intermediate staging experiment.

The author identified the drawing mismatch as the problem after v03: segmented
trousers/sleeves, box shoes and attached-looking fists did not match the side
character. V04 changes drawing only. All 69 joint, body-axis, foot-direction and
ground-correction states match v03 exactly.

[Drawing helpers](../tools/front_study_drawing.py) now outline joined garment
silhouettes using the side rig's SVG morphology technique. Fuller trousers,
rounded knees/elbows and shoulder caps replace bone-by-bone outlines. Curled
hand contours and overlapping cuffs follow the side drawing. Sneakers have a
rounded upper, rubber toe cap, thin sole and curved laces; construction-face
edges and ladder-like sole marks are removed. The original front head, torso
and source artwork remain intact.

**Visual judgment:** clothing reads as continuous fabric and sneakers are closer
to the side design in the inspected phase sheets and decoded MP4 frames.
The author subsequently requested engine registration. Folded heels still hide at .0/.5, soles are simplified,
and front-view hand perspective needs review. The contact envelope is still
the v03 shoe proxy, not a planted-foot or pixel-grounding solver.

### V01 assessment before changes

V01 suggests a light jog, but its front silhouette does not sell a strong run.
The prepared CMU loop supplies running poses; copying its directions does not
guarantee readable motion at this character's proportions.

| Area | Matched-phase observation | Study response |
| --- | --- | --- |
| Knee drive | At .25/.75 the forward thigh still reads as a long vertical trouser leg. | Increase forward thigh pitch without changing bone length. |
| Heel recovery | At .0/.5 the source heel folds behind the knee, but the shoe paints across it. | Add recovery fold/spread and order leg segments by depth. |
| Arm swing | At .125 both hands hang low; .75 has a much stronger single-arm lift. | Blend toward mirrored half-cycle directions and recenter/enlarge sagittal swing. |
| Foreshortening | Most depth travel disappears in the front projection. | Stage the angles; keep perspective and fixed-length chains. |
| Silhouette | Narrow overlapping legs obscure swing versus support. | Raise the swing knee and slightly spread the recovering ankle. |
| Overlap | Whole-leg sorting puts a rear heel in front of its own thigh. | Sort shoes separately from joined trouser silhouettes. This remains painter ordering, not a depth buffer. |
| Body weight | Bob is visible, but the tall torso looks carried rather than loaded. | Retain measured bob for now; stronger flight poses alone do not solve loading. |
| Contact | Shoe-plane correction prevents penetration but gives no stance anchor or foot roll. | Keep this limitation explicit; do not call the guide line a contact test. |

## What this study changes

[FrontStudy](../tools/front_run_study.py) uses a measured 3D running reference,
not `reference-run`, `tools.motion.sample`, or the old leg-scaling renderer.
It uses the existing hoodie's torso, head and palette only for identity.

The reference supplies knee/heel recovery, opposite-arm motion, pelvis/chest
orientation and body bob. Fixed-length character-specific 3D leg and arm chains
are reconstructed from measured bone directions. Newly generated sleeve/trouser
contours and rounded shoe surfaces are projected into the front view. Laces
appear on the upper surface; foreground sleeves are clipped at the torso depth
plane after outlining, avoiding a drawn seam at that plane. No standing limb path is
axially stretched to simulate this run.

These are new drawings saved with v04, not changes to the original SVG artwork.
Ground contact and future contour, foreshortening or occlusion edits still need review.
The renderer currently targets the hoodie's proportions; the source motion data
is independent of that drawing. Do not call this universal retargeting.

## Measured source and preparation

[The reference data](../motions/front-run-study/athletic-reference.json) comes
from CMU Graphics Lab motion **09_01**, indexed as “run” in the
[CMU BVH index](https://raw.githubusercontent.com/una-dinosauria/cmu-mocap/master/cmu-mocap-index-text.txt).
The source is the cgspeed MotionBuilder-friendly conversion, obtained from
[this BVH mirror](https://raw.githubusercontent.com/konyshevgmbh/cmu-mocap/master/data/009/09_01.bvh).
The full source SHA-256 and selected frame numbers are stored in the data.

- BVH frame 0 is an added T-pose and is excluded.
- Frames 44–136 provide a right-stance-to-right-stance cycle.
- The documented capture rate is 120 fps; the BVH's rounded `0.0083333` frame
  time is normalized to that nominal rate. One cycle lasts `92/120` seconds.
- Heading and root travel are removed. An endpoint residual is removed with
  smoothstep before making 48 periodic samples. This is an adapted loop, not
  untouched capture data or automatic video tracing.
- The preview repeats three cycles: **2.3 seconds, 69 native 30 fps frames**.

The [source usage notice](../motions/front-run-study/READMEFIRST.txt) permits
research and commercial use without additional BVH-conversion restrictions.
Acknowledgment: “The data used in this project was obtained from
mocap.cs.cmu.edu. The database was created with funding from NSF EIA-0196217.”

To reproduce the prepared JSON from the downloaded, hash-checked source file:

```sh
python3 -B -m tools.prepare_front_reference --bvh /path/to/09_01.bvh --start 44 --end 136 --out /fresh/path/reference.json
```

Rendering uses checked-in JSON and needs no network, new package installation,
paid generation, or external 3D application. From the toolkit root:

```sh
TMPDIR=/tmp/opencode python3 -B -m tools.front_run_study --out renders/front-run-study/v05 --baseline renders/front-run-study/v04 --encode
```

Choose a fresh directory. Outputs include eight editable SVG blocking poses,
their pose sheet, the repeated-stride MP4, per-frame 3D state, source provenance,
ground-adjustment metrics and encoder plan/result. Do not edit the PNGs as source.

The [review tool](../tools/front_study_review.py) generates the front and sagittal
comparisons every time. The source skeleton uses the prepared, loop-corrected
CMU samples, scaled to the character's leg length. Its torso proportions are
not stretched to match the artwork. Front views share a camera and crop;
sagittal views are orthographic diagnostics, not another animation action.
`--baseline` adds the before/after sheet using the prior eight keyframe PNGs.

### Reusable staging controls

`FrontStudy(readability=MotionReadability(...))` accepts independent staging
controls. The CLI accepts the same fields through `--readability settings.json`;
omitted fields use defaults. The report records all resolved values.

| Field | Default | Meaning |
| --- | --- | --- |
| `knee_drive` | .85 | Forward thigh pitch gain, weighted by squared forward direction. |
| `heel_fold` | .18 | Extra recovery shin pitch, weighted by fourth-power rearward direction. |
| `recovery_spread` | .18 | Outward recovery shin direction before renormalizing. |
| `arm_center` | .4 | Sagittal arm recentering in radians. |
| `arm_gain` | 1.35 | Swing gain around the recentered upper-arm angle. |
| `arm_symmetry` | .8 | Blend toward the mirrored half-cycle average; 1 is symmetric. |

Pitch gains are radians; direction weights and other gains are dimensionless.
All changes happen before projection. Whole arm chains rotate together to retain
the blended elbow bend. For measured bone directions, set the controls to zero
except `arm_gain`, which must be 1. This disables staging, but retains the new
segment ordering; use the checkpoint for the exact v01 renderer.

## How the installed repos helped

- `tracing-video-to-animated-svg` reference measurement: measure
  motion and review corresponding cycle phases rather than inventing a gait
  from standing shapes. Its upstream scripts were not executed for this BVH.
  Its `drawing-rigging-shipping.md` also informed joint-overlap and phase-sheet
  review. The study adapts painter ordering to front-facing 3D segments rather
  than importing the reference's side-facing bike rig or drawing style.
- `generative-media-skills` 2D rig guidance: separate perspective
  drawings, depth order, identity preservation and technical checks.
- `svg-character-animator` SVG contour interpolation: a possible
  later polish tool for compatible authored shapes, not a source of running
  poses. No morph runtime was imported.
- `stick-motion` contact-method audit: keep contact constraints
  separate from pose design and do not equate valid IK with convincing motion.

## Checks and remaining limits

Tests verify the BVH rotation order against known 3D points, finite data,
constant character bone lengths, actual depth excursion, loop position/velocity
continuity, request-order independence, unique SVG IDs and read-only source art.
They also check disabled staging against measured bone directions, mirrored
half-cycle arm symmetry, invalid controls, recovered-shoe depth order and a
six-decimal digest of the complete v03 motion states to guard drawing-only edits.
A test replaces the old front sampler/renderer with failures and confirms this
study still renders. Preparation reproduces the checked-in data exactly from
the recorded BVH source.

Grounding currently uses a constant shoe-depth alignment plus a smooth global
mesh-plane correction. This is **not a fitted world-space planted-foot solver**;
the report records the correction and does not claim drift-free contacts or
independent pixel grounding. At the preview scale, delivery pixels are 0.64 of
the native character units used in the report. Perspective means a 3D ground
point need not lie on the single screen-space guide line.
V03's maximum correction across its 69 delivery frames is 13.46 character units
(8.61 pixels before perspective). That is a penetration correction, not a
foot-slip measurement. No body-weight or planted-contact test has passed.

Relevant regression command (the test path is needed by existing cross-test imports):

```sh
PYTHONPATH=tests:. python3 -B -m unittest tests.test_front_study tests.test_front_run tests.test_reference_run tests.test_side_run tests.test_support_run tests.test_actions tests.test_dice_adapter tests.test_side_actions tests.test_side_transition tests.test_travel_run
```

These suites contain 70 tests. For the drawing revision, the front-study, side-run,
SupportRun, DICE and saved-action suites were rerun: **46 tests passed**.
The MP4 encoder probe
confirms H.264, 1280×720, 30 fps, 69 frames and 2.3 seconds, with no audio.
Delivery checks report no failures; optional audio/subtitle warnings are expected
for this silent pose study. Neither result is visual approval.

Preserve this saved revision when authoring scenes. Further motion, contact or
drawing changes require their own playback review; passing geometry checks does
not establish visual quality.
