"""Load saved left/right side runs without depending on preview render files."""
import json
import math

from tools.preview import ROOT


SIDE_ACTIONS = ('side-run-right', 'side-run-left')


def load_side_action(action, duration=None, speed=1.0, character=None):
    """Return a reusable SideRun instance; speed changes cadence, not poses.

    frame(t, n, clean=True) returns a standalone transparent SVG plus contact
    metadata. Rasterize it to transparent PNG for composition into a scene.
    Keep the returned instance between frames to reuse its shoe calibration.
    """
    from tools.side_run import SideRun

    if action not in SIDE_ACTIONS:
        raise ValueError(f'Unknown side action: {action}')
    if not isinstance(speed, (int, float)) or not math.isfinite(speed) or speed <= 0:
        raise ValueError('Speed must be finite and positive')
    config = json.loads((ROOT/'motions/side-run.json').read_text())
    config['facing'] = 'left' if action == 'side-run-left' else 'right'
    if duration is not None:
        if not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
            raise ValueError('Duration must be finite and positive')
        config['duration'] = duration
    config['cycle'] /= speed
    return SideRun(character or ROOT/'characters/hoodie-side', ROOT/'poses/side-run.json', config)
