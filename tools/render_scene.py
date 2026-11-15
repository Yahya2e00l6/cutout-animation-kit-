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


class SceneRenderer:
    """Keep one action instance per clip; isolate SVG IDs/styles per image."""

    def __init__(self, loader=load_side_action):
        self.loader = loader
        self.actions = {}

    def frame(self, sample, number):
        width, height = sample['output']['width'], sample['output']['height']
        canvas = ET.Element(f'{{{SVG}}}svg', {
            'width': str(width), 'height': str(height),
            'viewBox': f'0 0 {width} {height}',
        })
        ET.SubElement(canvas, f'{{{SVG}}}rect', {
            'width': '100%', 'height': '100%', 'fill': sample['stage']['background'],
        })
        records = []
        for actor in sample['actors']:
            key = actor['clipIndex']
            signature = (actor['action'], actor['duration'], actor['speed'])
            if key not in self.actions:
                self.actions[key] = (signature, self.loader(
                    actor['action'], duration=actor['duration'], speed=actor['speed']))
            previous, action = self.actions[key]
            if previous != signature:
                raise ValueError('Clip settings changed inside the frame manifest')
            anchor = [action.config['width'] / 2, action.config['floor']]
            if anchor != actor['sourceAnchor']:
                raise ValueError('Saved action anchor changed since scene validation')
            values = actor['transform']
            if len(values) != 6 or not all(math.isfinite(n) for n in values):
                raise ValueError('Invalid sampled transform')
            svg, contact = action.frame(actor['localTime'], number, clean=True)
            data = 'data:image/svg+xml;base64,' + base64.b64encode(svg).decode('ascii')
            # An SVG image is a separate document: IDs and CSS never leak between actors.
            ET.SubElement(canvas, f'{{{SVG}}}image', {
                'width': str(action.config['width']), 'height': str(action.config['height']),
                'transform': 'matrix(' + ' '.join(str(n) for n in values) + ')',
                'href': data, '{http://www.w3.org/1999/xlink}href': data,
            })
            records.append({'actor': actor['id'], 'clipIndex': key,
                            'transform': values, 'sourceContacts': contact})
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
        'scope': 'Saved action contact metadata in source coordinates; not independent scene-space contact verification.',
        'frames': contacts,
    }, indent=2, allow_nan=False) + '\n')
    return {'frameCount': len(samples), 'actionInstances': len(renderer.actions),
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
