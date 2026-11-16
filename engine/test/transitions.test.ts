import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync, mkdtempSync, mkdirSync, copyFileSync, writeFileSync, rmSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { tmpdir } from 'node:os';
import { sampleFrame, sampleScene, validateScene, toolkitRoot, type Scene } from '../src/scene.ts';

const example = (): Scene => JSON.parse(readFileSync(new URL('../../scenes/examples/stand-run-stop.json', import.meta.url), 'utf8'));

test('transition schedule includes real standing holds and preserves middle cadence', () => {
  const result = validateScene(example());
  assert.equal(result.valid, true, JSON.stringify(result.diagnostics));
  assert.equal(result.frameCount, 198);
  const at = (t: number) => sampleScene(result.scene!, t).actors[0];
  assert.deepEqual(at(0).transition, { mode: 'stand', weight: 0 });
  assert.deepEqual(at(0.4).transition, { mode: 'stand', weight: 0 });
  assert.equal(at(0.9).transition!.mode, 'start');
  assert(Math.abs(at(0.9).transition!.weight - 0.5) < 1e-12);
  assert.equal(at(1.3).transition, undefined);
  assert.equal(at(1.3).localTime, 0);
  assert(Math.abs(at(3.3).localTime - 2) < 1e-12);
  assert(Math.abs(at(3.3).speed - 0.3125) < 1e-12);
  assert.equal(at(5.3).transition!.mode, 'stop');
  assert(Math.abs(at(5.3).transition!.weight - 1) < 1e-12);
  assert.deepEqual(at(6.2).transition, { mode: 'stand', weight: 0 });
  assert.deepEqual(sampleFrame(result.scene!, 197).actors[0].transition, { mode: 'stand', weight: 0 });
  assert.deepEqual(at(0).position, [160, 620]);
  assert.deepEqual(at(6.2).position, example().clips[0].travel.to);
  assert(result.diagnostics.some(d => d.code === 'TRANSITION_TRIAL'));
});

test('fast trial doubles cadence and travel velocity, not just pose playback', () => {
  const fast: Scene = JSON.parse(readFileSync(new URL('../../scenes/examples/stand-run-stop-fast.json', import.meta.url), 'utf8'));
  const slow = validateScene(example());
  const quick = validateScene(fast);
  assert(quick.valid && slow.valid);
  const a = sampleScene(slow.scene!, 2).actors[0];
  const b = sampleScene(quick.scene!, 2).actors[0];
  assert(Math.abs(b.speed / a.speed - 2) < 1e-12);
  assert(Math.abs(b.travelVelocity! / a.travelVelocity! - 2) < 1e-12);
  assert.equal(quick.frameCount, 120);
  assert.deepEqual(sampleFrame(quick.scene!, 119).actors[0].transition, { mode: 'stand', weight: 0 });
});

test('standing pose is required only for transitions and malformed angles block validation', () => {
  const directory = mkdtempSync(join(process.env.TMPDIR || tmpdir(), 'cutout-standing-test-'));
  try {
    for (const file of ['characters/hoodie-side/character.svg', 'characters/hoodie-side/rig.json',
      'poses/side-run.json', 'motions/side-run.json', 'tools/side_actions.py', 'motions/side-run-travel.json']) {
      mkdirSync(dirname(join(directory, file)), { recursive: true });
      copyFileSync(join(toolkitRoot, file), join(directory, file));
    }
    assert(validateScene(example(), directory).diagnostics.some(d => d.code === 'ASSET_MISSING'));
    const legacy = example(); delete legacy.clips[0].transitions; legacy.clips[0].duration = 4;
    assert.equal(validateScene(legacy, directory).valid, true);
    const path = join(directory, 'poses/side-stand.json');
    copyFileSync(join(toolkitRoot, 'poses/side-stand.json'), path);
    assert.equal(validateScene(example(), directory).valid, true);
    writeFileSync(path, JSON.stringify({ version: 1, angles: { torso: 'upright' } }));
    assert(validateScene(example(), directory).diagnostics.some(d => d.code === 'STANDING_POSE'));
  } finally { rmSync(directory, { recursive: true }); }
});

test('transition sampling is deterministic and both run joins have continuous baseline placement', () => {
  const result = validateScene(example());
  assert(result.valid);
  const samples = Array.from({ length: 198 }, (_, i) => sampleFrame(result.scene!, i));
  for (let i = 197; i >= 0; --i) assert.deepEqual(sampleFrame(result.scene!, i), samples[i]);
  for (const t of [1.3, 5.3]) {
    const before = sampleScene(result.scene!, t - 1e-8).actors[0];
    const after = sampleScene(result.scene!, t + 1e-8).actors[0];
    assert(Math.abs(before.position[0] - after.position[0]) < 1e-5);
  }
});

for (const [name, code, mutate] of [
  ['disabled locking', 'TRANSITION_MODE', (s: Scene) => { s.clips[0].footLock = false; s.clips[0].speed = 1; }],
  ['no run interval', 'TRANSITION_RANGE', (s: Scene) => { s.clips[0].transitions!.start = 5; }],
  ['subframe transition', 'FRAME_ALIGNMENT', (s: Scene) => { s.clips[0].transitions!.start = 0.81; }],
  ['midflight stop', 'TRANSITION_CONTACT', (s: Scene) => { s.clips[0].travel.to[0] -= 50; }],
] as const) test(`transition validator rejects ${name}`, () => {
  const source = example(); mutate(source);
  const result = validateScene(source);
  assert.equal(result.valid, false);
  assert(result.diagnostics.some(d => d.code === code), JSON.stringify(result.diagnostics));
});
