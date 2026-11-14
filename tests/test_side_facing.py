import copy
import io
import json
import unittest
import xml.etree.ElementTree as ET

from tools.animate import raster
from tools.preview import ROOT, SVG
from tools.side_run import SideRun


class SideFacingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((ROOT/'motions/side-run-preview.json').read_text())
        cls.right = SideRun(ROOT/'characters/hoodie-side', ROOT/'poses/side-run.json', cls.config)
        cls.left = SideRun(ROOT/'characters/hoodie-side', ROOT/'poses/side-run.json', {**cls.config, 'facing': 'left'})

    def test_direction_does_not_change_motion_or_ground_contacts(self):
        for i in range(150):
            self.assertEqual(self.right.sample(i/30), self.left.sample(i/30))
            right_pose, right_record = self.right.pose(i/30)
            left_pose, left_record = self.left.pose(i/30)
            self.assertEqual(ET.tostring(right_pose.getroot()), ET.tostring(left_pose.getroot()))
            self.assertEqual(right_record, left_record)

    def test_only_the_character_is_inside_the_mirror(self):
        for i in [0, 3, 5, 7, 9, 14, 18]:
            right_bytes, right_record = self.right.frame(i/30, i)
            left_bytes, left_record = self.left.frame(i/30, i)
            right, left = ET.fromstring(right_bytes), ET.fromstring(left_bytes)
            mirror = left.find(f"{{{SVG}}}g[@id='side-facing-mirror']")
            self.assertIsNotNone(mirror)
            self.assertEqual(mirror.get('transform'), 'translate(1280 0) scale(-1 1)')
            self.assertFalse(list(mirror.iter(f'{{{SVG}}}text')))
            self.assertEqual(ET.tostring(right.find(f'{{{SVG}}}g')), ET.tostring(mirror[0]))
            self.assertEqual([ET.tostring(e) for e in right if e.tag != f'{{{SVG}}}g'], [ET.tostring(e) for e in left if e.tag != f'{{{SVG}}}g'])
            self.assertEqual(left_record['facing'], 'left')
            self.assertEqual(right_record['facing'], 'right')

    def test_rendered_character_is_a_horizontal_reflection(self):
        from PIL import Image, ImageChops, ImageStat
        for i in [0, 3, 5, 7, 9, 14, 18]:
            images = []
            for motion in [self.right, self.left]:
                data, _ = motion.frame(i/30, i)
                source = ET.fromstring(data)
                # Isolate the exact actor groups used in the delivered frame.
                actor = ET.Element(f'{{{SVG}}}svg', {'width': '1280', 'height': '720'})
                actor.append(copy.deepcopy(source.find(f'{{{SVG}}}defs')))
                actor.append(copy.deepcopy(source.find(f'{{{SVG}}}g')))
                buffer = io.BytesIO()
                raster(ET.tostring(actor), 1280, 720).write_to_png(buffer)
                with Image.open(buffer) as image:
                    images.append(image.convert('RGBA'))
            expected = images[0].transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            # Allow subpixel antialias differences from rasterizing reflected
            # vector paths; their silhouettes must still land on the same box.
            self.assertEqual(expected.getbbox(), images[1].getbbox(), i)
            difference = ImageChops.difference(expected, images[1])
            self.assertLess(max(ImageStat.Stat(difference).mean), 0.1, i)

    def test_invalid_direction_is_rejected(self):
        with self.assertRaises(ValueError):
            SideRun(ROOT/'characters/hoodie-side', ROOT/'poses/side-run.json', {**self.config, 'facing': 'up'})
