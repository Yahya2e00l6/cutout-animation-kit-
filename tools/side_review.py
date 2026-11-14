"""Render side-run construction poses, without changing the front-view action."""
import argparse
import copy
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.preview import ROOT, SVG, apply_pose, load_character, review_sheet


def world_point(tree, name, point):
    """Evaluate the translate/rotate chains used by this side-view rig."""
    nodes = {e.get('id'): e for e in tree.iter() if e.get('id')}
    parents = {child: parent for parent in tree.iter() for child in parent}
    node = nodes[name]
    x, y = point
    while node is not None:
        transform = node.get('transform', '')
        operations = re.findall(r'(translate|rotate)\(([^)]+)\)', transform)
        if re.sub(r'(translate|rotate)\([^)]+\)', '', transform).strip():
            raise ValueError(f'Unsupported side-rig transform: {transform}')
        for operation, arguments in reversed(operations):
            values = [float(v) for v in re.split(r'[ ,]+', arguments.strip())]
            if operation == 'translate' and len(values) == 2:
                x, y = x+values[0], y+values[1]
            elif operation == 'rotate' and len(values) == 1:
                angle = math.radians(values[0])
                x, y = x*math.cos(angle)-y*math.sin(angle), x*math.sin(angle)+y*math.cos(angle)
            else:
                raise ValueError(f'Unsupported side-rig transform: {transform}')
        node = parents.get(node)
    return x, y


def pose_character(tree, rig, key):
    posed = apply_pose(tree, rig, {'angles': key['angles']})
    nodes = {e.get('id'): e for e in posed.iter() if e.get('id')}
    root = nodes['root']
    root.set('transform', 'translate(300 0)')
    if 'support' in key:
        point = rig['review'][key['anchor']]
        _, sole_y = world_point(posed, f"ankle-{key['support']}", point)
        root_y = rig['review']['floor']-sole_y
    else:
        root_y = key['root_y']
    root.set('transform', f'translate(300 {root_y})')
    # Outline the posed union in vector space. Morphology filters in librsvg
    # drop portions of the curved sleeve edge at these joint rotations.
    # Paint all silhouette strokes first, then the original filled limb;
    # its fills cover internal joint seams without covering the outer stroke.
    parents = {child: parent for parent in posed.iter() for child in parent}
    for name in ['hip-left', 'hip-right', 'shoulder-left', 'shoulder-right']:
        limb = nodes[name]
        limb.attrib.pop('filter', None)
        outline = copy.deepcopy(limb)
        for node in outline.iter():
            node.attrib.pop('id', None)
            if node.tag == f'{{{SVG}}}path':
                if 'line' in node.get('class', '').split() or 'lace' in node.get('class', '').split():
                    node.set('style', 'display:none')
                else:
                    node.set('style', 'fill:#292b25;stroke:#292b25;stroke-width:3.6;stroke-linejoin:round;stroke-linecap:round')
        outline.set('id', f'{name}-silhouette')
        parent = parents[limb]
        parent.insert(list(parent).index(limb), outline)
    return posed


def main():
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--character', type=Path, default=ROOT/'characters/hoodie-side')
    parser.add_argument('--poses', type=Path, default=ROOT/'poses/side-run.json')
    parser.add_argument('--out', type=Path, default=ROOT/'renders/side-run/rig/v02')
    parser.add_argument('--png', action='store_true')
    args = parser.parse_args()
    if args.out.exists() and any(args.out.iterdir()):
        parser.error('Choose a new --out; existing previews will not be replaced')
    converter = shutil.which('rsvg-convert') if args.png else None
    if args.png and not converter:
        parser.error('--png requires rsvg-convert')
    tree, rig = load_character(args.character)
    if rig['type'] != 'humanoid-cutout-side':
        parser.error('This review requires a side-view rig')
    keys = json.loads(args.poses.read_text())['poses']
    if not keys:
        parser.error('At least one key pose is required')
    names = [key['name'] for key in keys]
    if len(set(names)) != len(names) or any(not re.fullmatch('[a-z0-9-]+', name) for name in names):
        parser.error('Pose names must be unique, lowercase letters/digits/hyphens')
    args.out.mkdir(parents=True, exist_ok=True)
    paths = []
    for key in keys:
        posed = pose_character(tree, rig, key)
        canvas = posed.getroot()
        line = ET.Element(f'{{{SVG}}}line', {'x1': '20', 'x2': '620', 'y1': str(rig['review']['floor']), 'y2': str(rig['review']['floor']), 'stroke': '#b8b9ae', 'stroke-width': '2'})
        canvas.insert(1, line)
        path = args.out/f"{key['name']}.svg"
        posed.write(path, encoding='utf-8', xml_declaration=True)
        paths.append(path)
        if args.png:
            subprocess.run([converter, '--background-color', '#f5f3ec', '--output', str(path.with_suffix('.png')), str(path)], check=True)
    sheet = args.out/'review-sheet.svg'
    review_sheet(paths, sheet)
    if args.png:
        subprocess.run([converter, '--output', str(sheet.with_suffix('.png')), str(sheet)], check=True)
    print(sheet)


if __name__ == '__main__':
    main()
