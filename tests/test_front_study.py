import math
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from tools.bvh_reference import BVH
from tools.front_run_study import FrontStudy
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
