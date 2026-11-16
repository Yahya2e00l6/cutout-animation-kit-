import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync, mkdtempSync, mkdirSync, copyFileSync, writeFileSync, symlinkSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { loadBackground } from '../src/background.ts';
import { sampleFrame, validateScene, toolkitRoot, type Scene } from '../src/scene.ts';

const example = (): Scene => JSON.parse(readFileSync(new URL('../../scenes/examples/dice-courtyard-background-test.json', import.meta.url), 'utf8'));
const image = { asset: 'dice-school-courtyard', fit: 'contain' as const };

test('registered background validates and sampling returns an independent pinned descriptor', () => {
  const source = example();
  const result = validateScene(source);
  assert.equal(result.valid, true, JSON.stringify(result.diagnostics));
  const sample = sampleFrame(result.scene!, 0);
  assert.equal(sample.stage.plate!.width, 1376);
  assert.equal(sample.stage.plate!.height, 768);
  assert.equal(sample.stage.plate!.file, 'dice-school-courtyard.jpg');
  assert.equal(sample.stage.plate!.fit, 'contain');
  assert.equal(sample.stage.plate!.mime, 'image/jpeg');
  assert(!result.diagnostics.some(d => d.code === 'BACKGROUND_CROP'));
  source.stage.image!.asset = 'unknown';
  sample.stage.plate!.file = 'wrong.jpg';
  sample.stage.image!.fit = 'cover';
  assert.equal(sampleFrame(result.scene!, 0).stage.plate!.file, 'dice-school-courtyard.jpg');
  assert.equal(sampleFrame(result.scene!, 0).stage.image!.fit, 'contain');
});

test('cover reports the crop instead of silently stretching the plate', () => {
  const source = example(); source.stage.image!.fit = 'cover';
  const result = validateScene(source);
  assert(result.valid);
  assert(result.diagnostics.some(d => d.code === 'BACKGROUND_CROP'));
  source.output.width = 1376; source.output.height = 768; source.stage.groundY = 700;
  source.clips[0].travel.from[1] = 700; source.clips[0].travel.to[1] = 700;
  assert(!validateScene(source).diagnostics.some(d => d.code === 'BACKGROUND_CROP'));
});

for (const [name, imageValue] of [
  ['URL', { asset: 'https://example.com/a.jpg', fit: 'contain' }],
  ['path', { asset: '../DICE/.env', fit: 'contain' }],
  ['stretch', { asset: image.asset, fit: 'stretch' }],
  ['unknown property', { ...image, url: 'https://example.com' }],
] as const) test(`background schema rejects ${name}`, () => {
  const source: any = example(); source.stage.image = imageValue;
  assert(validateScene(source).diagnostics.some(d => d.code === 'SCHEMA_INVALID'));
});

test('unknown background IDs are errors, not a solid-color fallback', () => {
  const source = example(); source.stage.image!.asset = 'unknown';
  const result = validateScene(source);
  assert.equal(result.valid, false);
  assert(result.diagnostics.some(d => d.code === 'BACKGROUND_ASSET'));
});

test('registry refuses traversal, symlinks, stale bytes and invalid metadata', () => {
  const root = mkdtempSync(join(process.env.TMPDIR || tmpdir(), 'cutout-background-test-'));
  try {
    mkdirSync(join(root, 'backgrounds'));
    const registry = JSON.parse(readFileSync(join(toolkitRoot, 'backgrounds/registry.json'), 'utf8'));
    const original = registry.assets[image.asset];
    const registryPath = join(root, 'backgrounds/registry.json');
    const save = (row: any) => writeFileSync(registryPath, JSON.stringify({ version: 1, assets: { [image.asset]: row } }));
    copyFileSync(join(toolkitRoot, 'backgrounds', original.file), join(root, 'backgrounds', original.file));
    save(original);
    assert.equal(loadBackground(image, root).width, 1376);
    for (const row of [{ ...original, file: '../secret.jpg' }, { ...original, sha256: '0'.repeat(64) },
      { ...original, width: 9000 }, { ...original, height: 0 }, { ...original, mime: 'image/svg+xml' },
      { ...original, mime: 'image/png' }]) {
      save(row);
      assert.throws(() => loadBackground(image, root));
    }
    symlinkSync(join(root, 'backgrounds', original.file), join(root, 'backgrounds/link.jpg'));
    save({ ...original, file: 'link.jpg' });
    assert.throws(() => loadBackground(image, root));
    save(original);
    writeFileSync(join(root, 'backgrounds', original.file), 'invalid image content');
    assert.throws(() => loadBackground(image, root));
  } finally { rmSync(root, { recursive: true }); }
});
