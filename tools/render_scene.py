"""Render trusted, engine-produced frame samples using saved action loaders.

This is an internal bridge, not another scene-language interpreter. Scheduling,
travel and action/view validation belong to engine/src/scene.ts.
"""
import argparse
import base64
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from tools.animate import raster
from tools.preview import SVG
from tools.side_actions import load_side_action
from tools.travel_run import TravelRun
from tools.side_transition import TransitionPose
from tools.background import Backgrounds
from tools.support_run import SupportRun


class SceneRenderer:
    """Keep one action instance per clip; isolate SVG IDs/styles per image."""

    def __init__(self, loader=load_side_action):
        self.loader = loader
        self.actions = {}
        self.travel = {}
        self.backgrounds = Backgrounds()
        self.support = {}
        self.dice = None

    def frame(self, sample, number):
        width, height = sample['output']['width'], sample['output']['height']
        canvas = ET.Element(f'{{{SVG}}}svg', {
            'width': str(width), 'height': str(height),
            'viewBox': f'0 0 {width} {height}',
        })
        ET.SubElement(canvas, f'{{{SVG}}}rect', {
            'width': '100%', 'height': '100%', 'fill': sample['stage']['background'],
        })
        plate = sample['stage'].get('plate')
        if plate:
            if plate['fit'] not in ('cover', 'contain'):
                raise ValueError('Unsupported background fit')
            data = self.backgrounds.image(plate)
            ET.SubElement(canvas, f'{{{SVG}}}image', {
                'id': 'stage-background', 'width': str(width), 'height': str(height),
                'preserveAspectRatio': 'xMidYMid ' + ('slice' if plate['fit'] == 'cover' else 'meet'),
                'href': data, '{http://www.w3.org/1999/xlink}href': data,
            })
        records = []
        for actor in sample['actors']:
            key = actor['clipIndex']
            signature = (actor['action'], actor['duration'], actor['speed'],
                         bool(actor.get('footLock')), actor.get('travelVelocity'), actor.get('scale'), actor.get('travelMode'), actor.get('runDuration'), actor.get('character', 'hoodie'))
            if key not in self.actions:
                self.actions[key] = (signature, self.loader(
                    actor['action'], duration=actor['duration'], speed=actor['speed']))
            previous, action = self.actions[key]
            if previous != signature:
                raise ValueError('Clip settings changed inside the frame manifest')
            anchor = [action.config['width'] / 2, action.config['floor']]
            if anchor != actor['sourceAnchor']:
                raise ValueError('Saved action anchor changed since scene validation')
            values = list(actor['transform'])
            if len(values) != 6 or not all(math.isfinite(n) for n in values):
                raise ValueError('Invalid sampled transform')
            transition = actor.get('transition')
            motion_time = actor['localTime']
            if transition:
                half_cycles = motion_time / action.config['cycle'] * 2
                if abs(half_cycles - round(half_cycles)) > 1e-6:
                    raise ValueError('Standing blends require a touchdown endpoint')
                motion_time = round(half_cycles) * action.config['cycle'] / 2
            motion_action = action
            support_leg = actor.get('travelMode') == 'support-leg'
            if actor.get('travelMode') and not support_leg:
                raise ValueError('Unsupported travel mode')
            if support_leg:
                if not actor.get('footLock'):
                    raise ValueError('Support-leg mode requires foot locking')
                if key not in self.support:
                    self.support[key] = SupportRun(action, actor['travelVelocity'], actor['scale'], actor['runDuration'])
                motion_action = self.support[key]
            rendered_action = TransitionPose(action, transition['weight'], transition) if transition else motion_action
            character = actor.get('character', 'hoodie')
            if character == 'dice-dongtae-upgraded':
                from tools.dice_adapter import DiceAdapter
                if self.dice is None:
                    self.dice = DiceAdapter()
                svg, contact = self.dice.frame(rendered_action, motion_time, number)
            elif character == 'hoodie':
                svg, contact = rendered_action.frame(motion_time, number, clean=True)
            else:
                raise ValueError('Unsupported scene character')
            locking = None
            if actor.get('footLock'):
                if key not in self.travel:
                    self.travel[key] = TravelRun(action)
                offset, locking = self.travel[key].correction(
                    motion_time, actor['travelVelocity'], actor['scale'], actor['position'][0])
                if transition:
                    side = locking['side']
                    if locking['mode'] != 'stance' or side is None:
                        raise ValueError('Standing blends require a touchdown endpoint')
                    phase = motion_time / action.config['cycle']
                    offset += actor['scale'] * (self.travel[key].toe_x(phase, side) - rendered_action.toe_x(motion_time, side))
                    locking = {**locking, 'mode': 'transition', 'rootOffsetX': offset,
                               'toeX': locking['anchorX'], 'transition': transition}
                elif support_leg:
                    adjustment = self.support[key].solve(motion_time)[1]
                    offset = adjustment['remainingRootOffsetX']
                    locking = {**locking, 'method': 'support-leg', 'rootOffsetX': offset,
                               'transferredRootOffsetX': adjustment['transferredRootOffsetX'],
                               'transferWeight': adjustment['transferWeight']}
                values[4] += offset
            data = 'data:image/svg+xml;base64,' + base64.b64encode(svg).decode('ascii')
            # An SVG image is a separate document: IDs and CSS never leak between actors.
            ET.SubElement(canvas, f'{{{SVG}}}image', {
                'width': str(action.config['width']), 'height': str(action.config['height']),
                'transform': 'matrix(' + ' '.join(str(n) for n in values) + ')',
                'href': data, '{http://www.w3.org/1999/xlink}href': data,
            })
            records.append({'actor': actor['id'], 'clipIndex': key,
                            'transform': values, 'sourceContacts': contact,
                            **({'horizontalLock': locking} if locking else {})})
        return ET.tostring(canvas, encoding='utf-8'), records


def render_manifest(manifest, output):
    """Write into a new frames/svg pair; refuse to replace any frame directory."""
    if manifest.get('version') != 1:
        raise ValueError('Unsupported internal render manifest')
    samples = manifest['samples']
    if not samples or len(samples) != manifest['frameCount']:
        raise ValueError('Frame manifest count mismatch')
    frames, svgs = output / 'frames', output / 'svg'
    if frames.exists() or svgs.exists():
        raise FileExistsError('Frame directories already exist; choose a new output folder')
    frames.mkdir()
    svgs.mkdir()
    renderer = SceneRenderer()
    contacts = []
    for number, sample in enumerate(samples):
        svg, record = renderer.frame(sample, number)
        (svgs / f'frame_{number:04d}.svg').write_bytes(svg)
        raster(svg, sample['output']['width'], sample['output']['height']).write_to_png(
            str(frames / f'frame_{number:04d}.png'))
        contacts.append({'frame': number, 'actors': record})
    (output / 'contacts.json').write_text(json.dumps({
        'scope': 'sourceContacts are source-space metadata for the selected action/adapter. horizontalLock is computed toe-X anchoring, not independent pixel/contact verification.',
        'frames': contacts,
    }, indent=2, allow_nan=False) + '\n')
    max_offset = max((abs(actor.get('horizontalLock', {}).get('rootOffsetX', 0))
                      for frame in contacts for actor in frame['actors']), default=0)
    max_run_offset = max((abs(actor.get('horizontalLock', {}).get('rootOffsetX', 0))
                          for frame in contacts for actor in frame['actors']
                          if actor.get('horizontalLock', {}).get('mode') != 'transition'), default=0)
    ik = [actor['sourceContacts']['supportIK'] for frame in contacts for actor in frame['actors']
          if 'supportIK' in actor['sourceContacts']]
    dice = [actor['sourceContacts']['diceRetarget'] for frame in contacts for actor in frame['actors']
            if 'diceRetarget' in actor['sourceContacts']]
    return {'frameCount': len(samples), 'actionInstances': len(renderer.actions),
            'maxRootOffsetX': max_offset,
            'maxRunRootOffsetX': max_run_offset,
            'maxHipDrop': max((record['hipDrop'] for record in ik), default=0),
            'maxRecoveryLift': max((max(record.get('recoveryLift', {}).values(), default=0) for record in ik), default=0),
            'maxLegJointChangeDegrees': max((record['maxJointChangeDegrees'] for record in ik), default=0),
            **({'maxDiceAnkleError': max(record['maxAnkleError'] for record in dice),
                'maxDiceAdditionalHipDrop': max(record['additionalHipDrop'] for record in dice)} if dice else {}),
            'width': samples[0]['output']['width'], 'height': samples[0]['output']['height']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text())
        result = render_manifest(manifest, args.out)
        (args.out / 'render-result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result))
    except Exception as error:
        print(json.dumps({'error': str(error)}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
