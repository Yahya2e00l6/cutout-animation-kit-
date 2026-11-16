import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync, mkdtempSync, cpSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { sampleFrame, validateScene, toolkitRoot, type Scene } from '../src/scene.ts';

const example = (): Scene => JSON.parse(readFileSync(new URL('../../scenes/examples/dice-dongtae-courtyard.json', import.meta.url), 'utf8'));

test('DICE binds a separate registered character to shared scheduling', () => {
  const result = validateScene(example());
  assert(result.valid, JSON.stringify(result.diagnostics));
  assert(result.diagnostics.some(d => d.code === 'DICE_RETARGET_TRIAL'));
  const actor = sampleFrame(result.scene!, 40).actors[0];
  assert.equal(actor.character, 'dice-dongtae-upgraded');
  assert.equal(actor.travelMode, 'support-leg');
  assert(Math.abs(actor.speed - .625) < 1e-12);
});

test('hoodie scenes do not gain the DICE approval warning', () => {
  const scene = example(); scene.actors[0].character = 'hoodie';
  const result = validateScene(scene);
  assert(result.valid);
  assert(!result.diagnostics.some(d => d.code === 'DICE_RETARGET_TRIAL'));
});

test('DICE rejects a changed snapshot before scheduling', () => {
  const dir = mkdtempSync(join(tmpdir(), 'dice-snapshot-'));
  try {
    cpSync(join(toolkitRoot, 'characters/dice-dongtae-upgraded-side'), join(dir, 'characters/dice-dongtae-upgraded-side'), { recursive: true });
    writeFileSync(join(dir, 'characters/dice-dongtae-upgraded-side/character.svg'), '<svg/>');
    assert(validateScene(example(), dir).diagnostics.some(d => d.code === 'DICE_ASSET'));
  } finally { rmSync(dir, { recursive: true }); }
});
