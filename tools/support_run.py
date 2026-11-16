"""Opt-in leg IK: transfer the old root-X correction into both leg chains.

Feet retain the pose-preserving adapter's world paths and shoe rotations while
the middle run travels on the baseline. Short boundary ramps retain the old
transition tangents. A small, smooth hip drop keeps both ankles
within reach. This changes leg poses, not source artwork or saved run settings.
"""
import copy
import math

from tools.side_review import pose_character, world_point
from tools.side_run import SideRun
from tools.travel_run import TravelRun


def smooth_positive(value, width=0.1):
    """C1 upper bound on max(0, value), exactly zero below -width."""
    if value <= -width:
        return 0.0
    if value >= width:
        return value
    return (value + width)**2 / (4*width)


class SupportRun(SideRun):
    def __init__(self, action, velocity, scale, duration=None):
        if not all(math.isfinite(n) for n in (velocity, scale)) or not velocity or scale <= 0:
            raise ValueError('Support-leg travel requires finite nonzero velocity and positive scale')
        self.__dict__ = action.__dict__.copy()
        self.base = action
        self.travel_adapter = TravelRun(action)
        self.velocity = velocity
        self.actor_scale = scale
        if duration is not None and (not math.isfinite(duration) or duration <= 0):
            raise ValueError('Support-leg duration must be finite and positive')
        self.run_duration = duration
        self.solved = {}
        self.lengths = {}
        for side in ['right', 'left']:
            hip = world_point(self.tree, f'hip-{side}', (0, 0))
            knee = world_point(self.tree, f'knee-{side}', (0, 0))
            ankle = world_point(self.tree, f'ankle-{side}', (0, 0))
            if abs(hip[0]-knee[0]) > 1e-8 or abs(knee[0]-ankle[0]) > 1e-8 or not hip[1] < knee[1] < ankle[1]:
                raise ValueError('Support-leg travel requires the saved downward two-link chains')
            self.lengths[side] = (knee[1]-hip[1], ankle[1]-knee[1])

    def solve(self, seconds):
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError('Time must be finite and nonnegative')
        phase = round((seconds/self.config['cycle']) % 1, 12) % 1
        weight = 1.0
        if self.run_duration is not None:
            if seconds > self.run_duration + 1e-9:
                raise ValueError('Support-leg sample is beyond its running interval')
            window = min(self.config['cycle'] * 0.15, self.run_duration/2)
            def ease(value):
                u = max(0, min(1, value/window))
                return u*u*(3-2*u)
            weight = round(ease(seconds)*ease(self.run_duration-seconds), 12)
        cache_key = (phase, weight)
        if cache_key not in self.solved:
            time = phase * self.config['cycle']
            key = self.base.sample(time)
            original = copy.deepcopy(key)
            posed = pose_character(self.tree, self.rig, key)
            old_offset, _ = self.travel_adapter.correction(time, self.velocity, self.actor_scale, 0)
            sign = -1 if self.facing == 'left' else 1
            shift = sign * old_offset * weight / (self.actor_scale*self.config['scale'])
            targets = {}
            drop = 0.0
            for side, (upper, lower) in self.lengths.items():
                hx, hy = world_point(posed, f'hip-{side}', (0, 0))
                ax, ay = world_point(posed, f'ankle-{side}', (0, 0))
                dx, dy = ax-hx+shift, ay-hy
                reach = upper + lower - 0.5  # Avoid the fully straight IK singularity.
                if abs(dx) >= reach:
                    raise ValueError('Support-leg target exceeds horizontal reach')
                drop += smooth_positive(dy - math.sqrt(reach*reach-dx*dx))
                targets[side] = (dx, dy)
            key['root_y'] += drop
            maximum = 0.0
            for side, (dx, dy) in targets.items():
                upper, lower = self.lengths[side]
                dy -= drop
                radius = math.hypot(dx, dy)
                if not abs(upper-lower) < radius <= upper+lower:
                    raise ValueError('Support-leg target is unreachable; refusing a stretched/sliding leg')
                knee = math.acos(max(-1, min(1, (radius*radius-upper*upper-lower*lower)/(2*upper*lower))))
                hip = math.atan2(-dx, dy) - math.atan2(lower*math.sin(knee), upper+lower*math.cos(knee))
                shoe = sum(original['angles'][f'{joint}-{side}'] for joint in ['hip', 'knee', 'ankle'])
                values = {'hip': math.degrees(hip), 'knee': math.degrees(knee),
                          'ankle': shoe-math.degrees(hip)-math.degrees(knee)}
                for joint, angle in values.items():
                    name = f'{joint}-{side}'
                    maximum = max(maximum, abs(angle-original['angles'][name]))
                    key['angles'][name] = angle
            self.solved[cache_key] = (key, {'mode': 'support-leg', 'previousRootOffsetX': old_offset,
                                      'transferWeight': weight, 'transferredRootOffsetX': old_offset*weight,
                                      'remainingRootOffsetX': old_offset*(1-weight) if weight < 1 else 0.0,
                                      'hipDrop': drop*self.config['scale']*self.actor_scale,
                                      'maxJointChangeDegrees': maximum})
        return copy.deepcopy(self.solved[cache_key])

    def sample(self, seconds):
        return self.solve(seconds)[0]

    def pose(self, seconds):
        posed, record = super().pose(seconds)
        record['supportIK'] = self.solve(seconds)[1]
        return posed, record
