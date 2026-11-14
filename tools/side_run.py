"""Render reusable side runs or motion-review previews.

This is separate from the approved front-view action. Ground
correction prevents shoe penetration; it is not a horizontal stance-lock solve.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
import copy
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import time
import xml.etree.ElementTree as ET

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.animate import element, raster, render_frame
from tools.preview import ROOT, SVG, load_character
from tools.side_review import pose_character, world_point


def periodic_curve(phase, knots, values):
    """Periodic shape-preserving cubic: continuous velocity without overshoot."""
    phase %= 1
    index = next((i-1 for i, p in enumerate(knots) if p > phase), len(knots)-1)
    i, j = index, (index+1) % len(knots)

    def span(a, b):
        return (knots[b]-knots[a]) % 1

    def tangent(k):
        prev, following = (k-1) % len(knots), (k+1) % len(knots)
        h0, h1 = span(prev, k), span(k, following)
        d0, d1 = (values[k]-values[prev])/h0, (values[following]-values[k])/h1
        if d0*d1 <= 0:
            return 0.0
        w0, w1 = 2*h1+h0, h1+2*h0
        return (w0+w1)/(w0/d0+w1/d1)

    h = span(i, j)
    u = ((phase-knots[i]) % 1)/h
    return ((2*u**3-3*u*u+1)*values[i] + (u**3-2*u*u+u)*h*tangent(i)
            + (-2*u**3+3*u*u)*values[j] + (u**3-u*u)*h*tangent(j))


class SideRun:
    def __init__(self, character, poses, config):
        self.tree, self.rig = load_character(character)
        if self.rig['type'] != 'humanoid-cutout-side':
            raise ValueError('SideRun requires a side-view rig')
        self.facing = config.get('facing', self.rig['facing'])
        if self.facing not in ['left', 'right']:
            raise ValueError('Facing must be left or right')
        self.keys = json.loads(Path(poses).read_text())['poses']
        self.config = copy.deepcopy(config)
        self.phases = config['key_phases']
        if (len(self.keys) != len(self.phases) or len(self.phases) != 8
                or self.phases[0] != 0 or self.phases[-1] >= 1
                or any(b <= a for a, b in zip(self.phases, self.phases[1:]))):
            raise ValueError('Eight key phases must increase from 0 to less than 1, one per pose')
        for name in ['cycle', 'duration', 'scale', 'fps', 'width', 'height']:
            value = config[name]
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f'{name} must be finite and positive')
        count = config['duration']*config['fps']
        if not math.isfinite(count) or round(count) < 1 or abs(count-round(count)) > 1e-8:
            raise ValueError('Duration must be a whole number of frames')
        if any(config[name] != int(config[name]) for name in ['fps', 'width', 'height']):
            raise ValueError('fps, width, and height must be integers')
        self.root_heights = [world_point(pose_character(self.tree, self.rig, key), 'root', (0, 0))[1] for key in self.keys]
        joints = set(self.keys[0]['angles'])
        if any(set(key['angles']) != joints for key in self.keys):
            raise ValueError('All key poses must contain the same joints')
        self.channels = {name: [key['angles'][name] for key in self.keys] for name in sorted(joints)}
        self.shoe_cache = {}

    def sample(self, seconds):
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError('Time must be finite and nonnegative')
        phase = (seconds/self.config['cycle']) % 1
        angles = {name: periodic_curve(phase, self.phases, values) for name, values in self.channels.items()}
        if 'arm_cycle' in self.config:
            # Shoulder and elbow are a quarter-cycle apart, giving the fists
            # distinct high/low return arcs rather than retracing one line.
            # A full-period curve spreads the exchange across the stride.
            arm = self.config['arm_cycle']
            for side, offset in [('right', 0), ('left', 0.5)]:
                theta = math.tau*(phase+arm['phase']+offset)
                angles[f'shoulder-{side}'] = arm['shoulder_center']+arm['shoulder_amplitude']*math.cos(theta)
                angles[f'elbow-{side}'] = arm['elbow_center']+arm['elbow_amplitude']*math.sin(theta)
        return {
            'angles': angles,
            'root_y': periodic_curve(phase, self.phases, self.root_heights),
        }

    def shoe_bottom(self, side, angle):
        """Measure opaque shoe pixels at 4x; rotated ink bounds only size the crop.

        librsvg's rotated ink rectangles can include substantial empty space.
        They must not be used as sole contact coordinates.
        """
        cache_key = (side, round(angle, 9))
        if cache_key not in self.shoe_cache:
            from PIL import Image
            import gi
            gi.require_version('Rsvg', '2.0')
            from gi.repository import Rsvg
            nodes = {e.get('id'): e for e in self.tree.iter() if e.get('id')}
            fragment = ET.Element(f'{{{SVG}}}svg', {'width': '1', 'height': '1'})
            fragment.append(copy.deepcopy(self.tree.getroot().find(f'{{{SVG}}}defs')))
            shoe = copy.deepcopy(nodes[f'ankle-{side}'])
            shoe.set('transform', f'rotate({angle})')
            fragment.append(shoe)
            handle = Rsvg.Handle.new_from_data(ET.tostring(fragment))
            viewport = Rsvg.Rectangle()
            viewport.x, viewport.y, viewport.width, viewport.height = 0, 0, 1, 1
            success, ink, _ = handle.get_geometry_for_layer(f'#ankle-{side}', viewport)
            if not success or ink.height <= 0:
                raise ValueError('Cannot measure side-view shoe')
            x0, y0 = math.floor(ink.x)-3, math.floor(ink.y)-3
            width, height = math.ceil(ink.x+ink.width)-x0+3, math.ceil(ink.y+ink.height)-y0+3
            if max(width, height)*4 > 4096:
                raise ValueError('Side-view shoe calibration exceeds 4096 pixels')
            fragment.attrib.update({'viewBox': f'{x0} {y0} {width} {height}', 'width': str(width*4), 'height': str(height*4)})
            buffer = io.BytesIO()
            raster(ET.tostring(fragment), width*4, height*4).write_to_png(buffer)
            with Image.open(buffer) as image:
                bounds = image.convert('RGBA').getchannel('A').point(lambda value: 255 if value >= 128 else 0).getbbox()
            if bounds is None:
                raise ValueError('Empty side-view shoe')
            if bounds[0] <= 0 or bounds[1] <= 0 or bounds[2] >= width*4 or bounds[3] >= height*4:
                raise ValueError('Side-view shoe calibration clipped')
            self.shoe_cache[cache_key] = y0+bounds[3]/4
        return self.shoe_cache[cache_key]

    def pose(self, seconds):
        key = self.sample(seconds)
        posed = pose_character(self.tree, self.rig, key)
        nodes = {e.get('id'): e for e in posed.iter() if e.get('id')}
        bottoms = {}
        for side in ['left', 'right']:
            angle = sum(key['angles'][f'{joint}-{side}'] for joint in ['hip', 'knee', 'ankle'])
            _, ankle_y = world_point(posed, f'ankle-{side}', (0, 0))
            bottoms[side] = ankle_y+self.shoe_bottom(side, angle)
        correction = max(0.0, max(bottoms.values())-self.rig['review']['floor'])
        nodes['root'].set('transform', f"translate(300 {key['root_y']-correction})")
        return posed, {'ground_correction': correction, 'shoe_clearance': {side: self.rig['review']['floor']-y+correction for side, y in bottoms.items()}}

    def frame(self, seconds, number, *, clean=False):
        """Return SVG bytes and contacts; clean=True exports only the actor.

        The clean canvas is transparent and retains the same placement, timing
        and facing as the review. Export PNGs before compositing with other rigs
        to avoid collisions between their SVG IDs or global style selectors.
        """
        posed, record = self.pose(seconds)
        config = self.config
        canvas = ET.Element(f'{{{SVG}}}svg', {'width': str(config['width']), 'height': str(config['height']), 'viewBox': f"0 0 {config['width']} {config['height']}"})
        canvas.append(copy.deepcopy(posed.getroot().find(f'{{{SVG}}}defs')))
        if not clean:
            element(canvas, 'rect', width='100%', height='100%', fill='#f5f3ec')
            element(canvas, 'rect', x=0, y=config['floor'], width=config['width'], height=config['height']-config['floor'], fill='#e1e5d9')
            element(canvas, 'line', x1=40, y1=config['floor'], x2=config['width']-40, y2=config['floor'], stroke='#9aab92', stroke_width=2)
        # Reflect only the character, around the canvas centre. Ground, labels,
        # canonical joint names and the latest corrected motion stay unchanged.
        parent = canvas
        if self.facing != self.rig['facing']:
            parent = element(canvas, 'g', id='side-facing-mirror', transform=f"translate({config['width']} 0) scale(-1 1)")
        group = element(parent, 'g', transform=f"translate({config['width']/2-300*config['scale']} {config['floor']-self.rig['review']['floor']*config['scale']}) scale({config['scale']})")
        group.append(next(e for e in posed.iter() if e.get('id') == 'root'))
        if not clean:
            title = element(canvas, 'text', x=40, y=42, fill='#29392f', font_family='sans-serif', font_size=22)
            title.text = 'SIDE RUN / MOTION REVIEW'
            note = element(canvas, 'text', x=40, y=69, fill='#657165', font_family='sans-serif', font_size=15)
            note.text = 'Revised artwork · in-place loop · prototype'
        record.update({'frame': number, 'seconds': seconds, 'facing': self.facing})
        return ET.tostring(canvas), record


def main():
    from tools.side_actions import SIDE_ACTIONS, load_side_action
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--character', type=Path, default=ROOT/'characters/hoodie-side')
    parser.add_argument('--poses', type=Path, default=ROOT/'poses/side-run.json')
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--config', type=Path, help='Custom config; default is motions/side-run-preview.json')
    source.add_argument('--action', choices=SIDE_ACTIONS, help='Saved reusable side run')
    parser.add_argument('--duration', type=float, help='Saved action duration in seconds (whole frames)')
    parser.add_argument('--speed', type=float, help='Saved action cadence multiplier; default 1')
    parser.add_argument('--clean', action='store_true', help='Export transparent PNGs without review labels or ground')
    parser.add_argument('--facing', choices=['left', 'right'], help='Mirror character only; default is the source/config direction')
    parser.add_argument('--out', type=Path, help='New output folder; default is direction-specific')
    parser.add_argument('--jobs', type=int, default=2, choices=range(1, 5))
    args = parser.parse_args()
    if args.action and args.facing:
        parser.error('--action already specifies direction; do not also pass --facing')
    if args.action and args.poses != ROOT/'poses/side-run.json':
        parser.error('Saved actions use poses/side-run.json; use --config for custom poses')
    if not args.action and (args.duration is not None or args.speed is not None):
        parser.error('--duration and --speed require --action')
    try:
        if args.action:
            run = load_side_action(args.action, args.duration, args.speed if args.speed is not None else 1, args.character)
            config = run.config
        else:
            config = json.loads((args.config or ROOT/'motions/side-run-preview.json').read_text())
            if args.facing:
                config['facing'] = args.facing
            run = SideRun(args.character, args.poses, config)
    except ValueError as error:
        parser.error(str(error))
    if args.out is None:
        args.out = ROOT/('renders/side-run-left/motion/v01' if run.facing == 'left' else 'renders/side-run/motion/v04')
    if args.out.exists() and any(args.out.iterdir()):
        parser.error('Choose a new --out; existing outputs will not be replaced')
    directory = args.out/'frames'
    directory.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    jobs, records = [], []
    for index in range(round(config['duration']*config['fps'])):
        data, record = run.frame(index/config['fps'], index, clean=args.clean)
        jobs.append((data, config['width'], config['height'], str(directory/f'frame_{index:04d}.png')))
        records.append(record)
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        for index, _ in enumerate(pool.map(render_frame, jobs, chunksize=2)):
            if (index+1) % 30 == 0 or index+1 == len(jobs):
                print(f'Rendered {index+1}/{len(jobs)}', flush=True)
    report = {
        'action': args.action, 'config': config, 'clean': args.clean, 'frames': records, 'render_seconds': time.monotonic()-started,
        'source_sha256': hashlib.sha256((args.character/'character.svg').read_bytes()).hexdigest(),
        'poses_sha256': hashlib.sha256(args.poses.read_bytes()).hexdigest(),
        'implementation_sha256': {name: hashlib.sha256((ROOT/'tools'/name).read_bytes()).hexdigest() for name in ['side_run.py', 'side_review.py']},
        'max_ground_correction': max(record['ground_correction'] for record in records),
        'limitations': ['Mechanical checks do not establish natural acting.', 'Vertical ground correction only; no horizontal foot locking, scene travel or standing transitions.'],
    }
    with (args.out/'motion-validation.json').open('x') as stream:
        stream.write(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'frames'}, indent=2))


if __name__ == '__main__':
    main()
