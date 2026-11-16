import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync, mkdtempSync, mkdirSync, copyFileSync, writeFileSync, rmSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { tmpdir } from 'node:os';
import { sampleFrame, validateScene, toolkitRoot, type Scene } from '../src/scene.ts';

const example = (): Scene => JSON.parse(readFileSync(new URL('../../scenes/examples/front-run-in-place.json', import.meta.url), 'utf8'));
const frontFiles = ['characters/hoodie/character.svg', 'characters/hoodie/rig.json', 'motions/reference-run.json', 'tools/actions.py', 'tools/front_run.py'];

test('front run binds existing preset with stationary placement and unscaled local time', () => {
  const scene = example(); scene.clips[0].speed = 2;
  const result = validateScene(scene);
  assert(result.valid, JSON.stringify(result.diagnostics));
  assert.equal(result.frameCount, 120);
  const actor = sampleFrame(result.scene!, 60).actors[0];
  assert.equal(actor.action, 'reference-run');
  assert.equal(actor.view, 'front');
  assert.equal(actor.localTime, 2);
  assert.equal(actor.speed, 2);
  assert.deepEqual(actor.sourceAnchor, [640, 650]);
  assert.deepEqual(actor.transform, [1, 0, 0, 1, 0, 0]);
  assert(result.diagnostics.some(d => d.code === 'FRONT_RUN_IN_PLACE'));
  assert(!result.diagnostics.some(d => d.code === 'UNLOCKED_TRAVEL'));
});

for (const [name, change, code] of [
  ['lateral travel', (s: Scene) => { s.clips[0].travel.to[0] += 100; }, 'FRONT_TRAVEL'],
  ['depth travel', (s: Scene) => { s.clips[0].travel.to[1] -= 100; }, 'FRONT_TRAVEL'],
  ['automatic cadence', (s: Scene) => { s.clips[0].speed = 'auto'; }, 'FRONT_MODE'],
  ['side foot locking', (s: Scene) => { s.clips[0].footLock = true; }, 'FRONT_MODE'],
  ['side support solver', (s: Scene) => { s.clips[0].travelMode = 'support-leg'; }, 'FRONT_MODE'],
  ['standing transitions', (s: Scene) => { s.clips[0].transitions = { standBefore: .5, start: .5, stop: .5, standAfter: .5 }; }, 'FRONT_MODE'],
  ['DICE front fallback', (s: Scene) => { s.actors[0].character = 'dice-dongtae-upgraded'; }, 'CHARACTER_VIEW_MISMATCH'],
  ['wrong view', (s: Scene) => { s.actors[0].view = 'side-right'; }, 'ACTION_VIEW_MISMATCH'],
] as const) {
  test(`front run rejects ${name}`, () => {
    const scene = example(); change(scene);
    const result = validateScene(scene);
    assert(!result.valid);
    assert(result.diagnostics.some(d => d.code === code), JSON.stringify(result.diagnostics));
  });
}

test('front-only scenes need no side assets; mixed scenes keep per-action anchors', () => {
  const dir = mkdtempSync(join(tmpdir(), 'front-binding-'));
  const copy = (files: string[]) => {
    for (const file of files) {
      mkdirSync(dirname(join(dir, file)), { recursive: true });
      copyFileSync(join(toolkitRoot, file), join(dir, file));
    }
  };
  try {
    copy(frontFiles);
    const config = JSON.parse(readFileSync(join(dir, 'motions/reference-run.json'), 'utf8'));
    config.width = 1000; config.floor = 630;
    writeFileSync(join(dir, 'motions/reference-run.json'), JSON.stringify(config));
    const scene = example();
    const front = validateScene(scene, dir);
    assert(front.valid, JSON.stringify(front.diagnostics));
    assert.deepEqual(sampleFrame(front.scene!, 0).actors[0].sourceAnchor, [500, 630]);
    copy(['characters/hoodie-side/character.svg', 'characters/hoodie-side/rig.json', 'poses/side-run.json', 'motions/side-run.json', 'tools/side_actions.py']);
    scene.actors.push({ id: 'side', character: 'hoodie', view: 'side-right', scale: .5 });
    scene.clips.push({ ...structuredClone(scene.clips[0]), actor: 'side', action: 'side-run-right' });
    const mixed = validateScene(scene, dir);
    assert(mixed.valid, JSON.stringify(mixed.diagnostics));
    const actors = sampleFrame(mixed.scene!, 60).actors;
    assert.deepEqual(actors.map(actor => actor.sourceAnchor), [[500, 630], [640, 650]]);
    config.run.cycle = 0;
    writeFileSync(join(dir, 'motions/reference-run.json'), JSON.stringify(config));
    assert(validateScene(scene, dir).diagnostics.some(d => d.code === 'ASSET_INVALID'));
  } finally { rmSync(dir, { recursive: true }); }
});
