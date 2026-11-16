# Stand → run → stop trial

Add `transitions` to a locked side-run clip to hold a neutral stance, blend into
the saved run, blend back to neutral, and hold again. The upright standing pose
was accepted visually in the faster-run v02 review. Transition timing and
velocity joins remain experimental. Saved action APIs, artwork, and
the middle running interval remain unchanged.

See [the complete example](../scenes/examples/stand-run-stop.json) or the
[twice-as-fast trial](../scenes/examples/stand-run-stop-fast.json). From `engine/`:

```sh
TMPDIR=/tmp/opencode npm run scene -- export ../scenes/examples/stand-run-stop.json ../renders/scenes/stand-run-stop/v02
```

Choose a fresh output folder. The example lasts 6.6 seconds: 0.5 standing,
0.8 starting, 4 running, 0.8 stopping, and 0.5 standing. It travels two calibrated
cycles (944.762176 output pixels at scale 1). That trial distance is chosen to
end at touchdown; it does not replace the accepted five-second travel example.
The faster trial covers the same distance in two running seconds, doubling both
cadence and travel velocity, with 0.5-second start/stop blends and a total of
four seconds. It remains toe-locked; increasing cadence alone would not match
the fixed travel distance.

## Clip fields

```json
"transitions": {
  "standBefore": 0.5,
  "start": 0.8,
  "stop": 0.8,
  "standAfter": 0.5
}
```

All four fields are required, positive seconds aligned to whole frames. Their
sum is subtracted from clip duration to obtain the running interval, which must
contain at least one frame. `footLock: true` is required. Automatic cadence uses
the running interval, not total duration. The clip still binds to the existing
`side-run-right` or `side-run-left`; there are no standalone idle/walk actions.

The running interval must end at a whole half-cycle (touchdown), within `1e-6`
half-cycles. `TRANSITION_CONTACT` rejects other endpoints, including mid-flight
stops. The bridge snaps the transition endpoint within that tolerance. With
automatic cadence, a suitable travel distance is:

```text
distance = calibratedPixelsPerCycle * actorScale * numberOfHalfCycles / 2
```

Do not silently change an author's distance or timing to satisfy this constraint.
Omitting `transitions` retains the previous scene behavior.

## Rendering and limits

TypeScript schedules holds and supplies transition progress and duration, plus
a smoothstep weight for inspection. During holds
and blends it freezes action time at the adjacent run endpoint. `localTime` in
samples therefore means run time, not elapsed clip time. Baseline placement
holds at `travel.from/to` outside the running interval.

Python uses cubic Hermite curves between the explicit
[standing pose](../poses/side-stand.json) and the adjacent
run pose. Standing endpoints have zero joint velocity; run endpoints match
the saved action's joint velocities, measured with a periodic central difference.
Tangents use degrees per second and the actual blend duration, so the middle
run's cadence is unchanged. This does not regenerate or crossfade artwork. The lowest measured shoe
is grounded vertically. A root-X correction plants the support toe, including
through the blends. The other shoe may move. Baseline endpoints are not exact
corrected body positions. Contacts record `mode: "transition"`, the blend mode
and weight, progress/duration for moving blends, toe anchor, and applied root offset.

Matching joint velocity removes the old horizontal body-speed snap at run joins
while retaining the toe anchor. The rendered root moves as the planted leg
changes pose; the baseline path itself still holds outside the running interval.
This is kinematic easing, not a force-based acceleration/deceleration model.
Acceleration is not matched, and raster grounding can still introduce small
vertical steps or switch the lowest shoe. Long blends or new cadences can
overshoot joint angles: review them rather than assuming smooth curves look natural.
The standing pose uses straight knees, lightly staggered flat feet, a torso
aligned over the pelvis, and arms hanging at the sides. It replaces both the
stacked zero-angle pose and the rejected bent-knee standing trial.
Acceptance covers that upright pose, not arbitrary transition acting. Judge
the body shift, settling, limb overlap, and timing in playback before accepting
this approach. `TRANSITION_TRIAL` and `POSE_PRESERVING_TRAVEL` remain in reports.

With [support-leg travel](support-leg-travel.md), short transfer ramps inside
the run preserve the same endpoint tangents and accepted standing blends.
That mode emits `SUPPORT_LEG_TRAVEL` rather than `POSE_PRESERVING_TRAVEL`.

Tests cover schedule boundaries, static holds, repeatable sampling, invalid
timing/contact endpoints, saved-pose equivalence at touchdown, mirrored toe
placement through the delivered SVG, actual raster grounding, and independent
horizontal root/head/hand velocity checks at all four joins in both facings and
two scales. Tests also verify joint tangents across several blend durations.
These checks do not
establish natural motion or stationary contact over the whole sole.
