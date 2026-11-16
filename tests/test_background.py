import copy
import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET

from PIL import Image

from tools.animate import raster
from tools.background import Backgrounds
from tools.preview import ROOT, SVG
from tools.render_scene import SceneRenderer


class BackgroundTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='cutout-background-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root/'backgrounds').mkdir()
        image = Image.new('RGB', (40, 20), 'red')
        image.paste('blue', (20, 0, 40, 20))
        self.path = self.root/'backgrounds/test.png'
        image.save(self.path)
        self.plate = {'asset': 'test', 'file': 'test.png', 'width': 40, 'height': 20,
                      'mime': 'image/png', 'sha256': hashlib.sha256(self.path.read_bytes()).hexdigest(), 'fit': 'contain'}
        self.patch = patch('tools.background.ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_contain_and_cover_preserve_aspect_and_mat_color(self):
        for fit in ['contain', 'cover']:
            plate = {**self.plate, 'fit': fit}
            sample = {'output': {'width': 100, 'height': 100},
                      'stage': {'background': '#00ff00', 'plate': plate}, 'actors': []}
            renderer = SceneRenderer()
            svg, records = renderer.frame(sample, 0)
            self.assertEqual(records, [])
            node = ET.fromstring(svg).find(f'{{{SVG}}}image')
            self.assertEqual(node.get('preserveAspectRatio'), 'xMidYMid ' + ('meet' if fit == 'contain' else 'slice'))
            buffer = io.BytesIO()
            raster(svg, 100, 100).write_to_png(buffer)
            image = Image.open(buffer).convert('RGB')
            self.assertEqual(image.getpixel((10, 50)), (255, 0, 0))
            self.assertEqual(image.getpixel((90, 50)), (0, 0, 255))
            self.assertEqual(image.getpixel((10, 5)), (0, 255, 0) if fit == 'contain' else (255, 0, 0))
            self.assertEqual(renderer.frame(sample, 0)[0], svg)
            self.assertEqual(len(renderer.backgrounds.cache), 1)

    def test_changed_or_misdescribed_images_fail_before_rendering(self):
        for field, value in [('width', 41), ('mime', 'image/jpeg'), ('sha256', '0'*64), ('file', '../secret.png')]:
            with self.assertRaises(ValueError):
                Backgrounds().image({**self.plate, field: value})
        link = self.root/'backgrounds/link.png'
        link.symlink_to(self.path)
        with self.assertRaises(ValueError):
            Backgrounds().image({**self.plate, 'file': 'link.png'})
        self.path.write_bytes(b'not an image anymore')
        with self.assertRaisesRegex(ValueError, 'changed'):
            Backgrounds().image(self.plate)

    def test_registered_jpeg_is_behind_the_actor_and_sources_are_preserved(self):
        self.patch.stop()
        import json
        row = json.loads((ROOT/'backgrounds/registry.json').read_text())['assets']['dice-school-courtyard']
        plate = {**row, 'asset': 'dice-school-courtyard', 'fit': 'contain'}
        original = (ROOT/'backgrounds'/row['file']).read_bytes()
        sample = {'output': {'width': 320, 'height': 180},
                  'stage': {'background': '#ffffff', 'plate': plate},
                  'actors': [{'id': 'runner', 'clipIndex': 0, 'action': 'side-run-right',
                              'duration': 1, 'speed': 1, 'localTime': 0,
                              'sourceAnchor': [640, 650], 'position': [160, 170], 'scale': 0.2,
                              'transform': [0.2, 0, 0, 0.2, 32, 40]}]}
        before = copy.deepcopy(sample)
        svg, records = SceneRenderer().frame(sample, 0)
        images = ET.fromstring(svg).findall(f'{{{SVG}}}image')
        self.assertEqual(len(images), 2)
        self.assertEqual(images[0].get('id'), 'stage-background')
        self.assertTrue(images[0].get('href').startswith('data:image/jpeg;base64,'))
        self.assertTrue(images[1].get('href').startswith('data:image/svg+xml;base64,'))
        self.assertEqual(len(records), 1)
        self.assertEqual(sample, before)
        self.assertEqual((ROOT/'backgrounds'/row['file']).read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
