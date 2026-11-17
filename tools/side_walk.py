"""Shared contact-driven side walk. Separate from every approved run.

Independent implementation informed by stick-motion's stance derivation and
our SupportRun's strict fixed-length IK / measured shoe contact approach.
No upstream browser code, timeline, artwork or motion samples are copied.
"""
import copy
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

from tools.preview import ROOT, SVG
from tools.run_profile import finite
from tools.svg_rig import SvgRig, ANCHORS
from tools.side_review import pose_character, world_point
from tools.support_run import smooth_positive


SIDES = ('right', 'left')


def smooth5(u):
    return u*u*u*(10+u*(-15+6*u))


def foot_path(phase, stance, distance, height):
    """C2 target: exact -distance stance velocity, matched swing endpoints.

    phase is in [0,1). Positive x is forward. Height is positive clearance.
    Unlike a sine lift, the swing has zero velocity/acceleration at contact.
    """
    amplitude = distance*stance/2
    if phase <= stance:
        return amplitude-distance*phase, 0.0, True
    u = (phase-stance)/(1-stance)
    carry = distance*(1-stance)
    x = -amplitude-carry*u+(2*amplitude+carry)*smooth5(u)
    lift = height*64*u**3*(1-u)**3
    return x, lift, False


def solve_leg(dx, dy, upper, lower):
    """Our SVG/down-reference convention; reject, never shorten a target."""
    radius = math.hypot(dx, dy)
    if not abs(upper-lower)+1e-7 < radius < upper+lower-1e-7:
        raise ValueError('Walk target unreachable; refusing stretched/sliding legs')
    cosine = (radius*radius-upper*upper-lower*lower)/(2*upper*lower)
    knee = math.acos(max(-1, min(1, cosine)))
    hip = math.atan2(-dx, dy)-math.atan2(lower*math.sin(knee), upper+lower*math.cos(knee))
    return math.degrees(hip), math.degrees(knee)


class GenericBody:
    """The existing rig, unchanged artwork and FK, with explicit walk placement."""
    def __init__(self, path):
        self.rig = SvgRig(path)
        self.joints = self.rig.joints
        self.lengths = {s: (self.rig.lengths[f'thigh-{s}'], self.rig.lengths[f'shin-{s}']) for s in SIDES}
        self.box = self.rig.box
        self.floor = self.box[1]+self.box[3]*.94
        self.shoe_bottom = self.rig.shoe_bottom

    def pose(self, sample):
        points, rotations = self.rig.skeleton(sample)
        points = {k: (p[0], p[1]+sample['rootShift']) for k, p in points.items()}
        root = self.rig.canvas()
        for role in self.rig.rig['layers']:
            root.append(self.rig.part(role, points[ANCHORS[role]], rotations[role]))
        return root, points


class AstraBody:
    """Read-only adapter for Astra's existing nested artwork, not a new rig."""
    def __init__(self):
        from tools.side_actions import load_side_action
        # Reuse only loading, native chain geometry and shoe calibration.
        self.asset = load_side_action('side-run-right')
        self.joints = {name: world_point(self.asset.tree, name, (0, 0)) for name in
                       ['root', 'neck']+[f'{j}-{s}' for s in SIDES for j in
                                        ('hip', 'knee', 'ankle', 'shoulder', 'elbow', 'wrist')]}
        self.lengths = {s: tuple(math.dist(self.joints[f'{a}-{s}'], self.joints[f'{b}-{s}'])
                                for a, b in [('hip', 'knee'), ('knee', 'ankle')]) for s in SIDES}
        self.box = (0, 0, 640, 1000)
        self.floor = self.asset.rig['review']['floor']
        self.shoe_bottom = self.asset.shoe_bottom

    def pose(self, sample):
        posed = pose_character(self.asset.tree, self.asset.rig,
                               {'angles': sample['angles'], 'root_y': self.joints['root'][1]+sample['rootShift']})
        points = {name: world_point(posed, name, (0, 0)) for name in self.joints}
        canvas = ET.Element(f'{{{SVG}}}svg', viewBox='0 0 640 1000', width='640', height='1000')
        canvas.append(copy.deepcopy(posed.getroot().find(f'{{{SVG}}}defs')))
        canvas.append(copy.deepcopy(next(n for n in posed.iter() if n.get('id') == 'root')))
        return canvas, points


class SideWalk:
    def __init__(self, body, config=None):
        self.body = body
        self.config = copy.deepcopy(config) if config is not None else json.loads((ROOT/'motions/side-walk.json').read_text())
        c = self.config
        fields = {'version', 'type', 'cycle', 'stance', 'distancePerCycle', 'stepHeight', 'hipHeight',
                  'hipBob', 'torsoLean', 'armSwing', 'elbowBend', 'status'}
        if (not isinstance(c, dict) or set(c) != fields or type(c['version']) is not int
                or c['version'] != 1 or c['type'] != 'side-walk'
                or not all(finite(c[k]) for k in fields-{'version', 'type', 'status'})):
            raise ValueError('Invalid side-walk configuration')
        bounds = {'cycle': (.5, 3), 'stance': (.51, .75), 'distancePerCycle': (.1, 1),
                  'stepHeight': (.01, .2), 'hipHeight': (.8, .98), 'hipBob': (0, .04),
                  'torsoLean': (-5, 10), 'armSwing': (0, 35), 'elbowBend': (-35, 0)}
        if any(not lo <= c[k] <= hi for k, (lo, hi) in bounds.items()):
            raise ValueError('Walk settings outside supported ranges')
        self.cycle = c['cycle']
        self.leg_length = sum(sum(body.lengths[s]) for s in SIDES)/2
        self.distance = c['distancePerCycle']*self.leg_length
        # One pelvis height, calibrated against both native shoes and leg lengths.
        self.base_shift = min(body.floor-body.shoe_bottom(s, 0)-c['hipHeight']*sum(body.lengths[s])
                              -body.joints[f'hip-{s}'][1] for s in SIDES)

    def sample(self, seconds, speed=1):
        if not finite(seconds) or seconds < 0 or not finite(speed) or speed <= 0:
            raise ValueError('Time must be finite/nonnegative; cadence finite/positive')
        turns = seconds*speed/self.cycle
        travel = turns*self.distance
        velocity = speed*self.distance/self.cycle
        if not all(math.isfinite(v) for v in (turns, travel, velocity)):
            raise ValueError('Walk time/cadence overflow')
        phase = turns % 1
        c, body = self.config, self.body
        # Lowest around weight transfer; highest over the mid-stance support.
        shift = self.base_shift+c['hipBob']*self.leg_length*math.cos(4*math.pi*(phase-.06))
        angles = {'torso': c['torsoLean'], 'head': -c['torsoLean']}
        contacts, targets, paths = {}, {}, {}
        drop = 0.0
        for side, offset in [('right', 0), ('left', .5)]:
            local = (phase-offset) % 1
            dx, lift, planted = foot_path(local, c['stance'], self.distance, c['stepHeight']*self.leg_length)
            swing = 0 if planted else (local-c['stance'])/(1-c['stance'])
            shoe_angle = -8*math.sin(math.pi*swing)**2
            hip_x, hip_y = body.joints[f'hip-{side}']
            ankle_y = body.floor-body.shoe_bottom(side, shoe_angle)-lift
            upper, lower = body.lengths[side]
            # Same support-leg principle as the accepted run: lower the pelvis
            # rather than stretch the limb or move its contact target. Keep a
            # soft 10-degree minimum knee bend away from the IK singularity.
            reach = math.sqrt(upper*upper+lower*lower+2*upper*lower*math.cos(math.radians(10)))
            if abs(dx) >= reach:
                raise ValueError('Walk target exceeds horizontal reach')
            drop += smooth_positive(ankle_y-hip_y-shift-math.sqrt(reach*reach-dx*dx), width=.5)
            paths[side] = (dx, ankle_y, shoe_angle)
            contacts[side] = {'stance': planted, 'localPhase': local, 'clearance': lift, 'shoeAngle': shoe_angle}
            targets[side] = [hip_x+dx, ankle_y]
        shift += drop
        for side, offset in [('right', 0), ('left', .5)]:
            dx, ankle_y, shoe_angle = paths[side]
            hip_y = body.joints[f'hip-{side}'][1]
            hip, knee = solve_leg(dx, ankle_y-hip_y-shift, *body.lengths[side])
            angles.update({f'hip-{side}': hip, f'knee-{side}': knee,
                           f'ankle-{side}': shoe_angle-hip-knee,
                           f'shoulder-{side}': c['armSwing']*math.cos(math.tau*(phase-offset-.06)),
                           f'elbow-{side}': c['elbowBend']-4*math.sin(math.tau*(phase-offset-.06))})
        return {'phase': phase, 'angles': angles, 'rootShift': shift, 'reachHipDrop': drop, 'contacts': contacts,
                'ankleTargets': targets, 'travel': travel, 'velocity': velocity}

    def frame(self, seconds, speed=1, facing='right'):
        if facing not in ('right', 'left'):
            raise ValueError('Facing must be right or left')
        sample = self.sample(seconds, speed)
        root, points = self.body.pose(sample)
        sign = 1 if facing == 'right' else -1
        pivot = self.body.joints['root'][0]
        if sign == -1:
            group = ET.Element(f'{{{SVG}}}g', transform=f'translate({2*pivot} 0) scale(-1 1)')
            for child in list(root):
                if child.tag != f'{{{SVG}}}defs':
                    root.remove(child); group.append(child)
            root.append(group)
        sample['joints'] = {k: [pivot+sign*(p[0]-pivot), p[1]] for k, p in points.items()}
        sample['worldJoints'] = {k: [pivot+sign*(p[0]-pivot+sample['travel']), p[1]] for k, p in points.items()}
        sample['facing'] = facing
        sample['travel'] *= sign
        sample['velocity'] *= sign
        sample['targetResidual'] = max(math.dist(points[f'ankle-{s}'], sample['ankleTargets'][s]) for s in SIDES)
        return ET.tostring(root), sample
