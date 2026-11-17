import hashlib
import io
import math
import unittest
import xml.etree.ElementTree as ET

from PIL import Image

from tools.animate import raster
from tools.preview import ROOT, SVG
from tools.run_profile import RunProfile
from tools.svg_rig import SvgRig, ENDS


class PonytailSetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.asset = ROOT/'characters/ponytail-hoodie-side'
        cls.rig = SvgRig(cls.asset/'rig.json')
        cls.profile = RunProfile(ROOT/'motions/shared-side-run.json')

    def test_packaged_svg_is_the_exact_separated_source(self):
        source = ROOT/'characters/ponytail-hoodie-side-source/character.svg'
        self.assertEqual(source.read_bytes(), (self.asset/'character.svg').read_bytes())
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), self.rig.rig['sha256'])
        self.assertEqual(len(self.rig.groups), 14)
        self.assertIn('profile-head-with-ponytail', self.rig.groups)
        self.assertNotEqual(self.rig.rig['parts']['foot-left'], self.rig.rig['parts']['foot-right'])
        for node in self.rig.root.iter():
            self.assertNotIn(node.tag, (f'{{{SVG}}}image', f'{{{SVG}}}use', f'{{{SVG}}}script'))

    def test_saved_profile_drives_native_lengths_without_custom_animation_code(self):
        self.assertFalse(list(self.asset.glob('*.py')))
        for i in range(75):
            points, _ = self.rig.skeleton(self.profile.sample(i/30))
            for side in ('left', 'right'):
                for part, (a, b) in ENDS.items():
                    self.assertAlmostEqual(math.dist(points[f'{a}-{side}'], points[f'{b}-{side}']),
                                           self.rig.lengths[f'{part}-{side}'], places=8)

    def test_key_pose_rasters_are_visible_unclipped_and_source_is_read_only(self):
        before = ET.tostring(self.rig.root)
        for i in range(8):
            svg, _ = self.rig.frame(self.profile, i/8*self.profile.cycle)
            buffer = io.BytesIO(); raster(svg, 900, 1100).write_to_png(buffer)
            with Image.open(buffer) as image:
                box = image.getchannel('A').getbbox()
                self.assertIsNotNone(box)
                self.assertGreater(min(box[:2]), 0)
                self.assertLess(box[2], 900)
                self.assertLess(box[3], 1100)
        self.assertEqual(ET.tostring(self.rig.root), before)


if __name__ == '__main__':
    unittest.main()
