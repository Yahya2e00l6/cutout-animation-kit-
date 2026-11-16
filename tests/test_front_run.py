import base64
import math
import unittest
import xml.etree.ElementTree as ET

from tools.animate import frame_svg
from tools.front_run import FrontRun
from tools.preview import SVG
from tools.render_scene import SceneRenderer


class FrontRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.action = FrontRun()

    def test_all_120_clean_frames_keep_the_approved_actor_and_contacts_unchanged(self):
        action = self.action
        for i in range(120):
            actual, contacts = action.frame(i/30, i, clean=True)
            original, expected = frame_svg(action.tree, action.rig, action.model, action.timeline, i/30, i)
            clean = ET.fromstring(actual)
            saved = ET.fromstring(original)
            actor = lambda root: next(e for e in root if e.get('id') == 'root')
            self.assertEqual(ET.tostring(actor(clean)), ET.tostring(actor(saved)))
            self.assertEqual(contacts, expected)
            self.assertEqual(len(clean), 2)
            self.assertEqual(clean[0].tag, f'{{{SVG}}}defs')

    def test_numeric_speed_changes_only_cadence_and_scrubbing_is_deterministic(self):
        fast = FrontRun(duration=2, speed=2)
        for t in [0, .1, .2, .4, .7, .9]:
            _, normal = self.action.frame(t*2, 0, clean=True)
            _, changed = fast.frame(t, 0, clean=True)
            self.assertAlmostEqual(normal['root_height'], changed['root_height'], places=8)
            for side in ('left', 'right'):
                self.assertAlmostEqual(normal['contacts'][side]['y'], changed['contacts'][side]['y'], places=8)
        expected = [self.action.frame(i/30, i, clean=True) for i in range(20)]
        for i in reversed(range(20)):
            self.assertEqual(self.action.frame(i/30, i, clean=True), expected[i])

    def test_invalid_times_fail_and_saved_preset_is_not_mutated(self):
        from tools.preview import ROOT
        path = ROOT/'motions/reference-run.json'
        original = path.read_bytes()
        for t in [-1, math.nan, math.inf, 4]:
            with self.assertRaises(ValueError):
                self.action.frame(t, 0)
        FrontRun(duration=2, speed=2).frame(.1, 0, clean=True)
        self.assertEqual(path.read_bytes(), original)

    def test_mixed_scene_routes_and_isolates_both_registered_views(self):
        def actor(ident, action, view, index):
            return {'id': ident, 'character': 'hoodie', 'view': view, 'clipIndex': index,
                    'action': action, 'duration': 4, 'speed': 1, 'localTime': .1,
                    'sourceAnchor': [640, 650], 'position': [640, 650], 'scale': 1,
                    'transform': [1, 0, 0, 1, 0, 0]}
        sample = {'output': {'width': 1280, 'height': 720}, 'stage': {'background': '#ffffff'},
                  'actors': [actor('front', 'reference-run', 'front', 0),
                             actor('side', 'side-run-right', 'side-right', 1)]}
        renderer = SceneRenderer()
        svg, records = renderer.frame(sample, 3)
        images = ET.fromstring(svg).findall(f'{{{SVG}}}image')
        self.assertEqual(len(images), 2)
        roots = [ET.fromstring(base64.b64decode(image.get('href').split(',')[1])) for image in images]
        self.assertNotEqual(ET.tostring(roots[0]), ET.tostring(roots[1]))
        self.assertIn('contacts', records[0]['sourceContacts'])
        self.assertIn('shoe_clearance', records[1]['sourceContacts'])
        # Only the first frame per clip may construct/calibrate an action.
        actions = [value[1] for value in renderer.actions.values()]
        renderer.frame(sample, 3)
        self.assertEqual(actions, [value[1] for value in renderer.actions.values()])


if __name__ == '__main__':
    unittest.main()
