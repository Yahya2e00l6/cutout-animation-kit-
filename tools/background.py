"""Read bounded, hash-pinned background plates from the toolkit asset directory."""
import base64
import hashlib
import io
import re
import stat

from PIL import Image

from tools.preview import ROOT


class Backgrounds:
    def __init__(self):
        self.cache = {}

    def image(self, plate):
        key = tuple(plate[name] for name in ['file', 'sha256', 'mime', 'width', 'height'])
        if key not in self.cache:
            if not re.fullmatch(r'[a-zA-Z0-9_-]+\.(jpg|jpeg|png)', plate['file']):
                raise ValueError('Invalid background file name')
            path = ROOT/'backgrounds'/plate['file']
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or not 8 <= info.st_size <= 20*1024*1024:
                raise ValueError('Background must be a regular image file under 20 MiB')
            data = path.read_bytes()
            if not 8 <= len(data) <= 20*1024*1024:
                raise ValueError('Background byte size exceeds the render limit')
            if hashlib.sha256(data).hexdigest() != plate['sha256']:
                raise ValueError('Background changed since scene validation')
            with Image.open(io.BytesIO(data)) as image:
                width, height = image.size
                if (width, height) != (plate['width'], plate['height']) or max(width, height) > 8192 or width*height > 16777216:
                    raise ValueError('Background dimensions do not match a bounded registry entry')
                if {'JPEG': 'image/jpeg', 'PNG': 'image/png'}.get(image.format) != plate['mime']:
                    raise ValueError('Background MIME type does not match decoded image')
                image.load()
            self.cache[key] = f"data:{plate['mime']};base64," + base64.b64encode(data).decode('ascii')
        return self.cache[key]
