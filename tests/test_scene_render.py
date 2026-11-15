import base64
import io
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from PIL import Image, ImageChops

from tools.animate import raster
from tools.preview import SVG
from tools.render_scene import SceneRenderer, render_manifest
from tools.side_actions import load_side_action


def sample(actors=None):
    return {'output': {'width': 100, 'height': 80, 'fps': 30},
            'stage': {'background': '#ffffff'}, 'actors': actors or []}


def actor(index=0, x=20, action='side-run-right'):
    return {'id': f'actor{index}', 'clipIndex': index, 'action': action,
            'duration': 1, 'speed': 1.25, 'localTime': 0.1,
            'sourceAnchor': [20, 30], 'transform': [1, 0, 0, 1, x-20, 20]}


def image(svg, width=100, height=80):
    output = io.BytesIO()
    raster(svg, width, height).write_to_png(output)
    return Image.open(output).convert('RGBA')


class FakeAction:
    config = {'width': 40, 'height': 40, 'floor': 30}

    def __init__(self, color):
        self.color = color
        self.calls = []

    def frame(self, seconds, number, clean):
        self.calls.append((seconds, number, clean))
        # Deliberately identical IDs and global CSS across both actor documents.
        return (f'<svg xmlns="{SVG}" width="40" height="40" viewBox="0 0 40 40">'
                f'<style>.paint{{fill:url(#color)}}</style>'
                f'<defs><linearGradient id="color"><stop stop-color="{self.color}"/></linearGradient></defs>'
                '<rect id="body" class="paint" x="10" y="10" width="20" height="20"/></svg>').encode(), {'source': True}


class SceneRenderTests(unittest.TestCase):
    def test_embedded_documents_isolate_ids_gradients_and_global_styles(self):
        def loader(action, **kwargs):
            return FakeAction('#ff0000' if action == 'side-run-right' else '#0000ff')
        renderer = SceneRenderer(loader)
        svg, records = renderer.frame(sample([actor(), actor(1, 60, 'side-run-left')]), 0)
        pixels = image(svg)
        self.assertEqual(pixels.getpixel((20, 40)), (255, 0, 0, 255))
        self.assertEqual(pixels.getpixel((60, 40)), (0, 0, 255, 255))
        self.assertEqual(pixels.getpixel((0, 0)), (255, 255, 255, 255))
        images = ET.fromstring(svg).findall(f'{{{SVG}}}image')
        self.assertEqual(len(images), 2)
        for element in images:
            embedded = base64.b64decode(element.get('href').split(',')[1])
            self.assertIn(b'id="color"', embedded)
        self.assertEqual(len(records), 2)

    def test_reuses_one_instance_per_clip_and_does_not_multiply_local_time(self):
        instances = []

        def loader(action, **kwargs):
            self.assertEqual(kwargs, {'duration': 1, 'speed': 1.25})
            instance = FakeAction('#ff0000')
            instances.append(instance)
            return instance
        renderer = SceneRenderer(loader)
        renderer.frame(sample([actor()]), 0)
        renderer.frame(sample([actor()]), 1)
        renderer.frame(sample([actor(1)]), 2)
        self.assertEqual(len(instances), 2)
        self.assertEqual(instances[0].calls, [(0.1, 0, True), (0.1, 1, True)])

    def test_actor_draw_order_and_scene_clipping(self):
        renderer = SceneRenderer(lambda name, **kwargs: FakeAction('#ff0000' if name.endswith('right') else '#0000ff'))
        svg, _ = renderer.frame(sample([actor(), actor(1, 20, 'side-run-left')]), 0)
        self.assertEqual(image(svg).getpixel((20, 40)), (0, 0, 255, 255))
        svg, _ = renderer.frame(sample([actor(2, -5)]), 1)
        self.assertEqual(image(svg).size, (100, 80))
        self.assertEqual(image(svg).getpixel((0, 40)), (255, 0, 0, 255))

    def test_hidden_actors_produce_background_only(self):
        svg, record = SceneRenderer().frame(sample(), 0)
        self.assertEqual(image(svg).getextrema(), ((255, 255),) * 4)
        self.assertEqual(record, [])

    def test_anchor_and_clip_setting_drift_are_rejected(self):
        renderer = SceneRenderer(lambda *args, **kwargs: FakeAction('#ff0000'))
        renderer.frame(sample([actor()]), 0)
        changed = actor(); changed['speed'] = 2
        with self.assertRaisesRegex(ValueError, 'settings changed'):
            renderer.frame(sample([changed]), 1)
        changed = actor(); changed['sourceAnchor'] = [1, 2]
        with self.assertRaisesRegex(ValueError, 'anchor changed'):
            renderer.frame(sample([changed]), 2)

    def test_saved_action_matches_direct_render_on_white_without_source_changes(self):
        root = Path(__file__).resolve().parents[1]
        paths = [root/'characters/hoodie-side/character.svg', root/'motions/side-run.json', root/'poses/side-run.json']
        originals = [p.read_bytes() for p in paths]
        saved = load_side_action('side-run-left', duration=1, speed=1.25)
        svg, _ = saved.frame(0.1, 3, clean=True)
        direct = image(svg, 1280, 720)
        background = Image.new('RGBA', direct.size, '#ffffff')
        expected = Image.alpha_composite(background, direct)
        item = actor(action='side-run-left')
        item.update(sourceAnchor=[640, 650], transform=[1, 0, 0, 1, 0, 0])
        state = sample([item]); state['output'].update(width=1280, height=720)
        combined, _ = SceneRenderer().frame(state, 3)
        difference = ImageChops.difference(expected, image(combined, 1280, 720))
        self.assertLessEqual(max(hi for lo, hi in difference.getextrema()), 1)
        self.assertEqual([p.read_bytes() for p in paths], originals)

    def test_manifest_refuses_existing_frame_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            frames = output/'frames'; frames.mkdir()
            keep = frames/'keep.txt'; keep.write_text('keep')
            with self.assertRaises(FileExistsError):
                render_manifest({'version': 1, 'frameCount': 1, 'samples': [sample()]}, output)
            self.assertEqual(keep.read_text(), 'keep')
            self.assertFalse((output/'svg').exists())

    def test_manifest_writes_exact_empty_frames_and_scoped_contacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            result = render_manifest({'version': 1, 'frameCount': 2, 'samples': [sample(), sample()]}, output)
            self.assertEqual(result['frameCount'], 2)
            self.assertEqual(len(list((output/'frames').glob('*.png'))), 2)
            self.assertEqual(len(list((output/'svg').glob('*.svg'))), 2)
            contacts = json.loads((output/'contacts.json').read_text())
            self.assertIn('not independent', contacts['scope'])


if __name__ == '__main__':
    unittest.main()
