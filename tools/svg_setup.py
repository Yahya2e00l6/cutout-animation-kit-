"""One-time SVG setup CLI: inspect -> template -> map pivots -> build -> preview.

V1 is not a visual joint editor or automatic segmentation tool. It accepts
fourteen separated top-level SVG groups and explicit viewBox-space pivots.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

from tools.animate import raster
from tools.preview import ROOT
from tools.run_profile import RunProfile
from tools.svg_rig import SvgRig, build, read_svg, template


def preview(rig, motion, out, duration, speed, encode):
    from PIL import Image, ImageDraw
    if out.exists():
        raise FileExistsError('Choose a fresh preview directory')
    if duration <= 0 or duration > 30 or abs(duration*30-round(duration*30)) > 1e-6:
        raise ValueError('Preview duration must be frame-aligned, positive and at most 30 seconds')
    character, profile = SvgRig(rig), RunProfile(motion)
    profile.sample(0, speed)
    width, height = round(character.box[2]), round(character.box[3])
    if width % 2 or height % 2:
        raise ValueError('Preview export needs even source viewBox dimensions')
    out.mkdir(parents=True)
    for name in ('frames', 'svg'):
        (out/name).mkdir()
    if encode:
        (out/'review-frames').mkdir()
    sheet = Image.new('RGB', (1600, 800), '#f7f6f0')
    for i in range(8):
        svg, _ = character.frame(profile, i/8*profile.cycle/speed, speed)
        path = out/f'pose_{i:02d}.png'
        raster(svg, width, height).write_to_png(str(path))
        with Image.open(path) as image:
            image = image.convert('RGBA'); image.thumbnail((380, 350))
            x, y = i%4*400, i//4*400
            sheet.paste(image, (x+(400-image.width)//2, y+35), image)
            ImageDraw.Draw(sheet).text((x+12, y+10), f'phase {i/8:.3f}', fill='#29392f')
    sheet.save(out/'pose-sheet.png')
    records = []
    for i in range(round(duration*30)):
        svg, record = character.frame(profile, i/30, speed)
        (out/'svg'/f'frame_{i:04d}.svg').write_bytes(svg)
        frame = out/'frames'/f'frame_{i:04d}.png'
        raster(svg, width, height).write_to_png(str(frame))
        with Image.open(frame) as image:
            bounds = image.convert('RGBA').getchannel('A').point(lambda n: 255 if n >= 128 else 0).getbbox()
        if not bounds or min(bounds[:2]) <= 0 or bounds[2] >= width or bounds[3] >= height:
            raise ValueError(f'Frame {i} is empty/clipped; add fixed margins to the SVG viewBox before setup')
        if encode:
            with Image.open(out/'frames'/f'frame_{i:04d}.png') as source:
                rgba = source.convert('RGBA')
                plate = Image.new('RGB', (width, height), '#f7f6f0')
                plate.paste(rgba, (0, 0), rgba)
                plate.save(out/'review-frames'/f'frame_{i:04d}.png')
        records.append(record)
    (out/'report.json').write_text(json.dumps({'status': 'technical retarget test; not visual approval',
        'duration': duration, 'fps': 30, 'frameCount': len(records),
        'motionSource': profile.data['source'], 'character': str(rig), 'frames': records}, indent=2)+'\n')
    if encode:
        command = [sys.executable, '-B', str(ROOT/'tools/encode_sequence.py'), '--dir', str(out/'review-frames'),
                   '--pattern', 'frame_%04d.png', '--fps', '30', '-o', str(out/'run.mp4'), '--json']
        (out/'encode-plan.json').write_text(subprocess.check_output(command+['--dry-run'], text=True))
        (out/'encode-result.json').write_text(subprocess.check_output(command, text=True))
    print(out/'pose-sheet.png')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('inspect', 'template'):
        command = commands.add_parser(name)
        command.add_argument('--svg', required=True, type=Path)
        if name == 'template':
            command.add_argument('--out', required=True, type=Path)
    command = commands.add_parser('build')
    command.add_argument('--svg', required=True, type=Path)
    command.add_argument('--map', required=True, type=Path)
    command.add_argument('--out', required=True, type=Path)
    command = commands.add_parser('check')
    command.add_argument('--rig', required=True, type=Path)
    command = commands.add_parser('preview')
    command.add_argument('--rig', required=True, type=Path)
    command.add_argument('--motion', type=Path, default=ROOT/'motions/shared-side-run.json')
    command.add_argument('--out', required=True, type=Path)
    command.add_argument('--duration', type=float, default=2)
    command.add_argument('--speed', type=float, default=1)
    command.add_argument('--encode', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'inspect':
            _, _, box, groups = read_svg(args.svg)
            print(json.dumps({'viewBox': box, 'partGroups': list(groups),
                              'preparation': 'ready for manual mapping' if len(groups) == 14 else 'needs part separation/reorganization first',
                              'next': 'Create a template; map body parts and mark joints. Anatomy is not inferred.'}, indent=2))
        elif args.command == 'template':
            with args.out.open('x') as stream:
                stream.write(json.dumps(template(args.svg), indent=2)+'\n')
        elif args.command == 'build':
            build(args.svg, args.map, args.out)
            print(args.out/'rig.json')
        elif args.command == 'check':
            rig = SvgRig(args.rig)
            print(json.dumps({'valid': True, 'partCount': len(rig.rig['parts']), 'boneLengths': rig.lengths}, indent=2))
        else:
            preview(args.rig, args.motion, args.out, args.duration, args.speed, args.encode)
    except (ValueError, OSError, KeyError, ET.ParseError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
