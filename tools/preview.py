"""Pose any compatible SVG rig; optional PNG previews use local rsvg-convert."""
import argparse
import copy
import json
import math
import re
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)


def interpolate_path(source, target, weight):
    """Interpolate matched SVG path commands; reject incompatible artwork."""
    token = r'[A-Za-z]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?'
    a, b = re.findall(token, source), re.findall(token, target)
    if len(a) != len(b) or any(x != y for x, y in zip(a, b) if x.isalpha() or y.isalpha()):
        raise ValueError('Hand morph paths must have matching command topology')
    return ' '.join(x if x.isalpha() else f'{float(x)+(float(y)-float(x))*weight:.8g}' for x,y in zip(a,b))


def load_character(directory):
    directory = Path(directory)
    rig = json.loads((directory / "rig.json").read_text())
    tree = ET.parse(directory / rig["source"])
    ids = [e.attrib["id"] for e in tree.iter() if "id" in e.attrib]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate SVG IDs")
    for joint in rig["joints"]:
        if joint not in ids:
            raise ValueError(f"Missing joint: {joint}")
    for expression in rig["expressions"]:
        if f"face-{expression}" not in ids:
            raise ValueError(f"Missing face: {expression}")
    return tree, rig


def apply_pose(tree, rig, pose):
    """Append local rotations after each joint's existing rest transform."""
    tree = copy.deepcopy(tree)
    nodes = {e.get("id"): e for e in tree.iter() if e.get("id")}
    for side, weight in pose.get('hand_curl', {}).items():
        if side not in ['left', 'right'] or not isinstance(weight, (int, float)) or not 0 <= weight <= 1:
            raise ValueError('Hand curl requires left/right weights between 0 and 1')
        for part in ['outline', 'lines']:
            artwork = nodes[f'hand-{part}-{side}']
            artwork.set('d', interpolate_path(artwork.get('d'), rig['hand_morph'][part], weight))
    for side, lengths in pose.get("arm_projection", {}).items():
        if side not in ["left", "right"] or set(lengths) != {"upper", "lower"}:
            raise ValueError("Arm projection requires left/right upper and lower scales")
        for segment, control in [("upper", "elbow"), ("lower", "wrist")]:
            factor = lengths[segment]
            if not isinstance(factor, (int, float)) or not 0.6 <= factor <= 1:
                raise ValueError("Arm projection scale must be between 0.6 and 1")
            joint = nodes[f"{control}-{side}"]
            match = re.fullmatch(r"translate\(0\s+([\d.]+)\)", joint.get("transform", ""))
            if not match:
                raise ValueError("Arm projection needs downward translation-only elbow/wrist rest joints")
            joint.set("transform", f"translate(0 {float(match[1])*factor})")
            names = [f"arm-{segment}-{side}"] + ([f"arm-cuff-{side}"] if segment == "lower" else [])
            for name in names:
                artwork = nodes[rig["motion_geometry"][name]]
                if artwork.get("transform"):
                    raise ValueError("Projected arm artwork requires identity rest transforms")
                artwork.set("transform", f"scale(1 {factor})")
    for joint, angle in pose.get("angles", {}).items():
        if joint not in rig["joints"]:
            raise ValueError(f"Unknown joint: {joint}")
        if not isinstance(angle, (int, float)) or not math.isfinite(angle):
            raise ValueError(f"Invalid angle for {joint}")
        node = nodes[joint]
        node.set("transform", f'{node.get("transform", "")} rotate({angle})'.strip())
    expression = pose.get("expression", "neutral")
    if expression not in rig["expressions"]:
        raise ValueError(f"Unknown expression: {expression}")
    for state in rig["expressions"]:
        nodes[f"face-{state}"].set("style", "display:inline" if state == expression else "display:none")
    apply_layers(tree, rig, pose.get("layers", {}))
    return tree


def apply_layers(tree, rig, layers):
    """Move selected forearms forward after evaluating the nested joint pose.

    The source hierarchy stays intact. Generated poses bake ancestor transforms
    into a foreground wrapper. Its outline includes the upper sleeve, but a
    forearm-alpha mask hides that context so no new elbow cap is outlined.
    """
    if set(layers) - {"front_forearms", "front_leg", "forearm_blend"}:
        raise ValueError("Unknown layer option")
    nodes = {e.get("id"): e for e in tree.iter() if e.get("id")}
    parents = {child: parent for parent in tree.iter() for child in parent}
    setup = rig.get("layering", {})
    forearms = layers.get("front_forearms", [])
    blends = layers.get("forearm_blend", {})
    if not isinstance(blends, dict):
            raise ValueError("forearm_blend must map elbow IDs to coverage weights")
    if set(forearms) & set(blends):
        raise ValueError("A forearm cannot use both hard foreground and depth blending")
    for name, weight in blends.items():
        if not isinstance(weight, (int, float)) or not 0 <= weight <= 1:
            raise ValueError("Forearm blend weight must be between 0 and 1")
        if name not in setup.get("forearms", {}):
            raise ValueError(f"Unsupported blended forearm: {name}")
    if not isinstance(forearms, list) or len(set(forearms)) != len(forearms):
        raise ValueError("front_forearms must be a list without duplicates")
    for name in [*forearms, *[name for name, weight in blends.items() if weight > 0]]:
        target_name = setup.get("forearms", {}).get(name)
        if not target_name:
            raise ValueError(f"Unsupported foreground forearm: {name}")
        node, target = nodes[name], nodes[target_name]
        ancestry = [node]
        ancestor = parents[node]
        while ancestor is not target:
            ancestry.append(ancestor)
            if ancestor not in parents:
                raise ValueError(f"{target_name} is not an ancestor of {name}")
            ancestor = parents[ancestor]
        transform = " ".join(e.get("transform", "") for e in reversed(ancestry[1:])).strip()
        parent = parents[node]
        wrapper = ET.Element(f"{{{SVG}}}g", {"id": f"{name}-foreground", "transform": transform})
        if "filter" in parent.attrib:
            # Outline the same union as the rear arm, then show only the forearm.
            # This preserves the join instead of outlining two separate caps.
            if len(ancestry) != 2:
                raise ValueError("Filtered foreground forearms require a direct shoulder parent")
            definitions = ET.SubElement(wrapper, f"{{{SVG}}}defs")
            mask_id, white_id = f"{name}-coverage", f"{name}-white"
            white = ET.SubElement(definitions, f"{{{SVG}}}filter", {"id": white_id})
            ET.SubElement(white, f"{{{SVG}}}feFlood", {"flood-color": "white", "result": "white"})
            ET.SubElement(white, f"{{{SVG}}}feComposite", {"in": "white", "in2": "SourceAlpha", "operator": "in"})
            mask = ET.SubElement(definitions, f"{{{SVG}}}mask", {
                "id": mask_id, "x": "-100%", "y": "-100%", "width": "300%", "height": "300%",
            })
            coverage = copy.deepcopy(node)
            for element in coverage.iter():
                element.attrib.pop("id", None)
            coverage.set("filter", f"url(#{white_id})")
            mask.append(coverage)
            wrapper.set("filter", parent.get("filter"))
            wrapper.set("mask", f"url(#{mask_id})")
            for sibling in parent:
                if sibling is node:
                    continue
                context = copy.deepcopy(sibling)
                for element in context.iter():
                    element.attrib.pop("id", None)
                wrapper.append(context)
        if name in blends:
            # Keep an opaque rear arm. Reveal the aligned foreground copy from
            # its outside edge, so torso lines never show through skin/cloth.
            # The rear copy preserves the silhouette outside the torso while
            # this clip changes which part occludes the body.
            definitions = wrapper.find(f"{{{SVG}}}defs")
            if definitions is None:
                definitions = ET.SubElement(wrapper, f"{{{SVG}}}defs")
            reveal_id = f"{name}-depth-reveal"
            reveal = ET.SubElement(definitions, f"{{{SVG}}}clipPath", {
                "id": reveal_id, "clipPathUnits": "objectBoundingBox",
            })
            weight = blends[name]
            ET.SubElement(reveal, f"{{{SVG}}}rect", {
                "x": str(0 if name.endswith("-right") else 1-weight),
                "y": "0", "width": str(weight), "height": "1",
            })
            wrapper.set("clip-path", f"url(#{reveal_id})")
            foreground = copy.deepcopy(node)
            for part in foreground.iter():
                if part.get("id"):
                    part.set("id", part.get("id") + "-front-copy")
            wrapper.append(foreground)
        else:
            parent.remove(node)
            wrapper.append(node)
        target.append(wrapper)
    front_leg = layers.get("front_leg")
    if front_leg is not None:
        legs = setup.get("legs", {})
        if front_leg not in legs.get("members", []):
            raise ValueError(f"Unsupported foreground leg: {front_leg}")
        parent = nodes[legs["parent"]]
        cover = nodes[legs["cover"]]
        leg = nodes[front_leg]
        parent.remove(leg)
        parent.insert(list(parent).index(cover), leg)


def review_sheet(paths, output):
    """Produce a self-contained SVG sheet without duplicate IDs or external files."""
    columns = min(4, len(paths))
    width, height = columns * 320, ((len(paths) + columns - 1) // columns) * 535
    sheet = ET.Element(f"{{{SVG}}}svg", {"width": str(width), "height": str(height), "viewBox": f"0 0 {width} {height}"})
    ET.SubElement(sheet, f"{{{SVG}}}rect", {"width": "100%", "height": "100%", "fill": "#f5f3ec"})
    for index, path in enumerate(paths):
        x, y = (index % columns) * 320, (index // columns) * 535
        ET.SubElement(sheet, f"{{{SVG}}}text", {"x": str(x + 12), "y": str(y + 22), "font-family": "sans-serif", "font-size": "16", "fill": "#252722"}).text = path.stem
        puppet = ET.parse(path).getroot()
        mapping = {e.get("id"): f"{path.stem}-{e.get('id')}" for e in puppet.iter() if e.get("id")}
        for element in puppet.iter():
            for key, value in list(element.attrib.items()):
                if key == "id":
                    element.set(key, mapping[value])
                elif key == "href" and value.startswith("#"):
                    element.set(key, "#" + mapping[value[1:]])
                elif key == "aria-labelledby":
                    element.set(key, " ".join(mapping[v] for v in value.split()))
                else:
                    for old, new in mapping.items():
                        value = value.replace(f"url(#{old})", f"url(#{new})")
                    element.set(key, value)
        puppet.attrib.update({"x": str(x), "y": str(y + 30), "width": "320", "height": "500"})
        sheet.append(puppet)
    ET.ElementTree(sheet).write(output, encoding="utf-8", xml_declaration=True)


def build_review(character, poses, output, png=False):
    if not poses:
        raise ValueError("At least one pose is required")
    tree, rig = load_character(character)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    converter = shutil.which("rsvg-convert") if png else None
    if png and not converter:
        raise RuntimeError("PNG export needs rsvg-convert; SVG output needs only Python.")
    paths = []
    for name, pose in poses.items():
        if not name or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in name):
            raise ValueError(f"Unsafe pose name: {name}")
        path = output / f"{name}.svg"
        paths.append(path)
        apply_pose(tree, rig, pose).write(path, encoding="utf-8", xml_declaration=True)
        if png:
            subprocess.run([converter, "--background-color", "#f5f3ec", "--output", str(path.with_suffix('.png')), str(path)], check=True)
        print(path)
    sheet = output / "review-sheet.svg"
    review_sheet(paths, sheet)
    if png:
        subprocess.run([converter, "--output", str(sheet.with_suffix('.png')), str(sheet)], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--character", type=Path, default=ROOT / "characters/hoodie")
    parser.add_argument("--poses", type=Path, default=ROOT / "poses/review.json")
    parser.add_argument("--out", type=Path, default=ROOT / "renders/v03")
    parser.add_argument("--png", action="store_true")
    args = parser.parse_args()
    build_review(args.character, json.loads(args.poses.read_text()), args.out, args.png)


if __name__ == "__main__":
    main()
