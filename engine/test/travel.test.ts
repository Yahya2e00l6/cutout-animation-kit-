import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync, mkdtempSync, mkdirSync, copyFileSync, writeFileSync, rmSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { tmpdir } from 'node:os';
import { validateScene, sampleFrame, toolkitRoot, type Scene } from '../src/scene.ts';

const example = (): Scene => JSON.parse(readFileSync(new URL('../../scenes/examples/side-run-locked.json', import.meta.url), 'utf8'));

test('auto cadence matches travel and sampled speed is numeric, not a second time multiplier', () => {
  const result = validateScene(example());
  assert.equal(result.valid, true, JSON.stringify(result.diagnostics));
  const actor = sampleFrame(result.scene!, 15).actors[0];
  assert(Math.abs(actor.speed - 0.25403218500811053) < 1e-12);
  assert.equal(actor.localTime, 0.5);
  assert.equal(actor.footLock, true);
  assert.equal(actor.travelVelocity, 192);
  assert.deepEqual(result.diagnostics.map(d => d.code), ['POSE_PRESERVING_TRAVEL']);
});

test('matched cadence scales with travel and actor size, and preserves left facing', () => {
  const scene = example();
  scene.actors[0].scale = 0.5;
  scene.actors[0].view = 'side-left'; scene.clips[0].action = 'side-run-left';
  [scene.clips[0].travel.from, scene.clips[0].travel.to] = [scene.clips[0].travel.to, scene.clips[0].travel.from];
  const result = validateScene(scene);
  assert.equal(result.valid, true);
  const actor = sampleFrame(result.scene!, 15).actors[0];
  assert(Math.abs(actor.speed - 2 * 0.25403218500811053) < 1e-12);
  assert.equal(actor.travelVelocity, -192);
  assert.equal(actor.transform[0], 0.5);
});

for (const [name, expected, mutate] of [
  ['auto without lock', 'CADENCE_MODE', (s: Scene) => s.clips[0].footLock = false],
  ['stationary lock', 'TRAVEL_REQUIRED', (s: Scene) => s.clips[0].travel.to = [...s.clips[0].travel.from]],
  ['mismatched numeric cadence', 'CADENCE_MISMATCH', (s: Scene) => s.clips[0].speed = 1],
  ['too slow', 'CADENCE_RANGE', (s: Scene) => s.clips[0].travel.to[0] = 170],
  ['too fast', 'CADENCE_RANGE', (s: Scene) => s.clips[0].travel.to[0] = 20000],
] as const) test(`travel validation rejects ${name}`, () => {
  const scene = example(); mutate(scene);
  const result = validateScene(scene);
  assert.equal(result.valid, false);
  assert(result.diagnostics.some(d => d.code === expected), JSON.stringify(result));
});

test('explicit matched cadence is accepted without changing old numeric clips', () => {
  const scene = example(); scene.clips[0].speed = 0.25403218500811053;
  assert.equal(validateScene(scene).valid, true);
  scene.clips[0].footLock = false; scene.clips[0].speed = 1;
  const result = validateScene(scene);
  assert.equal(result.valid, true);
  assert.equal(sampleFrame(result.scene!, 0).actors[0].footLock, undefined);
  assert.deepEqual(result.diagnostics.map(d => d.code), ['UNLOCKED_TRAVEL']);
});

test('missing or stale calibration blocks only the opt-in travel adapter', () => {
  const directory = mkdtempSync(join(process.env.TMPDIR || tmpdir(), 'cutout-calibration-test-'));
  try {
    const sources = ['characters/hoodie-side/character.svg', 'characters/hoodie-side/rig.json', 'poses/side-run.json', 'motions/side-run.json', 'tools/side_actions.py'];
    for (const file of sources) {
      mkdirSync(dirname(join(directory, file)), { recursive: true });
      copyFileSync(join(toolkitRoot, file), join(directory, file));
    }
    let result = validateScene(example(), directory);
    assert.equal(result.valid, false);
    assert(result.diagnostics.some(d => d.code === 'TRAVEL_CALIBRATION'));
    copyFileSync(join(toolkitRoot, 'motions/side-run-travel.json'), join(directory, 'motions/side-run-travel.json'));
    assert.equal(validateScene(example(), directory).valid, true);
    writeFileSync(join(directory, sources[0]), '<svg/>');
    result = validateScene(example(), directory);
    assert.equal(result.valid, false);
    assert(result.diagnostics.some(d => d.code === 'TRAVEL_CALIBRATION'));
    const unlocked = example(); unlocked.clips[0].footLock = false; unlocked.clips[0].speed = 1;
    assert.equal(validateScene(unlocked, directory).valid, true);
  } finally { rmSync(directory, { recursive: true }); }
});
