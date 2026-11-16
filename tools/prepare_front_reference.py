"""Extract one centered, heading-aligned CMU stride for the separate front study."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from tools.bvh_reference import BVH


JOINTS = ('Hips', 'LeftUpLeg', 'LeftLeg', 'LeftFoot', 'LeftToeBase', 'LeftToeBase/end',
          'RightUpLeg', 'RightLeg', 'RightFoot', 'RightToeBase', 'RightToeBase/end',
          'Neck', 'Head', 'LeftArm', 'LeftForeArm', 'LeftHand',
          'RightArm', 'RightForeArm', 'RightHand')


def extract(path, start=6, end=100, count=48):
    data = path.read_bytes()
    bvh = BVH(data.decode())
    nominal_fps = round(1/bvh.frame_time)
    if nominal_fps <= 0 or abs(bvh.frame_time*nominal_fps-1) > 1e-4:
        raise ValueError('Reference needs a declared nominal capture rate')
    if not 1 <= start < end < len(bvh.frames) or count < 8:
        raise ValueError('Choose a complete non-T-pose cycle and at least eight samples')
    frames = [bvh.frame(i) for i in range(start, end+1)]
    first, last = frames[0]['Hips'], frames[-1]['Hips']
    dx, dz = last[0]-first[0], last[2]-first[2]
    length = math.hypot(dx, dz)
    if length < 1:
        raise ValueError('Reference must contain measurable forward travel')
    fx, fz = dx/length, dz/length
    def centered(frame, index):
        root = frame['Hips']
        u = index/(end-start)
        # Keep the recorded bob and lateral residual; remove locomotor travel.
        root_x = root[0]-(first[0]+dx*u)
        return {'height': root[1], 'sway': root_x*fz,
                'joints': {name: [
                    (frame[name][0]-root[0])*fz-(frame[name][2]-root[2])*fx,
                    frame[name][1]-root[1],
                    (frame[name][0]-root[0])*fx+(frame[name][2]-root[2])*fz,
                ] for name in JOINTS}}
    centered_frames = [centered(frame, i) for i, frame in enumerate(frames)]
    def flatten(frame):
        return [frame['height'], frame['sway']]+[n for name in JOINTS for n in frame['joints'][name]]
    values = [flatten(frame) for frame in centered_frames]
    delta = [b-a for a, b in zip(values[0], values[-1])]
    samples = []
    for index in range(count):
        u = index/count
        t = u*(end-start); i = int(t); f = t-i
        row = [a+(b-a)*f-(3*u*u-2*u*u*u)*d
               for a, b, d in zip(values[i], values[i+1], delta)]
        samples.append({'height': row[0], 'sway': row[1],
                        'joints': {name: row[2+j*3:5+j*3] for j, name in enumerate(JOINTS)}})
    return {
        'version': 1, 'status': 'unapproved motion study',
        'source': {'dataset': 'CMU Graphics Lab Motion Capture Database',
                   'motion': path.stem,
                   'url': f'https://raw.githubusercontent.com/konyshevgmbh/cmu-mocap/master/data/{int(path.stem.split("_")[0]):03d}/{path.name}',
                   'sha256': hashlib.sha256(data).hexdigest(),
                   'frames': [start, end], 'frameTime': bvh.frame_time, 'nominalFps': nominal_fps,
                   'conversion': 'cgspeed MotionBuilder-friendly BVH; frame 0 is a T-pose',
                   'rights': 'CMU permits research and commercial use; Bruce Hahne places no additional restrictions on this BVH conversion.',
                   'rightsSource': 'https://raw.githubusercontent.com/una-dinosauria/cmu-mocap/master/READMEFIRST.txt',
                   'acknowledgment': 'The data used in this project was obtained from mocap.cs.cmu.edu. The database was created with funding from NSF EIA-0196217.'},
        'cycle': (end-start)/nominal_fps,
        'preparation': 'Root travel removed, heading aligned, endpoint residual removed with smoothstep. Rounded BVH frame time uses the documented nominal capture rate. Periodic sampling is a study adaptation, not untouched mocap.',
        'samples': samples,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bvh', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--start', type=int, default=6)
    parser.add_argument('--end', type=int, default=100)
    args = parser.parse_args()
    result = extract(args.bvh, args.start, args.end)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x') as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False)+'\n')


if __name__ == '__main__':
    main()
