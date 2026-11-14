import copy
import hashlib
import io
import json
import math
import unittest
import xml.etree.ElementTree as ET

from tools.animate import raster
from tools.preview import ROOT, SVG
from tools.side_review import pose_character, world_point
from tools.side_run import SideRun, periodic_curve


class SideRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((ROOT/'motions/side-run-preview.json').read_text())
        cls.motion = SideRun(ROOT/'characters/hoodie-side', ROOT/'poses/side-run.json', cls.config)

    def test_preview_is_exactly_150_frames_and_eight_full_cycles(self):
        self.assertEqual(self.config['duration']*self.config['fps'], 150)
        self.assertEqual(self.config['duration']/self.config['cycle'], 8)

    def test_interpolation_keeps_authored_angles_at_every_key(self):
        for phase, key in zip(self.motion.phases, self.motion.keys):
            sample = self.motion.sample(phase*self.config['cycle'])
            for joint, angle in key['angles'].items():
                self.assertAlmostEqual(sample['angles'][joint], angle, places=8)

    def test_periodic_curve_has_no_value_or_velocity_seam(self):
        epsilon = 1e-6
        for channel in [*self.motion.channels.values(), self.motion.root_heights]:
            at = periodic_curve(0, self.motion.phases, channel)
            before = periodic_curve(1-epsilon, self.motion.phases, channel)
            after = periodic_curve(epsilon, self.motion.phases, channel)
            self.assertAlmostEqual(at, periodic_curve(1, self.motion.phases, channel))
            self.assertLess(abs((at-before)/epsilon-(after-at)/epsilon), 0.1)

    def test_interpolated_angles_are_bounded_by_authored_ranges(self):
        for i in range(150):
            sample = self.motion.sample(i/30)
            for joint, value in sample['angles'].items():
                self.assertTrue(math.isfinite(value))
                if joint.startswith('elbow-'):
                    # Continuous pump extremes fall between the review keys.
                    self.assertGreaterEqual(value, -125)
                    self.assertLessEqual(value, -40)
                    continue
                if joint.startswith('shoulder-'):
                    self.assertGreaterEqual(value, -25)
                    self.assertLessEqual(value, 65)
                    continue
                self.assertGreaterEqual(value, min(self.motion.channels[joint])-1e-8)
                self.assertLessEqual(value, max(self.motion.channels[joint])+1e-8)

    def test_ground_clearance_and_source_preservation_for_all_frames(self):
        original = ET.tostring(self.motion.tree.getroot())
        flight = 0
        for i in range(150):
            tree, record = self.motion.pose(i/30)
            self.assertGreaterEqual(min(record['shoe_clearance'].values()), -1e-8)
            flight += min(record['shoe_clearance'].values()) > 20
            ids = [e.get('id') for e in tree.iter() if e.get('id')]
            self.assertEqual(len(ids), len(set(ids)))
        self.assertGreater(flight, 0)
        self.assertEqual(ET.tostring(self.motion.tree.getroot()), original)

    def test_clearance_matches_independent_full_canvas_shoe_pixels(self):
        from PIL import Image
        config = self.config
        # Render world-transformed shoes independently at delivery resolution.
        # Do not reuse shoe_bottom() or its calibration crop as the oracle.
        for i in range(150):
            posed, record = self.motion.pose(i/30)
            nodes = {e.get('id'): e for e in posed.iter() if e.get('id')}
            angles = self.motion.sample(i/30)['angles']
            for side in ['left', 'right']:
                svg = ET.Element(f'{{{SVG}}}svg', {'width': str(config['width']), 'height': str(config['height'])})
                svg.append(copy.deepcopy(posed.getroot().find(f'{{{SVG}}}defs')))
                group = ET.SubElement(svg, f'{{{SVG}}}g', {'transform': f"translate({config['width']/2-300*config['scale']} {config['floor']-925*config['scale']}) scale({config['scale']})"})
                shoe = copy.deepcopy(nodes[f'ankle-{side}'])
                x, y = world_point(posed, f'ankle-{side}', (0, 0))
                angle = sum(angles[f'{joint}-{side}'] for joint in ['hip', 'knee', 'ankle'])
                shoe.set('transform', f'translate({x} {y}) rotate({angle})')
                group.append(shoe)
                buffer = io.BytesIO()
                raster(ET.tostring(svg), config['width'], config['height']).write_to_png(buffer)
                with Image.open(buffer) as image:
                    bounds = image.convert('RGBA').getchannel('A').point(lambda value: 255 if value >= 128 else 0).getbbox()
                gap = config['floor']-bounds[3]
                expected = record['shoe_clearance'][side]*config['scale']
                self.assertLessEqual(abs(gap-expected), 1.25, (i, side, gap, expected))
                self.assertGreaterEqual(gap, -1, (i, side))

    def test_previously_floating_stance_frames_reach_ground(self):
        for i, side in [(3, 'right'), (4, 'right'), (5, 'right'), (12, 'left'), (13, 'left'), (14, 'left')]:
            _, record = self.motion.pose(i/30)
            self.assertLessEqual(record['shoe_clearance'][side]*self.config['scale'], 0.5, i)

    def test_arms_oppose_their_thighs_at_all_key_poses(self):
        for phase in self.motion.phases:
            posed, _ = self.motion.pose(phase*self.config['cycle'])
            for side in ['left', 'right']:
                knee_x = world_point(posed, f'knee-{side}', (0, 0))[0]-world_point(posed, f'hip-{side}', (0, 0))[0]
                hand_x = world_point(posed, f'wrist-{side}', (0, 0))[0]-world_point(posed, f'shoulder-{side}', (0, 0))[0]
                self.assertLess(knee_x*hand_x, 0, (phase, side))

    def test_pronounced_arm_and_leg_alternation_remains_opposite_between_keys(self):
        for i in range(150):
            posed, _ = self.motion.pose(i/30)
            thigh, arm = {}, {}
            for side in ['left', 'right']:
                thigh[side] = world_point(posed, f'knee-{side}', (0, 0))[0]-world_point(posed, f'hip-{side}', (0, 0))[0]
                arm[side] = world_point(posed, f'wrist-{side}', (0, 0))[0]-world_point(posed, f'shoulder-{side}', (0, 0))[0]
            leg_difference = thigh['right']-thigh['left']
            arm_difference = arm['right']-arm['left']
            # Allow a small crossover window rather than enforcing a rigid
            # frame-perfect sign flip as all four limbs pass the body.
            if abs(leg_difference) > 25 and abs(arm_difference) > 25:
                self.assertLess(leg_difference*arm_difference, 0, i)

    def test_correction_preserves_artwork_leg_head_and_torso_channels(self):
        expected = json.loads((ROOT/'tests/fixtures/side-run-preservation.json').read_text())
        records = []
        for i in range(150):
            sample = self.motion.sample(i/30)
            records.append({'root_y': sample['root_y'], 'angles': {k: v for k, v in sample['angles'].items() if not k.startswith(('shoulder-', 'elbow-', 'wrist-'))}})
        digest = hashlib.sha256(json.dumps(records, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(digest, expected['non_arm_sample_sha256'])
        self.assertEqual(hashlib.sha256((ROOT/'characters/hoodie-side/character.svg').read_bytes()).hexdigest(), expected['artwork_sha256'])

    def test_shoulders_do_not_rush_through_the_crossover(self):
        for i in range(150):
            a = self.motion.sample(i/30)['angles']
            b = self.motion.sample(((i+1)%150)/30)['angles']
            for side in ['left', 'right']:
                name = f'shoulder-{side}'
                self.assertLess(abs(a[name]-b[name]), 22, (i, side))

    def test_palm_silhouettes_do_not_overlap_during_exchange(self):
        from PIL import Image, ImageChops
        # Check each distinct delivered phase, including the old collision at
        # frames 3/22. Isolate both complete hands so torso occlusion cannot
        # hide an intersection from the test.
        for i in range(75):
            key = self.motion.sample(i/30)
            posed = pose_character(self.motion.tree, self.motion.rig, key)
            nodes = {e.get('id'): e for e in posed.iter() if e.get('id')}
            masks = []
            for side in ['left', 'right']:
                svg = ET.Element(f'{{{SVG}}}svg', {'width': '640', 'height': '1000'})
                svg.append(copy.deepcopy(posed.getroot().find(f'{{{SVG}}}defs')))
                hand = copy.deepcopy(nodes[f'wrist-{side}'])
                x, y = world_point(posed, f'wrist-{side}', (0, 0))
                angle = key['angles']['torso'] + sum(key['angles'].get(f'{joint}-{side}', 0) for joint in ['shoulder', 'elbow', 'wrist'])
                hand.set('transform', f'translate({x} {y}) rotate({angle})')
                svg.append(hand)
                buffer = io.BytesIO()
                raster(ET.tostring(svg), 640, 1000).write_to_png(buffer)
                with Image.open(buffer) as image:
                    masks.append(image.convert('RGBA').getchannel('A').point(lambda v: 255 if v >= 128 else 0))
            self.assertIsNone(ImageChops.multiply(*masks).getbbox(), i)

    def test_invalid_time_is_rejected(self):
        for value in [-1, float('nan'), float('inf')]:
            with self.assertRaises(ValueError):
                self.motion.sample(value)
