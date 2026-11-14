"""Construction checks, not proof of natural continuous side-running motion."""
import io
import json
import unittest
import xml.etree.ElementTree as ET

from tools.animate import raster
from tools.preview import ROOT, load_character
from tools.side_review import pose_character, world_point


class SideRigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree, cls.rig = load_character(ROOT/'characters/hoodie-side')
        cls.keys = json.loads((ROOT/'poses/side-run.json').read_text())['poses']

    def test_view_is_separate_with_nested_joints_and_unique_ids(self):
        self.assertEqual(self.rig['type'], 'humanoid-cutout-side')
        self.assertEqual(self.rig['facing'], 'right')
        nodes = {e.get('id'): e for e in self.tree.iter() if e.get('id')}
        ids = [e.get('id') for e in self.tree.iter() if e.get('id')]
        self.assertEqual(len(ids), len(set(ids)))
        for chain in self.rig['chains'].values():
            for parent, child in zip(chain, chain[1:]):
                self.assertIn(nodes[child], list(nodes[parent]))

    def test_second_half_exchanges_legs_and_arms_instead_of_repeating(self):
        self.assertEqual(len(self.keys), 8)
        for near, far in zip(self.keys[:4], self.keys[4:]):
            self.assertEqual(near['phase'], far['phase'])
            for joint in ['hip', 'knee', 'ankle', 'shoulder', 'elbow']:
                self.assertEqual(near['angles'][f'{joint}-right'], far['angles'][f'{joint}-left'])
                self.assertEqual(near['angles'][f'{joint}-left'], far['angles'][f'{joint}-right'])
            if 'support' in near:
                self.assertEqual((near['support'], far['support']), ('right', 'left'))

    def test_support_markers_reach_the_review_floor(self):
        for key in self.keys:
            if 'support' not in key:
                continue
            posed = pose_character(self.tree, self.rig, key)
            point = self.rig['review'][key['anchor']]
            _, y = world_point(posed, f"ankle-{key['support']}", point)
            self.assertAlmostEqual(y, self.rig['review']['floor'], places=8)

    def test_flight_has_both_shoe_markers_above_ground(self):
        for key in self.keys:
            if key['phase'] != 'flight':
                continue
            posed = pose_character(self.tree, self.rig, key)
            for side in ['left', 'right']:
                for marker in ['standing_sole', 'toe']:
                    _, y = world_point(posed, f'ankle-{side}', self.rig['review'][marker])
                    self.assertLess(y, self.rig['review']['floor']-20)

    def test_elbows_stay_folded_and_arms_oppose_thighs_at_contact(self):
        for key in self.keys:
            for side in ['left', 'right']:
                # The reference's backward stroke opens the elbow; the
                # foreground fist remains folded on the forward stroke.
                self.assertTrue(-125 <= key['angles'][f'elbow-{side}'] <= -40)
                if key['phase'] == 'contact':
                    self.assertLess(key['angles'][f'shoulder-{side}']*key['angles'][f'hip-{side}'], 0)

    def test_depth_order_and_source_survive_every_pose(self):
        source = ET.tostring(self.tree.getroot())
        for key in self.keys:
            tree = pose_character(self.tree, self.rig, key)
            nodes = {e.get('id'): e for e in tree.iter() if e.get('id')}
            pelvis = list(nodes['pelvis'])
            self.assertLess(pelvis.index(nodes['hip-left']), pelvis.index(nodes['hip-right']))
            torso = list(nodes['torso'])
            self.assertLess(torso.index(nodes['shoulder-left']), torso.index(nodes['body-art']))
            self.assertGreater(torso.index(nodes['shoulder-right']), torso.index(nodes['body-art']))
        self.assertEqual(ET.tostring(self.tree.getroot()), source)

    def test_all_key_poses_rasterize_without_canvas_clipping(self):
        from PIL import Image
        for key in self.keys:
            with self.subTest(pose=key['name']):
                posed = pose_character(self.tree, self.rig, key)
                buffer = io.BytesIO()
                raster(ET.tostring(posed.getroot()), 640, 1000).write_to_png(buffer)
                with Image.open(buffer) as image:
                    x0, y0, x1, y1 = image.convert('RGBA').getchannel('A').getbbox()
                self.assertGreater(x0, 5)
                self.assertGreater(y0, 5)
                self.assertLess(x1, 635)
                self.assertLess(y1, 995)
