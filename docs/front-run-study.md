# Fresh front-run pose study

**Status: unapproved blocking study, not an engine action.** The author rejected
the old front loop and asked to start without treating it as a motion baseline.
The approved side run stays untouched. No DICE scenes are involved.

## What this study changes

[FrontStudy](../tools/front_run_study.py) uses a measured 3D running reference,
not `reference-run`, `tools.motion.sample`, or the old leg-scaling renderer.
It uses the existing hoodie's torso, head and palette only for identity.

The reference supplies knee/heel recovery, opposite-arm motion, pelvis/chest
orientation and body bob. Fixed-length character-specific 3D leg and arm chains
are reconstructed from measured bone directions. Newly generated sleeve/trouser
contours and rounded shoe faces are projected into the front view. Sole treads
and laces appear only on the visible shoe faces; forearms split at the torso
depth plane instead of crossfading through the body. No standing limb path is
axially stretched to simulate this run.

These are new study drawings, **not approved limb/shoe artwork**. Contours,
foreshortening, ground contact, occlusion and performance need playback review.
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
TMPDIR=/tmp/opencode python3 -B -m tools.front_run_study --out renders/front-run-study/v02 --encode
```

Choose a fresh directory. Outputs include eight editable SVG blocking poses,
their pose sheet, the repeated-stride MP4, per-frame 3D state, source provenance,
ground-adjustment metrics and encoder plan/result. Do not edit the PNGs as source.

## How the installed repos helped

- `tracing-video-to-animated-svg` reference measurement: measure
  motion and review corresponding cycle phases rather than inventing a gait
  from standing shapes. Its upstream scripts were not executed for this BVH.
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
A test replaces the old front sampler/renderer with failures and confirms this
study still renders. Preparation reproduces the checked-in data exactly from
the recorded BVH source.

Grounding currently uses a constant shoe-depth alignment plus a smooth global
mesh-plane correction. This is **not a fitted world-space planted-foot solver**;
the report records the correction and does not claim drift-free contacts or
independent pixel grounding. At the preview scale, delivery pixels are 0.64 of
the native character units used in the report. Perspective means a 3D ground
point need not lie on the single screen-space guide line.

Review the motion and silhouette before polishing clothing/shoes or changing
the engine. The next acceptance decision is whether the new stride reads as
running; passing the geometry checks does not answer that question.
