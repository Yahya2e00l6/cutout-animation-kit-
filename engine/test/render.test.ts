import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtempSync, readFileSync, writeFileSync, existsSync, readdirSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { renderScene, verifyProbe } from '../src/render.ts';

const example = () => JSON.parse(readFileSync(new URL('../../scenes/examples/side-run-across.json', import.meta.url), 'utf8'));
const temp = () => mkdtempSync(join(process.env.TMPDIR || tmpdir(), 'cutout-export-test-'));
const media = () => ({ video: { width: 1280, height: 720, fps: 30, codec: 'h264', pix_fmt: 'yuv420p', nb_frames: 150, variable_frame_rate_suspected: false }, audio: null, duration: 5 });

test('output probe rejects wrong frame count, codec, size, rate, duration, pixels or audio', () => {
  const output = { width: 1280, height: 720, fps: 30 };
  verifyProbe(media(), output, 150);
  for (const [field, value] of Object.entries({ width: 640, height: 360, fps: 25, codec: 'hevc', pix_fmt: 'yuv444p', nb_frames: 151, variable_frame_rate_suspected: true })) {
    const probe = media(); (probe.video as any)[field] = value;
    assert.throws(() => verifyProbe(probe, output, 150));
  }
  assert.throws(() => verifyProbe({ ...media(), duration: 5.1 }, output, 150));
  assert.throws(() => verifyProbe({ ...media(), audio: { codec: 'aac' } }, output, 150));
});

test('export refuses any existing output folder without changing its files', () => {
  const dir = temp();
  try {
    const keep = join(dir, 'keep.txt'); writeFileSync(keep, 'keep');
    assert.throws(() => renderScene(JSON.stringify(example()), dir, { encode: false }), /EEXIST/);
    assert.deepEqual(readdirSync(dir), ['keep.txt']);
    assert.equal(readFileSync(keep, 'utf8'), 'keep');
  } finally { rmSync(dir, { recursive: true }); }
});

test('invalid scenes and oversized render requests write nothing', () => {
  const dir = temp();
  try {
    for (const mutate of [(s: any) => s.clips[0].action = 'rear-run', (s: any) => s.output.width = 8192, (s: any) => s.output.duration = 121]) {
      const source = example(); mutate(source);
      const output = join(dir, 'new');
      assert.throws(() => renderScene(JSON.stringify(source), output, { encode: false }));
      assert.equal(existsSync(output), false);
    }
  } finally { rmSync(dir, { recursive: true }); }
});

test('failed renderer preserves its failed report and travel warning', () => {
  const dir = temp();
  try {
    const output = join(dir, 'failed');
    assert.throws(() => renderScene(JSON.stringify(example()), output, { encode: false, python: join(dir, 'missing-python') }));
    const report = JSON.parse(readFileSync(join(output, 'report.json'), 'utf8'));
    assert.equal(report.status, 'failed');
    assert.equal(report.warnings[0].code, 'UNLOCKED_TRAVEL');
    assert.equal(existsSync(join(output, 'scene.mp4')), false);
  } finally { rmSync(dir, { recursive: true }); }
});

test('real Python bridge renders two deterministic frames and refuses reuse', () => {
  const dir = temp();
  try {
    const source = example();
    source.output = { width: 320, height: 180, fps: 30, duration: 2 / 30 };
    source.stage.groundY = 150; source.actors[0].scale = 0.2;
    source.clips[0].duration = 2 / 30;
    source.clips[0].travel = { from: [160, 150], to: [160, 150] };
    source.actors.push({ ...source.actors[0], id: 'left', view: 'side-left', scale: 0.15 });
    source.clips.push({ ...structuredClone(source.clips[0]), actor: 'left', action: 'side-run-left', travel: { from: [230, 150], to: [230, 150] } });
    const output = join(dir, 'first');
    const report = renderScene(JSON.stringify(source), output, { encode: false });
    assert.equal(report.status, 'frames-complete');
    assert.equal(JSON.parse(readFileSync(join(output, 'render-result.json'), 'utf8')).actionInstances, 2);
    assert.equal(existsSync(join(output, 'scene.mp4')), false);
    assert.deepEqual(readdirSync(join(output, 'frames')), ['frame_0000.png', 'frame_0001.png']);
    const second = join(dir, 'second');
    renderScene(JSON.stringify(source), second, { encode: false });
    for (const frame of ['frame_0000.png', 'frame_0001.png']) {
      assert.deepEqual(readFileSync(join(output, 'frames', frame)), readFileSync(join(second, 'frames', frame)));
    }
    assert.throws(() => renderScene(JSON.stringify(source), output, { encode: false }), /EEXIST/);
  } finally { rmSync(dir, { recursive: true }); }
});

test('real sequence encoder produces exactly two silent H.264 frames', () => {
  const dir = temp();
  try {
    const source = example();
    source.output = { width: 320, height: 180, fps: 30, duration: 2 / 30 };
    source.stage.groundY = 150; source.actors[0].scale = 0.2;
    source.clips[0].duration = 2 / 30;
    source.clips[0].travel = { from: [160, 150], to: [162, 150] };
    const output = join(dir, 'encoded');
    const report = renderScene(JSON.stringify(source), output);
    assert.equal(report.status, 'complete');
    assert.equal(report.warnings[0].code, 'UNLOCKED_TRAVEL');
    const probe = JSON.parse(readFileSync(join(output, 'probe.json'), 'utf8'));
    assert.equal(probe.video.nb_frames, 2);
    assert.equal(probe.audio, null);
    assert.equal(existsSync(join(output, 'encode-plan.json')), true);
    assert.equal(existsSync(join(output, 'encode-result.json')), true);
  } finally { rmSync(dir, { recursive: true }); }
});
