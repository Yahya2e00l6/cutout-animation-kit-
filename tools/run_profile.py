"""Artwork-independent playback of a normalized, sampled side-run profile."""
import json
import math
from pathlib import Path


CHANNELS = ('torso', 'head') + tuple(f'{joint}-{side}' for side in ('right', 'left')
                                   for joint in ('hip', 'knee', 'ankle', 'shoulder', 'elbow'))


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


class RunProfile:
    def __init__(self, path):
        self.data = json.loads(Path(path).read_text())
        if not isinstance(self.data, dict):
            raise ValueError('Motion profile must be an object')
        self.cycle = self.data.get('cycle')
        self.rows = self.data.get('samples')
        if (type(self.data.get('version')) is not int or self.data.get('version') != 1
                or self.data.get('type') != 'normalized-side-run'
                or not finite(self.cycle) or self.cycle <= 0
                or not isinstance(self.rows, list) or not 8 <= len(self.rows) <= 4096):
            raise ValueError('Invalid shared side-run profile')
        for row in self.rows:
            if (not isinstance(row, dict) or not isinstance(row.get('angles'), dict)
                    or set(row['angles']) != set(CHANNELS)
                    or not all(finite(v) and abs(v) <= 720 for v in row['angles'].values())
                    or not finite(row.get('clearance')) or not 0 <= row['clearance'] <= 2):
                raise ValueError('Invalid motion-profile sample')

    def sample(self, seconds, speed=1):
        if not finite(seconds) or seconds < 0 or not finite(speed) or speed <= 0:
            raise ValueError('Time must be nonnegative and cadence must be positive')
        turns = seconds*speed/self.cycle
        if not math.isfinite(turns):
            raise ValueError('Cadence/time calculation overflowed')
        phase = turns % 1
        n = len(self.rows)
        u = phase*n
        i, t = int(u) % n, u-int(u)
        def curve(values):
            a, b, c, d = (values[k % n] for k in (i-1, i, i+1, i+2))
            def tangent(x, y):
                return 2*x*y/(x+y) if x*y > 0 else 0
            m0, m1 = tangent(b-a, c-b), tangent(c-b, d-c)
            return (2*t**3-3*t*t+1)*b+(t**3-2*t*t+t)*m0+(-2*t**3+3*t*t)*c+(t**3-t*t)*m1
        return {'phase': phase,
                'angles': {name: curve([r['angles'][name] for r in self.rows]) for name in CHANNELS},
                'clearance': max(0, curve([r['clearance'] for r in self.rows]))}
