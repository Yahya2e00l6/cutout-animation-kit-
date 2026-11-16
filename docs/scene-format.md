# Scene format v1 (draft)

This contract describes a fixed-camera scene assembled from registered saved run
actions. The [TypeScript package](../engine/README.md) implements validation,
deterministic scheduling/placement sampling, and SVG/PNG/video export through
the existing Python action loaders.

- [JSON schema](../schemas/scene.schema.json): Draft 7 structural rules.
- [Five-second example](../scenes/examples/side-run-across.json): one runner
  moving right across a white stage. This is a composition test, not an approved
  traveling run; the saved action has no horizontal foot locking.

The engine uses Ajv for schema validation and jsonc-parser for duplicate-key
detection. It contains no copied reference code or new artwork.
The saved [front-run loop](front-run.md) is also registered for in-place use.
An optional [standing-transition trial](standing-transitions.md)
wraps the saved side runs. Rear actions, camera moves, audio,
expressions, and arbitrary scripts are not part of v1.

## Coordinates and appearance

Output dimensions are even integer pixels, suitable for a later H.264 export.
The first adapter targets 30 fps, matching the saved action tools. The origin is
the top-left; X increases rightward and Y downward. The camera is fixed.
`background` is an opaque six-digit hex color. `groundY` is a placement guide,
not a visible line or a physics surface.
Optional `stage.image` selects a [registered background plate](../backgrounds/README.md)
by `asset` ID and `fit` (`contain` or `cover`). It draws behind all actors.
Contain preserves the whole image with solid-color margins; cover crops to fill
and reports `BACKGROUND_CROP`. Paths and URLs are not scene inputs. The sampler
includes a hash-pinned `stage.plate` descriptor for the rendering bridge; this
internal output field is not accepted in authoring JSON.

Each actor has a unique `id`, registered `character`, fixed `view`, and positive
`scale`. Scale 1 preserves the saved action's rendered size, including its
artwork scale (0.62 for hoodie side runs, 0.64 for `front-run`, 0.56 for legacy `reference-run`); it does not
mean one raw artwork unit per pixel.
Actors draw in array order, last actor on top. Offscreen artwork is clipped to
the output canvas, not automatically shrunk or repositioned.

`travel.from` and `travel.to` are positions of a **fixed ground anchor**. They
are not the current midpoint of the animated feet or the SVG's top-left.
For the saved side action's default canvas, the anchor is `(640, 650)`:
canvas center X and configured floor Y. This preserves authored root bob and
vertical contact correction. The adapter maps source point `p` to:

```text
scenePoint = travelPosition + actor.scale * (p - sourceAnchor)
```

Facing is already applied by the saved action. Do not mirror it again. Left
playback uses mirrored right-facing artwork, not a separately drawn left view.

## Timing and travel

All times are seconds. Output duration, clip start, and clip duration must map
to whole frames. Convert once to integer frame counts; accept a conversion only
when `abs(seconds * fps - round(seconds * fps)) <= 1e-6` frames.

For `N = round(output.duration * fps)`, export frame indices `0..N-1` at
`time = frameIndex / fps`. The example has 150 frames; there is no extra frame
at exactly five seconds.

Clips are active on `[start, start + duration)`. A clip begins at action-local
time zero and restarts the action phase; `speed` multiplies gait cadence using
the existing action loader. `speed: "auto"` resolves to a numeric cadence during
validation when opt-in toe-X anchoring is enabled. Pass unscaled local time to that loader: do not
apply speed twice. A clip does not imply a stand-to-run or run-to-stand blend.
Explicit `transitions` adds standing holds and pose blends, requires locking,
and must leave a running interval ending at touchdown. Its `localTime` freezes
at run endpoints during holds/blends; travel and matched cadence use only the
running interval. See the trial guide for fields, contact constraints, and limits.

Travel is linear. For local clip time `t` and duration `d`:

```text
u = t / d
travelPosition = from + u * (to - from)
```

The final encoded frame is just before the destination, because the clip's end
is excluded. Adjacent clips should use the previous destination as the next
origin for continuous placement. Equal endpoints produce an in-place action.
An actor is hidden outside its clips; an empty interval is not an implicit idle.
Overlapping clips on one actor are invalid. Different actors may overlap.

By default, travel and numeric cadence are independent; moving clips produce
`UNLOCKED_TRAVEL`. Optional `footLock: true` with `speed: "auto"` enables
[experimental pose-preserving toe-X anchoring](travel-foot-lock.md) and matched
cadence, with a `POSE_PRESERVING_TRAVEL` warning instead. It changes root travel,
not limb poses, and is not natural-motion approval. A successful render must
retain its warnings. Travel against facing is
invalid in v1. Vertical travel is unsupported: both endpoint Y values must equal
`stage.groundY` within `1e-6` output pixels.

Optional `travelMode: "support-leg"` on a locked clip selects
[leg IK with steadier middle-run body X](support-leg-travel.md). It changes both leg
chains and may lower the hips slightly. Planted contacts are retained;
airborne anchoring releases smoothly and a soft support knee prevents repeated
locking. An earlier airborne heel lift improves recovery. It emits
`SUPPORT_LEG_TRAVEL`. Saved poses and original action APIs remain unchanged;
omit the field to retain the previous adapter. Short transfer ramps at each
run boundary preserve the approved standing transitions.

## Initial registry contract

The validator binds these names to existing files and checks action/view
compatibility. It does not load Python rigs yet. Paths resolve from the toolkit
root, never from the scene directory.

| Character | View | Action | Existing loader |
| --- | --- | --- | --- |
| `hoodie` | `side-right` | `side-run-right` | `tools.side_actions.load_side_action` |
| `hoodie` | `side-left` | `side-run-left` | `tools.side_actions.load_side_action` |
| `hoodie` | `front` | `front-run` (Astra v04) | `tools.front_study_action.FrontStudyAction` |
| `hoodie` | `front` | `reference-run` (rejected; rollback only) | `tools.front_run.FrontRun` |
| `dice-dongtae-upgraded` | `side-right` / `side-left` | matching `side-run-right` / `side-run-left` | `tools.dice_adapter.DiceAdapter` over shared timing |

The two side bindings use `characters/hoodie-side/`, `poses/side-run.json`, and
`motions/side-run.json`. Keep their current settings and source artwork unchanged.
Use one loader instance per clip to retain calibration caches. Do not load
experimental preview settings or rear artwork as a fallback.

The `front-run` binding uses the hoodie's head/torso identity, newly drawn limbs,
`motions/front-run.json` and the prepared CMU cycle. It preserves Astra's v04
revision and uses shoe-proxy plane correction, not planted-foot verification.
The legacy front binding uses `characters/hoodie/` and `motions/reference-run.json`.
Both require identical travel endpoints, numeric speed, and no side `footLock`,
`travelMode` or standing `transitions`. `FRONT_RUN_IN_PLACE` discloses that the
saved projected gait is not depth travel. Source anchor, canvas size and cycle
are pinned per clip; mixed front/side scenes do not share one source config.

The [DICE adapter](dice-character-adapter.md) uses a separate unchanged SVG and
controller snapshot. It shares motion scheduling, not the hoodie's drawing or
bone lengths, and emits `DICE_RETARGET_TRIAL`. A successful hoodie test does not
approve the resulting DICE motion.

The bridge calls `frame(..., clean=True)` and embeds each returned SVG as an
isolated SVG image data URI in the scene SVG, then rasterizes that composite.
This avoids collisions between actors' IDs, references, and CSS selectors without
changing saved action geometry. Do not inline the raw SVG elements into a shared
document without namespacing them.

## Validation contract

The schema rejects unknown fields, unsupported versions/action names/views,
invalid colors, nonpositive dimensions/times/scales/speeds, and malformed points.
Strict-text checks (syntax and duplicate keys) run in `loadScene` before
`validateScene`; already parsed objects cannot retain duplicate-key evidence.
The schema cannot enforce all relationships. The implemented validator also:

1. Rejects nonstandard JSON numbers (`NaN`, infinity), duplicate object keys, and
   any non-finite calculated values. Never execute scene data as JavaScript.
2. Checks unique actor IDs, clip references, action/view compatibility, and that
   registered source assets exist. Reject unknown bindings; never substitute.
3. Converts times to whole frames; requires clips to end within output duration.
4. Rejects same-actor overlaps, including clips supplied out of time order.
   Adjacent half-open clips are allowed; source-array order breaks no ties.
5. Requires `0 <= groundY <= output.height`, horizontal travel on that ground,
   and nonnegative X displacement for right-facing / nonpositive for left-facing.
6. Checks opt-in travel calibration, cadence compatibility and range; emits
   `UNLOCKED_TRAVEL` for unlocked motion, `POSE_PRESERVING_TRAVEL` for default locked
   travel, or `SUPPORT_LEG_TRAVEL` for the opt-in leg solver. Locked
   motion. Warning-free output does not establish natural motion or likeness.

Diagnostics should include a stable code, JSON pointer, and readable explanation,
for example `ACTION_VIEW_MISMATCH` at `/clips/0/action`. Structural errors should
use `SCHEMA_INVALID`; frame, timing, reference, and asset checks should have
separate codes. Errors block sampling/export. Warnings remain visible.

## Next implementation boundary

The engine tests cover the example, stationary travel, mirrored left travel,
adjacent clips, unknown actors, duplicate IDs, mismatched views, fractional
frames, out-of-range ends, unsorted overlaps, invalid ground placement,
non-finite numbers, typos, and shuffled frame requests.

`sampleScene(prepared, time)` returns visible actors, action-local times,
placement, and draw order from a validated snapshot. Sampling uses no wall clock,
file reads, or mutable playhead. Pure engine sampling and cached rendering
adapters are separate layers.

The action bridge, isolated SVG composition, and exact-frame video export are
implemented in `tools/render_scene.py` and `engine/src/render.ts`. The engine
guide documents commands, resource limits, and report status. The project-local
[cutout-scene skill](../.opencode/skills/cutout-scene/SKILL.md) guides JSON
authoring and inspection. Passing technical checks is not visual acceptance.
