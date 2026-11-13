"""Render walk/run arm changes beside cached frames, without re-rendering the baseline."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import sys
import time

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.animate import calibrate_soles, frame_svg, raster
from tools.motion import Humanoid, sample
from tools.preview import ROOT, load_character


def comparison_frame(job):
    from PIL import Image, ImageDraw, ImageFont
    data, source_frame, action, before, target, *extra = job
    options = extra[0] if extra else {}
    stream = io.BytesIO()
    raster(data, 1280, 720).write_to_png(stream)
    after = Image.open(stream).convert('RGB')
    with Image.open(before) as image:
        before = image.convert('RGB')
    sheet = Image.new('RGB', (1280, 720), '#f5f3ec')
    sheet.paste(before.crop(options.get('before_crop', (320, 0, 960, 720))), (0, 0))
    sheet.paste(after.crop((320, 0, 960, 720)), (640, 0))
    draw = ImageDraw.Draw(sheet)
    try:
        font_path = next(path for path in [Path('/usr/share/fonts/noto/NotoSans-Regular.ttf'), Path('/usr/share/fonts/TTF/DejaVuSans.ttf')] if path.is_file())
        font = ImageFont.truetype(str(font_path), 22)
        small = ImageFont.truetype(str(font_path), 16)
    except (OSError, StopIteration):
        font = small = ImageFont.load_default()
    draw.rectangle((0, 0, 1280, 110), fill='#f5f3ec')
    titles = options.get('titles', ['BEFORE / FRONT-ONLY ARMS', 'AFTER / FORWARD–BACK SWING'])
    for x, title in zip([25, 665], titles):
        draw.text((x, 25), title, font=font, fill='#29392f')
        draw.text((x, 65), action.upper()+'  ·  same legs and body timing', font=small, fill='#657165')
    draw.line((640, 0, 640, 720), fill='#b8c1ae', width=2)
    draw.rectangle((0, 680, 1280, 720), fill='#e1e5d9')
    draw.text((25, 689), f'Source frame {source_frame:03d} / 30 fps · silent comparison', font=small, fill='#465647')
    sheet.save(target)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, default=ROOT/'renders/motion-test/v05')
    parser.add_argument('--baseline', type=Path, default=ROOT/'renders/arm-test/v01/before-states.json')
    parser.add_argument('--out', type=Path, default=ROOT/'renders/arm-test/v02/comparison')
    parser.add_argument('--keyframes', action='store_true')
    parser.add_argument('--jobs', type=int, default=2, choices=range(1, 5))
    args = parser.parse_args()
    started = time.monotonic()
    baseline = json.loads(args.baseline.read_text())
    before_report = json.loads((args.before/'motion-validation.json').read_text())
    if before_report.get('implementation_sha256', {}).get('motion.py') != baseline['motion_sha256']:
        raise ValueError('Cached baseline does not match the starting motion code')
    tree, rig = load_character(ROOT/'characters/hoodie')
    timeline = json.loads((ROOT/'motions/walk-jump-run.json').read_text())
    authored = {s: rig['attachments'][f'sole-{s}']['point'] for s in ['left', 'right']}
    authored_model = Humanoid(tree, rig, authored)
    unchanged = ['height', 'sway', 'feet', 'lengths', 'leg_angles']
    states = [json.loads(json.dumps(sample(i/30, authored_model, timeline))) for i in range(288)]
    for index, (before, after) in enumerate(zip(baseline['states'], states)):
        if any(before[key] != after[key] for key in unchanged):
            raise ValueError(f'Leg/root regression at frame {index}')
        if before['action'] in ['idle', 'jump'] and before != after:
            raise ValueError(f'Idle/jump regression at frame {index}')
    soles = calibrate_soles(tree)
    model = Humanoid(tree, rig, soles)
    selected = [i for i, state in enumerate(states) if state['action'] in ['walk', 'run']]
    if args.keyframes:
        selected = [25, 40, 54, 70, 195, 203, 211, 220]
    directory = args.out/('keyframes' if args.keyframes else 'frames')
    directory.mkdir(parents=True, exist_ok=True)
    if any(directory.iterdir()):
        raise FileExistsError(f'Choose a new output folder: {directory}')
    jobs, records = [], []
    for index, source_frame in enumerate(selected):
        before = args.before/'frames'/f'frame_{source_frame:04d}.png'
        if not before.is_file():
            raise FileNotFoundError(before)
        data, record = frame_svg(tree, rig, model, timeline, source_frame/30, source_frame)
        target = directory/f'frame_{index:04d}.png'
        jobs.append((data, source_frame, states[source_frame]['action'], str(before), str(target)))
        record['arm_depth'] = states[source_frame]['pose']['arm_depth']
        record['forearm_blend'] = states[source_frame]['pose']['layers']['forearm_blend']
        records.append(record)
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        for index, _ in enumerate(pool.map(comparison_frame, jobs, chunksize=2)):
            if (index+1)%30 == 0 or index+1 == len(jobs):
                print(f'Rendered {index+1}/{len(jobs)} comparison frames', flush=True)
    report = {
        'fps': 30, 'frames': len(selected), 'duration': len(selected)/30, 'resolution': [1280, 720],
        'baseline': str(args.before), 'baseline_motion_sha256': baseline['motion_sha256'],
        'unchanged_leg_root_frames': 288, 'idle_and_jump_unchanged': True,
        'source_frames': selected, 'render_seconds': time.monotonic()-started,
        'implementation_sha256': {name: hashlib.sha256((ROOT/'tools'/name).read_bytes()).hexdigest() for name in ['motion.py', 'preview.py', 'arm_compare.py']},
        'contact_error_px': max(f['error_px'] for record in records for f in record['contacts'].values()),
        'records': records,
    }
    (args.out/('keyframe-report.json' if args.keyframes else 'comparison-report.json')).write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ['records', 'source_frames']}, indent=2))


if __name__ == '__main__':
    main()
