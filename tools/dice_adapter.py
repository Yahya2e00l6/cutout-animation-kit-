"""Retarget shared side-run foot paths onto an unchanged DICE SVG snapshot.

The donor owns cadence, recovery and standing transitions. DICE keeps its own
limb lengths, geometry, palette, face and hierarchy. Shoe rotations are shared,
but their contact heights are measured from DICE's own saved drawings.
"""
import copy
import hashlib
import io
import importlib.util
import json
import math
import xml.etree.ElementTree as ET

from tools.preview import ROOT, SVG
from tools.side_review import world_point
from tools.support_run import smooth_positive
from tools.animate import raster


ASSET = ROOT/'characters/dice-dongtae-upgraded-side'


class DiceAdapter:
    def __init__(self):
        provenance = json.loads((ASSET/'provenance.json').read_text())
        for name in ('character.svg', 'puppet_rig.py'):
            if hashlib.sha256((ASSET/name).read_bytes()).hexdigest() != provenance['files'][name]['sha256']:
                raise ValueError('DICE snapshot differs from its registered source')
        spec = importlib.util.spec_from_file_location('dice_snapshot_rig', ASSET/'puppet_rig.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.controller = module.PuppetRig
        self.source = (ASSET/'character.svg').read_text()
        rest = self.controller(self.source)
        self.pivots = {side: [rest._pivots[rest.prefix+part+'_'+side]
                              for part in ('thigh', 'shin', 'foot')]
                       for side in ('left', 'right')}
        self.lengths = {side: (math.dist(p[0], p[1]), math.dist(p[1], p[2]))
                        for side, p in self.pivots.items()}
        # One uniform display scale, not per-limb stretching. Preserve both
        # characters' native segment ratios; solve small differences with IK.
        self.ratio = sum(self.lengths['right'])/303
        self.shoe_cache = {}

    def shoe_bottom(self, side, angle):
        """Measure the actual saved shoe at 4x, retaining its root-scoped CSS."""
        cache_key = (side, round(angle, 9))
        if cache_key not in self.shoe_cache:
            from PIL import Image
            rig = self.controller(self.source)
            x, y = self.pivots[side][2]
            root = ET.fromstring(self.source)
            defs = copy.deepcopy(root.find(f'{{{SVG}}}defs'))
            for child in list(root):
                root.remove(child)
            root.append(defs)
            root.attrib.update(width='800', height='800', viewBox=f'{x-100} {y-100} 200 200')
            shoe = copy.deepcopy(rig.element('foot_'+side))
            shoe.set('transform', f'rotate({angle} {x} {y})')
            root.append(shoe)
            data = io.BytesIO()
            raster(ET.tostring(root), 800, 800).write_to_png(data)
            with Image.open(data) as image:
                bounds = image.convert('RGBA').getchannel('A').point(lambda v: 255 if v >= 128 else 0).getbbox()
            if not bounds or min(bounds) <= 0 or max(bounds) >= 800:
                raise ValueError('DICE shoe calibration clipped or empty')
            self.shoe_cache[cache_key] = -100+bounds[3]/4
        return self.shoe_cache[cache_key]

    def frame(self, action, seconds, number):
        posed, donor = action.pose(seconds)
        key = action.sample(seconds)
        rig = self.controller(self.source)
        k = self.ratio
        scale = action.config['scale']/k
        floor = 590+(925-600)*k
        _, hip_y = world_point(posed, 'hip-right', (0, 0))
        # Align native ankle-to-sole depths once, rather than repeatedly
        # dropping the body by ~23 px whenever the shorter DICE shoe plants.
        sole_alignment = action.shoe_bottom('right', 0)*k-self.shoe_bottom('right', 0)
        shift = (hip_y-600)*k+sole_alignment
        targets = {}
        shoe_angles = {}
        recovery_adjustments = {}
        for side in ('left', 'right'):
            toe_x, _ = world_point(posed, f'ankle-{side}', action.rig['review']['toe'])
            angle = sum(key['angles'][f'{joint}-{side}'] for joint in ('hip', 'knee', 'ankle'))
            shoe_angles[side] = angle
            theta = math.radians(angle)
            toe_offset_x = 60*math.cos(theta)-25*math.sin(theta)
            tx = 400+(toe_x-300)*k-toe_offset_x
            ty = floor-donor['shoe_clearance'][side]*k-self.shoe_bottom(side, angle)
            local = (seconds/action.config['cycle']-(.5 if side == 'left' else 0)) % 1
            weight = 0.0
            if .26 < local < 1:
                def ease(u):
                    u = max(0, min(1, u))
                    return u*u*(3-2*u)
                weight = ease((local-.26)/.03)*ease((1-local)/.12)
            # A differently drawn rotating shoe must not dictate swing-knee
            # extension. In the air, recover toward the shared ankle height;
            # blend back to measured sole contact before touchdown.
            _, ankle_y = world_point(posed, f'ankle-{side}', (0, 0))
            recovery_y = 590+(ankle_y-600)*k+sole_alignment
            upper_length, lower_length = self.lengths[side]
            knee = math.radians(key['angles'][f'knee-{side}'])
            radius2 = upper_length**2+lower_length**2+2*upper_length*lower_length*math.cos(knee)
            hip = self.pivots[side][0]
            recovery_y = min(recovery_y, hip[1]+shift+math.sqrt(max(0, radius2-(tx-hip[0])**2)))
            adjustment = weight*smooth_positive(ty-recovery_y)
            targets[side] = (tx, ty-adjustment)
            recovery_adjustments[side] = adjustment*scale
        drop = 0.0
        for side, (tx, ty) in targets.items():
            hip = self.pivots[side][0]
            reach = sum(self.lengths[side])-.5
            dx = tx-hip[0]
            if abs(dx) >= reach:
                raise ValueError('DICE retarget exceeds horizontal leg reach')
            required = ty-hip[1]-math.sqrt(reach*reach-dx*dx)
            drop += smooth_positive(required-shift-drop)
        rig.move_by('puppet', 0, shift+drop)
        errors = {}
        for side, target in targets.items():
            rig.reach('leg', side, *target, bend=1)
            leg_angle = sum(rig._angles[rig.prefix+part+'_'+side] for part in ('thigh', 'shin'))
            rig.set_rotation('foot_'+side, shoe_angles[side]-leg_angle)
            actual = rig.world_point('foot_'+side, *self.pivots[side][2])
            errors[side] = math.dist(actual, target)*scale
            if errors[side] > .01:
                raise ValueError('DICE retarget clamped an unreachable ankle')
            # Correct each native arm's rest direction before sharing angles.
            upper, lower = 'upper_arm_'+side, 'forearm_'+side
            shoulder = rig._pivots[rig.prefix+upper]
            elbow = rig._pivots[rig.prefix+lower]
            wrist = rig._pivots[rig.prefix+'hand_'+side]
            rest_upper = math.degrees(math.atan2(-(elbow[0]-shoulder[0]), elbow[1]-shoulder[1]))
            rest_lower = math.degrees(math.atan2(-(wrist[0]-elbow[0]), wrist[1]-elbow[1]))
            rig.set_rotation(upper, key['angles'][f'shoulder-{side}']-rest_upper)
            rig.set_rotation(lower, key['angles'][f'elbow-{side}']+rest_upper-rest_lower)
            rig.set_hand(side, 'fist')
        rig.set_rotation('upper_body', key['angles']['torso'])
        rig.set_rotation('head_group', key['angles']['head'])
        canvas = ET.Element(f'{{{SVG}}}svg', {
            'width': str(action.config['width']), 'height': str(action.config['height']),
            'viewBox': f"0 0 {action.config['width']} {action.config['height']}",
        })
        parent = canvas
        if action.facing == 'left':
            parent = ET.SubElement(parent, f'{{{SVG}}}g', {
                'transform': f"translate({action.config['width']} 0) scale(-1 1)"})
        group = ET.SubElement(parent, f'{{{SVG}}}g', {
            'transform': f"translate({action.config['width']/2-400*scale} {action.config['floor']-floor*scale}) scale({scale})"})
        # Keep the SVG root: its ID scopes Dongtae's CSS palette.
        root = rig.root
        root.set('overflow', 'visible')
        group.append(root)
        donor['diceRetarget'] = {
            'character': 'dice-dongtae-upgraded', 'maxAnkleError': max(errors.values()),
            'additionalHipDrop': drop*scale, 'shoeMode': 'measured-roll',
            'swingHeightAdjustment': recovery_adjustments,
            'soleAlignment': sole_alignment*scale,
            'sourceSha256': hashlib.sha256(self.source.encode()).hexdigest(),
        }
        donor.update({'frame': number, 'seconds': seconds, 'facing': action.facing})
        return ET.tostring(canvas), donor
