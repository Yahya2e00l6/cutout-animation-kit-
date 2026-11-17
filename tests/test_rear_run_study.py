import hashlib
import math
from pathlib import Path
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from tools.front_run_study import FrontStudy
from tools.preview import ROOT, SVG
from tools.rear_run_study import RearStudy, rear_point


class RearRunStudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rear = RearStudy()
        cls.front = FrontStudy()

    def test_rear_rotation_is_proper_and_its_own_inverse(self):
        self.assertEqual(rear_point((2, 3, 4)), (-2, 3, -4))
        self.assertEqual(rear_point(rear_point((2, 3, 4))), (2, 3, 4))
        # Retain the right-handed frame: X cross Y must still equal Z.
        from tools.front_run_study import cross
        self.assertEqual(cross(rear_point((1, 0, 0)), rear_point((0, 1, 0))), rear_point((0, 0, 1)))

    def test_both_views_share_the_same_motion_except_documented_root_correction(self):
        for i in range(69):
            front = self.front.pose(i/30)
            rear = self.rear.pose(i/30)
            correction = rear['rearGroundCorrection']
            self.assertEqual(front['phase'], rear['phase'])
            self.assertEqual(front['groundCorrection'], rear['sourceGroundCorrection'])
            for side in ('left', 'right'):
                for joint, point in front[side].items():
                    expected = list(rear_point(point))
                    if joint != 'foot_forward':
                        expected[1] += correction
                    self.assertEqual(tuple(expected), rear[side][joint])
                for a, b, length in [('hip', 'knee', 151), ('knee', 'ankle', 140),
                                     ('shoulder', 'elbow', 126), ('elbow', 'wrist', 105)]:
                    self.assertAlmostEqual(math.dist(rear[side][a], rear[side][b]), length, places=8)

    def test_rear_shoe_frames_stay_orthonormal_without_vertical_foot_flips(self):
        for i in range(241):
            pose = self.rear.pose(i/240*self.rear.cycle)
            for side in ('left', 'right'):
                right, up, forward = self.rear.shoe_basis(pose, side)
                self.assertLess(right[0], -.8)
                for vector in (right, up, forward):
                    self.assertAlmostEqual(sum(n*n for n in vector), 1, places=8)
                for a, b in [(right, up), (up, forward), (forward, right)]:
                    self.assertAlmostEqual(sum(x*y for x, y in zip(a, b)), 0, places=8)
                self.assertGreaterEqual(min(v[1] for v in self.rear.shoe(pose, side)[0]), -1e-8)

    def test_frame_contains_rear_identity_not_a_front_face_or_pocket(self):
        svg, _ = self.rear.frame(.1, clean=True)
        root = ET.fromstring(svg)
        ids = [e.get('id') for e in root.iter() if e.get('id')]
        self.assertEqual(len(ids), len(set(ids)))
        for name in ('rear-head', 'rear-hood', 'rear-torso', 'rear-pelvis'):
            self.assertIn(name, ids)
        self.assertFalse(set(ids) & {'face-neutral', 'head-art', 'neutral-features', 'front-study-character'})
        self.assertEqual(len(root), 2)
        self.assertEqual(root[0].tag, f'{{{SVG}}}defs')
        for node in root.iter():
            self.assertNotIn(node.tag, (f'{{{SVG}}}image', f'{{{SVG}}}use'))
        # Hair and hood remain the final identity layers, not mirrored front art.
        self.assertNotIn(b'drawstring', svg)

    def test_all_local_svg_references_resolve(self):
        import re
        svg, _ = self.rear.frame(.23)
        root = ET.fromstring(svg)
        ids = {e.get('id') for e in root.iter() if e.get('id')}
        for ident in re.findall(rb'url\(#([^\)]+)\)', svg):
            self.assertIn(ident.decode(), ids)

    def test_periodic_positions_velocities_and_random_access(self):
        action = self.rear
        h = 1e-6
        before, at, after = [action.pose(t) for t in (action.cycle-h, 0, h)]
        for side in ('left', 'right'):
            for joint in ('hip', 'knee', 'ankle', 'shoulder', 'elbow', 'wrist'):
                for a, b, c in zip(before[side][joint], at[side][joint], after[side][joint]):
                    self.assertLess(abs((b-a)/h-(c-b)/h), .5)
        expected = [action.frame(t)[0] for t in (0, .1, .4)]
        for i in (2, 0, 1):
            self.assertEqual(action.frame((0, .1, .4)[i])[0], expected[i])

    def test_invalid_times_fail_without_changing_sources(self):
        files = [ROOT/'characters/hoodie/character.svg', self.rear.identity,
                 ROOT/'motions/front-run.json', ROOT/'characters/hoodie-side/character.svg']
        before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in files]
        for t in (-1, math.nan, math.inf):
            with self.assertRaises(ValueError):
                self.rear.frame(t)
        self.rear.frame(.2)
        self.assertEqual(before, [hashlib.sha256(p.read_bytes()).hexdigest() for p in files])

    def test_front_drawing_and_earlier_rear_files_are_not_used(self):
        original_open = Path.open
        def guarded_open(path, *args, **kwargs):
            if (set(path.parts) & {'hoodie-back', 'hoodie-back-animation'} or
                    path.name in {'rear-run-preview.json', 'back-study-run.json', 'back-run-review.json'}):
                raise AssertionError(f'Historical rear input loaded: {path}')
            return original_open(path, *args, **kwargs)
        with patch.object(Path, 'open', guarded_open), \
             patch('tools.front_run_study.FrontStudy.frame', side_effect=AssertionError('Front drawing used')):
            svg, _ = RearStudy().frame(.2)
        self.assertIn(b'rear-study-character', svg)


if __name__ == '__main__':
    unittest.main()
