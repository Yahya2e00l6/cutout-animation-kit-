import hashlib
import io
import json
import unittest
import xml.etree.ElementTree as ET

from tools.animate import raster
from tools.preview import ROOT, SVG
from tools.side_actions import SIDE_ACTIONS, load_side_action


class SavedSideActionTests(unittest.TestCase):
    def test_named_actions_keep_the_saved_raster_appearance_without_cache_files(self):
        from PIL import Image
        expected = json.loads((ROOT/'tests/fixtures/saved-side-run-raster.json').read_text())
        for facing in ['left', 'right']:
            motion = load_side_action(f'side-run-{facing}')
            for frame, digest in expected[facing].items():
                i = int(frame)
                data, _ = motion.frame(i/30, i)
                buffer = io.BytesIO()
                raster(data, 1280, 720).write_to_png(buffer)
                with Image.open(buffer) as image:
                    actual = hashlib.sha256(image.convert('RGB').tobytes()).hexdigest()
                self.assertEqual(actual, digest, (facing, frame))

    def test_duration_and_cadence_do_not_change_the_cycle_shapes(self):
        for action in SIDE_ACTIONS:
            normal = load_side_action(action)
            longer = load_side_action(action, duration=10)
            faster = load_side_action(action, duration=10, speed=2)
            self.assertEqual(longer.config['duration'], 10)
            for i in range(150):
                self.assertEqual(normal.sample(i/30), longer.sample(i/30))
                self.assertEqual(normal.sample(i/30), faster.sample(i/60))

    def test_clean_export_has_alpha_and_no_review_elements(self):
        from PIL import Image
        for action in SIDE_ACTIONS:
            motion = load_side_action(action)
            data, record = motion.frame(0.2, 6, clean=True)
            review, review_record = motion.frame(0.2, 6)
            tree = ET.fromstring(data)
            self.assertEqual(record, review_record)
            self.assertFalse(list(tree.iter(f'{{{SVG}}}text')))
            self.assertFalse(list(tree.iter(f'{{{SVG}}}rect')))
            self.assertFalse(list(tree.iter(f'{{{SVG}}}line')))
            self.assertEqual(ET.tostring(tree.find(f'{{{SVG}}}g')), ET.tostring(ET.fromstring(review).find(f'{{{SVG}}}g')))
            buffer = io.BytesIO()
            raster(data, 1280, 720).write_to_png(buffer)
            with Image.open(buffer) as image:
                alpha = image.convert('RGBA').getchannel('A')
                self.assertIsNotNone(alpha.getbbox())
                self.assertEqual(alpha.getpixel((0, 0)), 0)
                self.assertEqual(alpha.getpixel((640, 690)), 0)
                self.assertEqual(alpha.getextrema(), (0, 255))

    def test_loads_have_independent_settings(self):
        first = load_side_action('side-run-left')
        first.config['arm_cycle']['shoulder_amplitude'] = 0
        self.assertEqual(load_side_action('side-run-left').config['arm_cycle']['shoulder_amplitude'], 40)

    def test_invalid_saved_action_options_fail_clearly(self):
        with self.assertRaises(ValueError):
            load_side_action('missing')
        for value in [0, -1, float('nan'), float('inf'), 1e308, 1e-308, 0.01]:
            with self.subTest(duration=value), self.assertRaises(ValueError):
                load_side_action('side-run-left', duration=value)
        for value in [0, -1, float('nan'), float('inf'), 1e-320]:
            with self.subTest(speed=value), self.assertRaises(ValueError):
                load_side_action('side-run-left', speed=value)
