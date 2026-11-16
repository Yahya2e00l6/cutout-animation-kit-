"""Unapproved front-run pose study from a measured 3D reference.

No reference-run, front_run, frame_svg or old front gait is sampled here.
Existing artwork supplies only the torso, head, palette and identity. Limbs
are newly constructed around constant-length 3D chains and projected to SVG.
"""
import argparse
import copy
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

from tools.animate import raster
from tools.preview import ROOT, SVG
from tools.side_run import periodic_curve
from tools.support_run import smooth_positive


def add(a, b): return tuple(x+y for x, y in zip(a, b))
def sub(a, b): return tuple(x-y for x, y in zip(a, b))
def times(a, n): return tuple(x*n for x in a)
def unit(a):
    size = math.sqrt(sum(x*x for x in a))
    if size < 1e-9:
        raise ValueError('Degenerate reference bone')
    return times(a, 1/size)
def cross(a, b):
    return a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]
def elt(parent, tag, **attrs):
    return ET.SubElement(parent, f'{{{SVG}}}{tag}', {k.replace('_', '-'): str(v) for k, v in attrs.items()})


@dataclass(frozen=True)
class MotionReadability:
    """Fixed-length staging: pitch controls in radians, other gains dimensionless."""
    knee_drive: float = .85
    heel_fold: float = .18
    recovery_spread: float = .18
    arm_center: float = .40
    arm_gain: float = 1.35
    arm_symmetry: float = .8

    def __post_init__(self):
        if (not all(math.isfinite(v) for v in asdict(self).values())
                or not 0 <= self.arm_symmetry <= 1 or self.arm_gain <= 0
                or not 0 <= self.knee_drive <= 1 or not 0 <= self.heel_fold <= .5
                or not 0 <= self.recovery_spread <= .4
                or abs(self.arm_center) > 1):
            raise ValueError('Invalid front-study readability controls')


def pitch(vector, angle):
    """Rotate toward camera in the sagittal plane, preserving length."""
    x, y, z = vector
    c, s = math.cos(angle), math.sin(angle)
    return x, y*c+z*s, z*c-y*s


class FrontStudy:
    def __init__(self, reference=ROOT/'motions/front-run-study/athletic-reference.json', readability=None):
        self.readability = readability or MotionReadability()
        self.reference = json.loads(reference.read_text())
        self.samples = self.reference['samples']
        if (self.reference.get('version') != 1 or len(self.samples) < 8
                or not math.isfinite(self.reference['cycle']) or self.reference['cycle'] <= 0):
            raise ValueError('Invalid front-study reference')
        names = set(self.samples[0]['joints'])
        required = {'Neck', 'Head'} | {side+part for side in ('Left', 'Right')
                                      for part in ('UpLeg', 'Leg', 'Foot', 'ToeBase', 'ToeBase/end', 'Arm', 'ForeArm', 'Hand')}
        if not required <= names:
            raise ValueError('Reference lacks required 3D joints')
        for sample in self.samples:
            if (set(sample['joints']) != names or not all(math.isfinite(sample[n]) for n in ('height', 'sway'))
                    or any(len(v) != 3 or not all(math.isfinite(n) for n in v) for v in sample['joints'].values())):
                raise ValueError('Invalid reference coordinates')
        self.phases = [i/len(self.samples) for i in range(len(self.samples))]
        self.cycle = self.reference['cycle']
        self.character = ROOT/'characters/hoodie/character.svg'
        self.original = ET.fromstring(self.character.read_bytes())
        self.nodes = {e.get('id'): e for e in self.original.iter() if e.get('id')}
        self.scale, self.floor, self.center = .64, 650, 640
        rest = self.samples[0]['joints']
        self.ratio = 291/(math.dist(rest['LeftUpLeg'], rest['LeftLeg'])+math.dist(rest['LeftLeg'], rest['LeftFoot']))
        # One constant shoe-depth alignment, then only a small smooth floor
        # correction. This is a blocking study, not a fitted contact solver.
        self.alignment = 0
        minimums = [min(v[1] for side in ('left', 'right') for v in self.shoe(self.pose(p*self.cycle, ground=False), side)[0])
                    for p in self.phases]
        self.alignment = -sorted(minimums)[len(minimums)//3]

    def sample(self, seconds):
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError('Study time must be finite and nonnegative')
        phase = (seconds/self.cycle) % 1
        def channel(values): return periodic_curve(phase, self.phases, values)
        joints = {name: tuple(channel([s['joints'][name][axis] for s in self.samples]) for axis in range(3))
                  for name in self.samples[0]['joints']}
        return {'joints': joints, 'height': channel([s['height'] for s in self.samples]),
                'sway': channel([s['sway'] for s in self.samples]), 'phase': phase}

    def pose(self, seconds, ground=True):
        sampled = self.sample(seconds); ref = sampled['joints']
        opposite = self.sample(seconds+self.cycle*.5)['joints']
        controls = self.readability
        hip_center = times(add(ref['LeftUpLeg'], ref['RightUpLeg']), .5)
        up = unit(sub(ref['Neck'], hip_center))
        hip_axis = unit(sub(ref['LeftUpLeg'], ref['RightUpLeg']))
        shoulder_axis = unit(sub(ref['LeftArm'], ref['RightArm']))
        root = (sampled['sway']*self.ratio,
                (sampled['height']+hip_center[1])*self.ratio+self.alignment, 0)
        out = {'root': root, 'up': up, 'hip_axis': hip_axis, 'shoulder_axis': shoulder_axis,
               'phase': sampled['phase'], 'groundCorrection': 0.0}
        out['neck'] = add(root, times(up, 307))
        chest = add(root, times(up, 251))
        for side, name, sign in [('left', 'Left', 1), ('right', 'Right', -1)]:
            hip = add(root, times(hip_axis, 43*sign))
            thigh = unit(sub(ref[name+'Leg'], ref[name+'UpLeg']))
            shin = unit(sub(ref[name+'Foot'], ref[name+'Leg']))
            # C1 staging: amplify forward knee drive and folded recovery, while
            # retaining the reference's phase and its fixed-length chains.
            drive = controls.knee_drive*max(0, thigh[2])**2
            recovery = max(0, -shin[2])**4
            fold = -controls.heel_fold*recovery
            shin = unit(add(shin, (sign*controls.recovery_spread*recovery, 0, 0)))
            knee = add(hip, times(pitch(thigh, drive), 151))
            ankle = add(knee, times(pitch(shin, fold), 140))
            shoulder = add(chest, times(shoulder_axis, 74*sign))
            other = 'Right' if name == 'Left' else 'Left'
            def arm_direction(a, b):
                own = unit(sub(ref[name+b], ref[name+a]))
                mirror = unit(sub(opposite[other+b], opposite[other+a]))
                mirror = (-mirror[0], mirror[1], mirror[2])
                weight = controls.arm_symmetry*.5
                return unit(add(times(own, 1-weight), times(mirror, weight)))
            upper = arm_direction('Arm', 'ForeArm')
            lower = arm_direction('ForeArm', 'Hand')
            angle = math.atan2(upper[2], -upper[1])
            turn = (angle+controls.arm_center)*controls.arm_gain-angle
            elbow = add(shoulder, times(pitch(upper, turn), 126))
            wrist = add(elbow, times(pitch(lower, turn), 105))
            out[side] = {'hip': hip, 'knee': knee, 'ankle': ankle, 'shoulder': shoulder,
                         'elbow': elbow, 'wrist': wrist,
                         'foot_forward': pitch(unit(sub(ref[name+'ToeBase/end'], ref[name+'ToeBase'])), fold)}
        if ground:
            lowest = min(v[1] for side in ('left', 'right') for v in self.shoe(out, side)[0])
            correction = smooth_positive(-lowest, 1)
            out['groundCorrection'] = correction
            out['root'] = add(out['root'], (0, correction, 0))
            out['neck'] = add(out['neck'], (0, correction, 0))
            for side in ('left', 'right'):
                for joint in ('hip', 'knee', 'ankle', 'shoulder', 'elbow', 'wrist'):
                    out[side][joint] = add(out[side][joint], (0, correction, 0))
        return out

    def project(self, point):
        x, y, z = point
        angle = math.radians(7)
        height, distance = 420, 1800
        depth = distance-(z*math.cos(angle)+(y-height)*math.sin(angle))
        if depth < 600:
            raise ValueError('Study point outside projection bounds')
        factor = (distance+height*math.sin(angle))/depth
        vertical = -height*math.cos(angle)-((y-height)*math.cos(angle)-z*math.sin(angle))*factor
        return (self.center+x*factor*self.scale, self.floor+vertical*self.scale, factor*self.scale)

    def shoe(self, pose, side):
        ankle = pose[side]['ankle']; forward = pose[side]['foot_forward']
        right = unit(cross((0, 1, 0), forward)); up = unit(cross(forward, right))
        def pt(x, y, z): return add(ankle, add(times(right, x), add(times(up, y), times(forward, z))))
        # Authored 3D shoe silhouette, not a stretched standing shoe. Toe, heel,
        # top and sole faces remain opaque and reorder by actual depth.
        vertices = [pt(-22, -8, -17), pt(22, -8, -17), pt(34, -16, 70), pt(-34, -16, 70),
                    pt(-24, -35, -20), pt(24, -35, -20), pt(35, -35, 74), pt(-35, -35, 74)]
        return vertices, pt

    def limb_path(self, start, end, wa, wb):
        a = self.project(start); b = self.project(end)
        dx, dy = b[0]-a[0], b[1]-a[1]
        length = math.hypot(dx, dy)
        if length < 1:
            dx, dy, length = 0, 1, 1
        ux, uy = dx/length, dy/length; nx, ny = -uy, ux
        wa *= a[2]; wb *= b[2]
        def pt(p, n, along=0): return f'{p[0]+nx*n+ux*along:.3f},{p[1]+ny*n+uy*along:.3f}'
        return (f'M {pt(a, wa)} C {pt(a, wa*1.03, length*.3)} {pt(b, wb*1.02, -length*.25)} {pt(b, wb)} '
                f'Q {pt(b, 0, wb*.55)} {pt(b, -wb)} '
                f'C {pt(b, -wb*1.02, -length*.25)} {pt(a, -wa*1.03, length*.3)} {pt(a, -wa)} '
                f'Q {pt(a, 0, -wa*.55)} {pt(a, wa)} Z')

    def limb(self, parent, start, end, wa, wb, color, ident):
        return elt(parent, 'path', id=ident, d=self.limb_path(start, end, wa, wb), fill=color,
                   stroke='#292b25', stroke_width=2.4, stroke_linejoin='round')

    def foot_svg(self, parent, pose, side):
        verts, pt = self.shoe(pose, side)
        faces = [([0, 1, 2, 3], '#465352'), ([4, 5, 6, 7], '#aec5c8'),
                 ([0, 1, 5, 4], '#718887'), ([1, 2, 6, 5], '#849c9e'),
                 ([2, 3, 7, 6], '#aec5c8'), ([3, 0, 4, 7], '#849c9e')]
        center = times(tuple(sum(v[i] for v in verts) for i in range(3)), 1/8)
        visible = set()
        for indices, color in sorted(faces, key=lambda f: sum(verts[i][2] for i in f[0])/len(f[0])):
            face_center = times(tuple(sum(verts[j][i] for j in indices) for i in range(3)), 1/4)
            normal = cross(sub(verts[indices[1]], verts[indices[0]]), sub(verts[indices[2]], verts[indices[0]]))
            if sum(a*b for a, b in zip(normal, sub(face_center, center))) < 0:
                normal = times(normal, -1)
            if sum(a*b for a, b in zip(normal, sub((0, 420, 1800), face_center))) <= 0:
                continue
            visible.add(tuple(indices))
            points = [self.project(verts[i])[:2] for i in indices]
            # Round the projected shoe corners; the volume is a construction
            # guide, not a box-shaped replacement for the character's sneakers.
            def near(a, b):
                length = math.dist(a, b)
                amount = min(.22, 4/max(length, 1))
                return tuple(x+(y-x)*amount for x, y in zip(a, b))
            first = near(points[0], points[-1])
            d = f'M {first[0]} {first[1]}'
            for i, point in enumerate(points):
                before, after = near(point, points[i-1]), near(point, points[(i+1)%len(points)])
                d += f' L {before[0]} {before[1]} Q {point[0]} {point[1]} {after[0]} {after[1]}'
            elt(parent, 'path', d=d+' Z', fill=color, stroke='#292b25', stroke_width=1.7, stroke_linejoin='round')
        if (0, 1, 2, 3) in visible:
            for z in (10, 27, 44):
                a, b = self.project(pt(-17, -10-z*.08, z)), self.project(pt(17, -10-z*.08, z))
                elt(parent, 'path', d=f'M {a[0]} {a[1]} L {b[0]} {b[1]}', fill='none', stroke='#b8cccd', stroke_width=1.5)
        if (4, 5, 6, 7) in visible:
            for z in (-6, 10, 27, 44, 60):
                a, b = self.project(pt(-20, -35.2, z)), self.project(pt(20, -35.2, z))
                elt(parent, 'path', d=f'M {a[0]} {a[1]} L {b[0]} {b[1]}', fill='none', stroke='#6d888c', stroke_width=2)

    def depth(self, point, pose):
        up = pose['up']
        plane = pose['root'][2]+(point[1]-pose['root'][1])*up[2]/up[1]
        return point[2]-plane

    def arm(self, parent, pose, side, foreground):
        limb = pose[side]; a, b = limb['elbow'], limb['wrist']
        if not foreground:
            self.limb(parent, limb['shoulder'], a, 31, 29, '#85886a', 'study-upper-arm-'+side)
        da, db = self.depth(a, pose), self.depth(b, pose)
        if (da >= 0) != (db >= 0):
            t = da/(da-db)
            split = add(a, times(sub(b, a), t))
            low, high = (a, split) if (da >= 0) == foreground else (split, b)
            self.limb(parent, low, high, 29, 26, '#85886a', f'study-forearm-{side}-{foreground}')
        elif (da >= 0) == foreground:
            self.limb(parent, a, b, 29, 26, '#85886a', f'study-forearm-{side}-{foreground}')
        if (db >= 0) == foreground:
            wrist = self.project(b)
            direction = self.project(add(b, times(unit(sub(b, a)), 20)))
            angle = math.degrees(math.atan2(direction[1]-wrist[1], direction[0]-wrist[0]))-90
            group = elt(parent, 'g', transform=f'translate({wrist[0]} {wrist[1]}) rotate({angle}) scale({wrist[2]})')
            elt(group, 'path', d='M -26 -10 Q 0 -4 26 -10 L 24 10 Q 0 17 -24 10 Z', fill='#74795c', stroke='#292b25', stroke_width=3)
            elt(group, 'path', d='M -19 8 Q -28 15 -24 32 Q -21 47 -5 48 L 14 44 Q 25 38 24 23 Q 23 10 13 8 Z', fill='#dfbd94', stroke='#292b25', stroke_width=3)
            elt(group, 'path', d='M -18 27 Q -4 20 12 26 M -10 39 L -9 30 M 1 40 L 2 30 M 12 36 L 12 28', fill='none', stroke='#292b25', stroke_width=2)

    def body_transform(self, pose, axis):
        origin = self.project(pose['root'])
        up = self.project(add(pose['root'], times(pose['up'], 251)))
        left = self.project(add(add(pose['root'], times(pose['up'], 251)), times(axis, 74)))
        right = self.project(add(add(pose['root'], times(pose['up'], 251)), times(axis, -74)))
        a, b = (left[0]-right[0])/148, (left[1]-right[1])/148
        c, d = (origin[0]-up[0])/251, (origin[1]-up[1])/251
        return f'matrix({a} {b} {c} {d} {origin[0]} {origin[1]})'

    def frame(self, seconds, skeleton=False):
        pose = self.pose(seconds)
        canvas = ET.Element(f'{{{SVG}}}svg', {'width': '1280', 'height': '720', 'viewBox': '0 0 1280 720'})
        canvas.append(copy.deepcopy(self.original.find(f'{{{SVG}}}defs')))
        elt(canvas, 'rect', width='1280', height='720', fill='#f7f6f0')
        elt(canvas, 'line', x1=270, y1=self.floor+2, x2=1010, y2=self.floor+2, stroke='#d7d8cf', stroke_width=1)
        air = min(v[1] for side in ('left', 'right') for v in self.shoe(pose, side)[0])
        elt(canvas, 'ellipse', cx=self.center, cy=self.floor+5, rx=58-max(0, air)*.12, ry=7, fill='#48564d', opacity=.14)
        group = elt(canvas, 'g', id='front-study-character')
        # Sort segments, not whole legs: a recovered heel belongs behind its
        # own advancing knee. Whole-leg ordering painted shoes over the knees.
        pieces = []
        for side in ('left', 'right'):
            limb = pose[side]
            for part, a, b, wa, wb in [('thigh', 'hip', 'knee', 34, 28), ('shin', 'knee', 'ankle', 28, 23)]:
                node = ET.Element(f'{{{SVG}}}g')
                self.limb(node, limb[a], limb[b], wa, wb, '#596666', f'study-{part}-{side}')
                pieces.append(((limb[a][2]+limb[b][2])/2, node))
            node = ET.Element(f'{{{SVG}}}g', {'id': 'study-shoe-'+side})
            self.foot_svg(node, pose, side)
            pieces.append((sum(v[2] for v in self.shoe(pose, side)[0])/8, node))
        for _, node in sorted(pieces, key=lambda item: item[0]):
            group.append(node)
        pelvis = elt(group, 'g', transform=self.body_transform(pose, pose['hip_axis']))
        pelvis.append(copy.deepcopy(self.nodes['pelvis-art']))
        for side in ('left', 'right'):
            self.arm(group, pose, side, False)
        torso = copy.deepcopy(self.nodes['torso'])
        for child in list(torso):
            if child.get('id') in ('shoulder-left', 'shoulder-right', 'neck'):
                torso.remove(child)
        torso.set('transform', self.body_transform(pose, pose['shoulder_axis']))
        group.append(torso)
        neck_point = self.project(pose['neck'])
        head = copy.deepcopy(self.nodes['neck'])
        roll = math.degrees(math.atan2(pose['up'][0], pose['up'][1]))*.3
        head.set('transform', f'translate({neck_point[0]} {neck_point[1]}) rotate({roll}) scale({neck_point[2]})')
        group.append(head)
        for side in ('left', 'right'):
            self.arm(group, pose, side, True)
        if skeleton:
            for side in ('left', 'right'):
                for a, b in [('hip', 'knee'), ('knee', 'ankle'), ('shoulder', 'elbow'), ('elbow', 'wrist')]:
                    pa, pb = self.project(pose[side][a]), self.project(pose[side][b])
                    elt(canvas, 'path', d=f'M {pa[0]} {pa[1]} L {pb[0]} {pb[1]}', stroke='#ce514a', stroke_width=2, fill='none')
        return ET.tostring(canvas), pose


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--duration', type=float, help='Default: three complete reference cycles')
    parser.add_argument('--encode', action='store_true')
    parser.add_argument('--baseline', type=Path, help='Previous study directory for matched-phase before/after images')
    parser.add_argument('--readability', type=Path, help='JSON overrides for MotionReadability angular staging controls')
    args = parser.parse_args()
    controls = MotionReadability(**json.loads(args.readability.read_text())) if args.readability else MotionReadability()
    if args.baseline and not all((args.baseline/'keyframes'/f'pose_{i:02d}.png').is_file() for i in range(8)):
        parser.error('Baseline needs all eight matched-phase keyframe PNGs')
    action = FrontStudy(readability=controls)
    if args.duration is None:
        args.duration = action.cycle*3
    if not math.isfinite(args.duration) or args.duration <= 0 or abs(args.duration*30-round(args.duration*30)) > 1e-6:
        parser.error('Duration must be positive and frame-aligned')
    args.out.mkdir(parents=True)  # Refuse existing output directories.
    keys = args.out/'keyframes'; keys.mkdir()
    from PIL import Image, ImageDraw
    sheet = Image.new('RGB', (1600, 900), '#eaece5')
    for i in range(8):
        phase = i/8
        svg, _ = action.frame(phase*action.cycle, skeleton=True)
        (keys/f'pose_{i:02d}.svg').write_bytes(svg)
        raster(svg, 1280, 720).write_to_png(str(keys/f'pose_{i:02d}.png'))
        tile = Image.open(keys/f'pose_{i:02d}.png').convert('RGB').crop((350, 40, 930, 690)).resize((400, 425))
        x, y = i%4*400, i//4*450
        sheet.paste(tile, (x, y+25)); ImageDraw.Draw(sheet).text((x+10, y+6), f'phase {phase:.3f}', fill='#29392f')
    sheet.save(args.out/'pose-study.png')
    from tools.front_study_review import review_images
    review_images(action, args.out, args.baseline)
    frames = args.out/'frames'; frames.mkdir()
    svgs = args.out/'svg'; svgs.mkdir()
    states = []
    for i in range(round(args.duration*30)):
        svg, pose = action.frame(i/30)
        (svgs/f'frame_{i:04d}.svg').write_bytes(svg)
        raster(svg, 1280, 720).write_to_png(str(frames/f'frame_{i:04d}.png'))
        states.append(pose)
    report = {'status': 'unapproved pose study', 'cycle': action.cycle, 'duration': args.duration,
              'fps': 30, 'frames': len(states), 'reference': action.reference['source'],
              'sourceArtworkSha256': hashlib.sha256(action.character.read_bytes()).hexdigest(),
              'constantShoeAlignment': action.alignment,
              'readability': asdict(action.readability),
              'maxGroundCorrection': max(s['groundCorrection'] for s in states),
              'limitations': ['Not an engine action or visual approval.', 'Retargeted mocap proportions, camera and drawn limb volumes are study choices.',
                              'Mesh-plane grounding is not a solved world-space stance constraint; contact and occlusion need playback review.'],
              'states': states}
    (args.out/'study-report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    if args.encode:
        command = [sys.executable, '-B', str(ROOT/'tools/encode_sequence.py'), '--dir', str(frames),
                   '--pattern', 'frame_%04d.png', '--fps', '30', '-o', str(args.out/'study.mp4'), '--json']
        plan = subprocess.check_output(command+['--dry-run'], text=True)
        (args.out/'encode-plan.json').write_text(plan)
        result = subprocess.check_output(command, text=True)
        (args.out/'encode-result.json').write_text(result)
    print(json.dumps({k: v for k, v in report.items() if k != 'states'}, indent=2))


if __name__ == '__main__':
    main()
