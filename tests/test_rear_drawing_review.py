from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

from tools.rear_drawing_review import artwork_crop, review


class RearDrawingReviewTests(unittest.TestCase):
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
