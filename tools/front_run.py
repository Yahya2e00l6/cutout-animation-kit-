"""Rollback scene bridge for the unchanged, rejected reference-run front loop."""
import math
import xml.etree.ElementTree as ET

from tools.actions import build_timeline
from tools.animate import calibrate_soles, frame_svg
from tools.motion import Humanoid
from tools.preview import ROOT, SVG, load_character


class FrontRun:
    def __init__(self, action='reference-run', duration=None, speed=1):
        self.timeline = build_timeline(action, duration, speed)
        self.config = {name: self.timeline[name] for name in ('width', 'height', 'floor', 'fps', 'scale')}
        self.config.update(cycle=self.timeline['run']['cycle'], duration=self.timeline['segments'][0]['duration'])
        self.tree, self.rig = load_character(ROOT/'characters/hoodie')
        self.model = Humanoid(self.tree, self.rig, calibrate_soles(self.tree))

    def frame(self, seconds, number, *, clean=False):
        if not math.isfinite(seconds) or not 0 <= seconds < self.config['duration']:
            raise ValueError('Front-run time is outside its half-open interval')
        svg, contacts = frame_svg(self.tree, self.rig, self.model, self.timeline, seconds, number)
        if clean:
            canvas = ET.fromstring(svg)
            for node in list(canvas):
                if node.tag != f'{{{SVG}}}defs' and node.get('id') != 'root':
                    canvas.remove(node)
            svg = ET.tostring(canvas, encoding='utf-8')
        return svg, contacts
