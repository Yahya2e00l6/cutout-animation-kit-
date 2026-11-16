import math
import hashlib
import json
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from tools.bvh_reference import BVH
from tools.front_run_study import FrontStudy, MotionReadability, sub, unit
from tools.preview import ROOT


FIXTURE = '''HIERARCHY
ROOT root {
OFFSET 0 0 0
CHANNELS 6 Xposition Yposition Zposition Zrotation Yrotation Xrotation
JOINT child {
OFFSET 1 0 0
CHANNELS 3 Zrotation Yrotation Xrotation
End Site { OFFSET 1 0 0 }
}
}
MOTION
Frames: 1
Frame Time: 0.0083333
0 0 0 90 0 0 0 90 0
'''


class BVHReferenceTests(unittest.TestCase):
    def test_ordered_rotations_and_parent_offsets_against_known_points(self):
        points = BVH(FIXTURE).frame(0)
        for name, expected in [('root', (0, 0, 0)), ('child', (0, 1, 0)), ('child/end', (0, 1, -1))]:
            for a, b in zip(points[name], expected):
                self.assertAlmostEqual(a, b, places=9)

    def test_invalid_channels_numbers_and_frames_are_rejected(self):
        for text in [FIXTURE.replace('Yrotation Xrotation', 'Xposition Xrotation'),
                     FIXTURE.replace('0.0083333', '0'), FIXTURE.replace('0 0 0 90 0 0 0 90 0', '0 0 nan 90 0 0 0 90 0'),
                     FIXTURE.replace('Frames: 1', 'Frames: 2')]:
            with self.assertRaises(ValueError):
                BVH(text)
        for index in (-1, 1, .5, True):
            with self.assertRaises(ValueError):
                BVH(FIXTURE).frame(index)


class FrontStudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.action = FrontStudy()

    def test_source_provenance_is_a_new_reference_not_the_old_gait(self):
        ref = self.action.reference
        self.assertEqual(ref['source']['motion'], '09_01')
        self.assertEqual(ref['source']['frames'], [44, 136])
        self.assertEqual(ref['source']['sha256'], '90641ccca814b9d8d59f63576a548bb5612477364462d142a9f741268fbe3b78')
        self.assertEqual(ref['source']['nominalFps'], 120)
        self.assertAlmostEqual(self.action.cycle, 92/120)
        self.assertEqual(len(ref['samples']), 48)

    def test_invalid_times_are_rejected(self):
        for seconds in (-1, math.nan, math.inf):
            with self.assertRaises(ValueError):
                self.action.frame(seconds)

    def test_drawing_revision_keeps_v03_motion_and_contact_states(self):
        # Captured from v03 study-report.json before the drawing-only revision.
        # Includes all joints, foot directions, body axes and ground corrections.
        def rounded(value):
            if isinstance(value, float):
                return round(value, 6)
            if isinstance(value, (tuple, list)):
                return [rounded(v) for v in value]
            if isinstance(value, dict):
                return {k: rounded(v) for k, v in value.items()}
            return value
        states = [self.action.pose(i/30) for i in range(69)]
        data = json.dumps(rounded(states), sort_keys=True, separators=(',', ':')).encode()
        self.assertEqual(hashlib.sha256(data).hexdigest(),
                         '973434487239c782f927338bb46596034eff85a00cb0ae4bcd3ca5ec304a5d26')

    def test_staging_can_be_disabled_to_recover_measured_bone_directions(self):
        measured = FrontStudy(readability=MotionReadability(
            knee_drive=0, heel_fold=0, recovery_spread=0,
            arm_center=0, arm_gain=1, arm_symmetry=0))
        for i in range(24):
            t = i/24*measured.cycle
            pose = measured.pose(t)
            ref = measured.sample(t)['joints']
            for side, name in [('left', 'Left'), ('right', 'Right')]:
                for a, b, ra, rb in [('hip', 'knee', 'UpLeg', 'Leg'), ('knee', 'ankle', 'Leg', 'Foot'),
                                      ('shoulder', 'elbow', 'Arm', 'ForeArm'), ('elbow', 'wrist', 'ForeArm', 'Hand')]:
                    actual = unit(sub(pose[side][b], pose[side][a]))
                    expected = unit(sub(ref[name+rb], ref[name+ra]))
                    for x, y in zip(actual, expected):
                        self.assertAlmostEqual(x, y, places=9)

    def test_invalid_staging_controls_are_rejected(self):
        for config in [{'knee_drive': math.nan}, {'arm_symmetry': 1.1}, {'arm_gain': 0},
                       {'recovery_spread': -.1}, {'heel_fold': 1}, {'arm_center': math.inf}]:
            with self.assertRaises(ValueError):
                MotionReadability(**config)

    def test_full_arm_symmetry_matches_mirrored_half_cycle_directions(self):
        action = FrontStudy(readability=MotionReadability(arm_symmetry=1))
        for i in range(16):
            a = action.pose(i/16*action.cycle)['left']
            b = action.pose((i/16+.5)*action.cycle)['right']
            for start, end in [('shoulder', 'elbow'), ('elbow', 'wrist')]:
                left, right = sub(a[end], a[start]), sub(b[end], b[start])
                for x, y in zip(left, (-right[0], right[1], right[2])):
                    self.assertAlmostEqual(x, y, places=7)

    def test_recovering_shoe_is_drawn_behind_its_own_advancing_thigh(self):
        # Phase zero has the left heel tucked behind the knee. This used to
        # paint the shoe across the knee despite its much lower world depth.
        svg, pose = self.action.frame(0)
        self.assertLess(pose['left']['ankle'][2], pose['left']['knee'][2])
        ids = [e.get('id') for e in ET.fromstring(svg).iter() if e.get('id')]
        self.assertLess(ids.index('study-shoe-left'), ids.index('study-thigh-left'))

    def test_retargeted_bones_keep_actual_3d_lengths_and_feet_stay_above_mesh_plane(self):
        depths = {side: [] for side in ('left', 'right')}
        for i in range(241):
            pose = self.action.pose(i/240*self.action.cycle)
            self.assertTrue(all(math.isfinite(n) for n in pose['root']))
            for side in ('left', 'right'):
                limb = pose[side]
                for a, b, length in [('hip', 'knee', 151), ('knee', 'ankle', 140),
                                     ('shoulder', 'elbow', 126), ('elbow', 'wrist', 105)]:
                    self.assertAlmostEqual(math.dist(limb[a], limb[b]), length, places=7)
                verts, _ = self.action.shoe(pose, side)
                self.assertGreaterEqual(min(v[1] for v in verts), -1e-8)
                depths[side].append(limb['ankle'][2])
        for values in depths.values():
            self.assertGreater(max(values)-min(values), 150)

    def test_loop_positions_and_velocities_match_and_scrubbing_is_order_independent(self):
        h = 1e-6
        poses = [self.action.pose(t) for t in [self.action.cycle-h, 0, h]]
        for side in ('left', 'right'):
            for joint in ('hip', 'knee', 'ankle', 'shoulder', 'elbow', 'wrist'):
                for axis in range(3):
                    a, b, c = [p[side][joint][axis] for p in poses]
                    self.assertLess(abs((b-a)/h-(c-b)/h), .5, (side, joint, axis))
        times = [i*self.action.cycle/23 for i in range(23)]
        expected = [self.action.frame(t)[0] for t in times]
        for i in reversed(range(23)):
            self.assertEqual(self.action.frame(times[i])[0], expected[i])

    def test_old_front_motion_is_not_called_and_identity_art_is_read_only(self):
        path = ROOT/'characters/hoodie/character.svg'
        before = path.read_bytes()
        original = ET.tostring(self.action.original)
        with patch('tools.actions.build_timeline', side_effect=AssertionError('Old front action called')), \
             patch('tools.animate.frame_svg', side_effect=AssertionError('Old front renderer called')), \
             patch('tools.motion.sample', side_effect=AssertionError('Old front sampler called')):
            svg, _ = self.action.frame(.2)
        root = ET.fromstring(svg)
        ids = [e.get('id') for e in root.iter() if e.get('id')]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertNotIn('leg-upper-left-art', ids)
        self.assertIn('head-art', ids)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(ET.tostring(self.action.original), original)


if __name__ == '__main__':
    unittest.main()
