"""Read a BVH reference into world-space joints; not an animation backend.

Offsets and ordered Euler channels are preserved. Only position channels before
rotation channels are supported; unsupported layouts fail instead of guessing.
"""
import math
import re


IDENTITY = ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.))


def mul(a, b):
    return tuple(tuple(sum(a[i][k]*b[k][j] for k in range(3)) for j in range(3)) for i in range(3))


def vector(a, p):
    return tuple(sum(a[i][k]*p[k] for k in range(3)) for i in range(3))


def rotation(axis, degrees):
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return {'X': ((1, 0, 0), (0, c, -s), (0, s, c)),
            'Y': ((c, 0, s), (0, 1, 0), (-s, 0, c)),
            'Z': ((c, -s, 0), (s, c, 0), (0, 0, 1))}[axis]


class BVH:
    def __init__(self, text):
        hierarchy, motion = text.split('MOTION', 1)
        tokens = re.findall(r'[^\s{}]+|[{}]', hierarchy)
        self.nodes = []
        self.channels = 0
        cursor = 0
        def take(expected=None):
            nonlocal cursor
            if cursor >= len(tokens):
                raise ValueError('Truncated BVH hierarchy')
            value = tokens[cursor]; cursor += 1
            if expected is not None and value != expected:
                raise ValueError(f'Expected {expected}, got {value}')
            return value
        def node(parent):
            kind = take()
            if kind == 'End':
                take('Site'); name = parent['name']+'/end'
            elif kind in ('ROOT', 'JOINT'):
                name = take()
            else:
                raise ValueError('Unsupported BVH node')
            if any(n['name'] == name for n in self.nodes):
                raise ValueError('Duplicate BVH node')
            current = {'name': name, 'parent': parent, 'channels': [], 'index': self.channels}
            self.nodes.append(current)
            take('{'); take('OFFSET')
            current['offset'] = tuple(float(take()) for _ in range(3))
            if not all(math.isfinite(n) for n in current['offset']):
                raise ValueError('Invalid BVH offset')
            if kind != 'End':
                take('CHANNELS'); count = int(take())
                current['channels'] = [take() for _ in range(count)]
                allowed = {a+b for a in 'XYZ' for b in ('position', 'rotation')}
                channels = current['channels']
                if (count not in (3, 6) or len(set(channels)) != count or not set(channels) <= allowed
                        or any(c.endswith('position') for c in channels[3:])
                        or (count == 3 and any(c.endswith('position') for c in channels))):
                    raise ValueError('Unsupported BVH channel layout')
                self.channels += count
            while cursor < len(tokens) and tokens[cursor] != '}':
                node(current)
            take('}')
        take('HIERARCHY'); node(None)
        if cursor != len(tokens):
            raise ValueError('Unexpected trailing BVH hierarchy')
        match = re.match(r'\s*Frames:\s*(\d+)\s*Frame Time:\s*([\d.eE+-]+)\s*(.*)', motion, re.S)
        if not match:
            raise ValueError('Invalid BVH motion header')
        count, self.frame_time = int(match[1]), float(match[2])
        if count <= 0 or not math.isfinite(self.frame_time) or self.frame_time <= 0:
            raise ValueError('Invalid BVH frame count or time')
        numbers = [float(n) for n in match[3].split()]
        if len(numbers) != count*self.channels or not all(math.isfinite(n) for n in numbers):
            raise ValueError('Invalid BVH motion data')
        self.frames = [numbers[i*self.channels:(i+1)*self.channels] for i in range(count)]

    def frame(self, index):
        if type(index) is not int or not 0 <= index < len(self.frames):
            raise ValueError('Invalid BVH frame index')
        result, transforms = {}, {}
        for node in self.nodes:
            local = IDENTITY
            translation = list(node['offset'])
            values = self.frames[index][node['index']:node['index']+len(node['channels'])]
            for channel, value in zip(node['channels'], values):
                if channel.endswith('position'):
                    translation['XYZ'.index(channel[0])] += value
                else:
                    local = mul(local, rotation(channel[0], value))
            parent = node['parent']
            if parent:
                matrix, point = transforms[parent['name']]
                offset = vector(matrix, translation)
                position = tuple(a+b for a, b in zip(point, offset))
                local = mul(matrix, local)
            else:
                position = tuple(translation)
            transforms[node['name']] = local, position
            result[node['name']] = position
        return result
