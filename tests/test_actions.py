import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.actions import build_timeline
from tools.animate import calibrate_soles, frame_svg, raster
from tools.motion import Humanoid, sample
from tools.preview import ROOT, load_character


class ActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads((ROOT/'tests/fixtures/reference-run-approved.json').read_text())
        tree, rig = load_character(ROOT/'characters/hoodie')
        cls.model = Humanoid(tree, rig, cls.fixture['measured_soles'])

    def test_default_preserves_all_120_approved_motion_states(self):
        timeline = build_timeline('reference-run')
        states = [sample(i/30, self.model, timeline) for i in range(120)]
        digest = hashlib.sha256(json.dumps(states, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(digest, self.fixture['states_sha256'])

    def test_default_reproduces_all_120_approved_raster_frames(self):
        from PIL import Image
        tree, rig = load_character(ROOT/'characters/hoodie')
        model = Humanoid(tree, rig, calibrate_soles(tree))
        timeline = build_timeline('reference-run')
        self.assertEqual((timeline['width'], timeline['height']), (1280, 720))
        digest = hashlib.sha256()
        for frame in range(120):
            svg, _ = frame_svg(tree, rig, model, timeline, frame/30, frame)
            buffer = io.BytesIO()
            raster(svg, timeline['width'], timeline['height']).write_to_png(buffer)
            with Image.open(buffer) as image:
                digest.update(image.convert('RGB').tobytes())
        self.assertEqual(digest.hexdigest(), self.fixture['rgb_frames_sha256'])

    def test_cli_refuses_existing_reports_without_writing_frames(self):
        for keyframes in [False, True]:
            with self.subTest(keyframes=keyframes), tempfile.TemporaryDirectory() as directory:
                out = Path(directory)
                report = out/('keyframe-validation.json' if keyframes else 'motion-validation.json')
                original = b'existing report\n'
                report.write_bytes(original)
                command = [sys.executable, '-B', str(ROOT/'tools/animate.py'),
                           '--action', 'reference-run', '--duration', '0.1', '--out', str(out)]
                if keyframes:
                    command.append('--keyframes')
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('Output report already exists', result.stderr)
                self.assertEqual(report.read_bytes(), original)
                self.assertEqual(list(out.iterdir()), [report])

    def test_cli_reports_overflowing_duration_clearly(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)/'output'
            result = subprocess.run([
                sys.executable, '-B', str(ROOT/'tools/animate.py'), '--action', 'reference-run',
                '--duration', '1e308', '--out', str(out),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn('Duration produces a nonfinite frame count', result.stderr)
            self.assertNotIn('Traceback', result.stderr)
            self.assertFalse(out.exists())

    def test_duration_reuses_the_same_motion_without_mutating_preset(self):
        original = build_timeline('reference-run')
        longer = build_timeline('reference-run', duration=10)
        for i in range(120):
            self.assertEqual(sample(i/30, self.model, original), sample(i/30, self.model, longer))
        longer['run']['lift'] = 0
        self.assertEqual(build_timeline('reference-run'), original)

    def test_speed_changes_only_cadence_and_loop_repeats(self):
        normal = build_timeline('reference-run')
        fast = build_timeline('reference-run', speed=2)
        for i in range(20):
            t = i/30
            self.assertEqual(sample(t/2, self.model, fast), sample(t, self.model, normal))
            a = sample(t, self.model, normal)
            b = sample(t+normal['run']['cycle'], self.model, normal)
            self.assertAlmostEqual(a['height'], b['height'], places=9)
            self.assertAlmostEqual(a['sway'], b['sway'], places=9)
            for side in ['left', 'right']:
                self.assertAlmostEqual(a['feet'][side]['lift'], b['feet'][side]['lift'], places=9)
                self.assertAlmostEqual(a['pose']['angles'][f'elbow-{side}'], b['pose']['angles'][f'elbow-{side}'], places=9)

    def test_invalid_options_are_rejected(self):
        for duration in [0, -1, float('nan'), float('inf'), 0.01, 1e308]:
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                build_timeline('reference-run', duration=duration)
        for speed in [0, -1, float('nan'), float('inf')]:
            with self.subTest(speed=speed), self.assertRaises(ValueError):
                build_timeline('reference-run', speed=speed)
        with self.assertRaises(ValueError):
            build_timeline('unknown')
