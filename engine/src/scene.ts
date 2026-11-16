import { readFileSync, statSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { Ajv } from 'ajv';
import { parseTree, type Node as JsonNode, type ParseError } from 'jsonc-parser';

export const toolkitRoot = fileURLToPath(new URL('../../', import.meta.url));
const schema = JSON.parse(readFileSync(new URL('../../schemas/scene.schema.json', import.meta.url), 'utf8'));
const structuralCheck = new Ajv({ allErrors: true, strict: true }).compile(schema);
const pointer = (key: string) => key.replaceAll('~', '~0').replaceAll('/', '~1');

export type Diagnostic = {
  severity: 'error' | 'warning'; code: string; path: string; message: string;
};
export type Point = [number, number];
export type Actor = {
  id: string; character: 'hoodie'; view: 'side-right' | 'side-left'; scale: number;
};
export type Clip = {
  actor: string; action: 'side-run-right' | 'side-run-left';
  start: number; duration: number; speed: number | 'auto'; footLock?: boolean; travel: { from: Point; to: Point };
  transitions?: { standBefore: number; start: number; stop: number; standAfter: number };
};
export type Scene = {
  version: 1;
  output: { width: number; height: number; fps: 30; duration: number };
  stage: { background: string; groundY: number };
  actors: Actor[]; clips: Clip[];
};
type ScheduledClip = Omit<Clip, 'speed'> & { speed: number; index: number; startFrame: number; durationFrames: number };
type Plan = {
  output: Scene['output']; stage: Scene['stage']; actors: Actor[];
  clips: ScheduledClip[]; frameCount: number; sourceAnchor: Point;
  warnings: Diagnostic[];
};
// Plans are opaque snapshots. Only a successful validator can produce one.
const plans = new WeakMap<PreparedScene, Plan>();
const preparedTag = Symbol('validated scene');
export type PreparedScene = { readonly [preparedTag]: true };
function prepare(plan: Plan): PreparedScene {
  const handle = Object.freeze({ [preparedTag]: true as const });
  plans.set(handle, structuredClone(plan));
  return handle;
}
export type ValidationResult = {
  valid: boolean; diagnostics: Diagnostic[]; scene?: PreparedScene; frameCount?: number;
};

/** Parse strict JSON, including a duplicate-key check before JSON.parse loses keys. */
export function parseScene(text: string): { value?: unknown; diagnostics: Diagnostic[] } {
  const diagnostics: Diagnostic[] = [];
  let value: unknown;
  try { value = JSON.parse(text); }
  catch (error) {
    return { diagnostics: [{ severity: 'error', code: 'JSON_INVALID', path: '', message: String(error) }] };
  }
  const errors: ParseError[] = [];
  const tree = parseTree(text, errors, { disallowComments: true, allowTrailingComma: false });
  if (!tree || errors.length) {
    return { diagnostics: [{ severity: 'error', code: 'JSON_INVALID', path: '', message: 'Invalid strict JSON.' }] };
  }
  function walk(node: JsonNode, path: string): void {
    if (node.type === 'object') {
      const keys = new Set<string>();
      for (const property of node.children ?? []) {
        const [key, child] = property.children!;
        const name = key.value as string;
        const next = `${path}/${pointer(name)}`;
        if (keys.has(name)) diagnostics.push({ severity: 'error', code: 'JSON_DUPLICATE_KEY', path: next, message: `Duplicate key: ${name}` });
        keys.add(name);
        walk(child, next);
      }
    } else if (node.type === 'array') {
      node.children?.forEach((child, index) => walk(child, `${path}/${index}`));
    }
  }
  walk(tree, '');
  return diagnostics.length ? { diagnostics } : { value, diagnostics };
}

/** Check schema, scheduling, bindings and actual source files without loading a rig. */
export function validateScene(value: unknown, root = toolkitRoot): ValidationResult {
  if (!structuralCheck(value)) {
    return { valid: false, diagnostics: (structuralCheck.errors ?? []).map(error => ({
      severity: 'error', code: 'SCHEMA_INVALID',
      path: error.instancePath + (error.keyword === 'additionalProperties' ? `/${pointer(error.params.additionalProperty)}` :
        error.keyword === 'required' ? `/${pointer(error.params.missingProperty)}` : ''),
      message: error.message ?? 'Invalid scene structure.',
    })) };
  }
  const scene = value as Scene;
  const diagnostics: Diagnostic[] = [];
  const error = (code: string, path: string, message: string) => diagnostics.push({ severity: 'error', code, path, message });
  const frames = (seconds: number, path: string, positive: boolean): number => {
    const raw = seconds * scene.output.fps;
    const count = Math.round(raw);
    if (!Number.isSafeInteger(count) || Math.abs(raw - count) > 1e-6 || (positive && count < 1)) {
      error('FRAME_ALIGNMENT', path, 'Time must resolve to a safe whole frame count (tolerance 1e-6 frames).');
      return 0;
    }
    return count;
  };
  const frameCount = frames(scene.output.duration, '/output/duration', true);
  if (!Number.isSafeInteger(scene.output.width) || !Number.isSafeInteger(scene.output.height)) {
    error('NUMERIC_RANGE', '/output', 'Dimensions must be safe integers.');
  }
  if (scene.stage.groundY > scene.output.height) error('GROUND_RANGE', '/stage/groundY', 'Ground must be inside the canvas.');
  const actors = new Map<string, Actor>();
  scene.actors.forEach((actor, index) => {
    if (actors.has(actor.id)) error('DUPLICATE_ACTOR', `/actors/${index}/id`, 'Actor ID must be unique.');
    actors.set(actor.id, actor);
  });
  const requiredFiles = [
    'characters/hoodie-side/character.svg', 'characters/hoodie-side/rig.json',
    'poses/side-run.json', 'motions/side-run.json', 'tools/side_actions.py',
    ...(scene.clips.some(clip => clip.transitions) ? ['poses/side-stand.json'] : []),
  ];
  for (const file of requiredFiles) {
    try { if (!statSync(resolve(root, file)).isFile()) throw new Error('Not a file'); }
    catch { error('ASSET_MISSING', '', `Required toolkit file missing: ${file}`); }
  }
  let sourceAnchor: Point = [640, 650];
  if (scene.clips.some(clip => clip.transitions) && !diagnostics.some(item => item.code === 'ASSET_MISSING')) {
    try {
      const standing = JSON.parse(readFileSync(resolve(root, 'poses/side-stand.json'), 'utf8'));
      const running = JSON.parse(readFileSync(resolve(root, 'poses/side-run.json'), 'utf8'));
      if (standing.version !== 1 || !standing.angles || typeof standing.angles !== 'object' || Array.isArray(standing.angles) ||
          JSON.stringify(Object.keys(standing.angles).sort()) !== JSON.stringify(Object.keys(running.poses[0].angles).sort()) ||
          !Object.values(standing.angles).every(Number.isFinite)) throw new Error('Invalid standing pose');
    } catch { error('STANDING_POSE', '', 'Standing pose must contain finite angles matching the saved side-run joints.'); }
  }
  let sourceWidth = 1280;
  let sourceHeight = 720;
  let cycle = 0.625;
  if (!diagnostics.some(item => item.code === 'ASSET_MISSING')) {
    try {
      const config = JSON.parse(readFileSync(resolve(root, 'motions/side-run.json'), 'utf8'));
      if (![config.width, config.height, config.floor, config.cycle].every(Number.isFinite) ||
          config.width <= 0 || config.height <= 0 || config.cycle <= 0 || config.fps !== 30) throw new Error('Invalid saved config');
      sourceAnchor = [config.width / 2, config.floor];
      sourceWidth = config.width; sourceHeight = config.height; cycle = config.cycle;
    } catch { error('ASSET_INVALID', '', 'Saved side-run configuration is invalid.'); }
  }
  let pixelsPerCycle = 0;
  if (scene.clips.some(clip => clip.footLock)) {
    try {
      const calibration = JSON.parse(readFileSync(resolve(root, 'motions/side-run-travel.json'), 'utf8'));
      if (calibration.version !== 1 || calibration.marker !== 'toe' || calibration.baseCycle !== cycle ||
          calibration.stanceEndPhase !== 0.26 || !Number.isFinite(calibration.pixelsPerCycle) || calibration.pixelsPerCycle <= 0) throw new Error('Invalid travel calibration');
      for (const file of requiredFiles.slice(0, 4)) {
        const actual = createHash('sha256').update(readFileSync(resolve(root, file))).digest('hex');
        if (calibration.sources[file] !== actual) throw new Error('Stale travel calibration');
      }
      pixelsPerCycle = calibration.pixelsPerCycle;
    } catch { error('TRAVEL_CALIBRATION', '', 'Travel calibration is missing, invalid or does not match the saved source files.'); }
  }
  for (const [index, actor] of scene.actors.entries()) {
    if (![sourceWidth * actor.scale, sourceHeight * actor.scale, ...sourceAnchor.map(n => n * actor.scale)].every(Number.isFinite)) {
      error('NUMERIC_RANGE', `/actors/${index}/scale`, 'Scaled source canvas must remain finite.');
    }
  }
  const clips: ScheduledClip[] = scene.clips.map((clip, index) => {
    const path = `/clips/${index}`;
    const startFrame = frames(clip.start, `${path}/start`, false);
    const durationFrames = frames(clip.duration, `${path}/duration`, true);
    const actor = actors.get(clip.actor);
    if (!actor) error('ACTOR_UNKNOWN', `${path}/actor`, 'Clip refers to an unknown actor.');
    else if (clip.action !== (actor.view === 'side-right' ? 'side-run-right' : 'side-run-left')) {
      error('ACTION_VIEW_MISMATCH', `${path}/action`, 'Action does not match the actor view.');
    }
    if (!Number.isSafeInteger(startFrame + durationFrames) || startFrame + durationFrames > frameCount) {
      error('CLIP_RANGE', path, 'Clip ends outside the output duration.');
    }
    const [x0, y0] = clip.travel.from;
    const [x1, y1] = clip.travel.to;
    const dx = x1 - x0;
    const transitionDuration = clip.transitions ? Object.values(clip.transitions).reduce((a, b) => a + b, 0) : 0;
    const runDuration = clip.duration - transitionDuration;
    if (clip.transitions) {
      for (const [name, seconds] of Object.entries(clip.transitions)) frames(seconds, `${path}/transitions/${name}`, true);
      if (!Number.isFinite(runDuration) || runDuration * scene.output.fps < 1 - 1e-6) error('TRANSITION_RANGE', `${path}/transitions`, 'Transitions must leave at least one running frame.');
      if (!clip.footLock) error('TRANSITION_MODE', `${path}/transitions`, 'Transition trial requires footLock: true.');
      diagnostics.push({ severity: 'warning', code: 'TRANSITION_TRIAL', path: `${path}/transitions`, message: 'Velocity-matched standing blends plant one toe and preserve the middle run. Grounding and acting still need playback review; this is not physical simulation.' });
    }
    let speed = typeof clip.speed === 'number' ? clip.speed : 1;
    if (clip.speed === 'auto' && !clip.footLock) error('CADENCE_MODE', `${path}/speed`, 'Automatic cadence requires footLock: true.');
    if (clip.footLock) {
      if (dx === 0) error('TRAVEL_REQUIRED', `${path}/footLock`, 'Foot locking requires nonzero horizontal travel.');
      const matched = actor && pixelsPerCycle > 0 ? Math.abs(dx / runDuration) * cycle / (pixelsPerCycle * actor.scale) : 0;
      if (!Number.isFinite(matched) || matched < 0.2 || matched > 2) error('CADENCE_RANGE', `${path}/speed`, 'Matched cadence must be between 0.2 and 2 times the saved cadence. Change distance, duration or actor scale.');
      if (clip.speed === 'auto') speed = matched;
      else if (matched && Math.abs(speed / matched - 1) > 0.05) error('CADENCE_MISMATCH', `${path}/speed`, 'Explicit cadence differs from travel-matched cadence by more than 5%; use speed: "auto".');
      diagnostics.push({ severity: 'warning', code: 'POSE_PRESERVING_TRAVEL', path: `${path}/footLock`, message: 'Experimental toe-X anchoring alters body travel, not poses. Shoe roll and natural motion still need visual review.' });
    }
    if (clip.transitions && runDuration > 0) {
      const halfCycles = runDuration * speed / cycle * 2;
      if (!Number.isFinite(halfCycles) || Math.abs(halfCycles - Math.round(halfCycles)) > 1e-6) error('TRANSITION_CONTACT', `${path}/travel`, 'The running interval must end at a touchdown (a whole half-cycle). Adjust distance or explicit cadence.');
    }
    if (Math.abs(y0 - scene.stage.groundY) > 1e-6 || Math.abs(y1 - scene.stage.groundY) > 1e-6) {
      error('TRAVEL_GROUND', `${path}/travel`, 'Travel endpoints must lie on stage.groundY.');
    }
    if (actor && ((actor.view === 'side-right' && dx < 0) || (actor.view === 'side-left' && dx > 0))) {
      error('TRAVEL_FACING', `${path}/travel`, 'Travel goes against the actor facing.');
    }
    if (!clip.footLock && (x0 !== x1 || y0 !== y1)) diagnostics.push({ severity: 'warning', code: 'UNLOCKED_TRAVEL', path: `${path}/travel`, message: 'Travel has no horizontal foot locking; sliding and cadence need visual review.' });
    if (![dx, clip.duration * speed, clip.duration * speed / cycle, cycle / speed].every(Number.isFinite) ||
        clip.duration * speed <= 0 || cycle / speed <= 0 ||
        (actor && ![x0, x1].flatMap(x => [x - actor.scale * sourceAnchor[0], x + actor.scale * (sourceWidth - sourceAnchor[0])]).concat(
          [y0, y1].flatMap(y => [y - actor.scale * sourceAnchor[1], y + actor.scale * (sourceHeight - sourceAnchor[1])])
        ).every(Number.isFinite))) {
      error('NUMERIC_RANGE', path, 'Travel, cadence and placement calculations must remain finite and representable.');
    }
    return { ...clip, speed, index, startFrame, durationFrames };
  });
  for (const actor of actors.values()) {
    const ordered = clips.filter(clip => clip.actor === actor.id).sort((a, b) => a.startFrame - b.startFrame);
    let end = -1;
    for (const clip of ordered) {
      if (clip.startFrame < end) error('CLIP_OVERLAP', `/clips/${clip.index}`, 'Clips for the same actor overlap.');
      end = Math.max(end, clip.startFrame + clip.durationFrames);
    }
  }
  if (diagnostics.some(item => item.severity === 'error')) return { valid: false, diagnostics };
  const prepared = prepare({
    output: scene.output, stage: scene.stage, actors: scene.actors, clips,
    frameCount, sourceAnchor, warnings: diagnostics,
  });
  return { valid: true, diagnostics, frameCount, scene: prepared };
}

export function loadScene(text: string, root = toolkitRoot): ValidationResult {
  const parsed = parseScene(text);
  return parsed.diagnostics.length ? { valid: false, diagnostics: parsed.diagnostics } : validateScene(parsed.value, root);
}

export function sampleScene(scene: PreparedScene, time: number) {
  const plan = plans.get(scene);
  if (!plan) throw new TypeError('Sampling requires a successfully validated scene.');
  const { fps } = plan.output;
  if (!Number.isFinite(time) || time < 0 || time >= plan.frameCount / fps) throw new RangeError('Sample time is outside the half-open scene duration.');
  // Snap only floating-point roundoff near an integer frame, not arbitrary subframes.
  let frame = time * fps;
  const nearest = Math.round(frame);
  if (nearest < plan.frameCount && Math.abs(frame - nearest) <= Number.EPSILON * Math.max(1, Math.abs(frame)) * 8) frame = nearest;
  const visible = plan.actors.flatMap((actor, drawOrder) => {
    const clip = plan.clips.find(clip => clip.actor === actor.id && frame >= clip.startFrame && frame < clip.startFrame + clip.durationFrames);
    if (!clip) return [];
    const elapsedFrame = frame - clip.startFrame;
    const tr = clip.transitions;
    const beforeFrames = tr ? Math.round(tr.standBefore * fps) : 0;
    const startFrames = tr ? Math.round(tr.start * fps) : 0;
    const stopFrames = tr ? Math.round(tr.stop * fps) : 0;
    const afterFrames = tr ? Math.round(tr.standAfter * fps) : 0;
    const runFrames = clip.durationFrames - beforeFrames - startFrames - stopFrames - afterFrames;
    const runDuration = runFrames / fps;
    const runStartFrame = beforeFrames + startFrames;
    const runEndFrame = runStartFrame + runFrames;
    const localTime = Math.max(0, Math.min(runFrames, elapsedFrame - runStartFrame)) / fps;
    const smooth = (u: number) => u * u * (3 - 2 * u);
    let transition: { mode: 'start' | 'stop' | 'stand'; weight: number; progress?: number; duration?: number } | undefined;
    if (tr && elapsedFrame < runStartFrame) transition = elapsedFrame < beforeFrames
      ? { mode: 'stand', weight: 0 }
      : { mode: 'start', weight: smooth((elapsedFrame - beforeFrames) / startFrames),
          progress: (elapsedFrame - beforeFrames) / startFrames, duration: startFrames / fps };
    if (tr && elapsedFrame >= runEndFrame) transition = elapsedFrame < runEndFrame + stopFrames
      ? { mode: 'stop', weight: 1 - smooth((elapsedFrame - runEndFrame) / stopFrames),
          progress: (elapsedFrame - runEndFrame) / stopFrames, duration: stopFrames / fps }
      : { mode: 'stand', weight: 0 };
    const u = tr ? localTime / runDuration : elapsedFrame / clip.durationFrames;
    const position: Point = [
      clip.travel.from[0] + u * (clip.travel.to[0] - clip.travel.from[0]),
      clip.travel.from[1] + u * (clip.travel.to[1] - clip.travel.from[1]),
    ];
    return [{
      id: actor.id, character: actor.character, view: actor.view, drawOrder,
      clipIndex: clip.index, action: clip.action, localTime,
      duration: clip.durationFrames / fps, speed: clip.speed,
      ...(transition ? { transition } : {}),
      ...(clip.footLock ? { footLock: true, travelVelocity: (clip.travel.to[0] - clip.travel.from[0]) / runDuration } : {}),
      position, scale: actor.scale, sourceAnchor: [...plan.sourceAnchor],
      // SVG affine matrix [a,b,c,d,e,f], without applying facing a second time.
      transform: [actor.scale, 0, 0, actor.scale, position[0] - actor.scale * plan.sourceAnchor[0], position[1] - actor.scale * plan.sourceAnchor[1]],
    }];
  });
  return { time, output: { ...plan.output }, stage: { ...plan.stage }, actors: visible, warnings: structuredClone(plan.warnings) };
}

export function sampleFrame(scene: PreparedScene, frameIndex: number) {
  const plan = plans.get(scene);
  if (!plan) throw new TypeError('Sampling requires a successfully validated scene.');
  if (!Number.isSafeInteger(frameIndex) || frameIndex < 0 || frameIndex >= plan.frameCount) throw new RangeError('Frame index is outside the scene.');
  return sampleScene(scene, frameIndex / plan.output.fps);
}
