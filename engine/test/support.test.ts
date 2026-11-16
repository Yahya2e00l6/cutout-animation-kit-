import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { sampleFrame, validateScene, type Scene } from '../src/scene.ts';

const example = (): Scene => JSON.parse(readFileSync(new URL('../../scenes/examples/dice-courtyard-support-leg.json', import.meta.url), 'utf8'));

test('support-leg mode resolves matched cadence and discloses changed leg poses', () => {
  const result = validateScene(example());
  assert.equal(result.valid, true, JSON.stringify(result.diagnostics));
  const actor = sampleFrame(result.scene!, 40).actors[0];
  assert.equal(actor.travelMode, 'support-leg');
  assert(Math.abs(actor.speed - 0.625) < 1e-12);
  assert(result.diagnostics.some(d => d.code === 'SUPPORT_LEG_TRAVEL'));
  assert(!result.diagnostics.some(d => d.code === 'POSE_PRESERVING_TRAVEL'));
});

test('support-leg mode is opt-in; old scenes retain the previous adapter', () => {
  const source = example(); delete source.clips[0].travelMode;
  const result = validateScene(source);
  assert(result.valid);
  assert.equal(sampleFrame(result.scene!, 40).actors[0].travelMode, undefined);
  assert(result.diagnostics.some(d => d.code === 'POSE_PRESERVING_TRAVEL'));
  assert(!result.diagnostics.some(d => d.code === 'SUPPORT_LEG_TRAVEL'));
});

test('support-leg mode requires locking and rejects unknown modes', () => {
  const source = example(); source.clips[0].footLock = false;
  assert(validateScene(source).diagnostics.some(d => d.code === 'TRAVEL_MODE'));
  const invalid: any = example(); invalid.clips[0].travelMode = 'physics';
  assert(validateScene(invalid).diagnostics.some(d => d.code === 'SCHEMA_INVALID'));
});
