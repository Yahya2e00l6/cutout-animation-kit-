import base64
import io
import json
import math
import unittest
import xml.etree.ElementTree as ET

from PIL import Image

from tools.animate import raster
from tools.preview import ROOT, SVG
from tools.render_scene import SceneRenderer
from tools.side_actions import load_side_action
from tools.travel_run import TravelRun, calibration, SOURCES


def shoe_pixels(svg, side):
    """Independently rasterize the delivered shoe, retaining all ancestor transforms."""
    outer = ET.fromstring(svg)
    for rect in outer.findall(f'{{{SVG}}}rect'):
        outer.remove(rect)
    image = outer.find(f'{{{SVG}}}image')
    document = ET.fromstring(base64.b64decode(image.get('href').split(',')[1]))
    shoe = next(node for node in document.iter() if node.get('id') == f'ankle-{side}')
    parents = {child: parent for parent in document.iter() for child in parent}
    keep = set(shoe.iter())
    node = shoe
    while node in parents:
        node = parents[node]
        keep.add(node)
    for defs in document.findall(f'{{{SVG}}}defs'):
        keep.update(defs.iter())
    for parent in list(document.iter()):
        for child in list(parent):
            if child not in keep:
                parent.remove(child)
    data = 'data:image/svg+xml;base64,' + base64.b64encode(ET.tostring(document)).decode()
    image.set('href', data)
    image.set('{http://www.w3.org/1999/xlink}href', data)
    buffer = io.BytesIO()
    raster(ET.tostring(outer), 1280, 720).write_to_png(buffer)
    pixels = Image.open(buffer).convert('RGBA').getchannel('A').point(lambda n: 255 if n >= 128 else 0)
    return pixels.getbbox()


class TravelRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.calibration = calibration()
        cls.speed = 192 * 0.625 / cls.calibration['pixelsPerCycle']

    def test_calibration_matches_saved_sources_and_measured_stride(self):
        self.assertEqual(self.calibration, json.loads((ROOT/'motions/side-run-travel.json').read_text()))
        self.assertGreater(self.calibration['pixelsPerCycle'], 0)

    def test_dense_stance_toe_coordinates_agree_with_independent_forward_kinematics(self):
        for facing, sign in [('right', 1), ('left', -1)]:
            action = load_side_action(f'side-run-{facing}', speed=self.speed)
            adapter = TravelRun(action)
            for scale in [0.5, 1, 1.25]:
                velocity = sign * 192 * scale
                for half in range(6):
                    side = 'right' if half % 2 == 0 else 'left'
                    start = half * adapter.cycle / 2
                    anchors = []
                    for fraction in [0, 0.025, 0.05, 0.1, 0.16, 0.2, 0.26]:
                        time = start + fraction * adapter.cycle
                        position = 640 + velocity * time
                        offset, record = adapter.correction(time, velocity, scale, position)
                        angles = action.sample(time)['angles']
                        h, k, a = [math.radians(angles[f'{joint}-{side}']) for joint in ['hip', 'knee', 'ankle']]
                        relative = -145*math.sin(h)-158*math.sin(h+k)+75*math.cos(h+k+a)-49*math.sin(h+k+a)
                        actual = position + sign * action.config['scale'] * scale * relative + offset
                        self.assertAlmostEqual(actual, record['toeX'], places=6)
                        self.assertAlmostEqual(actual, record['anchorX'], places=6)
                        anchors.append(actual)
                    self.assertLess(max(anchors)-min(anchors), 1e-6)

    def test_offsets_are_periodic_order_independent_and_have_continuous_velocity(self):
        adapter = TravelRun(load_side_action('side-run-right', speed=self.speed))
        def offset(t):
            return adapter.correction(t, 192, 1, 160+192*t)[0]
        expected = [offset(i*adapter.cycle/100) for i in range(101)]
        for i in reversed(range(101)):
            self.assertAlmostEqual(offset(i*adapter.cycle/100), expected[i], places=8)
            self.assertAlmostEqual(offset((i/100+2)*adapter.cycle), expected[i], places=7)
        for phase in [0.26, 0.5, 0.76, 1, 1.26]:
            t = phase * adapter.cycle
            h = 1e-5
            self.assertLess(abs((offset(t)-offset(t-h))/h-(offset(t+h)-offset(t))/h), 0.2)

    def test_actual_flat_stance_shoe_pixels_do_not_slide_in_both_directions(self):
        for facing, direction in [('right', 1), ('left', -1)]:
            config = load_side_action(f'side-run-{facing}', speed=self.speed).config
            bounds = {True: [], False: []}
            for lock in [False, True]:
                renderer = SceneRenderer()
                for phase in [0, 0.1]:
                    t = phase * config['cycle']
                    x = 640 + direction * 192 * t
                    item = {'id': 'runner', 'clipIndex': 0, 'action': f'side-run-{facing}',
                            'duration': 5, 'speed': self.speed, 'localTime': t,
                            'sourceAnchor': [640, 650], 'position': [x, 620], 'scale': 1,
                            'transform': [1, 0, 0, 1, x-640, -30],
                            'footLock': lock, 'travelVelocity': direction*192}
                    sample = {'output': {'width': 1280, 'height': 720},
                              'stage': {'background': '#ffffff'}, 'actors': [item]}
                    svg, _ = renderer.frame(sample, round(t*30))
                    bbox = shoe_pixels(svg, 'right')
                    self.assertIsNotNone(bbox)
                    self.assertLessEqual(abs(bbox[3]-620), 1.25)
                    bounds[lock].append((bbox[0]+bbox[2])/2)
            self.assertLessEqual(abs(bounds[True][1]-bounds[True][0]), 1)
            self.assertGreater(abs(bounds[False][1]-bounds[False][0]), 30)

    def test_rendered_correction_preserves_source_assets_and_unlocked_frames(self):
        original = {name: (ROOT/name).read_bytes() for name in SOURCES}
        action = load_side_action('side-run-right', speed=self.speed)
        before, _ = action.frame(0.2, 6, clean=True)
        adapter = TravelRun(action)
        for t in [1.2, 0.2, 2.5, 0]:
            adapter.correction(t, 192, 1, 160+192*t)
        after, _ = action.frame(0.2, 6, clean=True)
        self.assertEqual(before, after)
        self.assertEqual(original, {name: (ROOT/name).read_bytes() for name in SOURCES})

    def test_invalid_inputs_are_rejected(self):
        adapter = TravelRun(load_side_action('side-run-right'))
        for values in [(-1, 192, 1, 0), (0, math.inf, 1, 0), (0, 192, 0, 0), (0, 192, 1, math.nan)]:
            with self.assertRaises(ValueError):
                adapter.correction(*values)


if __name__ == '__main__':
    unittest.main()
