from pathlib import Path
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

from PIL import Image, ImageDraw

from tools.rear_drawing_review import artwork_crop, review, standing_side_svg
from tools.preview import ROOT


class RearDrawingReviewTests(unittest.TestCase):
    def test_side_reference_uses_saved_upright_pose_without_modifying_sources(self):
        paths = [ROOT/'characters/hoodie-side/character.svg', ROOT/'poses/side-stand.json',
                 ROOT/'motions/side-run.json']
        before = [p.read_bytes() for p in paths]
        svg = ET.fromstring(standing_side_svg())
        nodes = {e.get('id'): e for e in svg.iter() if e.get('id')}
        for name, angle in [('torso', -9), ('head', 9)]:
            rotations = re.findall(r'rotate\(([-.\d]+)\)', nodes[name].get('transform'))
            self.assertEqual(float(rotations[-1]), angle)
        self.assertEqual(before, [p.read_bytes() for p in paths])

    def test_white_and_transparent_margins_are_cropped_without_distortion(self):
        for background in ('white', (0, 0, 0, 0)):
            image = Image.new('RGBA', (100, 200), background)
            ImageDraw.Draw(image).rectangle((30, 40, 69, 159), fill='#505a5c')
            before = image.tobytes()
            cropped = artwork_crop(image)
            self.assertEqual(cropped.size, (46, 126))
            self.assertEqual(image.tobytes(), before)

    def test_empty_drawing_is_rejected(self):
        for background in ('white', (0, 0, 0, 0)):
            with self.assertRaises(ValueError):
                artwork_crop(Image.new('RGBA', (30, 60), background))

    def test_existing_output_is_refused_without_reading_or_overwriting_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            keep = out/'keep.txt'
            keep.write_text('preserve')
            with patch('tools.rear_drawing_review.Image.open', side_effect=AssertionError('Source opened')):
                with self.assertRaises(FileExistsError):
                    review(out/'missing.png', out)
            self.assertEqual(keep.read_text(), 'preserve')


if __name__ == '__main__':
    unittest.main()
