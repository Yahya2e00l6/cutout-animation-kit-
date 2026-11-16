# Experimental pose-preserving travel

Use this opt-in mode to anchor a shoe's toe **horizontally** during authored
stance intervals while keeping the saved limb angles, artwork, and vertical
motion unchanged. It shifts the whole actor rather than solving leg IK.
An alternative [support-leg trial](support-leg-travel.md) changes leg poses
instead of running body X. The method here remains the default when
`travelMode` is omitted.
The five-second side-right comparison was accepted in playback. That acceptance
covers this example, not all cadences, characters, or transition motion.

## Use

Add these fields to a moving side-run clip:

```json
"speed": "auto",
"footLock": true
```

The surrounding clip structure is unchanged. See the complete
[locked example](../scenes/examples/side-run-locked.json) and
[same-cadence unlocked comparison](../scenes/examples/side-run-matched.json).
From `engine/`, choose fresh output versions:

```sh
TMPDIR=/tmp/opencode npm run scene -- export ../scenes/examples/side-run-locked.json ../renders/scenes/side-run-locked/v02
TMPDIR=/tmp/opencode npm run scene -- export ../scenes/examples/side-run-matched.json ../renders/scenes/side-run-matched/v02
```

Omitting `footLock`, or setting it to `false`, preserves existing numeric-speed
scene behavior. The saved front/side action APIs, poses, and source artwork are
not changed. `speed: "auto"` is valid only with `footLock: true` and nonzero
horizontal travel. In-place runs keep their existing numeric cadence.

## What changes—and what does not

- A fixed authored toe landmark stays at one world X during phases `0..0.26`
  (right anatomical leg) and `0.5..0.76` (left anatomical leg). Facing mirrors
  the result, not the anatomical leg names.
- The body follows the requested linear path **plus a periodic X correction**.
  `travel.from/to` therefore describe the baseline, not guaranteed corrected
  root endpoints when a clip ends mid-stride. `sampleFrame` returns the baseline
  transform; `contacts.json` records the applied transform and correction.
- Outside those intervals, a cubic Hermite recovery joins the next stance with
  continuous position and velocity. This is not ballistic flight or a force solve.
- Shoe rotation and vertical placement remain authored. A rolling shoe's lowest
  pixel can change even when its toe X is fixed. This is not full sole pinning.
- The correction can make the body hesitate or briefly move backward. It does
  not fix the original pose timing, produce standing transitions, or guarantee
  continuity between independently restarted clips. Judge those in playback.

For the five-second example, matched cadence is approximately `0.254032` of the
saved cadence (a `2.460318` second cycle). Maximum sampled root deviation is about
`42.51` output pixels. This is substantially slower than the original run;
cadence fitting is not evidence that the performance looks natural.

## Cadence and calibration

[motions/side-run-travel.json](../motions/side-run-travel.json) records a stride
estimate derived from the saved pose hierarchy's toe landmark, in saved-canvas
pixels. It includes SHA-256 hashes of artwork, rig, poses, and saved settings.
The validator rejects missing or stale calibration with `TRAVEL_CALIBRATION`.
Do not silently regenerate it or change approved source data to pass validation.

For world travel velocity `v`, actor scale `s`, base cycle `T0`, and calibrated
pixels per cycle `D`, automatic cadence is:

```text
speed = abs(v) * T0 / (D * s)
```

The current experimental envelope is `0.2 <= speed <= 2`. An explicit numeric
cadence with locking must be within 5% of the matched value; otherwise validation
returns `CADENCE_MISMATCH`. Change requested distance, duration, or actor scale
with the user's agreement rather than hiding a mismatch.

To inspect a fresh calibration without writing files, run from the toolkit root:

```sh
python3 -B -m tools.travel_run
```

## Root correction

The adapter reads toe coordinates through the existing pose hierarchy. With
elapsed stance time `tau`, source-canvas toe X at touchdown `p0`, and current
toe X `p`, apply this additional scene-space translation:

```text
correctionX = -v * tau + s * (p0 - p)
actualRootX = baselineRootX + correctionX
```

Touchdown anchors are calculated from phase and trajectory, never remembered
from previously rendered frames. Scrubbing and shuffled requests give the same
correction. The adapter operates per clip and never mutates the saved action.

## Evidence and reporting

Locked clips emit `POSE_PRESERVING_TRAVEL`, not a warning-free success claim.
Unlocked moving clips retain `UNLOCKED_TRAVEL`. Export reports include
`render.maxRootOffsetX`; per-frame records contain `horizontalLock` with mode,
stance side, computed toe/anchor X, and root offset. These are model quantities,
not independent rendered-contact proof.

Tests separately check source preservation, mirrored/scaled forward kinematics,
phase seams, request-order independence, and actual isolated shoe rasters.
At the two flat-shoe stance keys, the pixel test requires at most one pixel of
horizontal drift in either facing; the same-cadence unlocked fixture slides by
more than 30 pixels. Dense model checks cover the rest of stance, but do not
establish all-pixel stationary contact while the shoe rolls, or natural motion.

Before adopting this mode for a story, compare it against unlocked playback at
the **same cadence**. A comparison with only the original faster run confounds
retiming and foot correction. Review new combinations before using them in a story.
