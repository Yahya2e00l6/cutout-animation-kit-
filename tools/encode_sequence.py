"""Run the installed FFmpeg skill sequence encoder with native PNG timestamps.

Preserves the skill's overwrite/probe safeguards; only supplies the concat
demuxer's per-file frame-rate hint so a 30 fps render isn't sampled at 25 Hz.
"""
import argparse
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--skill-dir", type=Path, default=Path.home() / ".config/opencode/skills/ffmpeg/scripts")
    options, args = parser.parse_known_args()
    if not (options.skill_dir / "sequence.py").is_file():
        raise FileNotFoundError("Install the ffmpeg skill or pass --skill-dir to its scripts directory")
    sys.path.insert(0, str(options.skill_dir))
    import sequence
    rate = float(args[args.index("--fps") + 1]) if "--fps" in args else 30.0
    original = sequence._concat_list_line
    sequence._concat_list_line = lambda path: original(path) + f"\noption framerate {rate:g}"
    sys.argv = [str(options.skill_dir / "sequence.py"), *args]
    return sequence.main()


if __name__ == "__main__":
    sys.exit(main())
