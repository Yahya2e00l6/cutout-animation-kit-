"""Experimental standing blends around an unchanged saved SideRun.

The TypeScript sampler owns scheduling and blend weights. One authored toe is
anchored horizontally; the lowest rendered shoe is grounded vertically. This
is a pose blend, not an acceleration/IK solver or a new approved saved action.
"""
from functools import lru_cache
import json
import math

from tools.preview import ROOT
from tools.side_run import SideRun
from tools.side_review import world_point


@lru_cache(maxsize=1)
def standing_angles():
    pose = json.loads((ROOT/'poses/side-stand.json').read_text())
    if pose.get('version') != 1 or not isinstance(pose.get('angles'), dict):
        raise ValueError('Invalid standing pose')
    if not all(type(value) in (int, float) and math.isfinite(value) for value in pose['angles'].values()):
        raise ValueError('Standing angles must be finite numbers')
    return pose['angles']


class TransitionPose(SideRun):
    def __init__(self, action, weight):
        if not 0 <= weight <= 1:
            raise ValueError('Transition weight must be in [0, 1]')
        # Sources/config are read-only; keep the existing shoe measurement cache.
        self.__dict__ = action.__dict__.copy()
        self.weight = weight
        self.standing = standing_angles()
        if set(self.standing) != set(self.channels):
            raise ValueError('Standing pose joints must match the saved side run')

    def sample(self, seconds):
        key = super().sample(seconds)
        # Blend an explicit standing pose, not the rig's stacked zero-angle pose.
        key['angles'] = {name: self.standing[name] + (value - self.standing[name]) * self.weight
                         if self.weight < 1 else value for name, value in key['angles'].items()}
        key['root_y'] = key['root_y'] * self.weight if self.weight else 0.0
        return key

    def pose(self, seconds):
        posed, record = super().pose(seconds)
        # Grounding here may move DOWN too, unlike the unchanged running solve.
        clearance = min(record['shoe_clearance'].values())
        root = next(node for node in posed.iter() if node.get('id') == 'root')
        _, y = world_point(posed, 'root', (0, 0))
        root.set('transform', f'translate(300 {y + clearance})')
        record['transition_ground_shift'] = clearance
        record['shoe_clearance'] = {side: value - clearance for side, value in record['shoe_clearance'].items()}
        return posed, record

    def toe_x(self, seconds, side):
        posed, _ = self.pose(seconds)
        x = world_point(posed, f'ankle-{side}', self.rig['review']['toe'])[0]
        x = self.config['width'] / 2 + (x - 300) * self.config['scale']
        return self.config['width'] - x if self.facing == 'left' else x
