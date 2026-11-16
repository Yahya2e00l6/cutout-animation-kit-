"""Matched-phase diagnostics for FrontStudy; no scene or engine dependency."""
import io

from PIL import Image, ImageDraw

from tools.animate import raster
from tools.front_run_study import add, times
from tools.preview import ROOT


SIDES = [('Left', 'left', '#c35d45'), ('Right', 'right', '#357e9e')]


def drawing_comparison(action, out):
    """Compare side artwork and front drawings at equal displayed height."""
    sheet = Image.new('RGB', (1200, 700), '#f7f6f0')
    draw = ImageDraw.Draw(sheet)
    buffer = io.BytesIO()
    raster((ROOT/'characters/hoodie-side/character.svg').read_bytes(), 640, 1000).write_to_png(buffer)
    side = Image.open(buffer).convert('RGBA')
    side = side.crop(side.getbbox())
    side.thumbnail((360, 590), Image.Resampling.LANCZOS)
    sheet.paste(side, ((400-side.width)//2, 75+590-side.height), side)
    draw.text((20, 20), 'SIDE ARTWORK | size normalized', fill='#29392f')
    for col, phase in [(1, 0), (2, .25)]:
        svg, _ = action.frame(phase*action.cycle)
        buffer = io.BytesIO(); raster(svg, 1280, 720).write_to_png(buffer)
        image = Image.open(buffer).convert('RGB').crop((440, 40, 840, 690))
        sheet.paste(image, (col*400, 50))
        draw.text((col*400+20, 20), f'FRONT DRAWING | phase {phase:.2f}', fill='#29392f')
    sheet.save(out/'character-style-comparison.png')


def reference_points(action, seconds):
    sample = action.sample(seconds)
    return {name: add(times(point, action.ratio),
                      (sample['sway']*action.ratio, sample['height']*action.ratio+action.alignment, 0))
            for name, point in sample['joints'].items()}


def review_images(action, out, baseline=None):
    """Eight exact phases, same camera/crop; sagittal views expose hidden bends."""
    sheets = {name: Image.new('RGB', (2000, 840), '#f7f6f0')
              for name in ('reference-comparison', 'sagittal-comparison')}
    if baseline is not None:
        sheets['before-after'] = Image.new('RGB', (2000, 840), '#f7f6f0')
    crop = (440, 40, 840, 690)
    def tile(image):
        return image.crop(crop).resize((250, 390))
    for i in range(8):
        seconds = i/8*action.cycle
        svg, pose = action.frame(seconds)
        surface = raster(svg, 1280, 720)
        buffer = io.BytesIO(); surface.write_to_png(buffer)
        character = tile(Image.open(buffer).convert('RGB'))
        points = reference_points(action, seconds)
        ref_image = Image.new('RGB', (1280, 720), '#f7f6f0')
        draw = ImageDraw.Draw(ref_image)
        def front(p): return action.project(p)[:2]
        for name, _, color in SIDES:
            for chain in [('UpLeg', 'Leg', 'Foot', 'ToeBase', 'ToeBase/end'), ('Arm', 'ForeArm', 'Hand')]:
                draw.line([front(points[name+j]) for j in chain], fill=color, width=4)
        for a, b in [('LeftUpLeg', 'RightUpLeg'), ('LeftArm', 'RightArm'), ('Hips', 'Neck'), ('Neck', 'Head')]:
            draw.line([front(points[a]), front(points[b])], fill='#596653', width=4)
        x, y = i%4*500, i//4*420
        sheet = sheets['reference-comparison']
        sheet.paste(tile(ref_image), (x, y+30)); sheet.paste(character, (x+250, y+30))
        ImageDraw.Draw(sheet).text((x+8, y+8), f'CMU adapted | phase {i/8:.3f}                  study', fill='#29392f')

        sheet = sheets['sagittal-comparison']; draw = ImageDraw.Draw(sheet)
        draw.text((x+8, y+8), f'CMU side | phase {i/8:.3f}                study side (+Z right)', fill='#29392f')
        for col in range(2):
            def sidepoint(p): return x+125+250*col+p[2]*.52, y+398-p[1]*.52
            for name, side, color in SIDES:
                chains = ([points[name+j] for j in ('UpLeg', 'Leg', 'Foot', 'ToeBase/end')],
                          [points[name+j] for j in ('Arm', 'ForeArm', 'Hand')]) if col == 0 else (
                              [pose[side][j] for j in ('hip', 'knee', 'ankle')],
                              [pose[side][j] for j in ('shoulder', 'elbow', 'wrist')])
                for chain in chains:
                    draw.line([sidepoint(p) for p in chain], fill=color, width=3)
                    for p in chain:
                        px, py = sidepoint(p)
                        draw.ellipse((px-3, py-3, px+3, py+3), fill=color)
            body = [points['Hips'], points['Neck']] if col == 0 else [pose['root'], pose['neck']]
            draw.line([sidepoint(p) for p in body], fill='#596653', width=3)
            draw.line((x+col*250+10, y+398, x+col*250+240, y+398), fill='#d7d8cf')
        if baseline is not None:
            sheet = sheets['before-after']
            with Image.open(baseline/'keyframes'/f'pose_{i:02d}.png') as image:
                sheet.paste(tile(image.convert('RGB')), (x, y+30))
            sheet.paste(character, (x+250, y+30))
            ImageDraw.Draw(sheet).text((x+8, y+8), f'{baseline.name} (bones shown) | {i/8:.3f}              new study', fill='#29392f')
    for name, image in sheets.items():
        image.save(out/f'{name}.png')
    drawing_comparison(action, out)
