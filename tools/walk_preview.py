"""Review the same side walk on Astra and a packaged SVG, without scene binding."""
import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw

from tools.animate import raster
from tools.preview import ROOT
from tools.run_profile import finite
from tools.side_walk import AstraBody, GenericBody, SideWalk
from tools.preview import SVG


def placed_actor(svg, body, scale, center, floor):
    """Rasterize once at delivery scale, preserving fractional stage placement."""
    x = center-(body.joints['root'][0]-body.box[0])*scale
    y = floor-(body.floor-body.box[1])*scale
    ix, iy = math.floor(x), math.floor(y)
    width, height = math.ceil(body.box[2]*scale)+2, math.ceil(body.box[3]*scale)+2
    canvas = ET.Element(f'{{{SVG}}}svg', width=str(width), height=str(height), viewBox=f'0 0 {width} {height}')
    group = ET.SubElement(canvas, f'{{{SVG}}}g', transform=f'translate({x-ix} {y-iy}) scale({scale})')
    source = ET.fromstring(svg)
    source.set('width', str(body.box[2])); source.set('height', str(body.box[3]))
    group.append(source)
    buffer = io.BytesIO(); raster(ET.tostring(canvas), width, height).write_to_png(buffer)
    with Image.open(buffer) as image:
        return image.convert('RGBA'), (ix, iy)


def preview(out, rig, duration=3.6, speed=1, facing='right', mode='loop', encode=False, fps=60):
    if out.exists():
        raise FileExistsError('Choose a fresh walk preview directory')
    if type(fps) is not int or fps not in (30, 60):
        raise ValueError('Review frame rate must be 30 or 60')
    if not finite(duration) or not 0 < duration <= 30 or abs(duration*fps-round(duration*fps)) > 1e-7:
        raise ValueError('Duration must be positive, frame-aligned and at most 30 seconds')
    if mode not in ('loop', 'travel'):
        raise ValueError('Choose loop or travel review')
    bodies = [AstraBody(), GenericBody(rig)]
    walks = [SideWalk(body) for body in bodies]
    for walk in walks:
        walk.sample(0, speed)
    if facing not in ('right', 'left'):
        raise ValueError('Facing must be right or left')
    scale, width, height, floor = .8, 1800, 1000, 900
    if mode == 'travel' and any(w.distance*duration*speed/w.cycle*scale > 520 for w in walks):
        raise ValueError('Travel review exceeds the fixed stage; use a shorter duration or loop mode')
    out.mkdir(parents=True)
    for name in ('astra', 'svg-character', 'review-frames'):
        (out/name).mkdir()
    sheet = Image.new('RGB', (1800, 1500), '#f7f6f0')
    records = []
    count = round(duration*fps)
    chosen = [round(i*(count-1)/5) for i in range(6)]
    for index in range(count):
        seconds = index/fps
        plate = Image.new('RGB', (width, height), '#f7f6f0')
        draw = ImageDraw.Draw(plate)
        draw.text((35, 25), f'SIDE WALK / {mode.upper()} / {facing.upper()} / movement review, not approval', fill='#29392f')
        draw.line((900, 70, 900, 960), fill='#d3d5cc', width=2)
        frame_records = []
        for slot, (name, body, walk) in enumerate(zip(('Astra', 'Ponytail SVG'), bodies, walks)):
            svg, record = walk.frame(seconds, speed, facing)
            prefix = 'astra' if slot == 0 else 'svg-character'
            (out/prefix/f'frame_{index:04d}.svg').write_bytes(svg)
            buffer = io.BytesIO()
            bw, bh = map(round, body.box[2:])
            raster(svg, bw, bh).write_to_png(buffer)
            with Image.open(buffer) as image:
                actor = image.convert('RGBA')
            bounds = actor.getchannel('A').point(lambda n: 255 if n >= 128 else 0).getbbox()
            if not bounds or min(bounds[:2]) <= 0 or bounds[2] >= bw or bounds[3] >= bh:
                raise ValueError(f'{name} frame {index} clipped; artwork and fixed viewport were not changed')
            actor.save(out/prefix/f'frame_{index:04d}.png')
            center = slot*900+(180 if facing == 'right' else 720) if mode == 'travel' else slot*900+450
            advance = record['travel']*scale if mode == 'travel' else 0
            actor, position = placed_actor(svg, body, scale, center+advance, floor)
            # Ruler motion is exactly the body's implied speed in treadmill mode.
            ruler = -record['travel']*scale if mode == 'loop' else 0
            draw.line((slot*900+25, floor, slot*900+875, floor), fill='#a0ab98', width=2)
            for tick in range(25):
                tx = slot*900+25+(tick*50+ruler) % 850
                draw.line((tx, floor+4, tx, floor+14), fill='#a0ab98', width=2)
            # Pasting only opaque pixels from the transparent per-actor render
            # isolates the two source SVGs' definitions, selectors and IDs.
            plate.paste(actor, position, actor)
            planted = '+'.join(s for s in ('right', 'left') if record['contacts'][s]['stance'])
            draw.text((slot*900+35, 65), f'{name} | phase {record["phase"]:.3f} | support: {planted}', fill='#29392f')
            record['stageRootX'] = center+advance
            frame_records.append(record)
        plate.save(out/'review-frames'/f'frame_{index:04d}.png')
        if index in chosen:
            thumb = plate.resize((900, 500), Image.Resampling.LANCZOS)
            at = chosen.index(index)
            sheet.paste(thumb, ((at % 2)*900, (at//2)*500))
        records.append(frame_records)
    sheet.save(out/'pose-sheet.png')
    sources = ['motions/side-walk.json', 'tools/side_walk.py', 'tools/walk_preview.py',
               'tools/svg_rig.py', 'tools/side_review.py', 'characters/hoodie-side/character.svg',
               'characters/hoodie-side/rig.json']
    report = {'status': 'technical review only; movement awaits user acceptance', 'mode': mode,
              'duration': duration, 'fps': fps, 'width': width, 'height': height, 'frameCount': count,
              'facing': facing, 'speed': speed, 'config': walks[0].config,
              'sourceHashes': {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources},
              'rig': str(rig), 'rigSha256': hashlib.sha256(rig.read_bytes()).hexdigest(),
              'svgSha256': hashlib.sha256((rig.parent/'character.svg').read_bytes()).hexdigest(),
              'limitations': ['Steady state only; no stand/start/stop blending or production scene registration.',
                              'Flat support shoe, no articulated heel-to-toe roll.',
                              'Locked rigid shoe transform during stance, not a guarantee of whole-sole flatness on uneven drawings.',
                              'Constant-speed level travel; no acceleration or terrain solver.'], 'frames': records}
    (out/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    if encode:
        command = [sys.executable, '-B', str(ROOT/'tools/encode_sequence.py'), '--dir', str(out/'review-frames'),
                   '--pattern', 'frame_%04d.png', '--fps', str(fps), '-o', str(out/'walk.mp4'), '--json']
        for suffix, extra in [('plan', ['--dry-run']), ('result', [])]:
            result = subprocess.check_output(command+extra, text=True)
            (out/f'encode-{suffix}.json').write_text(result)
    print(out/'pose-sheet.png')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rig', type=Path, default=ROOT/'characters/ponytail-hoodie-side/rig.json')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--duration', type=float, default=3.6)
    parser.add_argument('--speed', type=float, default=1)
    parser.add_argument('--facing', choices=('right', 'left'), default='right')
    parser.add_argument('--mode', choices=('loop', 'travel'), default='loop')
    parser.add_argument('--encode', action='store_true')
    parser.add_argument('--fps', type=int, choices=(30, 60), default=60)
    args = parser.parse_args()
    try:
        preview(args.out, args.rig, args.duration, args.speed, args.facing, args.mode, args.encode, args.fps)
    except (ValueError, OSError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
