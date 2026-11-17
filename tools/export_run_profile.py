"""Export the approved steady-state support-leg run, without copying artwork.

This preparation step uses the original rig. Playback of the exported profile
does not import a hoodie or DICE renderer. It is a sampled approximation, not
the live support-leg/travel solver and not a replacement for approved scenes.
"""
import argparse
import hashlib
import json
from pathlib import Path

from tools.preview import ROOT
from tools.side_actions import load_side_action
from tools.support_run import SupportRun
from tools.run_profile import CHANNELS


def export(count=96):
    action = load_side_action('side-run-right')
    calibration = json.loads((ROOT/'motions/side-run-travel.json').read_text())
    velocity = calibration['pixelsPerCycle']/action.config['cycle']
    run = SupportRun(action, velocity, 1)  # Steady state, without entry/exit ramps.
    length = sum(run.lengths['right'])
    rows = []
    for i in range(count):
        t = i/count*action.config['cycle']
        angles = run.sample(t)['angles']
        _, record = run.pose(t)
        rows.append({'angles': {name: angles[name] for name in CHANNELS},
                     'clearance': max(0, min(record['shoe_clearance'].values()))/length})
    sources = ['tools/support_run.py', 'tools/side_run.py', 'tools/side_review.py',
               'tools/travel_run.py', 'poses/side-run.json', 'motions/side-run.json',
               'motions/side-run-travel.json', 'characters/hoodie-side/character.svg',
               'characters/hoodie-side/rig.json']
    return {'version': 1, 'type': 'normalized-side-run', 'cycle': action.config['cycle'],
            'source': {'action': 'steady-state SupportRun, approved leg-exchange revision',
                       'checkpoint': 'e0a6a1f', 'samples': count,
                       'sha256': {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources}},
            'units': 'angles in SVG degrees from downward bone directions; clearance in total leg lengths',
            'limitations': ['Sampled motion profile, not the live travel/contact solver.',
                            'New characters require visual review. No horizontal foot lock or standing transitions.'],
            'samples': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('Choose a fresh output file')
    data = export()
    with args.out.open('x') as stream:
        stream.write(json.dumps(data, indent=2, allow_nan=False)+'\n')


if __name__ == '__main__':
    main()
