"""Render sampled joint ranges for visual inspection, not an artistic pass/fail."""
import argparse
from pathlib import Path
from preview import ROOT, build_review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--character", type=Path, default=ROOT / "characters/hoodie")
    parser.add_argument("--out", type=Path, default=ROOT / "renders/v03/sweeps")
    parser.add_argument("--png", action="store_true")
    args = parser.parse_args()
    poses = {}
    for side, direction in [("left", -1), ("right", 1)]:
        for angle in [0, 30, 60, 90, 120]:
            poses[f"elbow-{side}-{angle:03}"] = {
                "angles": {f"elbow-{side}": direction * angle}
            }
            poses[f"elbow-{side}-{angle:03}-front"] = {
                "angles": {f"elbow-{side}": direction * angle},
                "layers": {"front_forearms": [f"elbow-{side}"]},
            }
        for angle in [0, 25, 50, 75, 100]:
            poses[f"knee-{side}-{angle:03}"] = {
                "angles": {f"knee-{side}": -direction * angle}
            }
    for angle in [-20, -10, 0, 10, 20]:
        label = f"minus{abs(angle):02}" if angle < 0 else f"plus{angle:02}"
        poses[f"head-{label}"] = {"angles": {"head": angle}}
    build_review(args.character, poses, args.out, args.png)


if __name__ == "__main__":
    main()
