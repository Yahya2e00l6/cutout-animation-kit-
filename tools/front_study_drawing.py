"""Rounded front-view garments and sneakers for the independent pose study.

Motion and contact geometry belong to FrontStudy. These drawings use its pose;
the side character supplies clothing construction and sneaker design language.
"""
import math

from tools.front_run_study import elt


def garment(action, parent, segments, ident, color):
    # The side rig outlines the union of overlapping cloth, not each bone.
    group = elt(parent, 'g', id=ident, filter='url(#study-cloth-outline)')
    for name, a, b, wa, wb in segments:
        joint_end = 'thigh' in name or 'upper-arm' in name
        elt(group, 'path', id=name, d=action.limb_path(a, b, wa, wb, cap_start=1.7,
                                                    cap_end=1.7 if joint_end else .55), fill=color)
    return group


def sneaker(action, parent, pose, side):
    """Rounded upper, rubber toe cap and thin sole; no construction-face ink."""
    _, pt = action.shoe(pose, side)
    # All points fit within the existing shoe contact envelope. Rendering never
    # changes the ankle, ground correction or foot orientation.
    stations = [(-20, 0, -25), (-15, 18, -16), (0, 24, -8),
                (20, 29, -10), (42, 32, -15), (57, 30, -21),
                (68, 21, -27), (74, 0, -29)]
    profile = stations
    stations = []
    for i in range(33):
        theta = i*math.pi/32
        z = 27-47*math.cos(theta)
        w = 32*math.sin(theta)*(.8+.2*math.sin(theta/2))
        index = next((j for j in range(len(profile)-1) if profile[j+1][0] >= z), len(profile)-2)
        a, b = profile[index], profile[index+1]
        t = (z-a[0])/(b[0]-a[0])
        top = a[2]+(b[2]-a[2])*t
        stations.append((z, w, top))
    rings = [[pt(w*math.cos(j*math.pi/16), -29+(top+29)*math.sin(j*math.pi/16), z)
              for j in range(17)] for z, w, top in stations]
    faces = []
    for i in range(len(rings)-1):
        color = '#b6cdd0' if stations[i][0] >= 42 else '#4b5553'
        for j in range(16):
            faces.append(([rings[i][j], rings[i+1][j], rings[i+1][j+1], rings[i][j+1]], color))
    rim = [ring[0] for ring in rings]+[ring[-1] for ring in reversed(rings)]
    bottom = [pt(w, -35, z) for z, w, _ in stations]+[pt(-w, -35, z) for z, w, _ in reversed(stations)]
    faces.append((bottom, '#9db7ba'))
    for i in range(len(rim)):
        j = (i+1)%len(rim)
        faces.append(([rim[i], rim[j], bottom[j], bottom[i]], '#b6cdd0'))
    group = elt(parent, 'g', filter='url(#study-shoe-outline)')
    for points, color in sorted(faces, key=lambda item: sum(p[2] for p in item[0])/len(item[0])):
        projected = [action.project(p) for p in points]
        elt(group, 'polygon', points=' '.join(f'{p[0]:.3f},{p[1]:.3f}' for p in projected),
            fill=color, stroke=color, stroke_width=.55, stroke_linejoin='round')
    # Curved laces follow the upper surface, visible only from its top side.
    forward = pose[side]['foot_forward']
    from tools.front_run_study import cross, unit, sub
    up = unit(cross(forward, unit(cross((0, 1, 0), forward))))
    camera = sub((0, 420, 1800), pose[side]['ankle'])
    if sum(a*b for a, b in zip(up, camera)) > 0:
        for z, height, width in [(9, -9, 25), (22, -11, 29), (35, -14, 31)]:
            points = [action.project(pt(x, -29+(height+29)*math.sqrt(1-(x/width)**2), z))
                      for x in (-13, 0, 13)]
            a, b, c = points
            elt(parent, 'path', d=f'M {a[0]} {a[1]} Q {b[0]} {b[1]} {c[0]} {c[1]}',
                fill='none', stroke='#c5d8d9', stroke_width=2.5, stroke_linecap='round')
