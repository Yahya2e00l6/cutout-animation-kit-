import base64
import hashlib
import math
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

from tools.front_study_action import FrontStudyAction
from tools.front_run_study import FrontStudy
from tools.preview import SVG
from tools.render_scene import SceneRenderer


class FrontStudyActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.action = FrontStudyAction()
        cls.source = FrontStudy()

    def test_all_69_frames_preserve_astra_v04_character_and_definitions(self):
        digest = hashlib.sha256()
        for i in range(69):
            actual, metadata = self.action.frame(i/30, i, clean=True)
            digest.update(ET.canonicalize(actual, rewrite_prefixes=True).encode())
            expected, pose = self.source.frame(i/30)
            clean, original = ET.fromstring(actual), ET.fromstring(expected)
            self.assertEqual(len(clean), 2)
            self.assertEqual(ET.tostring(clean[0]), ET.tostring(original[0]))
            character = original.find(f"{{{SVG}}}g[@id='front-study-character']")
            self.assertEqual(ET.tostring(clean[1]), ET.tostring(character))
            self.assertEqual(metadata['frontRun']['phase'], pose['phase'])
            self.assertEqual(metadata['frontRun']['groundCorrection'], pose['groundCorrection'])
            self.assertNotIn('contacts', metadata)  # Do not claim planted contacts.
        # Pin the saved revision, not just equality with a mutable study source.
        self.assertEqual(digest.hexdigest(), '9ab35dd1abcc411c99de91eb9c1bf1f1841669bc8d1e6b6b37435e058ab97236')

    def test_speed_changes_only_cadence_and_scrubbing_is_deterministic(self):
        fast = FrontStudyAction(duration=2, speed=2)
        for t in [.7, .1, 0, .4]:
            self.assertEqual(fast.frame(t, 0), self.action.frame(t*2, 0))
        self.assertAlmostEqual(fast.config['cycle'], self.source.cycle/2)

    def test_invalid_parameters_and_half_open_times_are_rejected(self):
        for kwargs in [{'action': 'reference-run'}, {'speed': 0}, {'speed': math.inf},
                       {'duration': -1}, {'duration': math.nan}]:
            with self.assertRaises(ValueError):
                FrontStudyAction(**kwargs)
        for t in [-1, math.nan, math.inf, 2.3]:
            with self.assertRaises(ValueError):
                self.action.frame(t, 0)

    def test_scene_routes_new_action_without_legacy_sampler_and_reuses_instance(self):
        actor = {'id': 'front', 'character': 'hoodie', 'view': 'front', 'clipIndex': 0,
                 'action': 'front-run', 'duration': 2.3, 'speed': 1, 'localTime': .1,
                 'sourceAnchor': [640, 650], 'position': [640, 650], 'scale': 1,
                 'transform': [1, 0, 0, 1, 0, 0]}
        sample = {'output': {'width': 1280, 'height': 720},
                  'stage': {'background': '#123456'}, 'actors': [actor]}
        renderer = SceneRenderer()
        with patch('tools.front_run.FrontRun', side_effect=AssertionError('Legacy renderer used')):
            svg, records = renderer.frame(sample, 3)
            instance = renderer.actions[0][1]
            renderer.frame(sample, 3)
        self.assertIs(renderer.actions[0][1], instance)
        image = ET.fromstring(svg).find(f'{{{SVG}}}image')
        source = base64.b64decode(image.get('href').split(',')[1])
        self.assertEqual(source, self.action.frame(.1, 3, clean=True)[0])
        self.assertIn('frontRun', records[0]['sourceContacts'])
        for field, value in [('view', 'side-right'), ('character', 'dice-dongtae-upgraded'),
                             ('footLock', True), ('travelMode', 'support-leg'),
                             ('transition', {'weight': .5})]:
            bad = {**sample, 'actors': [{**actor, field: value}]}
            with self.assertRaises(ValueError):
                SceneRenderer().frame(bad, 0)


if __name__ == '__main__':
    unittest.main()
