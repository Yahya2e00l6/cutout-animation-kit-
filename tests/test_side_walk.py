import copy
import io
import json
import math
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from PIL import Image

from tools.animate import raster
from tools.preview import ROOT, SVG
from tools.side_walk import AstraBody, GenericBody, SideWalk, foot_path, solve_leg
from tools.svg_rig import build


def only_shoe(svg, ident):
    root = ET.fromstring(svg)
    parents = {child: parent for parent in root.iter() for child in parent}
    shoe = next(n for n in root.iter() if n.get('id') == ident)
    keep = set(shoe.iter())
    node = shoe
    while node in parents:
        node = parents[node]; keep.add(node)
    for defs in root.findall(f'{{{SVG}}}defs'):
        keep.update(defs.iter())
    for node in list(root.iter()):
        for child in list(node):
            if child not in keep:
                node.remove(child)
    return ET.tostring(root)


class SideWalkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.bodies = [AstraBody(), GenericBody(ROOT/'characters/ponytail-hoodie-side/rig.json')]
        for name in ('compact', 'tall'):
            source = ROOT/'examples/svg-setup'
            out = Path(cls.tmp.name)/name
            build(source/f'{name}.svg', source/f'{name}.setup.json', out)
            cls.bodies.append(GenericBody(out/'rig.json'))
        cls.walks = [SideWalk(b) for b in cls.bodies]

    def test_walk_always_has_support_and_has_double_support_not_flight(self):
        for walk in self.walks:
            double = 0
            for i in range(240):
                record = walk.sample(i/240*walk.config['cycle'])
                count = sum(c['stance'] for c in record['contacts'].values())
                self.assertGreaterEqual(count, 1)
                double += count == 2
                for contact in record['contacts'].values():
                    if contact['stance']:
                        self.assertEqual(contact['clearance'], 0)
                        self.assertEqual(contact['shoeAngle'], 0)
            self.assertGreater(double, 40)
            self.assertLess(double, 80)

    def test_actual_fk_reaches_targets_without_stretching_on_four_bodies(self):
        for walk in self.walks:
            for i in range(72):
                _, record = walk.frame(i/72*walk.config['cycle'])
                self.assertLess(record['targetResidual'], 1e-8)
                for side in ('left', 'right'):
                    points = record['joints']
                    for index, (a, b) in enumerate([('hip', 'knee'), ('knee', 'ankle')]):
                        self.assertAlmostEqual(math.dist(points[f'{a}-{side}'], points[f'{b}-{side}']),
                                               walk.body.lengths[side][index], places=8)

    def test_rendered_world_ankles_are_fixed_in_each_stance_both_directions(self):
        for walk in self.walks[:2]:
            for facing in ('left', 'right'):
                for speed in (.7, 1.4):
                    anchors = {}
                    for i in range(151):
                        t = i/50*walk.config['cycle']/speed
                        _, record = walk.frame(t, speed, facing)
                        for side, offset in [('right', 0), ('left', .5)]:
                            if not record['contacts'][side]['stance']:
                                continue
                            cycle = math.floor(t*speed/walk.config['cycle']-offset+1e-9)
                            key = (side, cycle)
                            ankle = record['worldJoints'][f'ankle-{side}']
                            anchors.setdefault(key, ankle)
                            self.assertLess(math.dist(ankle, anchors[key]), 1e-7)

    def test_actual_shoe_pixels_touch_floor_and_swing_clear_it(self):
        for walk in self.walks[:2]:
            body = walk.body
            for local in (.1, .4, .8):
                svg, record = walk.frame(local*walk.config['cycle'])
                ident = 'ankle-right' if isinstance(body, AstraBody) else body.rig.rig['parts']['foot-right']
                fragment = only_shoe(svg, ident)
                w, h = map(round, body.box[2:])
                buffer = io.BytesIO(); raster(fragment, w*2, h*2).write_to_png(buffer)
                with Image.open(buffer) as image:
                    bounds = image.convert('RGBA').getchannel('A').point(lambda n: 255 if n >= 128 else 0).getbbox()
                self.assertIsNotNone(bounds)
                expected = body.floor-record['contacts']['right']['clearance']-body.box[1]
                self.assertAlmostEqual(bounds[3]/2, expected, delta=.8)

    def test_world_space_shoe_raster_is_stationary_through_stance(self):
        for walk in self.walks[:2]:
            body = walk.body
            ident = 'ankle-right' if isinstance(body, AstraBody) else body.rig.rig['parts']['foot-right']
            for facing in ('right', 'left'):
                boxes = []
                for phase in (.04, .18, .35, .55):
                    svg, record = walk.frame(phase*walk.config['cycle'], facing=facing)
                    root = ET.fromstring(only_shoe(svg, ident))
                    root.set('viewBox', f'-512 {body.box[1]} 2048 {body.box[3]}')
                    group = ET.Element(f'{{{SVG}}}g', transform=f'translate({record["travel"]} 0)')
                    for child in list(root):
                        if child.tag != f'{{{SVG}}}defs':
                            root.remove(child); group.append(child)
                    root.append(group)
                    buffer = io.BytesIO(); raster(ET.tostring(root), 2048, round(body.box[3])).write_to_png(buffer)
                    with Image.open(buffer) as image:
                        boxes.append(image.convert('RGBA').getchannel('A').point(lambda n: 255 if n >= 128 else 0).getbbox())
                self.assertTrue(all(box is not None for box in boxes))
                for box in boxes[1:]:
                    self.assertTrue(all(abs(a-b) <= 1 for a, b in zip(box, boxes[0])), boxes)

    def test_foot_path_matches_position_velocity_and_acceleration_at_boundaries(self):
        d, distance, lift, h = .62, 200, 25, 1e-5
        def at(p):
            return foot_path(p % 1, d, distance, lift)[:2]
        for boundary in (0, d):
            p0, pm, pp = at(boundary), at(boundary-h), at(boundary+h)
            for axis in (0, 1):
                left = (p0[axis]-pm[axis])/h
                right = (pp[axis]-p0[axis])/h
                self.assertAlmostEqual(left, right, delta=.001)
                self.assertAlmostEqual(left, -distance if axis == 0 else 0, delta=.001)
                aleft = (p0[axis]-2*pm[axis]+at(boundary-2*h)[axis])/h**2
                aright = (at(boundary+2*h)[axis]-2*pp[axis]+p0[axis])/h**2
                self.assertAlmostEqual(aleft, aright, delta=5)

    def test_pose_and_velocity_are_continuous_at_loop_and_stance_exchange(self):
        walk = self.walks[0]
        h = 1e-7
        for phase in (0, .5, .62, .12):
            records = [walk.sample((phase+dt) % 1*walk.config['cycle']) for dt in (-h, 0, h)]
            for channel in records[0]['angles']:
                a, b, c = [r['angles'][channel] for r in records]
                self.assertLess(abs(a-c), .01)
                self.assertLess(abs((b-a)/h-(c-b)/h), 1)

    def test_sampling_is_deterministic_and_cadence_applied_once(self):
        walk = self.walks[1]
        times = [0, .17, .43, 1.2, 2.77]
        expected = [walk.frame(t) for t in times]
        for i in (4, 0, 3, 2, 1):
            self.assertEqual(walk.frame(times[i]), expected[i])
        self.assertEqual(walk.sample(.2, 2)['angles'], walk.sample(.4)['angles'])
        self.assertEqual(walk.sample(.2, 2)['travel'], walk.sample(.4)['travel'])
        a, b = walk.sample(0), walk.sample(walk.config['cycle'])
        self.assertEqual(a['angles'], b['angles'])

    def test_stride_is_in_native_leg_lengths_and_arms_counter_swing(self):
        for walk in self.walks:
            c = walk.config
            length = sum(sum(v) for v in walk.body.lengths.values())/2
            at_start, at_end = walk.sample(0), walk.sample(c['cycle'])
            self.assertAlmostEqual(at_end['travel']-at_start['travel'], .68*length)
            before = walk.sample(.02*c['cycle'])
            after = walk.sample(.52*c['cycle'])
            self.assertAlmostEqual(before['ankleTargets']['right'][0]-after['ankleTargets']['right'][0], .34*length)
            # Near leg forward at contact, near arm back in the SVG convention.
            self.assertGreater(at_start['ankleTargets']['right'][0], walk.body.joints['hip-right'][0])
            self.assertGreater(at_start['angles']['shoulder-right'], 0)
            self.assertLess(at_start['angles']['shoulder-left'], 0)

    def test_inputs_reject_nonfinite_time_bad_config_and_unreachable_targets(self):
        walk = self.walks[0]
        for t, speed in [(-1, 1), (True, 1), (math.nan, 1), (0, 0), (0, math.inf), (1e308, 1e308)]:
            with self.assertRaises(ValueError):
                walk.sample(t, speed)
        for dx, dy in [(0, 0), (0, 200), (10, 0)]:
            with self.assertRaises(ValueError):
                solve_leg(dx, dy, 55, 45)
        for key, value in [('cycle', 0), ('stance', .4), ('hipHeight', math.nan), ('armSwing', True)]:
            config = copy.deepcopy(walk.config); config[key] = value
            with self.assertRaises(ValueError):
                SideWalk(walk.body, config)
        with self.assertRaises(ValueError):
            walk.frame(0, facing='back')
        config = copy.deepcopy(walk.config); config.update(distancePerCycle=1, hipHeight=.98, hipBob=.04)
        lowered = SideWalk(walk.body, config)
        _, record = lowered.frame(0)
        self.assertGreater(record['reachHipDrop'], 0)
        self.assertLess(record['targetResidual'], 1e-8)

    def test_original_assets_and_run_files_are_not_modified(self):
        # A source-level boundary guard in addition to git/source-hash checks.
        module = (ROOT/'tools/side_walk.py').read_text()
        self.assertNotIn('SupportRun(', module)
        for walk in self.walks[:2]:
            if isinstance(walk.body, GenericBody):
                before = ET.tostring(walk.body.rig.root)
                walk.frame(.45)
                self.assertEqual(ET.tostring(walk.body.rig.root), before)
            else:
                before = ET.tostring(walk.body.asset.tree.getroot())
                walk.frame(.45)
                self.assertEqual(ET.tostring(walk.body.asset.tree.getroot()), before)


if __name__ == '__main__':
    unittest.main()
