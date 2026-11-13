"""Checks for the opt-in run candidate; visual approval remains separate."""
import json
import unittest

from tools.animate import frame_svg
from tools.motion import Humanoid, sample
from tools.preview import ROOT, load_character


class ReferenceRunTests(unittest.TestCase):
    def setUp(self):
        self.tree, self.rig = load_character(ROOT/'characters/hoodie')
        soles = {s: self.rig['attachments'][f'sole-{s}']['point'] for s in ['left', 'right']}
        self.model = Humanoid(self.tree, self.rig, soles)
        self.timeline = json.loads((ROOT/'motions/reference-run-candidate.json').read_text())

    def test_cycle_closes_and_preserves_contacts(self):
        cycle = self.timeline['run']['cycle']
        flight = 0
        for frame in range(20):
            t = frame/30
            a = sample(t, self.model, self.timeline)
            b = sample(t+cycle, self.model, self.timeline)
            self.assertAlmostEqual(a['height'], b['height'], places=9)
            for side in self.model.legs:
                self.assertAlmostEqual(a['feet'][side]['lift'], b['feet'][side]['lift'], places=9)
                for joint in ['shoulder', 'elbow', 'wrist']:
                    key = f'{joint}-{side}'
                    self.assertAlmostEqual(a['pose']['angles'][key], b['pose']['angles'][key], places=9)
            flight += all(not f['contact'] for f in a['feet'].values())
            _, record = frame_svg(self.tree, self.rig, self.model, self.timeline, t, frame)
            for foot in record['contacts'].values():
                self.assertLess(foot['error_px'], 1e-7)
        self.assertGreater(flight, 0)

    def test_half_cycle_exchanges_feet(self):
        cycle = self.timeline['run']['cycle']
        for frame in range(20):
            a = sample(frame/30, self.model, self.timeline)
            b = sample(frame/30+cycle/2, self.model, self.timeline)
            for key in ['lift', 'depth']:
                self.assertAlmostEqual(a['feet']['left'][key], b['feet']['right'][key], places=9)
