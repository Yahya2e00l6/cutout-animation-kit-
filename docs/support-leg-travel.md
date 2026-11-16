# Steadier body travel with leg IK

This opt-in mode transfers the old root-X correction into the leg chains.
The author accepted Astra's revised general run as the smoother-run baseline.
Use this version for new support-leg scenes; do not restore the earlier
airborne anchoring or support-knee locking. This approval covers the general
hoodie run, not its character-specific adaptations or every new scene.
The middle run follows the baseline X path; feet retain planted contacts
and shoe rotations. Airborne legs release the stance correction before swinging
forward. A soft support knee and earlier heel lift improve the exchange.
Omitting `travelMode` retains the legacy pose-preserving behavior. Artwork,
saved settings, and standing angles are unchanged.

Add to a locked clip:

```json
"speed": "auto",
"footLock": true,
"travelMode": "support-leg"
```

The [courtyard trial](../scenes/examples/dice-courtyard-support-leg.json) uses
the same four-second timing, background, scale, cadence and distance as
[the previous test](../scenes/examples/dice-courtyard-background-test.json).
From `engine/`, choose a fresh output folder:

```sh
TMPDIR=/tmp/opencode npm run scene -- export ../scenes/examples/dice-courtyard-support-leg.json ../renders/scenes/dice-courtyard-support-leg/v06
```

Omit `travelMode` to retain the previous adapter. Support-leg mode requires
locking and the same calibration, cadence, facing and touchdown checks.

## Solve and limits

Each planted ankle target absorbs the previous root correction, then a two-link
solve changes hip/knee angles without stretching bones. Each leg releases that
correction with smoothstep from its toe-off (local phase 0.26) to opposite
touchdown (0.5), stays free through 0.76, and smoothly reacquires it by its next
touchdown (1.0). Value and velocity match at the joins. Applying the full
correction to the airborne leg during opposite stance pulled it backward before
its forward swing. Swing X therefore differs from the pose-preserving adapter.
Ankle angles compensate to preserve
each shoe's total rotation. Upper-body joint angles are retained apart from
numerical phase normalization. Shoe roll remains; this is not full sole pinning.

After each leg's toe-off at local phase 0.26, an earlier-peaked recovery arc
lifts that ankle until the opposite touchdown at phase 0.5. Its height is
`0.1 * legLength * (729/16) * u^2 * (1-u)^4`, multiplied by transfer weight,
where `u` runs from zero to one through this interval. Peak lift is at `u=1/3`;
value and velocity are zero at both ends. With this rig it adds at most 18.79
output pixels at scale 1. It changes airborne Y, not planted contact or foot X.

The original pose's measured vertical correction is applied before solving.
Lifting a released shoe therefore cannot lower the other shoe or change the
original standing height. `originalGroundCorrection` records this value in
source units; `recoveryLift` records each leg's added lift in output pixels.
`legOffsetX` records each leg's signed horizontal correction in output pixels.

At each end of the running interval, a smoothstep ramp over 0.15 cycles eases
the transfer in/out (short clips cap each ramp at half the running interval).
The remaining correction still moves the root during those ramps. This keeps
the approved start/stop blends and their joint velocities unchanged instead of
introducing a new backward launch or overshooting stop. In the two-cycle trial,
85% of running time has full transfer and exactly linear body X.

Targets can exceed reach if hip height is unchanged. A continuous smooth upper
bound on required hip drop keeps a half-source-unit reserve from full extension.
A phase-dependent knee-flexion floor prevents the support knee from locking,
bending, then locking again: it eases from 0 to 30 degrees at compression,
extends to 12 degrees at toe-off, then eases to 0 at the flight key. The floor
is multiplied by the boundary transfer weight. Its corresponding two-link
radius limits reach while the ankle targets stay fixed.
Unreachable or invalid targets fail instead of silently stretching or sliding.
Sampling one matched cycle at 600 phase intervals found about **5.07 output pixels**
of added hip drop and **23.43 degrees** maximum leg-joint change. Those are model
quantities, not a natural-motion verdict. Vertical motion remains the authored
bob plus this reach drop; only the fully transferred middle body X is linear.

Standing blends retain their previous saved-run endpoint velocities and upright
pose. Transition body X still comes from toe anchoring rather than a linear path.

## Reports and review

This mode emits `SUPPORT_LEG_TRAVEL` instead of `POSE_PRESERVING_TRAVEL`.
Standing clips retain `TRANSITION_TRIAL`. Contacts include `sourceContacts.supportIK`
with the transferred root offset, output-pixel hip drop and maximum leg-joint
change. During running, `horizontalLock.method` is `support-leg`;
`transferWeight` records the ramp and `rootOffsetX` is zero when transfer is
complete. Holds/blends retain their usual transition records.

`maxRunRootOffsetX` excludes standing transitions; `maxRootOffsetX` includes
them. `maxHipDrop` and `maxLegJointChangeDegrees` summarize sampled running
frames, not exhaustive continuous-time bounds. `maxRecoveryLift` reports sampled
heel lift; all three leg-solver metrics are zero for legacy clips.

The four-second courtyard export at `renders/scenes/dice-courtyard-support-leg/v05`
retains v04's 14.17-pixel maximum running root offset during boundary ramps.
With swing release and the knee floor, sampled hip drop is 4.52 pixels,
heel lift 18.59 pixels, and maximum leg-joint change 23.06 degrees.
All 60 standing/start/stop PNGs match v04 pixel-for-pixel. At frames 65–68,
support-knee flexion now decreases through 23.2, 17.7, 15.5 and 11.8 degrees,
instead of 6.6, 6.6, 15.5 and 6.6. The other leg repeats this at frames 50–53.
Frame close-ups were inspected, and the author accepted Astra's revised general
run in playback. The measurements support regression checks; they do not
approve different characters, cadences or scene performances.

Tests check independent delivered joint transforms, isolated shoe rasters,
mirrored/scaled targets, fixed limb lengths, prompt knee recovery after release,
forward swing without the backward tug, support extension without re-locking,
unchanged planted contacts, upper-body preservation, scrubbing,
reach failures, source preservation and horizontal velocity at the run joins.
The TypeScript export test also reads the final SVG joint transforms to check
that the scene engine delivers the free swing and single support extension.
Review playback against the previous test before adopting this mode. This is
kinematic leg IK, not force/gravity simulation, a general rig solver, or acting
approval. The courtyard test still uses the hoodie runner, not the DICE cast.
