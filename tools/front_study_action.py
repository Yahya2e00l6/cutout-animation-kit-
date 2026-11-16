"""Scene adapter for Astra's v04 front run, with its drawing and poses intact."""
import json
import math
import xml.etree.ElementTree as ET

from tools.front_run_study import FrontStudy, MotionReadability
from tools.preview import ROOT, SVG


class FrontStudyAction:
    def __init__(self, action='front-run', duration=None, speed=1):
        if action != 'front-run':
            raise ValueError('Unsupported front-study action')
        duration = 2.3 if duration is None else duration
        if (not math.isfinite(duration) or duration <= 0 or not math.isfinite(speed)
                or speed <= 0 or not math.isfinite(duration*speed)):
            raise ValueError('Front run requires finite positive duration and cadence')
        preset = json.loads((ROOT/'motions/front-run.json').read_text())
        if (preset['version'] != 1 or
                [preset[n] for n in ('width', 'height', 'floor', 'fps', 'scale')] != [1280, 720, 650, 30, .64]):
            raise ValueError('Front-run preset does not match the source camera')
        self.study = FrontStudy(readability=MotionReadability(**preset['readability']))
        self.speed = speed
        self.config = {name: preset[name] for name in ('width', 'height', 'floor', 'fps', 'scale')}
        self.config.update(cycle=self.study.cycle/speed, duration=duration)

    def frame(self, seconds, number, *, clean=False):
        if not math.isfinite(seconds) or not 0 <= seconds < self.config['duration']:
            raise ValueError('Front-run time is outside its half-open interval')
        svg, pose = self.study.frame(seconds*self.speed)
        if clean:
            canvas = ET.fromstring(svg)
            # Keep definitions and the exact character, without the study plate,
            # floor guide or shadow. The scene owns its background and placement.
            for node in list(canvas):
                if node.tag != f'{{{SVG}}}defs' and node.get('id') != 'front-study-character':
                    canvas.remove(node)
            svg = ET.tostring(canvas)
        return svg, {'frontRun': {'sourceCheckpoint': '6fc6134', 'phase': pose['phase'],
                                 'groundCorrection': pose['groundCorrection'],
                                 'grounding': 'shoe-proxy plane correction; not planted-foot verification'}}
