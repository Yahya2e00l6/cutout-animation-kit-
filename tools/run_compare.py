"""Compare folded running arms against the latest cached arm comparison."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
import time

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.animate import calibrate_soles, frame_svg
from tools.arm_compare import comparison_frame
from tools.motion import Humanoid, sample
from tools.preview import ROOT, load_character


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, default=ROOT/'renders/arm-test/v02/comparison')
    parser.add_argument('--baseline', type=Path, default=ROOT/'renders/run-arms/v01/before-states.json')
    parser.add_argument('--out', type=Path, default=ROOT/'renders/run-arms/v01/comparison')
    parser.add_argument('--keyframes', action='store_true')
    args = parser.parse_args()
    started = time.monotonic()
    baseline = json.loads(args.baseline.read_text())
    before_report = json.loads((args.before/'comparison-report.json').read_text())
    if before_report['implementation_sha256']['motion.py'] != baseline['motion_sha256']:
        raise ValueError('Cached comparison does not match the pre-change running arms')
    tree, rig = load_character(ROOT/'characters/hoodie')
    timeline = json.loads((ROOT/'motions/walk-jump-run.json').read_text())
    authored = {s: rig['attachments'][f'sole-{s}']['point'] for s in ['left', 'right']}
    model = Humanoid(tree, rig, authored)
    states = [json.loads(json.dumps(sample(i/30, model, timeline))) for i in range(288)]
    keys = ['height', 'sway', 'feet', 'lengths', 'leg_angles']
    for index, (before, after) in enumerate(zip(baseline['states'], states)):
        if any(before[key] != after[key] for key in keys):
            raise ValueError(f'Leg/root regression at frame {index}')
        if before['action'] != 'run' and before != after:
            raise ValueError(f'Walk/idle/jump regression at frame {index}')
    soles = calibrate_soles(tree)
    model = Humanoid(tree, rig, soles)
    selected = [i for i, state in enumerate(states) if state['action'] == 'run']
    if args.keyframes:
        selected = [195, 203, 211, 220, 233, 248]
    before_indices = {frame: index for index, frame in enumerate(before_report['source_frames'])}
    directory = args.out/('keyframes' if args.keyframes else 'frames')
    directory.mkdir(parents=True, exist_ok=True)
    if any(directory.iterdir()):
        raise FileExistsError(f'Choose a new output directory: {directory}')
    jobs, records = [], []
    for index, frame in enumerate(selected):
        before = args.before/'frames'/f'frame_{before_indices[frame]:04d}.png'
        if not before.is_file():
            raise FileNotFoundError(before)
        data, record = frame_svg(tree, rig, model, timeline, frame/30, frame)
        options = {'before_crop': (640, 0, 1280, 720),
                   'titles': ['BEFORE / PREVIOUS RUN', 'AFTER / BENT RUNNING ARMS']}
        jobs.append((data, frame, 'run', str(before), str(directory/f'frame_{index:04d}.png'), options))
        record['elbow_degrees'] = {side: abs(states[frame]['pose']['angles'][f'elbow-{side}']) for side in ['left', 'right']}
        records.append(record)
    with ProcessPoolExecutor(max_workers=2) as pool:
        for index, _ in enumerate(pool.map(comparison_frame, jobs, chunksize=2)):
            if (index+1)%30 == 0 or index+1 == len(jobs):
                print(f'Rendered {index+1}/{len(jobs)} running comparisons', flush=True)
    settled = [abs(states[i]['pose']['angles'][f'elbow-{side}']) for i in range(188, 255) for side in ['left', 'right']]
    report = {'frames': len(selected), 'fps': 30, 'duration': len(selected)/30, 'resolution': [1280,720],
              'source_frames': selected, 'baseline': str(args.before),
              'unchanged_leg_root_frames': 288, 'walk_idle_jump_unchanged': True,
              'settled_elbow_flexion_degrees': [min(settled),max(settled)],
              'contact_error_px': max(f['error_px'] for record in records for f in record['contacts'].values()),
              'render_seconds': time.monotonic()-started,
              'implementation_sha256': {name: hashlib.sha256((ROOT/'tools'/name).read_bytes()).hexdigest() for name in ['motion.py','preview.py','run_compare.py']},
              'records': records}
    (args.out/('keyframe-report.json' if args.keyframes else 'comparison-report.json')).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['records','source_frames']},indent=2))


if __name__ == '__main__':
    main()
