import json
import math
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from tools.preview import ROOT, apply_pose, load_character, review_sheet


def nodes_in(tree):
    return {e.get("id"): e for e in tree.iter() if e.get("id")}


def world_point(tree, name, point=(0, 0)):
    """Independent point evaluator for this rig's translate/rotate transforms."""
    nodes = nodes_in(tree)
    parents = {child: parent for parent in tree.iter() for child in parent}
    node = nodes[name]
    x, y = point
    while node is not None:
        transforms = re.findall(r"(translate|rotate)\(([^)]+)\)", node.get("transform", ""))
        for operation, arguments in reversed(transforms):
            values = [float(v) for v in re.split(r"[ ,]+", arguments.strip())]
            if operation == "translate":
                x += values[0]
                y += values[1] if len(values) > 1 else 0
            else:
                angle = math.radians(values[0])
                x, y = x * math.cos(angle) - y * math.sin(angle), x * math.sin(angle) + y * math.cos(angle)
        node = parents.get(node)
    return x, y


class PuppetTests(unittest.TestCase):
    def setUp(self):
        self.tree, self.rig = load_character(ROOT / "characters/hoodie")

    def test_vector_only(self):
        for element in self.tree.iter():
            self.assertNotIn(element.tag.split('}')[-1], ("image", "script", "foreignObject"))

    def test_chains_are_nested(self):
        nodes = {e.get("id"): e for e in self.tree.iter() if e.get("id")}
        for chain in self.rig["chains"].values():
            for parent, child in zip(chain, chain[1:]):
                self.assertIn(nodes[child], list(nodes[parent].iter()))

    def test_all_review_poses(self):
        original = ET.tostring(self.tree.getroot())
        poses = json.loads((ROOT / "poses/review.json").read_text())
        poses.update(json.loads((ROOT / "poses/checks.json").read_text()))
        for pose in poses.values():
            posed = apply_pose(self.tree, self.rig, pose)
            nodes = {e.get("id"): e for e in posed.iter() if e.get("id")}
            visible = [s for s in self.rig["expressions"] if nodes[f"face-{s}"].get("style") == "display:inline"]
            self.assertEqual(visible, [pose.get("expression", "neutral")])
        self.assertEqual(original, ET.tostring(self.tree.getroot()))

    def test_pelvis_parents_both_legs_and_changes_their_positions(self):
        nodes = nodes_in(self.tree)
        for side in ["left", "right"]:
            self.assertIn(nodes[f"hip-{side}"], list(nodes["pelvis"]))
        posed = apply_pose(self.tree, self.rig, {"angles": {"pelvis": 12}})
        for side in ["left", "right"]:
            self.assertNotEqual(world_point(self.tree, f"ankle-{side}"), world_point(posed, f"ankle-{side}"))
        self.assertEqual(world_point(self.tree, "head"), world_point(posed, "head"))

    def test_head_rotation_pivot_is_at_neck_attachment(self):
        self.assertEqual(world_point(self.tree, "head"), (320, 292))
        self.assertEqual(world_point(self.tree, "head-art"), (320, 214))
        for angle in [-20, 20]:
            posed = apply_pose(self.tree, self.rig, {"angles": {"head": angle}})
            self.assertEqual(world_point(posed, "head"), (320, 292))
            self.assertNotEqual(world_point(posed, "head-art"), (320, 214))

    def test_neutral_and_talk_share_identical_upper_face(self):
        nodes = nodes_in(self.tree)
        for name in ["neutral", "talk"]:
            uses = list(nodes[f"face-{name}"].iter("{http://www.w3.org/2000/svg}use"))
            self.assertEqual([e.get("href") for e in uses], ["#neutral-features"])

    def test_forearm_depth_change_preserves_joint_and_grip_positions(self):
        for side in ["left", "right"]:
            for angle in [0, 30, 60, 90, 120]:
                pose = {"angles": {"torso": 7, f"shoulder-{side}": -15, f"elbow-{side}": angle, f"wrist-{side}": 12}}
                behind = apply_pose(self.tree, self.rig, pose)
                pose["layers"] = {"front_forearms": [f"elbow-{side}"]}
                front = apply_pose(self.tree, self.rig, pose)
                for name, point in [(f"elbow-{side}", (0, 0)), (f"wrist-{side}", (0, 45))]:
                    before, after = world_point(behind, name, point), world_point(front, name, point)
                    for a, b in zip(before, after):
                        self.assertAlmostEqual(a, b, places=8)
                nodes = nodes_in(front)
                foreground = nodes[f"elbow-{side}-foreground"]
                self.assertIs(list(nodes["torso"])[-1], foreground)
                self.assertIn(nodes[f"elbow-{side}"], list(foreground))

    def test_foreground_union_has_mask_and_unique_resolvable_references(self):
        posed = apply_pose(self.tree, self.rig, {
            "layers": {"front_forearms": ["elbow-left", "elbow-right"]}
        })
        ids = [e.get("id") for e in posed.iter() if e.get("id")]
        self.assertEqual(len(ids), len(set(ids)))
        nodes = nodes_in(posed)
        for side in ["left", "right"]:
            foreground = nodes[f"elbow-{side}-foreground"]
            self.assertEqual(foreground.get("filter"), "url(#limb-outline)")
            self.assertEqual(foreground.get("mask"), f"url(#elbow-{side}-coverage)")
            # Both sleeve segments participate in the outline; only forearm
            # coverage is visible in this foreground layer.
            self.assertTrue(any(e.tag == f"{{http://www.w3.org/2000/svg}}path" for e in foreground))
        for element in posed.iter():
            for value in element.attrib.values():
                for reference in re.findall(r"url\(#([^)]+)\)", value):
                    self.assertIn(reference, ids)

    def test_leg_depth_change_preserves_poses_and_cover(self):
        pose = {"angles": {"pelvis": 9, "hip-left": 18, "knee-left": -12}}
        behind = apply_pose(self.tree, self.rig, pose)
        for side in ["left", "right"]:
            pose["layers"] = {"front_leg": f"hip-{side}"}
            front = apply_pose(self.tree, self.rig, pose)
            nodes = nodes_in(front)
            self.assertEqual([e.get("id") for e in list(nodes["pelvis"])[-2:]], [f"hip-{side}", "pelvis-art"])
            for joint in ["ankle-left", "ankle-right"]:
                self.assertEqual(world_point(behind, joint), world_point(front, joint))

    def test_invalid_layer_settings_rejected(self):
        for layers in [{"typo": []}, {"front_forearms": ["head"]}, {"front_forearms": ["elbow-left", "elbow-left"]}, {"front_leg": "neck"}]:
            with self.assertRaises(ValueError):
                apply_pose(self.tree, self.rig, {"layers": layers})

    def test_sheet_has_unique_ids_and_resolvable_local_references(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = []
            for name in ["a", "b"]:
                path = Path(temp) / f"{name}.svg"
                tree = self.tree if name == "a" else apply_pose(self.tree, self.rig, {
                    "layers": {"front_forearms": ["elbow-left", "elbow-right"]}
                })
                tree.write(path)
                paths.append(path)
            output = Path(temp) / "sheet.svg"
            review_sheet(paths, output)
            sheet = ET.parse(output)
            ids = [e.get("id") for e in sheet.iter() if e.get("id")]
            self.assertEqual(len(ids), len(set(ids)))
            for element in sheet.iter():
                for key, value in element.attrib.items():
                    if key == "href":
                        self.assertIn(value[1:], ids)
                    for reference in re.findall(r"url\(#([^)]+)\)", value):
                        self.assertIn(reference, ids)

    def test_unknown_joint_rejected(self):
        with self.assertRaises(ValueError):
            apply_pose(self.tree, self.rig, {"angles": {"typo": 30}})

    def test_invalid_angle_rejected(self):
        with self.assertRaises(ValueError):
            apply_pose(self.tree, self.rig, {"angles": {"head": float('nan')}})

    def test_unknown_expression_rejected(self):
        with self.assertRaises(ValueError):
            apply_pose(self.tree, self.rig, {"expression": "missing"})


if __name__ == "__main__":
    unittest.main()
