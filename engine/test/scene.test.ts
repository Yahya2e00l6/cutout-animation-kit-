import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync, mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { spawnSync } from 'node:child_process';
import { loadScene, parseScene, sampleFrame, sampleScene, validateScene, type Scene, type PreparedScene } from '../src/scene.ts';

const example = (): Scene => JSON.parse(readFileSync(new URL('../../scenes/examples/side-run-across.json', import.meta.url), 'utf8'));
const text = () => JSON.stringify(example());
const codes = (value: unknown) => validateScene(value).diagnostics.map(d => d.code);
function valid(scene = example()) {
  const result = validateScene(scene);
  assert.equal(result.valid, true, JSON.stringify(result.diagnostics));
  return result.scene!;
}

test('schema itself compiles; example validates with travel warning and 150 frames', () => {
  const result = loadScene(text());
  assert.equal(result.valid, true);
  assert.equal(result.frameCount, 150);
  assert.deepEqual(result.diagnostics.map(d => [d.code, d.path]), [['UNLOCKED_TRAVEL', '/clips/0/travel']]);
});

test('strict parsing rejects duplicate keys including escaped names and nested objects', () => {
  for (const source of ['{"a":1,"a":2}', '{"a":1,"\\u0061":2}', '{"x":[{"a/b":1,"a/b":2}]}']) {
    assert.equal(parseScene(source).diagnostics[0].code, 'JSON_DUPLICATE_KEY');
    assert.equal(loadScene(source).valid, false);
  }
  assert.equal(parseScene('{"x":[{"a/b":1,"a/b":2}]}').diagnostics[0].path, '/x/0/a~1b');
  assert.deepEqual(parseScene('{"a":1,"x":{"a":2}}').diagnostics, []);
});

test('strict JSON rejects comments, trailing commas, NaN, Infinity and trailing tokens', () => {
  for (const source of ['{"x":NaN}', '{"x":Infinity}', '{"x":1,}', '/*x*/{}', '{} {}', '']) {
    assert.equal(loadScene(source).diagnostics[0].code, 'JSON_INVALID');
  }
  assert.equal(loadScene(text().replace('"speed":1', '"speed":1e999')).valid, false);
});

const structuralCases: [string, (scene: any) => void][] = [
  ['unknown field', s => s.typo = true],
  ['nested typo', s => s.clips[0].speeed = 2],
  ['missing field', s => delete s.stage],
  ['version', s => s.version = 2],
  ['odd dimension', s => s.output.width = 1279],
  ['fps', s => s.output.fps = 24],
  ['invalid color', s => s.stage.background = 'white'],
  ['zero scale', s => s.actors[0].scale = 0],
  ['zero duration', s => s.clips[0].duration = 0],
  ['negative start', s => s.clips[0].start = -1],
  ['boolean speed', s => s.clips[0].speed = true],
  ['nonfinite speed', s => s.clips[0].speed = Infinity],
  ['nonfinite point', s => s.clips[0].travel.from[0] = NaN],
  ['malformed point', s => s.clips[0].travel.to = [1]],
  ['unknown action', s => s.clips[0].action = 'rear-run'],
  ['unknown view', s => s.actors[0].view = 'rear'],
  ['unknown character', s => s.actors[0].character = 'other'],
  ['empty actors', s => s.actors = []],
];
for (const [name, mutate] of structuralCases) test(`schema rejects ${name}`, () => {
  const scene = example(); mutate(scene);
  assert(codes(scene).includes('SCHEMA_INVALID'));
});

const semanticCases: [string, string, (scene: Scene) => void][] = [
  ['duplicate IDs', 'DUPLICATE_ACTOR', s => s.actors.push({ ...s.actors[0] })],
  ['unknown actor', 'ACTOR_UNKNOWN', s => s.clips[0].actor = 'missing'],
  ['view mismatch', 'ACTION_VIEW_MISMATCH', s => s.actors[0].view = 'side-left'],
  ['fractional output frames', 'FRAME_ALIGNMENT', s => s.output.duration = 5.01],
  ['fractional clip frames', 'FRAME_ALIGNMENT', s => s.clips[0].duration = 1.01],
  ['fractional start frames', 'FRAME_ALIGNMENT', s => s.clips[0].start = 0.01],
  ['subframe positive duration', 'FRAME_ALIGNMENT', s => s.clips[0].duration = 1e-12],
  ['unsafe frame count', 'FRAME_ALIGNMENT', s => s.output.duration = 1e20],
  ['unsafe dimension', 'NUMERIC_RANGE', s => s.output.width = 1e20],
  ['end outside scene', 'CLIP_RANGE', s => s.clips[0].start = 1],
  ['ground outside canvas', 'GROUND_RANGE', s => s.stage.groundY = 721],
  ['vertical travel', 'TRAVEL_GROUND', s => s.clips[0].travel.to[1] = 619],
  ['opposite travel', 'TRAVEL_FACING', s => s.clips[0].travel.to[0] = 0],
  ['overflowed scale', 'NUMERIC_RANGE', s => s.actors[0].scale = 1e308],
  ['overflowed cadence', 'NUMERIC_RANGE', s => s.clips[0].speed = 1e308],
  ['overflowed travel', 'NUMERIC_RANGE', s => { s.clips[0].travel.from[0] = -1e308; s.clips[0].travel.to[0] = 1e308; }],
];
for (const [name, expected, mutate] of semanticCases) test(`semantic validation rejects ${name}`, () => {
  const scene = example(); mutate(scene);
  const result = validateScene(scene);
  assert.equal(result.valid, false);
  assert.equal(result.scene, undefined);
  assert(result.diagnostics.some(d => d.code === expected), JSON.stringify(result));
});

test('stationary travel is warning-free and left travel uses the existing facing', () => {
  const stationary = example(); stationary.clips[0].travel.to = [...stationary.clips[0].travel.from];
  assert.deepEqual(validateScene(stationary).diagnostics, []);
  const left = example();
  left.actors[0].view = 'side-left'; left.clips[0].action = 'side-run-left';
  [left.clips[0].travel.from, left.clips[0].travel.to] = [left.clips[0].travel.to, left.clips[0].travel.from];
  const actor = sampleScene(valid(left), 2.5).actors[0];
  assert.equal(actor.position[0], 640);
  assert.equal(actor.transform[0], 1); // no extra mirror
});

test('sampling returns independent expected endpoints, midpoint and local speed', () => {
  const scene = example(); scene.clips[0].speed = 2;
  const plan = valid(scene);
  const first = sampleFrame(plan, 0).actors[0];
  assert.deepEqual(first.position, [160, 620]);
  assert.deepEqual(first.transform, [1, 0, 0, 1, -480, -30]);
  const middle = sampleFrame(plan, 75).actors[0];
  assert.deepEqual(middle.position, [640, 620]);
  assert.equal(middle.localTime, 2.5); // cadence speed is not applied twice
  assert.equal(middle.speed, 2);
  assert(Math.abs(sampleFrame(plan, 149).actors[0].position[0] - 1113.6) < 1e-10);
  assert.equal(sampleScene(plan, 5 - Number.EPSILON * 4).actors.length, 1);
  assert.throws(() => sampleScene(plan, 5), RangeError);
});

test('unsorted adjacent clips choose the new clip exactly at the boundary', () => {
  const scene = example();
  scene.clips[0].duration = 1 / 30;
  scene.clips.push({ ...structuredClone(scene.clips[0]), start: 1 / 30, duration: 1, speed: 2 });
  scene.clips.reverse();
  const plan = valid(scene);
  assert.equal(sampleFrame(plan, 0).actors[0].speed, 1);
  assert.equal(sampleFrame(plan, 1).actors[0].speed, 2);
  assert.equal(sampleFrame(plan, 1).actors[0].localTime, 0);
  assert.deepEqual(sampleScene(plan, 2).actors, []);
  scene.clips[0].start = 0;
  assert(codes(scene).includes('CLIP_OVERLAP'));
});

test('same-actor nested and unsorted overlaps are rejected', () => {
  const scene = example();
  scene.clips.push({ ...structuredClone(scene.clips[0]), start: 1, duration: 1 });
  scene.clips.reverse();
  assert(codes(scene).includes('CLIP_OVERLAP'));
});

test('different actors overlap and retain actor-array draw order', () => {
  const scene = example();
  scene.actors.push({ ...scene.actors[0], id: 'second', scale: 0.5 });
  scene.clips.unshift({ ...structuredClone(scene.clips[0]), actor: 'second' });
  const frame = sampleFrame(valid(scene), 0);
  assert.deepEqual(frame.actors.map(a => [a.id, a.drawOrder]), [['runner', 0], ['second', 1]]);
  assert.deepEqual(frame.actors[1].transform, [0.5, 0, 0, 0.5, -160, 295]);
});

test('input, output and diagnostics mutations cannot change a prepared plan', () => {
  const scene = example(); const result = validateScene(scene); const plan = result.scene!;
  const expected = sampleFrame(plan, 75);
  scene.clips[0].travel.from[0] = 999;
  scene.actors[0].scale = 5;
  result.diagnostics[0].message = 'changed';
  const output = sampleFrame(plan, 75);
  output.actors[0].position[0] = 123;
  output.actors[0].sourceAnchor[0] = 123;
  output.warnings[0].message = 'changed';
  output.stage.background = '#000000';
  assert.deepEqual(sampleFrame(plan, 75), expected);
});

test('shuffled frame requests match sequential requests', () => {
  const plan = valid();
  const sequential = Array.from({ length: 150 }, (_, n) => sampleFrame(plan, n));
  for (let i = 0; i < 150; i++) {
    const index = (i * 73) % 150;
    assert.deepEqual(sampleFrame(plan, index), sequential[index]);
  }
});

test('out-of-range times, invalid indices and forged handles are rejected', () => {
  const plan = valid();
  for (const time of [-1, -Number.MIN_VALUE, 5, Infinity, NaN]) assert.throws(() => sampleScene(plan, time), RangeError);
  for (const index of [-1, 0.1, 150, Infinity, NaN]) assert.throws(() => sampleFrame(plan, index), RangeError);
  assert.throws(() => sampleFrame({} as PreparedScene, 0), TypeError);
});

test('missing and malformed assets are reported without modifying the toolkit', () => {
  const dir = mkdtempSync(join(process.env.TMPDIR || tmpdir(), 'cutout-scene-test-'));
  try {
    assert(validateScene(example(), dir).diagnostics.some(d => d.code === 'ASSET_MISSING'));
    for (const file of ['characters/hoodie-side/character.svg', 'characters/hoodie-side/rig.json', 'poses/side-run.json', 'motions/side-run.json', 'tools/side_actions.py']) {
      mkdirSync(dirname(join(dir, file)), { recursive: true }); writeFileSync(join(dir, file), 'invalid');
    }
    assert(validateScene(example(), dir).diagnostics.some(d => d.code === 'ASSET_INVALID'));
  } finally { rmSync(dir, { recursive: true }); }
});

test('CLI validates and samples, and rejects invalid invocation', () => {
  const cli = new URL('../src/cli.ts', import.meta.url);
  const path = new URL('../../scenes/examples/side-run-across.json', import.meta.url).pathname;
  for (const [args, status] of [
    [['validate', path], 0], [['sample', path, '75'], 0],
    [['sample', path, '150'], 1], [['sample', path, '-1'], 1],
    [['sample', path, ''], 1], [['validate', path, 'extra'], 1],
    [['validate', path + '.missing'], 1],
  ] as [string[], number][]) {
    const result = spawnSync(process.execPath, [cli.pathname, ...args], { encoding: 'utf8' });
    assert.equal(result.status, status, result.stderr);
    if (status === 0) JSON.parse(result.stdout);
  }
});
