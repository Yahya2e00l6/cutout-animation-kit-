"""Reusable approved motion presets; no render cache is required."""
import json
import math

from tools.preview import ROOT


ACTION_NAMES = ('reference-run',)


def build_timeline(action, duration=None, speed=1.0):
    """Return a fresh timeline. Speed changes cadence, not the drawn poses.

    reference-run is the user-approved hoodie front-view, in-place loop.
    Durations must contain a whole number of frames at the preset's fps.
    Looping clips begin/end mid-stride; they do not ease into standing.
    """
    if action not in ACTION_NAMES:
        raise ValueError(f'Unknown reusable action: {action}')
    if not isinstance(speed, (int, float)) or not math.isfinite(speed) or speed <= 0:
        raise ValueError('Speed must be finite and positive')
    timeline = json.loads((ROOT/'motions'/f'{action}.json').read_text())
    if duration is not None:
        if not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
            raise ValueError('Duration must be finite and positive')
        timeline['segments'][0]['duration'] = duration
    duration = timeline['segments'][0]['duration']
    frames = duration*timeline['fps']
    if not math.isfinite(frames):
        raise ValueError('Duration produces a nonfinite frame count')
    if round(frames) < 1 or abs(round(frames)-frames) > 1e-8:
        raise ValueError('Duration must be a whole number of frames')
    cycle = timeline['run']['cycle']/speed
    if not math.isfinite(cycle) or cycle <= 0:
        raise ValueError('Speed produces an invalid cycle duration')
    timeline['run']['cycle'] = cycle
    return timeline
