import base64
import io
import math
import re
import unittest
import xml.etree.ElementTree as ET

from PIL import Image

from tools.animate import raster
from tools.preview import ROOT, SVG
from tools.render_scene import SceneRenderer
from tools.side_actions import load_side_action
from tools.side_transition import TransitionPose, standing_angles
from tools.travel_run import SOURCES


def transform_point(point, transform):
    x, y = point
    for kind, text in reversed(re.findall(r'(translate|rotate|scale|matrix)\(([^)]+)\)', transform)):
        numbers = [float(n) for n in re.split(r'[ ,]+', text.strip())]
        if kind == 'translate':
            x, y = x + numbers[0], y + (numbers[1] if len(numbers) > 1 else 0)
        elif kind == 'scale':
            x, y = x * numbers[0], y * numbers[-1]
        elif kind == 'rotate':
            angle = math.radians(numbers[0])
            x, y = x*math.cos(angle)-y*math.sin(angle), x*math.sin(angle)+y*math.cos(angle)
        else:
            a, b, c, d, e, f = numbers
            x, y = a*x+c*y+e, b*x+d*y+f
    return x, y


class SideTransitionTests(unittest.TestCase):
    def test_transition_requests_do_not_change_middle_run_or_request_order(self):
        renderer = SceneRenderer()
        item = {'id': 'runner', 'clipIndex': 0, 'action': 'side-run-right',
                'duration': 6.6, 'speed': 0.3125, 'localTime': 0.2,
                'sourceAnchor': [640, 650], 'position': [640, 620], 'scale': 1,
                'transform': [1, 0, 0, 1, 0, -30],
                'footLock': True, 'travelVelocity': 236.19054411583462}
        def frame(actor):
            return renderer.frame({'output': {'width': 1280, 'height': 720},
                                   'stage': {'background': '#ffffff'}, 'actors': [actor]}, 0)
        baseline = frame(item)
        requests = [{**item, 'localTime': 0, 'transition': {'mode': 'start', 'weight': w}}
                    for w in [0, 0.1, 0.5, 1]]
        expected = [frame(actor) for actor in requests]
        for actor, result in reversed(list(zip(requests, expected))):
            self.assertEqual(frame(actor), result)
        self.assertEqual(frame(item), baseline)

    def test_weights_are_bounded_and_neutral_is_static(self):
        action = load_side_action('side-run-right')
        for bad in [-0.1, 1.1, math.nan, math.inf]:
            with self.assertRaises(ValueError):
                TransitionPose(action, bad)
        pose = TransitionPose(action, 0)
        self.assertEqual(pose.sample(0)['angles'], standing_angles())
        self.assertNotEqual(pose.sample(0)['angles']['hip-left'], pose.sample(0)['angles']['hip-right'])
        _, contacts = pose.pose(0)
        self.assertLess(max(contacts['shoe_clearance'].values()), 0.5)
        self.assertGreater(abs(pose.toe_x(0, 'left') - pose.toe_x(0, 'right')), 20)
        for side in ['left', 'right']:
            self.assertEqual(pose.sample(0)['angles'][f'knee-{side}'], 0)
            self.assertEqual(sum(pose.sample(0)['angles'][f'{joint}-{side}'] for joint in ['hip', 'knee', 'ankle']), 0)
        from tools.side_review import world_point
        posed, _ = pose.pose(0)
        shoulders = [world_point(posed, f'shoulder-{side}', (0, 0))[0] for side in ['left', 'right']]
        pelvis_x = world_point(posed, 'pelvis', (0, 0))[0]
        self.assertLess(abs(sum(shoulders)/2 - pelvis_x), 3)
        self.assertEqual(pose.frame(0, 0, clean=True)[0], pose.frame(1, 0, clean=True)[0])

    def test_full_weight_touchdowns_match_saved_run_geometry_and_sources_are_unchanged(self):
        sources = {name: (ROOT/name).read_bytes() for name in SOURCES}
        for facing in ['left', 'right']:
            action = load_side_action(f'side-run-{facing}')
            for t in [0, action.config['cycle']/2, action.config['cycle']*2]:
                # Numeric spelling of the root transform can differ; compare rasters.
                a, _ = action.frame(t, 0, clean=True)
                b, _ = TransitionPose(action, 1).frame(t, 0, clean=True)
                def pixels(svg):
                    buffer = io.BytesIO()
                    raster(svg, 1280, 720).write_to_png(buffer)
                    return Image.open(buffer).convert('RGBA').tobytes()
                self.assertEqual(pixels(a), pixels(b))
                self.assertEqual(action.sample(t), TransitionPose(action, 1).sample(t))
        self.assertEqual(sources, {name: (ROOT/name).read_bytes() for name in SOURCES})

    def test_composed_transition_pixels_are_grounded_and_toe_x_matches_independent_fk(self):
        for facing, sign in [('right', 1), ('left', -1)]:
            action = load_side_action(f'side-run-{facing}', speed=0.3125)
            renderer = SceneRenderer()
            for time in [0, 1, 4]:  # touchdown at each half-cycle, including left support
                side = 'right' if round(time/action.config['cycle']*2) % 2 == 0 else 'left'
                anchored = []
                for weight in [0, 0.25, 0.5, 0.75, 1]:
                    x = 640
                    item = {'id': 'runner', 'clipIndex': 0, 'action': f'side-run-{facing}',
                            'duration': 6.6, 'speed': 0.3125, 'localTime': time,
                            'sourceAnchor': [640, 650], 'position': [x, 620], 'scale': 0.7,
                            'transform': [0.7, 0, 0, 0.7, x-448, 165],
                            'footLock': True, 'travelVelocity': sign*236.19054411583462,
                            'transition': {'mode': 'start', 'weight': weight}}
                    svg, records = renderer.frame({'output': {'width': 1280, 'height': 720},
                                                  'stage': {'background': '#ffffff'}, 'actors': [item]}, 0)
                    outer = ET.fromstring(svg)
                    outer.remove(outer.find(f'{{{SVG}}}rect'))
                    buffer = io.BytesIO()
                    raster(ET.tostring(outer), 1280, 720).write_to_png(buffer)
                    alpha = Image.open(buffer).convert('RGBA').getchannel('A').point(lambda n: 255 if n >= 128 else 0)
                    bounds = alpha.getbbox()
                    self.assertLessEqual(abs(bounds[3]-620), 1)
                    self.assertGreater(bounds[0], 0)
                    self.assertLess(bounds[2], 1280)
                    # Read the embedded delivered SVG rather than trusting its contact report.
                    image = outer.find(f'{{{SVG}}}image')
                    embedded = ET.fromstring(base64.b64decode(image.get('href').split(',')[1]))
                    parents = {child: parent for parent in embedded.iter() for child in parent}
                    node = next(n for n in embedded.iter() if n.get('id') == f'ankle-{side}')
                    point = action.rig['review']['toe']
                    while node is not None:
                        point = transform_point(point, node.get('transform', ''))
                        node = parents.get(node)
                    px, _ = transform_point(point, image.get('transform'))
                    anchored.append(px)
                    self.assertAlmostEqual(px, records[0]['horizontalLock']['anchorX'], places=6)
                    self.assertEqual(records[0]['horizontalLock']['mode'], 'transition')
                self.assertLess(max(anchored)-min(anchored), 1e-6)


if __name__ == '__main__':
    unittest.main()
