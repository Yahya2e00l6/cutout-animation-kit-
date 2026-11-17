# Reusable side walk — movement review

Status: **experimental, not yet accepted**. The same walk drives Astra's existing
side artwork and the ponytail girl's unchanged generic rig. No character artwork,
accepted running action, or existing motion profile is edited. No scene-engine
binding, standing transition, front walk or rear walk is added.

## Reference repositories and the running logic

Installed clones were consulted read-only. This is an independently implemented
Python walk, not a copy of a browser demo or its character designs.

- **Stick Motion**, revision `6315c09c4e5051267806988defa28279b965fe29`:
  `assets/starter.html` (`gaitFoot`, lines 182–209), and
  `references/rig-architecture.md` / `references/poses.md`. Its useful mechanism
  is a ground-relative foot target whose backward stance velocity exactly cancels
  forward root travel. A 62% duty cycle provides double support rather than the
  run's flight. Its original quadratic swing and sine lift have endpoint velocity
  jumps; this implementation replaces them with matched polynomial trajectories.
  Its unreachable-target clamping is not adopted.
  [Source](https://github.com/cafermutluozkan/stick-motion/tree/6315c09c4e5051267806988defa28279b965fe29).
- **Tracing Video to Animated SVG**, revision
  `6a26f505ab835c24437212182ec3def5cd35c050`:
  `references/measuring-and-tracing.md`, “Cycles: period and phase”. Review both
  bodies at the same cycle phase, with native joint coordinates retained and
  transparent per-character renders. No walk footage is bundled in that clone;
  this walk is procedural, **not motion-captured or traced from video**.
  [Source](https://github.com/ahnafnafee/tracing-video-to-animated-svg/tree/6a26f505ab835c24437212182ec3def5cd35c050).
- **Math.Skill**, revision `cce75aece3b5e071dec41355853ae63bae387b15`:
  `modules/verification_engine.md`. Use independent FK checks, rendered shoe
  pixels, domains, mirrored travel, and boundary derivatives—not merely a target
  that assigns itself the floor height. This repo supplies guidance, not a solver.
  [Source](https://github.com/Wholiver/Math.Skill/tree/cce75aece3b5e071dec41355853ae63bae387b15).
- **Our accepted run**: `tools/support_run.py` informed the initial smooth pelvis
  lowering when a fixed foot target approaches leg reach. The revised walk
  uses the same law-of-cosines / downward SVG-angle convention and preserves
  native lengths. `tools/side_review.py` supplies Astra's existing vector posing;
  `SideRun.shoe_bottom` and `SvgRig.shoe_bottom` supply actual rotated shoe-alpha
  measurement. The run sampler, timing, travel solver and saved files stay intact.

The SVG morphing repo does not supply a walk/contact solver; none of its parser,
path-morphing or React runtime is imported. No new runtime dependencies are added.

## Motion contract

`motions/side-walk.json` is reusable action data; `tools/side_walk.py` binds it to
native rig lengths. A complete cycle is 1.2 seconds (two steps, 100 steps/minute).
Distance per cycle is `0.68 × mean total leg length`. Changing `speed` scales
cadence **and** derived travel speed once; it does not change stride poses.

- Both legs are grounded for 20% of a cycle in total; at least one supports the
  body throughout. One leg's phase is half a cycle behind the other.
- During stance, the foot's relative X retreats linearly. Add `record.travel`
  to the actor position to obtain the intended constant-speed world trajectory.
  Stance ankles and rigid shoe transforms then remain fixed in world space.
- Swing X matches stance position, velocity and acceleration at both ends.
  A cubic-endpoint lift has zero contact velocity/acceleration. Small swing shoe
  dorsiflexion returns to a fixed zero-angle support shoe.
- Foot Y comes from that character's shoe alpha, not from an assumed universal
  shoe size. There is **no post-pose whole-body grounding correction** that could
   displace another planted foot. A shared reach envelope gives a brief loading
   response (5° to 12° knee floor) followed by extension, rather than holding a
   constant crouch. Its periodic filtered pelvis is prepared before playback.
- Arms swing opposite the forward leg, elbows relaxed, head approximately upright.
  Bone lengths remain fixed. The ponytail remains rigidly attached to its head.
- `frame(t, speed, facing)` is deterministic and supports both directions by
  reflecting the actor and signed world travel together. `joints` are mirrored
  in-place native coordinates; `worldJoints` include the matched world travel.
  `ankleTargets` remain canonical right-facing solver diagnostics.

`GenericBody` accepts the **existing** packaged `rig.json`, requiring no second
walk drawing, per-action joint map, or character-specific animation controller.
`AstraBody` only adapts the saved nested SVG to the same sampler.

## Reproduce and review

From the toolkit root, use fresh output directories:

```sh
TMPDIR=/tmp/opencode python3 -B -m tools.walk_preview --out renders/side-walk/my-review/loop --encode
TMPDIR=/tmp/opencode python3 -B -m tools.walk_preview --out renders/side-walk/my-review/travel --mode travel --encode
# Optional mirrored travel review:
TMPDIR=/tmp/opencode python3 -B -m tools.walk_preview --out renders/side-walk/my-review/left --mode travel --facing left --encode
# Another prepared character: add --rig path/to/rig.json
PYTHONPATH=tests:. TMPDIR=/tmp/opencode python3 -B -m unittest test_side_walk -v
```

Default previews: 3.6 seconds, three complete cycles, 216 frames, 1800×1000,
native 60 fps, silent H.264 (`--fps 30` remains available). Two independently rasterized actors avoid SVG
ID/style collisions. `astra/` and `svg-character/` contain transparent native
SVG/PNG frames; `review-frames/` contains the opaque paired composition.
`report.json` records action parameters, source hashes, poses and contact data.
Loop review scrolls the ground ruler at the matching implied velocity; travel
review keeps the ground fixed and moves the actors. A loop without its implied
travel is a treadmill view, **not a claim of world-space stationary feet**.

## Reproduce and check

From the toolkit root, choose fresh output directories:

```sh
TMPDIR=/tmp/opencode python3 -B -m tools.walk_preview --out renders/side-walk/new-loop --encode
TMPDIR=/tmp/opencode python3 -B -m tools.walk_preview --out renders/side-walk/new-travel --mode travel --encode
TMPDIR=/tmp/opencode python3 -B -m tools.walk_preview --out renders/side-walk/new-left --mode travel --facing left --duration 1.2 --encode
TMPDIR=/tmp/opencode python3 -B -m unittest discover -s tests -p test_side_walk.py -v
```

Pass another package's `--rig path/to/rig.json` to exercise its native proportions
without changing animation code. For direct sampling, construct
`SideWalk(GenericBody(rig_path))`; `frame(t, speed, facing)` returns transparent
SVG plus local/world joints, support phases, target residual and signed travel.
The returned SVG itself is in place; the caller must apply that signed travel
for constant-speed movement. Preview composition does this only in travel mode.

The tests cover Astra, the ponytail and both technical fixtures: native bone
lengths, independent FK/IK residuals, world ankle locking through several cycles
in both directions at two cadences, raster shoe height and world-space raster
stance stability, no flight, double support, stride units, arm opposition,
derivative/loop continuity, deterministic seeking and invalid/reach cases.
Reach correction lowers only the pelvis; it never silently clamps ankle targets.

Initial checkpoint validation: 11 walk tests, 37 selected existing setup/run
regressions, and 115 engine tests passed. The smoothing revision adds six walk
checks (17 total); see below. This is not a new full Python-suite run.
Raster stance checks allow one native-raster pixel for
sampling/antialiasing. These technical checks are separate from motion approval.

The initial `v03/loop` and `v04/travel` previews are retained for comparison, not
accepted baselines. Current reviews: `renders/side-walk/v06/loop/walk.mp4` and
`renders/side-walk/v06/travel/walk.mp4`. Generated media stays outside Git.

## Upright / smoothness revision

The user identified Astra's crouched pose around phase .583. The original walk
passed contact checks but kept both knees flexed too far. The boy's knee bends
in that pose were about 24°/27°; the revised sampler gives about 11°/18° without
editing the SVG. Contact correctness was not sufficient visual validation.

- Raise the preferred pelvis, remove the imposed sinusoidal bob, and derive
  weight transfer from fixed-length leg geometry. A brief loading response
  releases into a straighter support leg, with a conservative smooth maximum.
- Prepare a periodic low-pass pelvis envelope (256 samples, 16 Fourier modes,
  Gaussian phase width .025). Add a global safety offset against 1024 reach
  samples plus a small margin, rather than clamping the pelvis anew each frame.
  This is sampled preparation, not a universal reach proof for arbitrary rigs;
  unreachable runtime targets still fail instead of stretching the leg.
- Measure each foot at nine angles and use a C2 cubic support-height curve.
  Stance uses the exact zero-angle measurement. This removes the quarter-pixel
  jumps caused by reading a different rotated raster bound each frame. Swing
  angles now also have zero velocity/acceleration at their contact endpoints.
- Reduce torso lean and arm amplitude, lower the swing arc, and shorten stance
  from 62% to 60%. Keep the original cycle length and distance per cycle.
- Evaluate actual poses at 60 fps, not duplicated/interpolated 30 fps frames.
  Rasterize at delivery scale with fractional stage placement instead of
  rounding each actor's translation to a whole pixel.

The six additional tests cover the complaint pose, loading/release, C2 shoe
interpolation, conservative pelvis between preparation samples, fractional
delivery placement, and distinct native 60 fps frames. The existing planted-foot,
bone-length, mirrored-direction and random-access tests remain in force. A
phase-matched boy comparison is `renders/side-walk/v06/boy-before-after.png`.
Movement still needs the user's review; heel-to-toe articulation remains absent.

An equal-cadence, 60 Hz numerical comparison against `a9ba912` is saved locally
as `renders/side-walk/v06/comparison-metrics.json`. Peak right-knee angular
acceleration falls from roughly 10,913 to 5,662 deg/s² on Astra and 11,294 to
6,923 on the ponytail rig. This measures a reduction in abrupt joint changes;
it is not a perceptual smoothness or natural-walk approval score.

Revision validation: all 17 walk tests and 37 selected existing Python regressions
pass. Both v06 exports probe as 3.6 seconds, 216 frames, 1800×1000, native 60 fps,
silent H.264. Delivery checks have no failures and expected missing audio/subtitle
warnings; decoded sheets were inspected. Artwork and accepted running files are
byte-identical to the previous checkpoint.

Remaining limitations: no heel-to-toe articulation, uneven terrain, acceleration,
start/stop blending, automatic scene registration, dynamic layering or new
drawings. Raster shoe contact establishes the lowest visible pixel, not full-sole
flatness on an unevenly drawn sole. Preserve the existing relaxed hands and
deferred ponytail artwork issues. Passing numerical checks does not establish
natural motion or user acceptance; review playback before promoting this action.
