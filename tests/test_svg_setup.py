import copy
import hashlib
import io
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from PIL import Image

from tools.animate import raster
from tools.preview import ROOT, SVG
from tools.run_profile import RunProfile
from tools.svg_rig import SvgRig, PARTS, ENDS, build, read_svg, template, validate_setup


FIXTURES = ROOT/'examples/svg-setup'


class SvgSetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.directory = Path(cls.tmp.name)
        cls.profile = RunProfile(ROOT/'motions/shared-side-run.json')
        cls.rigs = []
        for name in ('compact', 'tall'):
            build(FIXTURES/f'{name}.svg', FIXTURES/f'{name}.setup.json', cls.directory/name)
            cls.rigs.append(SvgRig(cls.directory/name/'rig.json'))

    def test_inspect_and_template_report_groups_but_do_not_guess_anatomy(self):
        before = (FIXTURES/'compact.svg').read_bytes()
        data = template(FIXTURES/'compact.svg')
        self.assertEqual(len(data['availableGroups']), 14)
        self.assertEqual(set(data['parts']), set(PARTS))
        self.assertTrue(all(p is None for p in data['joints'].values()))
        self.assertEqual(before, (FIXTURES/'compact.svg').read_bytes())

    def test_build_copies_source_exactly_and_refuses_existing_packages(self):
        path = self.directory/'compact'
        source = (FIXTURES/'compact.svg').read_bytes()
        self.assertEqual((path/'character.svg').read_bytes(), source)
        self.assertEqual(self.rigs[0].rig['sha256'], hashlib.sha256(source).hexdigest())
        with self.assertRaises(FileExistsError):
            build(FIXTURES/'compact.svg', FIXTURES/'compact.setup.json', path)
        self.assertEqual((path/'character.svg').read_bytes(), source)

    def test_invalid_mapping_missing_pivots_zero_bones_and_bad_layers_fail(self):
        setup = json.loads((FIXTURES/'compact.setup.json').read_text())
        _, root, box, groups = read_svg(FIXTURES/'compact.svg')
        changes = [lambda s: s['parts'].pop('head'),
                   lambda s: s['parts'].update(head='unknown'),
                   lambda s: s['parts'].update(head=s['parts']['torso']),
                   lambda s: s['joints'].update(neck=None),
                   lambda s: s['joints'].update(neck=[math.nan, 5]),
                   lambda s: s['joints'].update(neck=[False, 5]),
                   lambda s: s['joints'].update(neck=[5000, 5]),
                   lambda s: s['joints'].update({'knee-right': s['joints']['hip-right']}),
                   lambda s: s.update(layers=s['layers'][:-1]),
                   lambda s: s.update(view='front'), lambda s: s.update(version=True)]
        for change in changes:
            bad = copy.deepcopy(setup); change(bad)
            with self.assertRaises(ValueError):
                validate_setup(bad, root, box, groups)

    def test_external_active_and_ambiguous_svg_inputs_are_rejected(self):
        source = (FIXTURES/'compact.svg').read_text()
        tails = ['<script>alert(1)</script>', '<image href="https://example.com/a.png"/>',
                 '<use href="#body"/>', '<g onload="bad()"/>',
                 '<style>@import "https://example.com/a.css";</style>',
                 '<style>.shirt{fill:url(https://example.com/a)}</style>',
                 '<style>#compact-test > g {opacity:.5}</style>']
        for i, tail in enumerate(tails):
            path = self.directory/f'bad-{i}.svg'; path.write_text(source.replace('</svg>', tail+'</svg>'))
            with self.assertRaises(ValueError):
                read_svg(path)
        path = self.directory/'dtd.svg'
        path.write_text('<!DOCTYPE svg [<!ENTITY foo "bad">]>'+source)
        with self.assertRaises(ValueError):
            read_svg(path)

    def test_flattened_svg_is_not_silently_claimed_as_ready(self):
        _, root, box, groups = read_svg(FIXTURES/'compact.svg')
        ET.SubElement(root, f'{{{SVG}}}path', d='M0 0L1 1')
        setup = json.loads((FIXTURES/'compact.setup.json').read_text())
        with self.assertRaises(ValueError):
            validate_setup(setup, root, box, groups)

    def test_same_profile_drives_different_lengths_without_stretching(self):
        self.assertNotEqual(self.rigs[0].lengths, self.rigs[1].lengths)
        for rig in self.rigs:
            for i in range(32):
                points, _ = rig.skeleton(self.profile.sample(i/32*self.profile.cycle))
                for side in ('left', 'right'):
                    for role, (a, b) in ENDS.items():
                        self.assertAlmostEqual(math.dist(points[f'{a}-{side}'], points[f'{b}-{side}']),
                                               rig.lengths[f'{role}-{side}'], places=8)

    def test_sources_and_artwork_paths_are_preserved_in_every_pose(self):
        rig = self.rigs[0]
        before = ET.tostring(rig.root)
        svg, _ = rig.frame(self.profile, .2)
        nodes = {e.get('id'): e for e in ET.fromstring(svg).iter() if e.get('id')}
        for ident, original in rig.groups.items():
            self.assertEqual(ET.tostring(nodes[ident]), ET.tostring(original))
        self.assertEqual(ET.tostring(rig.root), before)
        self.assertEqual(len(nodes), len([e for e in ET.fromstring(svg).iter() if e.get('id')]))

    def test_measured_vertical_grounding_matches_independent_shoe_pixels(self):
        for rig in self.rigs:
            for phase in (0, .125, .36, .5):
                svg, record = rig.frame(self.profile, phase*self.profile.cycle)
                root = ET.fromstring(svg)
                layer = root[-1]
                for child, role in list(zip(list(layer), rig.rig['layers'])):
                    if not role.startswith('foot-'):
                        layer.remove(child)
                out = io.BytesIO(); width, height = map(round, rig.box[2:])
                raster(ET.tostring(root), width*2, height*2).write_to_png(out)
                bounds = Image.open(out).getchannel('A').point(lambda n: 255 if n >= 128 else 0).getbbox()
                self.assertIsNotNone(bounds)
                expected = height*.94-record['clearance']
                self.assertAlmostEqual(bounds[3]/2, expected, delta=.8)

    def test_playback_needs_no_hoodie_or_dice_artwork(self):
        original_open = Path.open
        def guard(path, *args, **kwargs):
            if set(path.parts) & {'hoodie-side', 'hoodie', 'dice-dongtae-upgraded-side'}:
                raise AssertionError('Character-specific input used')
            return original_open(path, *args, **kwargs)
        with patch.object(Path, 'open', guard):
            profile = RunProfile(ROOT/'motions/shared-side-run.json')
            for name in ('compact', 'tall'):
                svg, _ = SvgRig(self.directory/name/'rig.json').frame(profile, .1)
                self.assertTrue(svg)

    def test_speed_loop_and_random_access_are_deterministic(self):
        profile = self.profile
        self.assertEqual(profile.sample(.1, 2), profile.sample(.2))
        for name in profile.sample(0)['angles']:
            self.assertAlmostEqual(profile.sample(0)['angles'][name], profile.sample(profile.cycle)['angles'][name])
        rig = self.rigs[0]
        expected = [rig.frame(profile, t) for t in (0, .1, .3)]
        for i in (2, 0, 1):
            self.assertEqual(rig.frame(profile, (0, .1, .3)[i]), expected[i])
        for seconds, speed in [(-1, 1), (math.nan, 1), (0, 0), (0, math.inf), (False, 1)]:
            with self.assertRaises(ValueError):
                profile.sample(seconds, speed)

    def test_stale_artwork_is_rejected_before_playback(self):
        out = self.directory/'stale'
        build(FIXTURES/'tall.svg', FIXTURES/'tall.setup.json', out)
        path = out/'character.svg'; path.write_bytes(path.read_bytes()+b'\n')
        with self.assertRaises(ValueError):
            SvgRig(out/'rig.json')

    def test_invalid_profiles_fail_before_sampling(self):
        good = self.profile.data
        bad_values = [[], {**good, 'cycle': 0}, {**good, 'cycle': math.inf},
                      {**good, 'samples': []}, {**good, 'samples': [None]*8},
                      {**good, 'samples': [{'angles': [], 'clearance': 0}]*8}]
        for i, bad in enumerate(bad_values):
            path = self.directory/f'profile-bad-{i}.json'
            path.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):
                RunProfile(path)

    def test_profile_knots_and_loop_velocities_match_the_export(self):
        p = self.profile
        for i, row in enumerate(p.rows):
            sample = p.sample(i/len(p.rows)*p.cycle)
            for name, expected in row['angles'].items():
                self.assertAlmostEqual(sample['angles'][name], expected, places=7)
        h = 1e-7
        for name in p.rows[0]['angles']:
            a, b, c = [p.sample(t)['angles'][name] for t in (p.cycle-h, 0, h)]
            self.assertLess(abs((b-a)/h-(c-b)/h), .1)

    def test_profile_provenance_and_source_angles_match_the_saved_support_run(self):
        from tools.side_actions import load_side_action
        from tools.support_run import SupportRun
        for name, digest in self.profile.data['source']['sha256'].items():
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(), digest)
        action = load_side_action('side-run-right')
        calibration = json.loads((ROOT/'motions/side-run-travel.json').read_text())
        source = SupportRun(action, calibration['pixelsPerCycle']/action.config['cycle'], 1)
        for phase in (0, .125, .25, .5, .75):
            expected = source.sample(phase*self.profile.cycle)['angles']
            actual = self.profile.sample(phase*self.profile.cycle)['angles']
            for name in actual:
                self.assertAlmostEqual(actual[name], expected[name], places=7)

    def test_preview_keeps_alpha_assets_but_encodes_opaque_review_frames(self):
        from tools.svg_setup import preview
        out = self.directory/'preview-check'
        with patch('tools.svg_setup.subprocess.check_output', return_value='{}') as encoder:
            preview(self.directory/'compact/rig.json', ROOT/'motions/shared-side-run.json', out, 1/30, 1, True)
        for call in encoder.call_args_list:
            command = call.args[0]
            self.assertEqual(command[command.index('--dir')+1], str(out/'review-frames'))
        with Image.open(out/'frames/frame_0000.png') as image:
            self.assertEqual(image.convert('RGBA').getpixel((0, 0))[3], 0)
        with Image.open(out/'review-frames/frame_0000.png') as image:
            self.assertEqual(image.convert('RGB').getpixel((0, 0)), (247, 246, 240))


if __name__ == '__main__':
    unittest.main()
