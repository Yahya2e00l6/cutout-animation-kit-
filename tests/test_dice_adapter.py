import base64
import hashlib
import io
import json
import math
import unittest
import xml.etree.ElementTree as ET

from PIL import Image
from tools.animate import raster
from tools.dice_adapter import DiceAdapter, ASSET
from tools.preview import SVG
from tools.render_scene import SceneRenderer
from test_support_run import actor_at, frame
from test_side_transition import delivered_point


class DiceAdapterTests(unittest.TestCase):
    def test_snapshot_is_byte_identical_and_drawings_survive_the_adapter(self):
        registry = json.loads((ASSET/'provenance.json').read_text())
        for name, entry in registry['files'].items():
            self.assertEqual(hashlib.sha256((ASSET/name).read_bytes()).hexdigest(), entry['sha256'])
        actor = actor_at(1.3); actor['character'] = 'dice-dongtae-upgraded'
        svg, _ = frame(SceneRenderer(), actor)
        outer = ET.fromstring(svg)
        root = ET.fromstring(base64.b64decode(outer.find(f'{{{SVG}}}image').get('href').split(',')[1]))
        original = ET.fromstring((ASSET/'character.svg').read_bytes())
        drawn = lambda r: [(e.tag, dict(e.attrib)) for e in r.iter()
                           if e.tag.rsplit('}', 1)[-1] in ('path', 'polygon', 'circle', 'ellipse', 'line', 'rect')]
        self.assertEqual(drawn(root), drawn(original))
        self.assertIsNotNone(next(e for e in root.iter() if e.get('id') == original.get('id')))
        self.assertEqual([e.text for e in root.iter() if e.tag == f'{{{SVG}}}style'],
                         [e.text for e in original.iter() if e.tag == f'{{{SVG}}}style'])

    def test_delivered_dice_toe_tracks_donor_and_native_bones_keep_their_lengths(self):
        adapter = DiceAdapter()
        for facing in ('right', 'left'):
            renderer = SceneRenderer()
            for t in (0, .6, .9, 1, 1.1, 1.26, 1.3, 1.333333, 1.5, 1.76, 2, 2.5, 3, 3.4, 3.9):
                actor = actor_at(t, facing)
                donor_svg, _ = frame(SceneRenderer(), actor)
                actor['character'] = 'dice-dongtae-upgraded'
                svg, records = frame(renderer, actor)
                report = records[0]['sourceContacts']['diceRetarget']
                self.assertLess(report['maxAnkleError'], .001)
                self.assertLess(report['additionalHipDrop'], 40)
                for side in ('left', 'right'):
                    hip, knee, ankle = adapter.pivots[side]
                    points = [delivered_point(svg, 'dt_upg_side_'+part+'_'+side, pivot)
                              for part, pivot in zip(('thigh', 'shin', 'foot'), (hip, knee, ankle))]
                    display_scale = .62/adapter.ratio
                    for length, a, b in zip(adapter.lengths[side], points, points[1:]):
                        self.assertAlmostEqual(math.dist(a, b), length*display_scale, places=6)
                    toe = delivered_point(svg, 'dt_upg_side_foot_'+side, (ankle[0]+60, ankle[1]+25))
                    expected = delivered_point(donor_svg, 'ankle-'+side, (75, 49))
                    self.assertAlmostEqual(toe[0], expected[0], places=6)

    def test_actual_shoes_touch_ground_and_palette_is_not_black(self):
        # No plate: pixels below the knees belong to the two unchanged shoes.
        for facing in ('right', 'left'):
            renderer = SceneRenderer()
            for t in (1, 1.1, 1.5, 1.6, 2, 2.1):
                actor = actor_at(t, facing); actor['character'] = 'dice-dongtae-upgraded'
                svg, _ = frame(renderer, actor)
                data = io.BytesIO(); raster(svg, 2560, 900).write_to_png(data)
                with Image.open(data) as image:
                    pixels = image.convert('RGB')
                    bounds = pixels.crop((0, 600, 2560, 640))
                    ink = [(x, y+600) for y in range(bounds.height) for x in range(bounds.width)
                           if max(bounds.getpixel((x, y))) < 150]
                    self.assertTrue(ink)
                    self.assertLessEqual(abs(max(y for _, y in ink)-620), 1)
                    self.assertGreater(sum(1 for rgb in pixels.getdata() if rgb[2] > rgb[0]+35 and rgb[0] < 50), 500)

    def test_delivered_dice_knee_does_not_repeat_the_post_release_hold(self):
        adapter = DiceAdapter()
        for facing in ('left', 'right'):
            for side, offset in (('right', 0), ('left', .5)):
                for phase in (.30, .333333):
                    actor = actor_at(1+offset+phase, facing)
                    actor['character'] = 'dice-dongtae-upgraded'
                    svg, records = frame(SceneRenderer(), actor)
                    hip, knee, ankle = [delivered_point(svg, 'dt_upg_side_'+part+'_'+side, pivot)
                                       for part, pivot in zip(('thigh', 'shin', 'foot'), adapter.pivots[side])]
                    upper = (knee[0]-hip[0], knee[1]-hip[1])
                    lower = (ankle[0]-knee[0], ankle[1]-knee[1])
                    cosine = sum(a*b for a, b in zip(upper, lower))/(math.hypot(*upper)*math.hypot(*lower))
                    self.assertGreater(math.degrees(math.acos(max(-1, min(1, cosine)))), 30)
                    self.assertLess(records[0]['sourceContacts']['diceRetarget']['additionalHipDrop'], 5)


if __name__ == '__main__':
    unittest.main()
