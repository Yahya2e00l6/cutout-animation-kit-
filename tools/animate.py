"""Render a front-view walk/jump/run test with reusable, proportion-aware motion."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import copy
import hashlib
import json
import math
from pathlib import Path
import sys
import time
import xml.etree.ElementTree as ET

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.motion import Humanoid, sample
from tools.actions import ACTION_NAMES, build_timeline
from tools.preview import ROOT, SVG, apply_pose, load_character


def raster(svg_bytes, width, height):
    import cairo
    import gi
    gi.require_version("Rsvg", "2.0")
    from gi.repository import Rsvg
    handle = Rsvg.Handle.new_from_data(svg_bytes)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    viewport = Rsvg.Rectangle()
    viewport.x, viewport.y, viewport.width, viewport.height = 0, 0, width, height
    handle.render_document(cairo.Context(surface), viewport)
    return surface


def calibrate_soles(tree):
    """Measure each shoe's lowest opaque outline pixel at 4x source resolution."""
    from PIL import Image
    import io
    nodes = {e.get("id"): e for e in tree.iter() if e.get("id")}
    import gi
    gi.require_version("Rsvg", "2.0")
    from gi.repository import Rsvg
    soles = {}
    for side in ["left", "right"]:
        fragment = ET.Element(f"{{{SVG}}}svg", {"width": "1", "height": "1"})
        fragment.append(copy.deepcopy(tree.getroot().find(f"{{{SVG}}}defs")))
        ankle = copy.deepcopy(nodes[f"ankle-{side}"])
        ankle.set("transform", "")
        fragment.append(ankle)
        handle = Rsvg.Handle.new_from_data(ET.tostring(fragment))
        viewport = Rsvg.Rectangle()
        viewport.x, viewport.y, viewport.width, viewport.height = 0, 0, 1, 1
        success, ink, _ = handle.get_geometry_for_layer(f"#ankle-{side}", viewport)
        if not success or ink.width <= 0 or ink.height <= 0:
            raise ValueError("Cannot measure shoe geometry")
        x0, y0 = math.floor(ink.x)-3, math.floor(ink.y)-3
        width, height = math.ceil(ink.x+ink.width)-x0+3, math.ceil(ink.y+ink.height)-y0+3
        if max(width, height)*4 > 4096:
            raise ValueError("Shoe calibration exceeds the supported 4096-pixel raster bound")
        fragment.attrib.update({"viewBox": f"{x0} {y0} {width} {height}", "width": str(width*4), "height": str(height*4)})
        surface = raster(ET.tostring(fragment), width*4, height*4)
        buffer = io.BytesIO()
        surface.write_to_png(buffer)
        alpha = Image.open(buffer).convert("RGBA").getchannel("A")
        opaque = alpha.point(lambda value: 255 if value >= 128 else 0)
        bounds = opaque.getbbox()
        if bounds is None:
            raise ValueError("Empty shoe during sole calibration")
        if bounds[0] <= 0 or bounds[1] <= 0 or bounds[2] >= width*4 or bounds[3] >= height*4:
            raise ValueError("Shoe calibration clipped; review the declared artwork")
        bottom = bounds[3] - 1
        pixels = [x for x in range(bounds[0], bounds[2]) if opaque.getpixel((x, bottom))]
        soles[side] = ((sum(pixels) / len(pixels) + 0.5) / 4 + x0, (bottom + 0.5) / 4 + y0)
    return soles


def element(parent, tag, **attributes):
    return ET.SubElement(parent, f"{{{SVG}}}{tag}", {key.replace('_', '-'): str(value) for key, value in attributes.items()})


def frame_svg(tree, rig, model, timeline, time_seconds, frame_number):
    state = sample(time_seconds, model, timeline)
    posed = apply_pose(tree, rig, state["pose"])
    nodes = {e.get("id"): e for e in posed.iter() if e.get("id")}
    scale, floor = timeline["scale"], timeline["floor"]
    actor = nodes["root"]
    actor.set("transform", f"translate({timeline['width'] / 2 + state['sway']*scale} {floor - state['height'] * scale}) scale({scale})")
    contacts = {}
    for side, leg in model.legs.items():
        upper_y, lower_y = state["lengths"][side]
        hip, knee, ankle = (nodes[f"{joint}-{side}"] for joint in ["hip", "knee", "ankle"])
        upper_path = nodes[model.geometry[f"upper-{side}"]]
        lower_path = nodes[model.geometry[f"lower-{side}"]]
        upper_path.set("transform", f"scale(1 {upper_y / leg['upper']})")
        lower_path.set("transform", f"scale(1 {lower_y / leg['lower']})")
        hip_angle, knee_angle = state["leg_angles"][side]
        hip.set("transform", f"translate({leg['hip'][0]} {leg['hip'][1]}) rotate({math.degrees(hip_angle)})")
        knee.set("transform", f"translate(0 {upper_y}) rotate({math.degrees(knee_angle)})")
        ankle.set("transform", f"translate(0 {lower_y}) rotate({-math.degrees(hip_angle+knee_angle)})")
        expected_y = floor - state["feet"][side]["lift"] * scale
        expected_x = timeline["width"]/2 + (leg["hip"][0] + leg["sole"][0])*scale
        actual_x = timeline["width"]/2 + (state["sway"]+leg["hip"][0]-upper_y*math.sin(hip_angle)-lower_y*math.sin(hip_angle+knee_angle)+leg["sole"][0])*scale
        actual_y = floor - state["height"] * scale + (leg["hip"][1] + upper_y*math.cos(hip_angle) + lower_y*math.cos(hip_angle+knee_angle) + leg["sole"][1]) * scale
        contacts[side] = {
            "planted": state["feet"][side]["contact"],
            "x": actual_x, "target_x": expected_x,
            "y": actual_y, "target_y": expected_y,
            "error_px": math.hypot(actual_x-expected_x, actual_y-expected_y),
        }
    canvas = ET.Element(f"{{{SVG}}}svg", {"width": str(timeline["width"]), "height": str(timeline["height"]), "viewBox": f"0 0 {timeline['width']} {timeline['height']}"})
    canvas.append(copy.deepcopy(posed.getroot().find(f"{{{SVG}}}defs")))
    element(canvas, "rect", width="100%", height="100%", fill="#f5f3ec")
    element(canvas, "rect", x=0, y=floor, width=timeline["width"], height=timeline["height"] - floor, fill="#e1e5d9")
    element(canvas, "line", x1=60, y1=floor, x2=timeline["width"] - 60, y2=floor, stroke="#7a8873", stroke_width=2)
    clearance = min(foot["lift"] for foot in state["feet"].values())
    element(canvas, "ellipse", cx=timeline["width"] / 2+state["sway"]*scale, cy=floor + 3, rx=max(30, 72 - clearance * 0.2), ry=7, fill="#87947c", opacity=max(0.12, 0.3 - clearance * 0.001))
    title = element(canvas, "text", x=54, y=42, fill="#29392f", font_family="sans-serif", font_size=25, font_weight="bold")
    title.text = "CUTOUT MOTION TEST / POSE REVISION"
    subtitle = element(canvas, "text", x=54, y=69, fill="#657165", font_family="sans-serif", font_size=15)
    subtitle.text = "FRONT VIEW  ·  IN-PLACE WALK / JUMP / RUN  ·  SILENT PREVIEW"
    label = element(canvas, "text", x=80, y=270, fill="#29392f", font_family="sans-serif", font_size=40, font_weight="bold")
    label.text = state["action"].upper()
    note = element(canvas, "text", x=82, y=302, fill="#657165", font_family="sans-serif", font_size=15)
    note.text = "Feet locked during stance" if state["action"] in ["walk", "run"] else "Takeoff / flight / recovery" if state["action"] == "jump" else "Ready / settle"
    canvas.append(actor)
    timecode = element(canvas, "text", x=timeline["width"] - 290, y=timeline["height"] - 24, fill="#465647", font_family="monospace", font_size=15)
    timecode.text = f"{time_seconds:05.2f}s   frame {frame_number:03d} / {timeline['fps']} fps"
    return ET.tostring(canvas, encoding="utf-8"), {"frame": frame_number, "seconds": time_seconds, "action": state["action"], "root_height": state["height"], "root_sway": state["sway"], "contacts": contacts}


def render_frame(job):
    data, width, height, output = job
    raster(data, width, height).write_to_png(output)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--character", type=Path, default=ROOT / "characters/hoodie")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--timeline", type=Path, help="Timeline JSON; defaults to motions/walk-jump-run.json")
    source.add_argument("--action", choices=ACTION_NAMES, help="Render a reusable approved action")
    parser.add_argument("--duration", type=float, help="Action duration in seconds (whole frames)")
    parser.add_argument("--speed", type=float, help="Action cadence multiplier; default 1")
    parser.add_argument("--out", type=Path, default=ROOT / "renders/motion-test/v06")
    parser.add_argument("--jobs", type=int, default=2, choices=range(1, 5))
    parser.add_argument("--keyframes", action="store_true", help="Render review frames first, not the full sequence")
    args = parser.parse_args()
    if args.action is None and (args.duration is not None or args.speed is not None):
        parser.error('--duration and --speed require --action')
    if args.action:
        try:
            timeline = build_timeline(args.action, args.duration, args.speed if args.speed is not None else 1.0)
        except ValueError as error:
            parser.error(str(error))
    else:
        timeline = json.loads((args.timeline or ROOT/'motions/walk-jump-run.json').read_text())
    started = time.monotonic()
    tree, rig = load_character(args.character)
    soles = calibrate_soles(tree)
    model = Humanoid(tree, rig, soles)
    duration = sum(segment["duration"] for segment in timeline["segments"])
    count = round(duration * timeline["fps"])
    if abs(count / timeline["fps"] - duration) > 1e-8:
        raise ValueError("Duration must be a whole number of frames")
    directory = args.out / ("keyframes" if args.keyframes else "frames")
    report_path = args.out / ("keyframe-validation.json" if args.keyframes else "motion-validation.json")
    if report_path.exists():
        parser.error(f'Output report already exists: {report_path}; choose a new --out')
    directory.mkdir(parents=True, exist_ok=True)
    if any(directory.iterdir()):
        raise FileExistsError(f"Output is not empty: {directory}; choose a new --out")
    indices = sorted({i for i in [0, 24, 40, 60, 84, 120, 135, 144, 156, 195, 216, 240, 267, count - 1] if i < count}) if args.keyframes else range(count)
    jobs, records = [], []
    for frame in indices:
        data, record = frame_svg(tree, rig, model, timeline, frame / timeline["fps"], frame)
        target = directory / f"frame_{frame:04d}.png"
        jobs.append((data, timeline["width"], timeline["height"], str(target)))
        records.append(record)
        if args.keyframes:
            target.with_suffix(".svg").write_bytes(data)
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        for index, _ in enumerate(pool.map(render_frame, jobs, chunksize=2)):
            if (index + 1) % 30 == 0 or index + 1 == len(jobs):
                print(f"Rendered {index + 1}/{len(jobs)}", flush=True)
    max_error = max(foot["error_px"] for record in records for foot in record["contacts"].values())
    max_drift = 0.0
    for previous, current in zip(records, records[1:]):
        if current["frame"] != previous["frame"] + 1:
            continue
        for side in model.legs:
            a, b = previous["contacts"][side], current["contacts"][side]
            if a["planted"] and b["planted"]:
                max_drift = max(max_drift, math_distance(a, b))
    report = {"duration": duration, "fps": timeline["fps"], "planned_frames": count, "rendered_frames": len(records),
              "resolution": [timeline["width"], timeline["height"]], "measured_soles": soles,
              "max_contact_error_px": max_error, "max_planted_drift_px": max_drift,
              "render_seconds": time.monotonic() - started,
              "source_sha256": hashlib.sha256((args.character / rig["source"]).read_bytes()).hexdigest(),
              "implementation_sha256": {name: hashlib.sha256((ROOT/'tools'/name).read_bytes()).hexdigest() for name in ['motion.py', 'animate.py', 'preview.py']},
              "timeline": timeline, "frames": records,
              "limitations": ["Front-view in-place gait combines limited articulation with axial foreshortening; no new side-view drawings.",
                               "Contacts checked in the 2D image plane, not proof of convincing acting or real-world depth travel.",
                               "Shoe contact calibration is raster-based at 4x resolution."]}
    with report_path.open('x') as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    if max_error > 0.5 or max_drift > 0.5:
        raise ValueError(f"Contact check failed: error={max_error}, drift={max_drift}")
    print(json.dumps({key: value for key, value in report.items() if key not in ["frames", "timeline"]}, indent=2))


def math_distance(a, b):
    return ((a["x"] - b["x"])**2 + (a["y"] - b["y"])**2)**0.5


if __name__ == "__main__":
    main()
