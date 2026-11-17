"""Data-only setup and playback for separated, flat side-view humanoid SVGs.

No character-specific IDs, paths, controllers or dimensions are built in.
Source drawing is read-only; each part receives a rigid world-space transform.
"""
import copy
import hashlib
import io
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from tools.animate import raster
from tools.preview import SVG
from tools.run_profile import RunProfile, finite


PARTS = ('torso', 'head') + tuple(f'{part}-{side}' for side in ('left', 'right')
                                 for part in ('upper-arm', 'forearm', 'hand', 'thigh', 'shin', 'foot'))
JOINTS = ('root', 'neck') + tuple(f'{joint}-{side}' for side in ('left', 'right')
                                for joint in ('shoulder', 'elbow', 'wrist', 'hip', 'knee', 'ankle'))
ENDS = {'upper-arm': ('shoulder', 'elbow'), 'forearm': ('elbow', 'wrist'),
        'thigh': ('hip', 'knee'), 'shin': ('knee', 'ankle')}
ANCHORS = {'torso': 'root', 'head': 'neck'} | {
    f'{part}-{side}': f'{joint}-{side}' for side in ('left', 'right')
    for part, joint in [('upper-arm', 'shoulder'), ('forearm', 'elbow'), ('hand', 'wrist'),
                        ('thigh', 'hip'), ('shin', 'knee'), ('foot', 'ankle')]}


def rotate(point, degrees):
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    x, y = point
    return x*c-y*s, x*s+y*c


def add(a, b): return tuple(x+y for x, y in zip(a, b))
def sub(a, b): return tuple(x-y for x, y in zip(a, b))
def down(length, angle): return rotate((0, length), angle)
def direction(a, b): return math.degrees(math.atan2(b[1]-a[1], b[0]-a[0]))


def read_svg(path):
    data = Path(path).read_bytes()
    if len(data) > 8*1024*1024 or re.search(br'<!\s*(DOCTYPE|ENTITY)', data, re.I):
        raise ValueError('SVG must be under 8 MiB and contain no DTD/entities')
    root = ET.fromstring(data)
    if root.tag != f'{{{SVG}}}svg':
        raise ValueError('Expected an SVG document')
    box = [float(v) for v in re.split(r'[ ,]+', root.get('viewBox', '').strip()) if v]
    if (len(box) != 4 or not all(finite(v) for v in box) or min(box[2:]) < 2 or max(box[2:]) > 4096):
        raise ValueError('SVG needs a finite viewBox, between 2 and 4096 units per side')
    forbidden = {'script', 'foreignObject', 'image', 'use', 'a', 'animate', 'animateTransform', 'set'}
    ids = set()
    for node in root.iter():
        tag = node.tag.split('}')[-1]
        if tag in forbidden or 'transform' in root.attrib:
            raise ValueError('V1 needs static vector groups; no scripts, images, use, animation or root transforms')
        ident = node.get('id')
        if ident:
            if ident in ids:
                raise ValueError(f'Duplicate SVG ID: {ident}')
            ids.add(ident)
        strings = list(node.attrib.values())+([node.text] if tag == 'style' and node.text else [])
        if any(k.split('}')[-1].lower().startswith('on') or k.split('}')[-1] == 'base' for k in node.attrib):
            raise ValueError('SVG event handlers and base-URL overrides are unsupported')
        if any('@' in text or '\\' in text for text in strings):
            raise ValueError('CSS imports/at-rules are unsupported')
        if tag == 'style' and node.text:
            for selector in re.findall(r'([^{}]+)\{', node.text):
                if any(token in selector for token in ('>', '+', '~', ':', '[')):
                    raise ValueError('V1 supports simple class/ID styles, not structural CSS')
        for text in strings:
            for url in re.findall(r'url\(([^)]+)\)', text, re.I):
                if not re.fullmatch(r'''["']?#[\w:.-]+["']?''', url.strip()):
                    raise ValueError('External SVG/CSS references are unsupported')
        for key, value in node.attrib.items():
            if key.split('}')[-1] == 'href' and not value.startswith('#'):
                raise ValueError('External references are unsupported')
    parts = {n.get('id'): n for n in root if n.tag == f'{{{SVG}}}g' and n.get('id')}
    return data, root, box, parts


def validate_setup(setup, root, box, groups):
    if (not isinstance(setup, dict) or type(setup.get('version')) is not int
            or setup.get('version') != 1 or setup.get('view') != 'side-right'):
        raise ValueError('V1 setup supports version 1 / side-right only')
    parts, joints, layers = setup.get('parts', {}), setup.get('joints', {}), setup.get('layers', [])
    if not isinstance(parts, dict) or not isinstance(joints, dict) or not isinstance(layers, list):
        raise ValueError('Setup needs parts/joints objects and a layers array')
    if set(parts) != set(PARTS) or not all(isinstance(v, str) and v in groups for v in parts.values()):
        raise ValueError('Map every required body part to a direct child SVG group ID')
    if len(set(parts.values())) != len(PARTS) or set(parts.values()) != set(groups):
        raise ValueError('Every source part group must be mapped exactly once')
    if sum(n.tag == f'{{{SVG}}}g' for n in root) != len(groups):
        raise ValueError('All top-level drawing groups need unique IDs')
    if any(n.tag.split('}')[-1] not in ('g', 'defs', 'style', 'title', 'desc', 'metadata') for n in root):
        raise ValueError('Put all visible artwork inside the mapped top-level groups')
    if set(joints) != set(JOINTS):
        raise ValueError('Mark all required joints, in SVG viewBox coordinates')
    for name, point in joints.items():
        if (not isinstance(point, list) or len(point) != 2 or not all(finite(v) for v in point)
                or not box[0] <= point[0] <= box[0]+box[2] or not box[1] <= point[1] <= box[1]+box[3]):
            raise ValueError(f'Invalid or missing pivot: {name}')
    for side in ('left', 'right'):
        for a, b in ENDS.values():
            if math.dist(joints[f'{a}-{side}'], joints[f'{b}-{side}']) < 1:
                raise ValueError('Bones must be at least one SVG unit long')
    if len(layers) != len(PARTS) or not all(isinstance(v, str) for v in layers) or set(layers) != set(PARTS):
        raise ValueError('Layer order must contain every body role exactly once, back to front')
    return setup


def template(path):
    _, root, box, groups = read_svg(path)
    return {'version': 1, 'view': 'side-right',
            'parts': {name: None for name in PARTS},
            'joints': {name: None for name in JOINTS}, 'layers': list(PARTS),
            'availableGroups': list(groups),
            'instructions': 'Replace nulls with SVG group IDs and [x,y] pivots; reorder layers back to front. No automatic anatomy detection.'}


def build(svg, mapping, out):
    if out.exists():
        raise FileExistsError('Choose a new character package directory')
    data, root, box, groups = read_svg(svg)
    setup = json.loads(Path(mapping).read_text())
    validate_setup(setup, root, box, groups)
    rig = {key: setup[key] for key in ('version', 'view', 'parts', 'joints', 'layers')}
    rig.update(type='svg-side-rig', source='character.svg', sha256=hashlib.sha256(data).hexdigest())
    out.mkdir(parents=True)
    (out/'character.svg').write_bytes(data)
    (out/'rig.json').write_text(json.dumps(rig, indent=2, allow_nan=False)+'\n')


class SvgRig:
    def __init__(self, path):
        path = Path(path)
        self.rig = json.loads(path.read_text())
        if not isinstance(self.rig, dict) or self.rig.get('type') != 'svg-side-rig' or self.rig.get('source') != 'character.svg':
            raise ValueError('Expected a packaged svg-side-rig')
        if set(self.rig) != {'version', 'type', 'view', 'source', 'sha256', 'parts', 'joints', 'layers'}:
            raise ValueError('Rig has missing or unsupported fields')
        data, self.root, self.box, self.groups = read_svg(path.parent/'character.svg')
        if hashlib.sha256(data).hexdigest() != self.rig.get('sha256'):
            raise ValueError('Artwork changed since setup; rebuild the package')
        validate_setup(self.rig, self.root, self.box, self.groups)
        self.joints = self.rig['joints']
        self.lengths = {f'{part}-{side}': math.dist(self.joints[f'{a}-{side}'], self.joints[f'{b}-{side}'])
                        for side in ('left', 'right') for part, (a, b) in ENDS.items()}
        self.leg_length = sum(self.lengths[f'{p}-{s}'] for s in ('left', 'right') for p in ('thigh', 'shin'))/2
        self.shoe_cache = {}
        self.shoe_radii = {}

    def skeleton(self, sample):
        angles, rest = sample['angles'], self.joints
        root = tuple(rest['root'])
        points = {'root': root, 'neck': add(root, rotate(sub(rest['neck'], root), angles['torso']))}
        rotations = {'torso': angles['torso'], 'head': angles['torso']+angles['head']}
        for side in ('left', 'right'):
            hip = tuple(rest[f'hip-{side}'])
            shoulder = add(root, rotate(sub(rest[f'shoulder-{side}'], root), angles['torso']))
            points[f'hip-{side}'], points[f'shoulder-{side}'] = hip, shoulder
            for chain, first, second, third in [('leg', 'hip', 'knee', 'ankle'), ('arm', 'shoulder', 'elbow', 'wrist')]:
                upper, lower = ('thigh', 'shin') if chain == 'leg' else ('upper-arm', 'forearm')
                a = angles[f'{first}-{side}']+(angles['torso'] if chain == 'arm' else 0)
                b = a+angles[f'{second}-{side}']
                points[f'{second}-{side}'] = add(points[f'{first}-{side}'], down(self.lengths[f'{upper}-{side}'], a))
                points[f'{third}-{side}'] = add(points[f'{second}-{side}'], down(self.lengths[f'{lower}-{side}'], b))
                for part, p, q in [(upper, first, second), (lower, second, third)]:
                    rotations[f'{part}-{side}'] = direction(points[f'{p}-{side}'], points[f'{q}-{side}'])-direction(rest[f'{p}-{side}'], rest[f'{q}-{side}'])
                rotations[f'foot-{side}' if chain == 'leg' else f'hand-{side}'] = a+angles[f'knee-{side}']+angles[f'ankle-{side}'] if chain == 'leg' else rotations[f'forearm-{side}']
        return points, rotations

    def part(self, role, pivot, angle):
        x, y = self.joints[ANCHORS[role]]
        wrapper = ET.Element(f'{{{SVG}}}g', transform=f'translate({pivot[0]} {pivot[1]}) rotate({angle}) translate({-x} {-y})')
        wrapper.append(copy.deepcopy(self.groups[self.rig['parts'][role]]))
        return wrapper

    def canvas(self):
        root = copy.deepcopy(self.root)
        for child in list(root):
            if child.tag == f'{{{SVG}}}g':
                root.remove(child)
        return root

    def shoe_bottom(self, side, angle):
        key = (side, round(angle, 9))
        if key not in self.shoe_cache:
            from PIL import Image
            px, py = self.joints[f'ankle-{side}']
            # First measure the native foot to choose a tight rotation-safe crop.
            if side not in self.shoe_radii:
                root = self.canvas()
                root.append(self.part(f'foot-{side}', (px, py), 0))
                buffer = io.BytesIO(); raster(ET.tostring(root), round(self.box[2]), round(self.box[3])).write_to_png(buffer)
                bounds = Image.open(buffer).getchannel('A').getbbox()
                if not bounds or bounds[0] == 0 or bounds[1] == 0 or bounds[2] >= self.box[2] or bounds[3] >= self.box[3]:
                    raise ValueError('Native shoe is empty/clipped; leave margin around SVG artwork')
                x0, y0, x1, y1 = bounds
                corners = [(x+self.box[0], y+self.box[1]) for x in (x0, x1) for y in (y0, y1)]
                self.shoe_radii[side] = math.ceil(max(math.dist((px, py), p) for p in corners))+3
            radius = self.shoe_radii[side]
            size = math.ceil(radius*8)
            if size > 2048:
                raise ValueError('Shoe calibration exceeds 2048 pixels; use smaller SVG coordinates')
            root = self.canvas()
            root.attrib.update(viewBox=f'{px-radius} {py-radius} {2*radius} {2*radius}', width=str(size), height=str(size))
            root.append(self.part(f'foot-{side}', (px, py), angle))
            buffer = io.BytesIO(); raster(ET.tostring(root), size, size).write_to_png(buffer)
            bounds = Image.open(buffer).getchannel('A').point(lambda n: 255 if n >= 128 else 0).getbbox()
            if not bounds or bounds[3] >= size:
                raise ValueError('Rotated shoe calibration clipped or empty')
            self.shoe_cache[key] = -radius+bounds[3]/4
        return self.shoe_cache[key]

    def frame(self, profile: RunProfile, seconds, speed=1):
        sample = profile.sample(seconds, speed)
        points, rotations = self.skeleton(sample)
        bottom = max(points[f'ankle-{s}'][1]+self.shoe_bottom(s, rotations[f'foot-{s}']) for s in ('left', 'right'))
        floor = self.box[1]+self.box[3]-.06*self.box[3]
        dy = floor-bottom-sample['clearance']*self.leg_length
        root = self.canvas()
        layer = ET.SubElement(root, f'{{{SVG}}}g', transform=f'translate(0 {dy})')
        for role in self.rig['layers']:
            layer.append(self.part(role, points[ANCHORS[role]], rotations[role]))
        return ET.tostring(root), {'phase': sample['phase'], 'joints': {k: [v[0], v[1]+dy] for k, v in points.items()},
                                    'groundShift': dy, 'clearance': sample['clearance']*self.leg_length,
                                    'scope': 'Measured vertical shoe grounding; no world-space planted-foot or horizontal locking guarantee.'}
