"""Shared front-view walk/run cycles and a jump, scaled to a character's legs.

The virtual stride goes into/out of the picture. Foreshortening is combined
with in-plane knee bends and support-side sway; no side-view artwork is made.
"""
import math
import re


def smooth(value):
    value = max(0.0, min(1.0, value))
    return value * value * (3 - 2 * value)


def hermite(a, b, velocity_a, velocity_b, duration, u):
    """Cubic position curve with velocities expressed per second."""
    return ((2*u**3 - 3*u*u + 1) * a + (u**3 - 2*u*u + u) * velocity_a * duration
            + (-2*u**3 + 3*u*u) * b + (u**3 - u*u) * velocity_b * duration)


def solve_planar(upper, lower, dx, dy, bend):
    distance = math.hypot(dx, dy)
    if not abs(upper - lower) < distance < upper + lower:
        raise ValueError("Unreachable projected in-plane leg target")
    knee = bend * math.acos(max(-1, min(1, (distance**2-upper**2-lower**2)/(2*upper*lower))))
    hip = math.atan2(-dx, dy) - math.atan2(lower*math.sin(knee), upper+lower*math.cos(knee))
    return hip, knee


def translation(node):
    match = re.fullmatch(r"translate\(\s*([-+.\deE]+)[ ,]+([-+.\deE]+)\s*\)", node.get("transform", ""))
    if not match:
        raise ValueError(f"Expected a translation-only rest joint: {node.get('id')}")
    return tuple(map(float, match.groups()))


class Humanoid:
    def __init__(self, tree, rig, soles):
        nodes = {e.get("id"): e for e in tree.iter() if e.get("id")}
        self.geometry = rig.get("motion_geometry", {})
        for control in ["torso", "pelvis"]:
            if translation(nodes[control]) != (0, 0):
                raise ValueError("Motion adapter requires identity torso/pelvis rest controls")
        self.legs = {}
        for side in ["left", "right"]:
            hip = translation(nodes[f"hip-{side}"])
            upper = translation(nodes[f"knee-{side}"])
            lower = translation(nodes[f"ankle-{side}"])
            if upper[0] != 0 or lower[0] != 0 or min(upper[1], lower[1]) <= 0:
                raise ValueError("This front-view model needs downward-aligned rest leg chains")
            for part, parent in [("upper", f"hip-{side}"), ("lower", f"knee-{side}")]:
                name = self.geometry.get(f"{part}-{side}")
                if name not in nodes or nodes[name] not in list(nodes[parent]):
                    raise ValueError(f"Declare direct-child motion_geometry for {part}-{side}")
                if nodes[name].get("transform", ""):
                    raise ValueError(f"Motion artwork must have identity rest transform: {name}")
                child_joint = nodes[f'knee-{side}' if part == 'upper' else f'ankle-{side}']
                if any(child is not nodes[name] and child is not child_joint for child in nodes[parent]):
                    raise ValueError(f"All segment artwork must be inside declared motion_geometry: {parent}")
            self.legs[side] = {"hip": hip, "upper": upper[1], "lower": lower[1], "sole": soles[side]}
        self.length = min(leg["upper"] + leg["lower"] for leg in self.legs.values())
        self.rest_height = min(leg["hip"][1] + leg["upper"] + leg["lower"] + leg["sole"][1] for leg in self.legs.values()) - 0.07 * self.length
        self.arms = {}
        for side in ['left', 'right']:
            match = re.fullmatch(r'translate\(([-\d.]+) ([-\d.]+)\) rotate\(([-\d.]+)\)', nodes[f'shoulder-{side}'].get('transform', ''))
            if not match:
                raise ValueError('Arm adapter needs translate/rotate shoulder rest transforms')
            self.arms[side] = {
                'rest_angle': math.radians(float(match[3])),
                'upper': translation(nodes[f'elbow-{side}'])[1],
                'lower': translation(nodes[f'wrist-{side}'])[1],
            }


def solve_projected_leg(upper, lower, vertical, depth):
    """Solve in sagittal space and return the two projected vertical lengths."""
    distance = math.hypot(vertical, depth)
    if not abs(upper - lower) < distance < upper + lower:
        raise ValueError(f"Unreachable leg target: {distance:.3f} for {upper}+{lower}")
    knee = -math.acos(max(-1.0, min(1.0, (distance**2 - upper**2 - lower**2) / (2 * upper * lower))))
    thigh = math.atan2(depth, vertical) - math.atan2(lower * math.sin(knee), upper + lower * math.cos(knee))
    upper_y = upper * math.cos(thigh)
    lower_y = lower * math.cos(thigh + knee)
    if min(upper_y / upper, lower_y / lower) < 0.15:
        raise ValueError("Pose requires alternate artwork rather than extreme foreshortening")
    return upper_y, lower_y


def gait_arms(phase, envelope, model, settings, feet, stride):
    """Opposite-leg arm swing with projected reach and opaque torso occlusion."""
    running = smooth((settings['lift']-0.10)/0.18)
    # Follow the actual eased foot trajectories: stance/swing duty changes mean
    # a plain cosine is not reliably opposite the legs during a run.
    relative_depth = (feet['left']['depth']-feet['right']['depth'])/stride if stride > 1e-9 else 0
    # Keep the eased foot signal without saturating its extremes into holds.
    right_depth = max(-1, min(1, relative_depth))
    strength = min(1.0, max(0.0, settings['arm_swing']/(15+17*running)))
    angles, projection, blend, depths = {}, {}, {}, {}
    for side, sign in [('right', -1), ('left', 1)]:
        arm = model.arms[side]
        depth = (-sign) * right_depth * envelope * strength
        forward, backward = max(depth, 0)**2, max(-depth, 0)**2
        upper_scale = 1-(0.035+0.065*running)*abs(depth)**2
        lower_scale = 1-(0.07+0.16*running)*forward-(0.04+0.04*running)*backward
        rest_elbow = math.radians(10*sign)
        a0, u, l = arm['rest_angle'], arm['upper'], arm['lower']
        x0 = -u*math.sin(a0)-l*math.sin(a0+rest_elbow)
        y0 = u*math.cos(a0)+l*math.cos(a0+rest_elbow)
        x = x0 + sign*(-10*forward-32*backward)
        # A little flexion remains through the running crossover. Projected
        # reach supplies the lift without pushing the elbow far out sideways.
        y = y0 - 12*running*envelope - (30+45*running)*forward-(12+2*running)*backward
        shoulder, elbow = solve_planar(u*upper_scale, l*lower_scale, x, y, sign)
        hand_lag = math.radians(5+5*running)*math.sin(phase*math.tau-0.35)*envelope
        if running:
            weight = running*envelope
            # A running arm stays folded. Drive the pump from the shoulder;
            # do not solve a near-straight reach on every backward stroke.
            target_shoulder = -sign*math.radians(32+6*depth)
            target_elbow = sign*math.radians(90+10*depth)
            if settings.get('profile') == 'reference-run':
                # Compact front-view pump: raise the forward fist toward the
                # chest rather than lifting the elbow sideways.
                target_shoulder = -sign*math.radians(26+4*depth)
                target_elbow = sign*math.radians(70+45*depth)
            shoulder += (target_shoulder-shoulder)*weight
            elbow += (target_elbow-elbow)*weight
            upper_scale += (0.98-0.20*forward+0.02*backward-upper_scale)*weight
            lower_scale += (0.86-0.18*forward-0.03*backward-lower_scale)*weight
            target_lag = math.radians(3)*math.sin(phase*math.tau-0.20)*envelope
            hand_lag += (target_lag-hand_lag)*weight
        hand_angle = shoulder+elbow+hand_lag
        angles.update({f'shoulder-{side}': math.degrees(shoulder-a0),
                       f'elbow-{side}': math.degrees(elbow),
                       f'wrist-{side}': math.degrees(hand_angle-shoulder-elbow)})
        projection[side] = {'upper': upper_scale, 'lower': lower_scale}
        # Ease geometric foreground coverage into the idle state. The renderer
        # reveals an opaque copy; this value is never an opacity.
        blend[f'elbow-{side}'] = 1-envelope + envelope*smooth((depth+0.25)/0.5)
        depths[side] = depth
    return angles, projection, blend, depths


def locomotion(local, duration, model, settings):
    envelope = smooth(min(local / 0.35, (duration - local) / 0.35, 1))
    if settings.get('loop', False):
        envelope = 1.0
    phase = local / settings["cycle"]
    stance = settings["stance"]
    stride = model.length * settings["stride"] * envelope
    feet = {}
    for side, offset in [("right", 0), ("left", 0.5)]:
        p = (phase + offset) % 1
        planted = p < stance
        if planted:
            # Both sides of touchdown/toe-off have zero depth velocity. A
            # linear stance joined to an eased swing made the knee speed jump.
            depth = stride * (0.5 - smooth(p / stance))
            lift = 0.0
        else:
            swing = (p - stance) / (1 - stance)
            depth = stride * (-0.5 + smooth(swing))
            lift = model.length * settings["lift"] * math.sin(math.pi * swing)**2 * envelope
        feet[side] = {"depth": depth, "lift": lift, "contact": planted}
    # Root height never selects a new shoe/support height at a contact boundary.
    # Run's compression and flight parabolas share positions AND velocities.
    p = phase % 0.5
    if stance < 0.5:
        amplitude = model.length * settings.get("flight", 0)
        if p < stance:
            u = p / stance
            offset = -4 * amplitude * stance / (0.5-stance) * u * (1-u)
        else:
            u = (p-stance) / (0.5-stance)
            offset = 4 * amplitude * u * (1-u)
            clearance = model.length * 0.045 * math.sin(math.pi*u)**2 * envelope
            for foot in feet.values():
                foot["lift"] += clearance
        height = model.rest_height + offset * envelope
    else:
        height = model.rest_height - model.length * 0.012 * math.sin(phase*2*math.pi)**2 * envelope
    # Near toe-off/landing, an airborne run leg must not overextend vertically.
    for side, foot in feet.items():
        if not foot["contact"]:
            leg = model.legs[side]
            reach_y = math.sqrt((0.99 * (leg["upper"] + leg["lower"]))**2 - foot["depth"]**2)
            foot["lift"] = max(foot["lift"], height - leg["hip"][1] - leg["sole"][1] - reach_y)
    arm_angles, projection, blend, depths = gait_arms(phase, envelope, model, settings, feet, stride)
    pose = {
        "expression": "neutral",
        "angles": {
            **arm_angles,
            "torso": 1.2 * math.sin(phase * math.tau) * envelope,
            "head": -1.2 * math.sin(phase * math.tau) * envelope,
        },
        "arm_projection": projection,
        "arm_depth": depths,
        "layers": {"forearm_blend": blend},
    }
    if settings['lift'] > 0.10:
        curl = smooth((settings['lift']-0.10)/0.18)*envelope
        pose['hand_curl'] = {'left': curl, 'right': curl}
    sway = -model.length * settings.get("sway", 0.04) * math.sin(phase*math.tau) * envelope
    return height, feet, pose, sway


def jump(local, duration, model, settings):
    p = local / duration
    base = model.rest_height
    crouch = settings["crouch"] * model.length
    flight_duration = 0.38 * duration
    peak = settings["height"] * model.length
    velocity = 4 * peak / flight_duration
    height, lift = base, 0.0
    arms = 0.0
    airborne = False
    if p < 0.23:
        height -= crouch * smooth(p / 0.23)
        arms = -12 * smooth(p / 0.23)
    elif p < 0.34:
        u = smooth((p - 0.23) / 0.11)
        height = hermite(base-crouch, base, 0, velocity, 0.11*duration, (p-0.23)/0.11)
        arms = -12 + 87 * u
    elif p < 0.72:
        u = (p - 0.34) / 0.38
        arc = 4 * u * (1 - u)
        height = base + settings["height"] * model.length * arc
        lift = height - base + settings["tuck"] * model.length * math.sin(math.pi * u)**2
        arms = 75 + 20 * math.sin(math.pi * u)**2
        airborne = True
    elif p < 0.82:
        u = smooth((p - 0.72) / 0.10)
        height = hermite(base, base-crouch, -velocity, 0, 0.10*duration, (p-0.72)/0.10)
        arms = 75 * (1 - u)
    else:
        height = base - crouch * (1 - smooth((p - 0.82) / 0.18))
    feet = {side: {"depth": 0, "lift": lift, "contact": not airborne} for side in model.legs}
    pose = {
        "expression": "happy" if 0.34 < p < 0.72 else "neutral",
        "angles": {"shoulder-right": arms, "shoulder-left": -arms,
                   "elbow-right": -10, "elbow-left": 10},
        "layers": {"front_forearms": ["elbow-right", "elbow-left"]},
    }
    return height, feet, pose, 0.0


def sample(time, model, timeline):
    if time < 0:
        raise ValueError("Time outside timeline")
    start = 0.0
    for segment in timeline["segments"]:
        duration, action = segment["duration"], segment["action"]
        if time < start + duration:
            local = time - start
            if action in ["walk", "run"]:
                height, feet, pose, sway = locomotion(local, duration, model, timeline[action])
            elif action == "jump":
                height, feet, pose, sway = jump(local, duration, model, timeline[action])
            elif action == "idle":
                height = model.rest_height
                sway = 0.0
                feet = {side: {"depth": 0, "lift": 0, "contact": True} for side in model.legs}
                pose = {"angles": {"elbow-right": -10, "elbow-left": 10},
                        "layers": {"front_forearms": ["elbow-right", "elbow-left"]}}
            else:
                raise ValueError(f"Unknown action: {action}")
            lengths = {}
            leg_angles = {}
            for side, leg in model.legs.items():
                vertical = height - leg["hip"][1] - leg["sole"][1] - feet[side]["lift"]
                a, b = solve_projected_leg(leg["upper"], leg["lower"], vertical, feet[side]["depth"])
                # Specify a modest front-view bend rather than converting all
                # unused reach into sideways knee spread (including at idle).
                compression = smooth((model.rest_height-height)/(0.16*model.length))
                lift_range = timeline[action]["lift"] if action in ["walk", "run"] else 0.28
                lift = smooth(feet[side]["lift"]/(lift_range*model.length))
                bend = math.radians(3 + 14*compression + 15*lift)
                # Preserve the sagittal length ratio, adding exactly the reach
                # required for this bend and lateral sway. The planar solve
                # still owns the fixed foot target.
                reach = math.sqrt(a*a + b*b + 2*a*b*math.cos(bend))
                factor = math.hypot(sway, vertical) / reach
                a *= factor
                b *= factor
                lengths[side] = (a, b)
                leg_angles[side] = solve_planar(a, b, -sway, vertical, 1 if side == "left" else -1)
            return {"action": action, "height": height, "sway": sway, "feet": feet, "pose": pose, "lengths": lengths, "leg_angles": leg_angles}
        start += duration
    raise ValueError("Time outside timeline")
