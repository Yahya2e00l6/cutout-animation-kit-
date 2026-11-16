import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync, mkdtempSync, mkdirSync, copyFileSync, writeFileSync, rmSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { tmpdir } from 'node:os';
import { sampleFrame, validateScene, toolkitRoot, type Scene } from '../src/scene.ts';

const example = (): Scene => JSON.parse(readFileSync(new URL('../../scenes/examples/front-run-v04.json', import.meta.url), 'utf8'));

test('Astra front-run binds v04 independently from the rejected preset', () => {
  const scene = example(); scene.clips[0].speed = 2;
  const result = validateScene(scene);
  assert(result.valid, JSON.stringify(result.diagnostics));
  assert.equal(result.frameCount, 69);
  const actor = sampleFrame(result.scene!, 30).actors[0];
  assert.equal(actor.action, 'front-run');
  assert.equal(actor.localTime, 1);
  assert.equal(actor.speed, 2);
  assert.deepEqual(actor.sourceAnchor, [640, 650]);
  assert.deepEqual(actor.transform, [1, 0, 0, 1, 0, 0]);
  assert(result.diagnostics.some(d => d.code === 'FRONT_RUN_IN_PLACE' && d.message.includes('shoe-proxy')));
});

for (const [name, change, code] of [
  ['lateral travel', (s: Scene) => { s.clips[0].travel.to[0] += 100; }, 'FRONT_TRAVEL'],
  ['depth travel', (s: Scene) => { s.clips[0].travel.to[1] -= 100; }, 'FRONT_TRAVEL'],
  ['automatic cadence', (s: Scene) => { s.clips[0].speed = 'auto'; }, 'FRONT_MODE'],
  ['foot locking', (s: Scene) => { s.clips[0].footLock = true; }, 'FRONT_MODE'],
  ['support solver', (s: Scene) => { s.clips[0].travelMode = 'support-leg'; }, 'FRONT_MODE'],
  ['standing blends', (s: Scene) => { s.clips[0].transitions = { standBefore: .1, start: .1, stop: .1, standAfter: .1 }; }, 'FRONT_MODE'],
  ['DICE fallback', (s: Scene) => { s.actors[0].character = 'dice-dongtae-upgraded'; }, 'CHARACTER_VIEW_MISMATCH'],
  ['wrong view', (s: Scene) => { s.actors[0].view = 'side-left'; }, 'ACTION_VIEW_MISMATCH'],
] as const) {
  test(`Astra front-run rejects ${name}`, () => {
    const scene = example(); change(scene);
    const result = validateScene(scene);
    assert(!result.valid);
    assert(result.diagnostics.some(d => d.code === code), JSON.stringify(result.diagnostics));
  });
}

test('Astra front-only binding needs no legacy/side assets and rejects invalid presets', () => {
  const dir = mkdtempSync(join(tmpdir(), 'astra-front-'));
  try {
    for (const file of ['characters/hoodie/character.svg', 'motions/front-run.json',
      'motions/front-run-study/athletic-reference.json', 'tools/front_study_action.py',
      'tools/front_run_study.py', 'tools/front_study_drawing.py']) {
      mkdirSync(dirname(join(dir, file)), { recursive: true });
      copyFileSync(join(toolkitRoot, file), join(dir, file));
    }
    const scene = example();
    assert(validateScene(scene, dir).valid);
    const path = join(dir, 'motions/front-run.json');
    const preset = JSON.parse(readFileSync(path, 'utf8'));
    for (const bad of [{ ...preset, width: 1000 }, { ...preset, readability: {} },
      { ...preset, readability: { ...preset.readability, arm_gain: 0 } }]) {
      writeFileSync(path, JSON.stringify(bad));
      assert(validateScene(scene, dir).diagnostics.some(d => d.code === 'ASSET_INVALID'));
    }
    writeFileSync(path, JSON.stringify(preset));
    rmSync(join(dir, 'tools/front_study_drawing.py'));
    assert(validateScene(scene, dir).diagnostics.some(d => d.code === 'ASSET_MISSING'));
  } finally { rmSync(dir, { recursive: true }); }
});

test('Astra front-run composes with both preserved side directions and legacy front', () => {
  const scene = example();
  for (const [id, view, action] of [['right', 'side-right', 'side-run-right'],
    ['left', 'side-left', 'side-run-left'], ['legacy', 'front', 'reference-run']] as const) {
    scene.actors.push({ id, character: 'hoodie', view, scale: .5 });
    scene.clips.push({ ...structuredClone(scene.clips[0]), actor: id, action });
  }
  const result = validateScene(scene);
  assert(result.valid, JSON.stringify(result.diagnostics));
  assert.deepEqual(sampleFrame(result.scene!, 10).actors.map(a => a.action),
    ['front-run', 'side-run-right', 'side-run-left', 'reference-run']);
});
