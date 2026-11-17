"""Rear-view study of the saved front run's 3D motion; not an engine action.

Motion is sampled once from the saved front-run controls, then rotated 180
degrees around world Y. Artwork and depth ordering are rear-specific. Earlier
rear assets and their provisional hand-keyed gait are never loaded or changed.
"""
import argparse
import copy
from dataclasses import asdict
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

from tools.animate import raster
from tools.front_run_study import FrontStudy, MotionReadability, add, cross, elt, sub, times, unit
from tools.front_study_drawing import garment, sneaker
from tools.preview import ROOT, SVG
from tools.support_run import smooth_positive


def rear_point(point):
    """Proper 180-degree rotation, not a screen-space reflection."""
    x, y, z = point
    return -x, y, -z


class RearStudy:
    def __init__(self):
        self.preset = json.loads((ROOT/'motions/front-run.json').read_text())
        self.motion = FrontStudy(readability=MotionReadability(**self.preset['readability']))
        self.cycle, self.scale = self.motion.cycle, self.motion.scale
        self.floor, self.center = self.motion.floor, self.motion.center
        self.identity = ROOT/'characters/hoodie-rear-study/identity.svg'
        self.original = ET.fromstring(self.identity.read_bytes())
        self.nodes = {e.get('id'): e for e in self.original.iter() if e.get('id')}

    # Geometry helpers work in camera coordinates, just as in the front study.
    project = FrontStudy.project
    limb_path = FrontStudy.limb_path
    depth = FrontStudy.depth
    body_transform = FrontStudy.body_transform

    def pose(self, seconds):
        source = self.motion.pose(seconds)
        pose = {name: rear_point(source[name]) for name in
                ('root', 'neck', 'up', 'hip_axis', 'shoulder_axis')}
        pose.update(phase=source['phase'], groundCorrection=source['groundCorrection'])
        for side in ('left', 'right'):
            pose[side] = {joint: rear_point(point) for joint, point in source[side].items()}
        # A foot's dorsal/sole orientation cannot be reconstructed from forward
        # direction plus world-up: that flips at a vertical recovering foot.
        # The rear shoe frame follows the shin, preserving the folded sole view.
        lowest = min(v[1] for side in ('left', 'right') for v in self.shoe(pose, side)[0])
        correction = smooth_positive(-lowest, 1)
        pose['sourceGroundCorrection'] = source['groundCorrection']
        pose['rearGroundCorrection'] = correction
        pose['groundCorrection'] += correction
        if correction:
            for name in ('root', 'neck'):
                pose[name] = add(pose[name], (0, correction, 0))
            for side in ('left', 'right'):
                for joint in ('hip', 'knee', 'ankle', 'shoulder', 'elbow', 'wrist'):
                    pose[side][joint] = add(pose[side][joint], (0, correction, 0))
        return pose

    def shoe_basis(self, pose, side):
        limb = pose[side]
        forward = limb['foot_forward']
        right = unit(cross(unit(sub(limb['knee'], limb['ankle'])), forward))
        return right, unit(cross(forward, right)), forward

    def shoe(self, pose, side):
        right, up, forward = self.shoe_basis(pose, side)
        def pt(x, y, z):
            return add(pose[side]['ankle'], add(times(right, x), add(times(up, y), times(forward, z))))
        vertices = [pt(-22, -8, -17), pt(22, -8, -17), pt(34, -16, 70), pt(-34, -16, 70),
                    pt(-24, -35, -20), pt(24, -35, -20), pt(35, -35, 74), pt(-35, -35, 74)]
        return vertices, pt

    def foot_svg(self, parent, pose, side):
        sneaker(self, parent, pose, side)
        # The shared surface mesh is unchanged. Replace its world-up lace test
        # with this rear shoe's full frame so laces never show through a sole.
        for node in list(parent):
            if node.tag == f'{{{SVG}}}path':
                parent.remove(node)
        _, pt = self.shoe(pose, side)
        _, up, _ = self.shoe_basis(pose, side)
        camera = sub((0, 420, 1800), pose[side]['ankle'])
        if sum(a*b for a, b in zip(up, camera)) >= 0:
            for z, height, width in [(9, -9, 25), (22, -11, 29), (35, -14, 31)]:
                points = [self.project(pt(x, -29+(height+29)*math.sqrt(1-(x/width)**2), z))
                          for x in (-13, 0, 13)]
                a, b, c = points
                elt(parent, 'path', d=f'M{a[0]} {a[1]} Q{b[0]} {b[1]} {c[0]} {c[1]}',
                    fill='none', stroke='#c5d8d9', stroke_width=2.5, stroke_linecap='round')
            return
        for z in (-2, 13, 29, 45, 59):
            width = 19 if z < 0 else 24 if z < 45 else 21
            a, b = self.project(pt(-width, -35.3, z)), self.project(pt(width, -35.3, z))
            elt(parent, 'path', d=f'M{a[0]} {a[1]} L{b[0]} {b[1]}',
                stroke='#6b888c', stroke_width=1.6, stroke_linecap='round', fill='none')

    def arm(self, parent, pose, side, foreground):
        limb = pose[side]
        a, b = limb['elbow'], limb['wrist']
        da, db = self.depth(a, pose), self.depth(b, pose)
        segments = [(f'rear-upper-arm-{side}-{foreground}', limb['shoulder'], a, 36, 33),
                    (f'rear-forearm-{side}-{foreground}', a, b, 33, 27)]
        if not foreground:
            garment(self, parent, segments, 'rear-sleeve-back-'+side, '#85886a')
        elif da >= 0 or db >= 0:
            low, high = a, b
            if (da >= 0) != (db >= 0):
                split = add(a, times(sub(b, a), da/(da-db)))
                low, high = (a, split) if da >= 0 else (split, b)
            ident = 'rear-sleeve-clip-'+side
            clip = elt(parent, 'clipPath', id=ident, clipPathUnits='userSpaceOnUse')
            elt(clip, 'path', d=self.limb_path(low, high, 37, 31))
            layer = elt(parent, 'g', clip_path=f'url(#{ident})')
            garment(self, layer, segments, 'rear-sleeve-front-'+side, '#85886a')
        if (db >= 0) != foreground:
            return
        wrist = self.project(b)
        end = self.project(add(b, times(unit(sub(b, a)), 20)))
        angle = math.degrees(math.atan2(end[1]-wrist[1], end[0]-wrist[0]))-90
        group = elt(parent, 'g', id=f'rear-hand-{side}',
                    transform=f'translate({wrist[0]} {wrist[1]}) rotate({angle}) scale({wrist[2]})')
        # Back-of-fist silhouette, distinct from the front study's palm details.
        elt(group, 'path', d='M-19 3 Q-29 17-25 32 Q-23 45-13 43 Q-7 50 1 45 Q9 50 16 43 Q27 44 27 32 L25 15 Q28 4 19 2 L8-2Z',
            fill='#dfbd94', stroke='#292b25', stroke_width=3, stroke_linejoin='round')
        elt(group, 'path', d='M-18 28 Q-8 22 0 27 M5 31 Q13 28 18 31',
            fill='none', stroke='#292b25', stroke_width=2, stroke_linecap='round')
        elt(group, 'path', d='M-28-9 Q0-2 29-9 L27 9 Q1 17-26 8Z',
            fill='#74795c', stroke='#292b25', stroke_width=3)

    def frame(self, seconds, skeleton=False, clean=False):
        pose = self.pose(seconds)
        canvas = ET.Element(f'{{{SVG}}}svg', width='1280', height='720', viewBox='0 0 1280 720')
        defs = copy.deepcopy(self.original.find(f'{{{SVG}}}defs'))
        canvas.append(defs)
        for ident, radius in [('study-cloth-outline', 1.15), ('study-shoe-outline', .9)]:
            filt = elt(defs, 'filter', id=ident, x='-50%', y='-50%', width='200%', height='200%', color_interpolation_filters='sRGB')
            elt(filt, 'feMorphology', **{'in': 'SourceAlpha'}, operator='dilate', radius=radius, result='edge')
            elt(filt, 'feFlood', flood_color='#292b25', result='ink')
            elt(filt, 'feComposite', **{'in': 'ink'}, in2='edge', operator='in', result='border')
            merge = elt(filt, 'feMerge')
            elt(merge, 'feMergeNode', **{'in': 'border'})
            elt(merge, 'feMergeNode', **{'in': 'SourceGraphic'})
        if not clean:
            elt(canvas, 'rect', width=1280, height=720, fill='#f7f6f0')
            elt(canvas, 'line', x1=270, x2=1010, y1=self.floor+2, y2=self.floor+2, stroke='#d7d8cf', stroke_width=1)
        group = elt(canvas, 'g', id='rear-study-character')
        pieces = []
        for side in ('left', 'right'):
            limb = pose[side]
            node = ET.Element(f'{{{SVG}}}g')
            garment(self, node, [(f'rear-thigh-{side}', limb['hip'], limb['knee'], 39, 32),
                                 (f'rear-shin-{side}', limb['knee'], limb['ankle'], 32, 27)],
                    'rear-trousers-'+side, '#505a5c')
            pieces.append(((limb['hip'][2]+limb['knee'][2])/2, node))
            shoe = ET.Element(f'{{{SVG}}}g', id='rear-shoe-'+side)
            self.foot_svg(shoe, pose, side)
            pieces.append((sum(v[2] for v in self.shoe(pose, side)[0])/8, shoe))
        for _, node in sorted(pieces, key=lambda item: item[0]):
            group.append(node)
        pelvis = elt(group, 'g', transform=self.body_transform(pose, times(pose['hip_axis'], -1)))
        pelvis.append(copy.deepcopy(self.nodes['rear-pelvis']))
        for side in ('left', 'right'):
            self.arm(group, pose, side, False)
        torso = elt(group, 'g', transform=self.body_transform(pose, times(pose['shoulder_axis'], -1)))
        torso.append(copy.deepcopy(self.nodes['rear-torso']))
        neck = self.project(pose['neck'])
        head = elt(group, 'g', transform=f'translate({neck[0]} {neck[1]}) scale({neck[2]})')
        head.append(copy.deepcopy(self.nodes['rear-head']))
        hood = elt(group, 'g', transform=self.body_transform(pose, times(pose['shoulder_axis'], -1)))
        hood.append(copy.deepcopy(self.nodes['rear-hood']))
        for side in ('left', 'right'):
            self.arm(group, pose, side, True)
        if skeleton:
            for side, color in [('left', '#c35d45'), ('right', '#357e9e')]:
                for a, b in [('hip', 'knee'), ('knee', 'ankle'), ('shoulder', 'elbow'), ('elbow', 'wrist')]:
                    pa, pb = self.project(pose[side][a]), self.project(pose[side][b])
                    elt(canvas, 'path', d=f'M{pa[0]} {pa[1]} L{pb[0]} {pb[1]}', stroke=color, stroke_width=2, fill='none')
        return ET.tostring(canvas), pose


def render_study(out, encode=False):
    from PIL import Image, ImageDraw
    action = RearStudy()
    out.mkdir(parents=True)  # Never replace a prior preview.
    for directory in ('svg', 'frames', 'keyframes'):
        (out/directory).mkdir()
    sheet = Image.new('RGB', (1600, 900), '#f7f6f0')
    for i in range(8):
        svg, _ = action.frame(i/8*action.cycle)
        (out/'keyframes'/f'pose_{i:02d}.svg').write_bytes(svg)
        buffer = io.BytesIO(); raster(svg, 1280, 720).write_to_png(buffer)
        image = Image.open(buffer).convert('RGB')
        image.save(out/'keyframes'/f'pose_{i:02d}.png')
        x, y = i%4*400, i//4*450
        sheet.paste(image.crop((440, 40, 840, 690)).resize((400, 425)), (x, y+25))
        ImageDraw.Draw(sheet).text((x+10, y+7), f'REAR | phase {i/8:.3f}', fill='#29392f')
    sheet.save(out/'pose-study.png')
    # Same motion phase and camera settings; no independent artwork rescaling.
    comparison = Image.new('RGB', (1600, 900), '#f7f6f0')
    for i in range(4):
        for row, view in [(0, action.motion), (1, action)]:
            svg, _ = view.frame(i/4*action.cycle)
            buffer = io.BytesIO(); raster(svg, 1280, 720).write_to_png(buffer)
            tile = Image.open(buffer).convert('RGB').crop((440, 40, 840, 690)).resize((400, 425))
            comparison.paste(tile, (i*400, row*450+25))
            ImageDraw.Draw(comparison).text((i*400+10, row*450+7),
                f'{"SAVED FRONT" if row == 0 else "NEW REAR"} | phase {i/4:.2f}', fill='#29392f')
    comparison.save(out/'front-rear-comparison.png')
    states = []
    duration = action.cycle*3
    for i in range(round(duration*30)):
        svg, pose = action.frame(i/30)
        (out/'svg'/f'frame_{i:04d}.svg').write_bytes(svg)
        raster(svg, 1280, 720).write_to_png(str(out/'frames'/f'frame_{i:04d}.png'))
        states.append(pose)
    report = {'status': 'unapproved rear-view study; not an engine action',
              'sourceMotion': 'front-run / Astra v04', 'reference': action.motion.reference['source'],
              'camera': 'world-Y rotation by 180 degrees before projection',
              'readability': asdict(action.motion.readability),
              'identitySha256': hashlib.sha256(action.identity.read_bytes()).hexdigest(),
              'cycle': action.cycle, 'duration': duration, 'fps': 30, 'frames': len(states),
              'maxGroundCorrection': max(p['groundCorrection'] for p in states),
              'maxAdditionalRearGroundCorrection': max(p['rearGroundCorrection'] for p in states),
              'limitations': ['Rear likeness and motion need playback review.',
                              'Shoe-proxy plane correction, not planted-foot or pixel-grounding verification.',
                              'Painter ordering, not full depth-buffer occlusion. No travel or standing transitions.'],
              'states': states}
    (out/'study-report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    if encode:
        command = [sys.executable, '-B', str(ROOT/'tools/encode_sequence.py'), '--dir', str(out/'frames'),
                   '--pattern', 'frame_%04d.png', '--fps', '30', '-o', str(out/'study.mp4'), '--json']
        (out/'encode-plan.json').write_text(subprocess.check_output(command+['--dry-run'], text=True))
        (out/'encode-result.json').write_text(subprocess.check_output(command, text=True))
    print(json.dumps({key: value for key, value in report.items() if key != 'states'}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--encode', action='store_true')
    args = parser.parse_args()
    render_study(args.out, args.encode)


if __name__ == '__main__':
    main()
