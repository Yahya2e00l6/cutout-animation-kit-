"""Opt-in horizontal toe anchoring without changing saved side-run poses.

The actor's root is shifted, not its legs. This trades linear body travel for
fixed toe X during stance; it is not IK, a physical simulation, or visual approval.
"""
import hashlib
import json
import math

from tools.motion import hermite
from tools.preview import ROOT
from tools.side_review import pose_character, world_point


SOURCES = ('characters/hoodie-side/character.svg', 'characters/hoodie-side/rig.json',
           'poses/side-run.json', 'motions/side-run.json')


class TravelRun:
    def __init__(self, action):
        self.action = action
        self.cycle = action.config['cycle']
        self.stance_end = action.phases[2]
        if action.phases[4] != 0.5 or not 0 < self.stance_end < 0.5:
            raise ValueError('Travel adapter requires the saved symmetric side-run phases')
        self.cache = {}

    def toe_x(self, phase, side):
        """Read a drawn shoe's fixed toe landmark through the actual pose hierarchy."""
        phase = round(phase % 1, 12)
        key = (phase, side)
        if key not in self.cache:
            pose = pose_character(self.action.tree, self.action.rig,
                                  self.action.sample(phase * self.cycle))
            x = world_point(pose, f'ankle-{side}', self.action.rig['review']['toe'])[0]
            x = self.action.config['width'] / 2 + (x - 300) * self.action.config['scale']
            if self.action.facing == 'left':
                x = self.action.config['width'] - x
            self.cache[key] = x
        return self.cache[key]

    def derivative(self, phase, side):
        h = 1e-5
        return (self.toe_x(phase + h, side) - self.toe_x(phase - h, side)) / (2 * h * self.cycle)

    def correction(self, seconds, velocity, scale, position_x):
        if not all(math.isfinite(n) for n in (seconds, velocity, scale, position_x)) or seconds < 0 or scale <= 0:
            raise ValueError('Invalid travel correction inputs')
        half = math.floor(seconds / self.cycle * 2 + 1e-12)
        start_phase = (half % 2) * 0.5
        side = 'right' if half % 2 == 0 else 'left'
        next_side = 'left' if side == 'right' else 'right'
        elapsed = max(0.0, seconds - half * self.cycle / 2)
        stance_duration = self.stance_end * self.cycle
        phase = start_phase + elapsed / self.cycle
        start_x = self.toe_x(start_phase, side)
        if elapsed <= stance_duration:
            toe = self.toe_x(phase, side)
            offset = -velocity * elapsed + scale * (start_x - toe)
            anchor = position_x - velocity * elapsed + scale * (start_x - self.action.config['width'] / 2)
            return offset, {'mode': 'stance', 'side': side, 'anchorX': anchor,
                            'toeX': position_x + scale * (toe - self.action.config['width'] / 2) + offset,
                            'rootOffsetX': offset}
        end_phase = start_phase + self.stance_end
        end_offset = -velocity * stance_duration + scale * (start_x - self.toe_x(end_phase, side))
        end_velocity = -velocity - scale * self.derivative(end_phase, side)
        next_velocity = -velocity - scale * self.derivative(start_phase + 0.5, next_side)
        flight_duration = (0.5 - self.stance_end) * self.cycle
        u = (elapsed - stance_duration) / flight_duration
        offset = hermite(end_offset, 0, end_velocity, next_velocity, flight_duration, u)
        return offset, {'mode': 'flight', 'side': None, 'rootOffsetX': offset}


def calibration():
    from tools.side_actions import load_side_action
    action = load_side_action('side-run-right')
    travel = TravelRun(action)
    stride = (travel.toe_x(0, 'right') - travel.toe_x(travel.stance_end, 'right')) / travel.stance_end
    return {'version': 1, 'status': 'Experimental pose-preserving travel; not natural-motion approval.',
            'marker': 'toe', 'stanceEndPhase': travel.stance_end,
            'baseCycle': action.config['cycle'], 'pixelsPerCycle': stride,
            'sources': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}}


if __name__ == '__main__':
    print(json.dumps(calibration(), indent=2))
