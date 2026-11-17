"""Compare one unrigged rear drawing with the original front and saved side art.

This tool only arranges existing images. It does not sample motion, edit source
art, trace vectors, segment parts or create a rig. Equal-height comparison uses
uniform resizing, not independent width fitting.
"""
import argparse
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from tools.animate import raster
from tools.preview import ROOT


def artwork_crop(image):
    """Crop white-margin reference art or a transparent character, keeping ink."""
    rgba = image.convert('RGBA')
    background = Image.new('RGBA', rgba.size, 'white')
    background.alpha_composite(rgba)
    # The source illustration is on white, unlike a warm-grey motion stage.
    mask = background.convert('RGB').convert('L').point(lambda n: 255 if n < 235 else 0)
    bounds = mask.getbbox()
    if bounds is None:
        raise ValueError('Drawing contains no visible artwork')
    padding = 3
    x0, y0, x1, y1 = bounds
    return rgba.crop((max(0, x0-padding), max(0, y0-padding),
                      min(rgba.width, x1+padding), min(rgba.height, y1+padding)))


def review(back, out):
    if out.exists():
        raise FileExistsError('Choose a fresh drawing-review output directory')
    with Image.open(back) as source:
        rear = artwork_crop(source)
    with Image.open(ROOT/'lastpic.jpeg') as source:
        front = artwork_crop(source)
    buffer = io.BytesIO()
    raster((ROOT/'characters/hoodie-side/character.svg').read_bytes(), 640, 1000).write_to_png(buffer)
    side = artwork_crop(Image.open(buffer))
    out.mkdir(parents=True)
    canvas = Image.new('RGB', (1800, 1200), 'white')
    draw = ImageDraw.Draw(canvas)
    font_path = '/usr/share/fonts/noto/NotoSans-Regular.ttf'
    try:
        title_font = ImageFont.truetype(font_path, 22)
        small_font = ImageFont.truetype(font_path, 16)
    except OSError:
        title_font = small_font = ImageFont.load_default(size=20)
    baseline, height = 1100, 970
    entries = [('FRONT | original identity', front),
               ('SIDE | saved artwork', side),
               ('BACK | unrigged drawing candidate', rear)]
    for column, (label, image) in enumerate(entries):
        scale = height/image.height
        size = (round(image.width*scale), height)
        if size[0] > 570:
            raise ValueError('Reference is too wide for an equal-height comparison')
        tile = image.resize(size, Image.Resampling.LANCZOS)
        x = column*600+(600-tile.width)//2
        canvas.paste(tile, (x, baseline-height), tile)
        draw.text((column*600+28, 40), label, fill='#292b25', font=title_font)
        draw.line((column*600+30, baseline+8, column*600+570, baseline+8), fill='#deded6', width=1)
    draw.text((30, 1155), 'Same displayed height; uniform scale only. Artwork review - no motion or rig changes.',
              fill='#53594e', font=small_font)
    canvas.save(out/'front-side-back.png')
    rear.save(out/'back-isolated.png')
    print(out/'front-side-back.png')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--drawing', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    review(args.drawing, args.out)


if __name__ == '__main__':
    main()
