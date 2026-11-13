import json
import copy
import hashlib
import io
import math
import re
import unittest
import xml.etree.ElementTree as ET

from tools.animate import frame_svg, calibrate_soles, raster
from tools.motion import Humanoid, sample, solve_projected_leg
from tools.preview import ROOT, load_character, apply_pose, interpolate_path


def world_point(tree, name, point):
    nodes = {e.get("id"): e for e in tree.iter() if e.get("id")}
    parents = {child: parent for parent in tree.iter() for child in parent}
    node, (x, y) = nodes[name], point
    while node is not None:
        for operation, arguments in reversed(re.findall(r"(translate|rotate|scale)\(([^)]+)\)", node.get("transform", ""))):
            values = [float(value) for value in re.split(r"[ ,]+", arguments.strip())]
            if operation == "translate":
                x, y = x + values[0], y + (values[1] if len(values) > 1 else 0)
            elif operation == "scale":
                x, y = x * values[0], y * (values[1] if len(values) > 1 else values[0])
            else:
                angle = math.radians(values[0])
                x, y = x * math.cos(angle) - y * math.sin(angle), x * math.sin(angle) + y * math.cos(angle)
        node = parents.get(node)
    return x, y


def asymmetric_fixture(tree, rig):
    tree = copy.deepcopy(tree)
    spec = json.loads((ROOT / 'tests/fixtures/asymmetric.json').read_text())
    nodes = {e.get('id'): e for e in tree.iter() if e.get('id')}
    for side in ['left', 'right']:
        settings = spec[side]
        nodes[f'hip-{side}'].set('transform', f"translate({settings['hip'][0]} {settings['hip'][1]})")
        nodes[f'knee-{side}'].set('transform', f"translate(0 {settings['upper']})")
        nodes[f'ankle-{side}'].set('transform', f"translate(0 {settings['lower']})")
        for part in ['upper', 'lower']:
            # Simple fixture artwork matches its altered limb length; this is
            # not a visual approval of a stretched copy of the hoodie character.
            nodes[rig['motion_geometry'][f'{part}-{side}']].set('d', f"M-30-25H30V{settings[part]+20}H-30Z")
        ankle = nodes[f'ankle-{side}']
        wrapper = ET.Element('{http://www.w3.org/2000/svg}g', {'transform': f"scale({settings['shoe_scale'][0]} {settings['shoe_scale'][1]})"})
        for child in list(ankle):
            ankle.remove(child)
            wrapper.append(child)
        ankle.append(wrapper)
    return tree, spec


class MotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree, cls.rig = load_character(ROOT / "characters/hoodie")
        # Pure math tests use the authored markers; raster calibration is a
        # separate measured step when rendering the actual character.
        cls.soles = {side: cls.rig["attachments"][f"sole-{side}"]["point"] for side in ["left", "right"]}
        cls.model = Humanoid(cls.tree, cls.rig, cls.soles)
        cls.timeline = json.loads((ROOT / "motions/walk-jump-run.json").read_text())

    def test_every_frame_reaches_target_and_keeps_planted_contacts(self):
        count = round(sum(s["duration"] for s in self.timeline["segments"]) * self.timeline["fps"])
        previous = None
        walk_frames, run_air_frames, jump_clearance = 0, 0, 0
        for frame in range(count):
            data, record = frame_svg(self.tree, self.rig, self.model, self.timeline, frame / self.timeline["fps"], frame)
            tree = ET.ElementTree(ET.fromstring(data))
            for side, foot in record["contacts"].items():
                actual = world_point(tree, f"ankle-{side}", self.soles[side])
                self.assertAlmostEqual(actual[0], foot["x"], places=8)
                self.assertAlmostEqual(actual[1], foot["target_y"], places=8)
                self.assertLessEqual(actual[1], self.timeline["floor"] + 1e-8)
                if foot["planted"]:
                    self.assertAlmostEqual(actual[1], self.timeline["floor"], places=8)
                    if previous and previous[side]["planted"]:
                        self.assertAlmostEqual(actual[0], previous[side]["x"], places=8)
                        self.assertAlmostEqual(actual[1], previous[side]["y"], places=8)
            contacts = record["contacts"]
            if record["action"] == "walk":
                self.assertTrue(any(foot["planted"] for foot in contacts.values()))
                walk_frames += 1
            if record["action"] == "run" and not any(foot["planted"] for foot in contacts.values()):
                run_air_frames += 1
            if record["action"] == "jump":
                jump_clearance = max(jump_clearance, min(self.timeline["floor"] - foot["y"] for foot in contacts.values()))
            previous = contacts
        self.assertEqual(count, 288)
        self.assertGreater(walk_frames, 60)
        self.assertGreater(run_air_frames, 10)
        self.assertGreater(jump_clearance, 50)

    def test_jump_and_run_are_continuous_at_sampled_frames(self):
        states = [sample(frame / 30, self.model, self.timeline) for frame in range(288)]
        for before, after in zip(states, states[1:]):
            limit = 1.0 if after['action'] == before['action'] == 'walk' else 5.0 if after['action'] == before['action'] == 'run' else 14.0
            self.assertLess(abs(after["height"] - before["height"]) * self.timeline["scale"], limit)
            for side in self.soles:
                self.assertLess(abs(after["feet"][side]["lift"] - before["feet"][side]["lift"]) * self.timeline["scale"], 25)

    def test_contact_and_action_boundaries_have_no_position_or_root_velocity_jumps(self):
        boundaries = []
        start = 0
        for segment in self.timeline['segments']:
            action, duration = segment['action'], segment['duration']
            if action in ['walk', 'run']:
                config = self.timeline[action]
                for cycle in range(math.ceil(duration / config['cycle'])+1):
                    for offset in [0, 0.5, config['stance'], (config['stance']+0.5) % 1]:
                        local = (cycle+offset)*config['cycle']
                        if 0 < local < duration:
                            boundaries.append(start+local)
            start += duration
            boundaries.append(start)
        duration = start
        for boundary in boundaries:
            if not 0 < boundary < duration:
                continue
            epsilon = 1e-7
            left = sample(boundary-epsilon, self.model, self.timeline)
            middle = sample(boundary, self.model, self.timeline)
            right = sample(boundary+epsilon, self.model, self.timeline)
            self.assertLess(abs(left['height']-right['height']), 0.001, boundary)
            velocity_left = (middle['height']-left['height'])/epsilon
            velocity_right = (right['height']-middle['height'])/epsilon
            self.assertLess(abs(velocity_left-velocity_right), 0.1, boundary)
            for side in self.soles:
                self.assertLess(abs(left['feet'][side]['lift']-right['feet'][side]['lift']), 0.001, (boundary, side))
                for joint in [0, 1]:
                    a, b, c = [state['leg_angles'][side][joint] for state in [left, middle, right]]
                    self.assertLess(abs((b-a)/epsilon-(c-b)/epsilon), 0.01, (boundary, side, joint))

    def test_jump_takeoff_and_landing_match_flight_velocity(self):
        start = sum(s['duration'] for s in self.timeline['segments'][:3])
        duration = self.timeline['segments'][3]['duration']
        expected_speed = 4*self.timeline['jump']['height']*self.model.length/(0.38*duration)
        for fraction, expected in [(0.34, expected_speed), (0.72, -expected_speed)]:
            boundary, epsilon = start+fraction*duration, 1e-6
            h = sample(boundary, self.model, self.timeline)['height']
            left = (h-sample(boundary-epsilon, self.model, self.timeline)['height'])/epsilon
            right = (sample(boundary+epsilon, self.model, self.timeline)['height']-h)/epsilon
            self.assertAlmostEqual(left, expected, delta=0.02)
            self.assertAlmostEqual(right, expected, delta=0.02)

    def test_gaits_have_weight_transfer_knee_articulation_and_run_clearance(self):
        states = [sample(frame/30, self.model, self.timeline) for frame in range(288)]
        for action in ['walk', 'run']:
            gait = [s for s in states if s['action'] == action]
            self.assertGreater(max(abs(s['sway']) for s in gait)*self.timeline['scale'], 5)
            self.assertGreater(max(abs(s['leg_angles']['left'][1]) for s in gait), 0.2)
        air = [s for s in states if s['action']=='run' and not any(f['contact'] for f in s['feet'].values())]
        self.assertGreater(max(min(f['lift'] for f in s['feet'].values()) for s in air)*self.timeline['scale'], 5)

    def test_running_hands_remain_separated_on_their_own_sides(self):
        right_heights, left_heights = [], []
        for frame in range(177, 267):
            data, _ = frame_svg(self.tree, self.rig, self.model, self.timeline, frame/30, frame)
            tree = ET.ElementTree(ET.fromstring(data))
            center = world_point(tree, 'root', (0, 0))[0]
            right = world_point(tree, 'wrist-right', (0, 45))
            left = world_point(tree, 'wrist-left', (0, 45))
            self.assertLess(right[0], center-5, frame)
            self.assertGreater(left[0], center+5, frame)
            self.assertGreater(left[0]-right[0], 25, frame)
            right_heights.append(right[1])
            left_heights.append(left[1])
        self.assertGreater(max(right_heights)-min(right_heights), 8)
        self.assertGreater(max(left_heights)-min(left_heights), 8)

    def test_knees_stay_subtle_at_rest_and_bounded_during_motion(self):
        for frame in range(288):
            state = sample(frame/30, self.model, self.timeline)
            for angles in state['leg_angles'].values():
                limit = 5 if state['action'] == 'idle' else 25
                self.assertLess(abs(math.degrees(angles[1])), limit, frame)

    def test_running_hands_alternate_relative_to_body_not_just_root_bob(self):
        heights = {'left': [], 'right': []}
        for frame in range(188, 255):
            data, _ = frame_svg(self.tree, self.rig, self.model, self.timeline, frame/30, frame)
            tree = ET.ElementTree(ET.fromstring(data))
            root_y = world_point(tree, 'root', (0, 0))[1]
            for side in heights:
                heights[side].append(world_point(tree, f'wrist-{side}', (0, 45))[1]-root_y)
        for values in heights.values():
            self.assertGreater(max(values)-min(values), 25)
        differences = [left-right for left, right in zip(heights['left'], heights['right'])]
        self.assertGreater(max(differences), 20)
        self.assertLess(min(differences), -20)

    def test_arm_only_pass_preserves_gait_idle_and_jump_snapshots(self):
        expected = json.loads((ROOT/'tests/fixtures/arm-preservation.json').read_text())
        states = [sample(frame/30, self.model, self.timeline) for frame in range(288)]
        keys = ['height', 'sway', 'feet', 'lengths', 'leg_angles']
        digest = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(digest([{key: state[key] for key in keys} for state in states]), expected['leg_root_sha256'])
        self.assertEqual(digest([state for state in states if state['action'] in ['idle', 'jump']]), expected['idle_jump_sha256'])

    def test_arm_depth_alternates_opposite_the_legs(self):
        foreground = {'left': False, 'right': False}
        rear = {'left': False, 'right': False}
        for frame in list(range(26, 88))+list(range(188, 255)):
            state = sample(frame/30, self.model, self.timeline)
            depth = state['pose']['arm_depth']
            self.assertAlmostEqual(depth['left'], -depth['right'])
            for side in foreground:
                weight = state['pose']['layers']['forearm_blend'][f'elbow-{side}']
                foreground[side] |= weight > 0.95
                rear[side] |= weight < 0.05
                foot_depth = state['feet'][side]['depth']
                if abs(depth[side]) > 0.4 and abs(foot_depth) > self.model.length*0.04:
                    self.assertLess(depth[side]*foot_depth, 0)
        self.assertTrue(all(foreground.values()))
        self.assertTrue(all(rear.values()))

    def test_soft_depth_copies_keep_original_arm_hierarchy_and_alignment(self):
        for frame in [30, 50, 195, 203, 211]:
            data, _ = frame_svg(self.tree, self.rig, self.model, self.timeline, frame/30, frame)
            tree = ET.ElementTree(ET.fromstring(data))
            nodes = {e.get('id'):e for e in tree.iter() if e.get('id')}
            ids = [e.get('id') for e in tree.iter() if e.get('id')]
            self.assertEqual(len(ids), len(set(ids)))
            for side in ['left', 'right']:
                self.assertIn(nodes[f'elbow-{side}'], list(nodes[f'shoulder-{side}']))
                duplicate = f'wrist-{side}-front-copy'
                if duplicate in nodes:
                    before = world_point(tree, f'wrist-{side}', (0,45))
                    after = world_point(tree, duplicate, (0,45))
                    for a, b in zip(before, after):
                        self.assertAlmostEqual(a, b, places=8)

    def test_arm_depth_crossings_are_smooth(self):
        for action_start, action in [(0.5, 'walk'), (5.9, 'run')]:
            cycle = self.timeline[action]['cycle']
            zero = self.timeline[action]['stance']/2
            for phase in [zero, zero+0.5, zero+1, zero+1.5]:
                t = action_start+phase*cycle
                left = sample(t-1e-6, self.model, self.timeline)['pose']
                right = sample(t+1e-6, self.model, self.timeline)['pose']
                for side in ['left', 'right']:
                    self.assertLess(abs(left['layers']['forearm_blend'][f'elbow-{side}']-right['layers']['forearm_blend'][f'elbow-{side}']), 0.001)
                    for joint in ['shoulder','elbow','wrist']:
                        self.assertLess(abs(left['angles'][f'{joint}-{side}']-right['angles'][f'{joint}-{side}']), 0.01)

    def test_running_arm_spread_and_frame_spacing_are_restrained(self):
        previous = None
        for frame in range(177, 267):
            angles = sample(frame/30, self.model, self.timeline)['pose']['angles']
            for side in ['left', 'right']:
                shoulder = angles[f'shoulder-{side}'] + math.degrees(self.model.arms[side]['rest_angle'])
                self.assertLess(abs(shoulder), 42, (frame, side))
                if previous:
                    self.assertLess(abs(angles[f'elbow-{side}']-previous[f'elbow-{side}']), 25, (frame, side))
            previous = angles

    def test_settled_running_elbows_stay_folded_and_wrists_neutral(self):
        for frame in range(188,255):
            pose = sample(frame/30,self.model,self.timeline)['pose']
            for side in ['left','right']:
                bend = abs(pose['angles'][f'elbow-{side}'])
                self.assertGreaterEqual(bend,80,(frame,side))
                self.assertLessEqual(bend,100,(frame,side))
                self.assertLessEqual(abs(pose['angles'][f'wrist-{side}']),3.000001)
                self.assertEqual(pose['hand_curl'][side],1)

    def test_running_experiment_does_not_change_walk_idle_or_jump(self):
        expected = json.loads((ROOT/'tests/fixtures/run-arm-preservation.json').read_text())
        states = [sample(i/30,self.model,self.timeline) for i in range(288)]
        non_run = [state for state in states if state['action']!='run']
        actual = hashlib.sha256(json.dumps(non_run,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(actual,expected['non_run_sha256'])

    def test_hand_curl_morph_is_matched_and_keeps_original_source(self):
        original = ET.tostring(self.tree.getroot())
        nodes = {e.get('id'):e for e in self.tree.iter() if e.get('id')}
        for weight in [0,0.25,0.5,0.75,1]:
            posed = apply_pose(self.tree,self.rig,{'hand_curl':{'left':weight,'right':weight}})
            actual = {e.get('id'):e for e in posed.iter() if e.get('id')}
            for side in ['left','right']:
                for part in ['outline','lines']:
                    name = f'hand-{part}-{side}'
                    self.assertEqual(actual[name].get('d'),interpolate_path(nodes[name].get('d'),self.rig['hand_morph'][part],weight))
        self.assertEqual(ET.tostring(self.tree.getroot()),original)
        for weight in [-1,2,float('nan')]:
            with self.assertRaises(ValueError):
                apply_pose(self.tree,self.rig,{'hand_curl':{'left':weight}})
        with self.assertRaises(ValueError):
            interpolate_path('M0 0L1 1','M0 0Q1 1 2 2',0.5)

    def test_partial_depth_reveal_uses_opaque_pixels_not_translucent_limbs(self):
        try:
            import gi, cairo
            from PIL import Image, ImageChops
        except ImportError:
            self.skipTest('Raster occlusion check needs GI, Cairo and Pillow')
        pose = sample(261/30, self.model, self.timeline)['pose']

        def render(side, weight):
            settings = copy.deepcopy(pose)
            settings['layers']['forearm_blend'][f'elbow-{side}'] = weight
            posed = apply_pose(self.tree, self.rig, settings)
            buffer = io.BytesIO()
            raster(ET.tostring(posed.getroot()), 640, 1000).write_to_png(buffer)
            return Image.open(buffer).convert('RGB')

        def distance(a, b):
            red, green, blue = ImageChops.difference(a, b).split()
            return ImageChops.lighter(ImageChops.lighter(red, green), blue)

        for side in ['left', 'right']:
            rear, front = render(side, 0), render(side, 1)
            for weight in [0.25, 0.5, 0.75]:
                partial = render(side, weight)
                # Every interior pixel should be from the opaque front OR rear
                # render, not a mix of skin and hoodie. Allow a narrow AA edge.
                error = ImageChops.darker(distance(partial, rear), distance(partial, front))
                unmatched = sum(error.histogram()[13:])
                self.assertLess(unmatched, 50, (side, weight, unmatched))

    def test_invalid_arm_projection_and_depth_settings_rejected(self):
        poses = [
            {'arm_projection': {'left': {'upper': 0.2, 'lower': 1}}},
            {'arm_projection': {'tail': {'upper': 1, 'lower': 1}}},
            {'layers': {'forearm_blend': {'elbow-left': 1.1}}},
            {'layers': {'forearm_blend': {'elbow-left': float('nan')}}},
            {'layers': {'forearm_blend': {'elbow-left': 0.5}, 'front_forearms': ['elbow-left']}},
        ]
        for pose in poses:
            with self.assertRaises(ValueError):
                apply_pose(self.tree, self.rig, pose)

    def test_offset_unequal_leg_fixture_preserves_contacts(self):
        fixture, spec = asymmetric_fixture(self.tree, self.rig)
        soles = {side: [self.soles[side][0]*spec[side]['shoe_scale'][0], self.soles[side][1]*spec[side]['shoe_scale'][1]] for side in self.soles}
        model = Humanoid(fixture, self.rig, soles)
        for frame in range(288):
            data, record = frame_svg(fixture, self.rig, model, self.timeline, frame/30, frame)
            tree = ET.ElementTree(ET.fromstring(data))
            # Contacts are expressed in ankle coordinates outside the fixture's
            # extra artwork scale, as they are after actual raster calibration.
            for side, foot in record['contacts'].items():
                point = world_point(tree, f'ankle-{side}', soles[side])
                self.assertAlmostEqual(point[0], foot['target_x'], places=8)
                self.assertAlmostEqual(point[1], foot['target_y'], places=8)

    def test_shoe_calibration_covers_artwork_outside_old_fixed_viewport(self):
        try:
            import gi, cairo, PIL
        except ImportError:
            self.skipTest('Raster calibration needs GI, Cairo and Pillow')
        fixture, _ = asymmetric_fixture(self.tree, self.rig)
        soles = calibrate_soles(fixture)
        self.assertGreater(soles['right'][1], 150)
        self.assertGreater(soles['left'][1], 90)
        model = Humanoid(fixture, self.rig, soles)
        for frame in [0, 38, 130, 145, 195, 220, 240]:
            data, record = frame_svg(fixture, self.rig, model, self.timeline, frame/30, frame)
            tree = ET.ElementTree(ET.fromstring(data))
            for side, foot in record['contacts'].items():
                point = world_point(tree, f'ankle-{side}', soles[side])
                self.assertAlmostEqual(point[0], foot['target_x'], places=8)
                self.assertAlmostEqual(point[1], foot['target_y'], places=8)

    def test_unsupported_motion_artwork_is_rejected(self):
        rig = copy.deepcopy(self.rig)
        rig['motion_geometry']['upper-left'] = 'head-shape'
        with self.assertRaises(ValueError):
            Humanoid(self.tree, rig, self.soles)

    def test_solver_projects_to_requested_height(self):
        for upper, lower in [(151, 140), (110, 100), (190, 180)]:
            for depth in [-50, 0, 50]:
                vertical = 0.85 * (upper + lower)
                a, b = solve_projected_leg(upper, lower, vertical, depth)
                self.assertAlmostEqual(a + b, vertical, places=8)

    def test_unreachable_target_rejected(self):
        with self.assertRaises(ValueError):
            solve_projected_leg(151, 140, 400, 0)

    def test_out_of_range_time_rejected(self):
        with self.assertRaises(ValueError):
            sample(100, self.model, self.timeline)


if __name__ == "__main__":
    unittest.main()
