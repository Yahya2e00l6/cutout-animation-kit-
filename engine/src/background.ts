import { readFileSync, lstatSync } from 'node:fs';
import { join } from 'node:path';
import { createHash } from 'node:crypto';

export type BackgroundImage = { asset: string; fit: 'contain' | 'cover' };
export type BackgroundPlate = BackgroundImage & {
  file: string; width: number; height: number; mime: 'image/jpeg' | 'image/png'; sha256: string;
};

/** Resolve a registered local plate; scene data never supplies a file path or URL. */
export function loadBackground(image: BackgroundImage, root: string): BackgroundPlate {
  const registry = JSON.parse(readFileSync(join(root, 'backgrounds/registry.json'), 'utf8'));
  if (registry.version !== 1 || !registry.assets || !Object.hasOwn(registry.assets, image.asset)) {
    throw new Error(`Unknown background asset: ${image.asset}`);
  }
  const row = registry.assets[image.asset];
  if (!row || typeof row.file !== 'string' || !/^[a-zA-Z0-9_-]+\.(jpg|jpeg|png)$/.test(row.file) ||
      ![row.width, row.height].every(n => Number.isSafeInteger(n) && n > 0 && n <= 8192) ||
      row.width * row.height > 16777216 || !['image/jpeg', 'image/png'].includes(row.mime) ||
      typeof row.sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(row.sha256)) throw new Error('Invalid background registry entry');
  const file = join(root, 'backgrounds', row.file);
  const stat = lstatSync(file);
  if (!stat.isFile() || stat.size > 20 * 1024 * 1024 || stat.size < 8) throw new Error('Background must be a regular image file under 20 MiB');
  const data = readFileSync(file);
  if (data.length < 8 || data.length > 20 * 1024 * 1024) throw new Error('Background byte size exceeds the render limit');
  const png = data.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]));
  const jpeg = data[0] === 255 && data[1] === 216 && data[2] === 255;
  if ((row.mime === 'image/png' ? !png : !jpeg) || createHash('sha256').update(data).digest('hex') !== row.sha256) {
    throw new Error('Background type or hash does not match its registry entry');
  }
  return { asset: image.asset, fit: image.fit, file: row.file,
    width: row.width, height: row.height, mime: row.mime, sha256: row.sha256 };
}
