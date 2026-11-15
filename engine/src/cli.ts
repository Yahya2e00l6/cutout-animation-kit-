import { readFileSync } from 'node:fs';
import { loadScene, sampleFrame } from './scene.ts';
import { renderScene } from './render.ts';

function main(): void {
  const [command, file, frameText, ...extra] = process.argv.slice(2);
  if ((command === 'render' || command === 'export') && file && frameText && extra.length === 0) {
    console.log(JSON.stringify(renderScene(readFileSync(file, 'utf8'), frameText, { encode: command === 'export' }), null, 2));
    return;
  }
  if (!['validate', 'sample'].includes(command) || !file || extra.length ||
      (command === 'validate' && frameText !== undefined) ||
      (command === 'sample' && (frameText === undefined || !/^\d+$/.test(frameText)))) {
    throw new Error('Usage: npm run scene -- validate <scene.json> | sample <scene.json> <frame-index> | render <scene.json> <new-output-dir> | export <scene.json> <new-output-dir>');
  }
  const result = loadScene(readFileSync(file, 'utf8'));
  if (!result.valid) {
    console.log(JSON.stringify(result, null, 2));
    process.exitCode = 1;
    return;
  }
  console.log(JSON.stringify(command === 'sample' ? sampleFrame(result.scene!, Number(frameText)) : {
    valid: true, frameCount: result.frameCount, diagnostics: result.diagnostics,
  }, null, 2));
}
try { main(); }
catch (error) {
  console.error(JSON.stringify({ error: error instanceof Error ? error.message : String(error) }));
  process.exitCode = 1;
}
