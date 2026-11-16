import copy
import math
import unittest

from tools.preview import ROOT
from tools.side_actions import load_side_action
from tools.side_review import pose_character, world_point
from tools.support_run import SupportRun
from tools.travel_run import TravelRun, SOURCES
from tools.render_scene import SceneRenderer
from test_side_transition import delivered_point
from test_travel_run import shoe_pixels


STRIDE = 472.38108823166925


def actor_at(t, facing='right', scale=1, run_duration=2):
    sign = 1 if facing == 'right' else -1
    velocity = sign*STRIDE*scale
    local = max(0, min(run_duration, t-1))
    x = 640 + velocity*local
    actor = {'id': 'runner', 'clipIndex': 0, 'action': f'side-run-{facing}',
             'duration': 4, 'speed': 0.625, 'localTime': local,
             'sourceAnchor': [640, 650], 'position': [x, 620], 'scale': scale,
             'transform': [scale, 0, 0, scale, x-640*scale, 620-650*scale],
             'footLock': True, 'travelMode': 'support-leg', 'travelVelocity': velocity}
    actor['runDuration'] = run_duration
    if t < 0.5 or t >= 1.5+run_duration:
        actor['transition'] = {'mode': 'stand', 'weight': 0}
    elif t < 1 or t >= 1+run_duration:
        mode = 'start' if t < 1 else 'stop'
        u = (t-0.5)/0.5 if mode == 'start' else (t-1-run_duration)/0.5
        weight = u*u*(3-2*u)
        actor['transition'] = {'mode': mode, 'weight': weight if mode == 'start' else 1-weight,
                               'duration': 0.5, 'progress': u}
    return actor


def frame(renderer, actor):
    return renderer.frame({'output': {'width': 2560, 'height': 900},
                           'stage': {'background': '#ffffff'}, 'actors': [actor]}, 0)


class SupportRunTests(unittest.TestCase):
    def test_boundary_ramps_transfer_part_of_the_correction_without_moving_the_toe(self):
        for facing in ['right', 'left']:
            renderer = SceneRenderer()
            weights = []
            for time in [0, .05, .1, .15, .2, 1, 1.8, 1.85, 1.9, 1.95, 2]:
                actor = actor_at(1+time, facing)
                # The endpoint here is a running sample, not the stop blend.
                actor.pop('transition', None)
                svg, records = frame(renderer, actor)
                locking = records[0]['horizontalLock']
                ik = records[0]['sourceContacts']['supportIK']
                weights.append(ik['transferWeight'])
                self.assertAlmostEqual(ik['transferredRootOffsetX'] + ik['remainingRootOffsetX'], ik['previousRootOffsetX'], places=7)
                self.assertAlmostEqual(delivered_point(svg, 'root', (0, 0))[0], actor['position'][0] + ik['remainingRootOffsetX'], places=6)
                if locking['mode'] == 'stance':
                    toe = delivered_point(svg, f"ankle-{locking['side']}", (75, 49))
                    self.assertAlmostEqual(toe[0], locking['anchorX'], places=6)
            self.assertEqual(weights[0], 0)
            self.assertEqual(weights[-1], 0)
            self.assertEqual(weights[3:8], [1]*5)
            self.assertGreater(weights[1], 0)
            self.assertLess(weights[1], 1)

    def test_dense_mirrored_scaled_feet_preserve_stance_and_release_swing_with_fixed_lengths(self):
        for facing, sign in [('right', 1), ('left', -1)]:
            for speed, scale in [(0.3125, 0.5), (0.625, 1), (1.25, 1.2)]:
                base = load_side_action(f'side-run-{facing}', speed=speed)
                velocity = sign*STRIDE*speed/0.625*scale
                action = SupportRun(base, velocity, scale)
                travel = TravelRun(base)
                for i in range(121):
                    t = i/120*base.config['cycle']
                    key, report = action.solve(t)
                    original = base.sample(t)
                    old, _ = base.pose(t)
                    new = pose_character(action.tree, action.rig, key)
                    offset, _ = travel.correction(t, velocity, scale, 0)
                    self.assertLessEqual(report['hipDrop'], 5.2*scale)
                    self.assertGreaterEqual(report['hipDrop'], 0)
                    self.assertLess(report['maxJointChangeDegrees'], 34)
                    for name in original['angles']:
                        if not name.startswith(('hip-', 'knee-', 'ankle-')):
                            self.assertAlmostEqual(key['angles'][name], original['angles'][name], places=8)
                    for side in ['left', 'right']:
                        a = world_point(old, f'ankle-{side}', base.rig['review']['toe'])
                        b = world_point(new, f'ankle-{side}', base.rig['review']['toe'])
                        local = (i/120 - (0.5 if side == 'left' else 0)) % 1
                        displacement = sign*(b[0]-a[0])*base.config['scale']*scale
                        self.assertAlmostEqual(displacement, report['legOffsetX'][side], places=6)
                        if local <= .26:
                            self.assertAlmostEqual(displacement, offset, places=6)
                        elif .5 <= local <= .76:
                            self.assertAlmostEqual(displacement, 0, places=6)
                        else:
                            self.assertLessEqual(abs(displacement), abs(offset)+1e-6)
                            self.assertGreaterEqual(displacement*offset, -1e-6)
                        self.assertAlmostEqual((a[1]-b[1])*base.config['scale']*scale, report['recoveryLift'][side], places=6)
                        if local <= .26 or local >= .5:
                            self.assertAlmostEqual(report['recoveryLift'][side], 0, places=6)
                        self.assertLessEqual(report['recoveryLift'][side], 18.8*scale)
                        points = [world_point(new, f'{joint}-{side}', (0, 0)) for joint in ['hip', 'knee', 'ankle']]
                        self.assertAlmostEqual(math.dist(points[0], points[1]), 145, places=6)
                        self.assertAlmostEqual(math.dist(points[1], points[2]), 158, places=6)
                        old_shoe = sum(original['angles'][f'{j}-{side}'] for j in ['hip', 'knee', 'ankle'])
                        self.assertAlmostEqual(sum(key['angles'][f'{j}-{side}'] for j in ['hip', 'knee', 'ankle']), old_shoe, places=6)

    def test_exchange_has_no_backward_swing_tug_or_support_knee_relock(self):
        for facing, sign in [('right', 1), ('left', -1)]:
            for speed, scale in [(.3125, .5), (.625, 1), (1.25, 1.2)]:
                base = load_side_action(f'side-run-{facing}', speed=speed)
                action = SupportRun(base, sign*STRIDE*speed/.625*scale, scale)
                for support, swing, offset in [('right', 'left', 0), ('left', 'right', .5)]:
                    # The reference held the airborne ankle back another 36 px
                    # over these four intervals, despite steady body travel.
                    positions = []
                    for phase in [0, 1/30, 2/30, 3/30, 4/30]:
                        posed, _ = action.pose((offset+phase)*base.config['cycle'])
                        hip = world_point(posed, f'hip-{swing}', (0, 0))
                        ankle = world_point(posed, f'ankle-{swing}', (0, 0))
                        positions.append((ankle[0]-hip[0])*base.config['scale'])
                    self.assertTrue(all(b >= a-.1 for a, b in zip(positions, positions[1:])), positions)
                    knees = [action.sample((offset+p)*base.config['cycle'])['angles'][f'knee-{support}']
                             for p in [4/30, 5/30, 6/30, 7/30, 8/30]]
                    self.assertTrue(all(b < a for a, b in zip(knees, knees[1:])), knees)
                    self.assertGreater(min(knees), 10)

    def test_swing_transfer_joins_have_continuous_ankle_velocity(self):
        base = load_side_action('side-run-right', speed=.625)
        action = SupportRun(base, STRIDE, 1)
        h = 1e-5
        for seam in [.26, .5, .76, 1]:
            poses = [action.pose(seam+d)[0] for d in [-h, 0, h]]
            for side in ['left', 'right']:
                points = [world_point(p, f'ankle-{side}', (0, 0)) for p in poses]
                for axis in [0, 1]:
                    a, b, c = [p[axis] for p in points]
                    self.assertLess(abs((b-a)/h-(c-b)/h), 2, (seam, side, axis))

    def test_released_knee_folds_promptly_instead_of_holding_near_full_extension(self):
        for facing, sign in [('right', 1), ('left', -1)]:
            for speed in [.3125, .625, 1.25]:
                base = load_side_action(f'side-run-{facing}', speed=speed)
                action = SupportRun(base, sign*STRIDE*speed/.625, 1)
                for side, offset in [('right', 0), ('left', .5)]:
                    # After toe-off at phase .26, the former adapter held this
                    # knee around 6.6 degrees through phase .30 (~two frames).
                    key = action.sample((offset+.30)*base.config['cycle'])
                    self.assertGreater(key['angles'][f'knee-{side}'], 30)
                    _, info = action.solve((offset+.30)*base.config['cycle'])
                    self.assertGreater(info['recoveryLift'][side], 10)
                    for phase in [.26, .5]:
                        _, endpoint = action.solve((offset+phase)*base.config['cycle'])
                        self.assertAlmostEqual(endpoint['recoveryLift'][side], 0, places=8)

    def test_delivered_knee_flexes_by_the_second_recovery_frame(self):
        for facing in ['right', 'left']:
            for side, offset in [('right', 0), ('left', .5)]:
                svg, _ = frame(SceneRenderer(), actor_at(1.30+offset, facing))
                hip, knee, ankle = [delivered_point(svg, f'{joint}-{side}', (0, 0)) for joint in ['hip', 'knee', 'ankle']]
                upper = (knee[0]-hip[0], knee[1]-hip[1])
                lower = (ankle[0]-knee[0], ankle[1]-knee[1])
                cosine = sum(a*b for a,b in zip(upper,lower))/(math.hypot(*upper)*math.hypot(*lower))
                self.assertGreater(math.degrees(math.acos(max(-1,min(1,cosine)))), 30)

    def test_actual_flat_stance_shoe_pixels_remain_anchored_with_linear_body_x(self):
        for facing in ['right', 'left']:
            centers = []
            renderer = SceneRenderer()
            for t in [2, 2.1]:
                actor = actor_at(t, facing)
                # Fit the isolated-shoe helper's fixed 1280x720 raster.
                actor['position'][0] = 640 + actor['travelVelocity']*(t-1)
                actor['transform'][4] = actor['position'][0]-640
                sample = {'output': {'width': 1280, 'height': 720}, 'stage': {'background': '#ffffff'}, 'actors': [actor]}
                svg, records = renderer.frame(sample, 0)
                bounds = shoe_pixels(svg, 'right')
                self.assertIsNotNone(bounds)
                centers.append((bounds[0]+bounds[2])/2)
                self.assertLessEqual(abs(bounds[3]-620), 1.25)
                self.assertEqual(records[0]['horizontalLock']['rootOffsetX'], 0)
                self.assertAlmostEqual(delivered_point(svg, 'root', (0, 0))[0], actor['position'][0], places=6)
            self.assertLessEqual(abs(centers[1]-centers[0]), 1)

    def test_standing_is_unchanged_and_delivered_joins_keep_horizontal_velocity(self):
        for facing in ['right', 'left']:
            for scale in [0.5, 1.1]:
                for duration in [0.5, 2]:
                    renderer = SceneRenderer()
                    for t in [0, 0.6, 0.8, 1.1+duration, 1.3+duration, 1.75+duration]:
                        actor = actor_at(t, facing, scale, duration)
                        svg, _ = frame(renderer, actor)
                        legacy = copy.deepcopy(actor); del legacy['travelMode']
                        before, _ = frame(SceneRenderer(), legacy)
                        for joint in ['root', 'head', 'ankle-left', 'ankle-right']:
                            for a, b in zip(delivered_point(svg, joint, (0, 0)), delivered_point(before, joint, (0, 0))):
                                self.assertAlmostEqual(a, b, places=6)
                    h = 1e-5
                    for seam in [0.5, 1, 1+duration, 1.5+duration]:
                        svgs = [frame(renderer, actor_at(seam+d, facing, scale, duration))[0] for d in [-h, 0, h]]
                        for joint in ['root', 'head', 'wrist-left', 'wrist-right', 'ankle-left', 'ankle-right']:
                            a, b, c = [delivered_point(svg, joint, (0, 0))[0] for svg in svgs]
                            self.assertLess(abs((b-a)/h-(c-b)/h), 1.5, (facing, scale, duration, seam, joint))

    def test_scrubbing_and_source_preservation(self):
        originals = {name: (ROOT/name).read_bytes() for name in (*SOURCES, 'poses/side-stand.json')}
        base = load_side_action('side-run-right', speed=.625)
        before = base.frame(.18, 0, clean=True)
        action = SupportRun(base, STRIDE, 1)
        expected = [action.sample(i/40) for i in range(41)]
        for i in reversed(range(41)):
            self.assertEqual(action.sample(i/40), expected[i])
            self.assertEqual(action.sample(i/40+2), expected[i])
        self.assertEqual(base.frame(.18, 0, clean=True), before)
        self.assertEqual({name: (ROOT/name).read_bytes() for name in originals}, originals)

    def test_invalid_or_unreachable_requests_fail_without_stretching(self):
        base = load_side_action('side-run-right', speed=.625)
        for velocity, scale in [(0, 1), (math.inf, 1), (STRIDE, 0)]:
            with self.assertRaises(ValueError):
                SupportRun(base, velocity, scale)
        action = SupportRun(base, 100000, 1)
        with self.assertRaises(ValueError):
            action.sample(.2)
        for t in [-1, math.nan, math.inf]:
            with self.assertRaises(ValueError):
                SupportRun(base, STRIDE, 1).sample(t)


if __name__ == '__main__':
    unittest.main()
