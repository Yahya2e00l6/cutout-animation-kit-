import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { Ajv } from 'ajv';

const schema = JSON.parse(readFileSync(new URL('../../schemas/svg-rig.schema.json', import.meta.url), 'utf8'));
const check = new Ajv({ strict: true, allErrors: true }).compile(schema);
const setup = JSON.parse(readFileSync(new URL('../../examples/svg-setup/compact.setup.json', import.meta.url), 'utf8'));
const rig = { ...setup, type: 'svg-side-rig', source: 'character.svg', sha256: 'a'.repeat(64) };

test('generic SVG rig contract compiles and accepts a complete explicit setup', () => {
  assert(check(rig), JSON.stringify(check.errors));
});

test('generic rig contract rejects unknown properties, missing parts, wrong views and duplicate layers', () => {
  for (const mutate of [(r: any) => { r.misspelled = true; }, (r: any) => { delete r.parts.head; },
    (r: any) => { r.view = 'front'; }, (r: any) => { r.layers[0] = r.layers[1]; },
    (r: any) => { r.joints.neck = [null, 0]; }, (r: any) => { r.source = '../../source.svg'; }]) {
    const bad = structuredClone(rig); mutate(bad);
    assert(!check(bad));
  }
});
