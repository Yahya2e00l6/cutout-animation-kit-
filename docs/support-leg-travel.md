# Steadier body travel with leg IK

This opt-in trial transfers the old root-X correction into both leg chains.
The middle run follows the baseline X path; feet retain planted contacts,
horizontal paths and shoe rotations. Released heels lift earlier to avoid a
near-straight-knee hold during exchange. The approved pose-preserving run
remains the default. Artwork, saved settings, and standing angles are unchanged.

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
TMPDIR=/tmp/opencode npm run scene -- export ../scenes/examples/dice-courtyard-support-leg.json ../renders/scenes/dice-courtyard-support-leg/v02
```

Omit `travelMode` to retain the previous adapter. Support-leg mode requires
locking and the same calibration, cadence, facing and touchdown checks.

## Solve and limits

Both ankle targets absorb the previous root correction, then a two-link solve
changes hip/knee angles without stretching bones. The swing leg is included so
its horizontal trajectory stays unchanged too. Ankle angles compensate to preserve
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

At each end of the running interval, a smoothstep ramp over 0.15 cycles eases
the transfer in/out (short clips cap each ramp at half the running interval).
The remaining correction still moves the root during those ramps. This keeps
the approved start/stop blends and their joint velocities unchanged instead of
introducing a new backward launch or overshooting stop. In the two-cycle trial,
85% of running time has full transfer and exactly linear body X.

Targets can exceed reach if hip height is unchanged. A continuous smooth upper
bound on required hip drop keeps a half-source-unit reserve from full extension.
Unreachable or invalid targets fail instead of silently stretching or sliding.
Dense model inspection of the matched trial found about **3.01 output pixels**
of added hip drop and **32.29 degrees** maximum leg-joint change. Those are model
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

The rendered four-second courtyard comparison reduced `maxRunRootOffsetX`
from 41.69 to 14.17 output pixels (about 66%). With earlier recovery, sampled hip
drop is 1.58 pixels, heel lift 18.59 pixels, and maximum leg-joint change 30.73
degrees. All standing/start/stop PNGs
matched the previous courtyard export pixel-for-pixel. The new leg performance
still needs playback acceptance; these measurements do not establish smoothness.

Tests check independent delivered joint transforms, isolated shoe rasters,
mirrored/scaled targets, fixed limb lengths, prompt knee recovery after release,
unchanged planted contacts, upper-body preservation, scrubbing,
reach failures, source preservation and horizontal velocity at the run joins.
Review playback against the previous test before adopting this mode. This is
kinematic leg IK, not force/gravity simulation, a general rig solver, or acting
approval. The courtyard test still uses the hoodie runner, not the DICE cast.
