import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { homedir } from 'node:os';
import { loadScene, sampleFrame, toolkitRoot, type Diagnostic, type Scene } from './scene.ts';

export type RenderOptions = { encode?: boolean; python?: string; skillDir?: string };
export type RenderReport = {
  status: 'rendering' | 'frames-complete' | 'complete' | 'failed';
  frameCount: number; output: Scene['output']; warnings: Diagnostic[];
  audio: 'none'; limitations: string[]; render?: unknown; video?: string; error?: string;
  background?: Scene['stage']['image'];
};
const timeout = 600_000;

/** Export exact sampled frames via one persistent Python action-rendering process. */
export function renderScene(text: string, output: string, options: RenderOptions = {}) {
  const result = loadScene(text);
  if (!result.valid) throw new Error(JSON.stringify({ diagnostics: result.diagnostics }));
  const first = sampleFrame(result.scene!, 0);
  // Resource bounds belong to this exporter, not the reusable scene language.
  if (first.output.width > 4096 || first.output.height > 4096 || result.frameCount! > 3600) {
    throw new Error('Initial exporter limit: dimensions <=4096 and at most 3600 frames.');
  }
  const source = JSON.parse(text);
  if (source.actors.length > 16) throw new Error('Initial exporter limit: at most 16 actors.');
  const directory = resolve(output);
  const python = options.python ?? 'python3';
  const skillDir = options.skillDir ?? join(homedir(), '.config/opencode/skills/ffmpeg/scripts');
  const run = (args: string[]) => execFileSync(python, ['-B', ...args], {
    cwd: toolkitRoot, encoding: 'utf8', timeout, maxBuffer: 32 * 1024 * 1024,
    env: process.env,
  });
  mkdirSync(dirname(directory), { recursive: true });
  mkdirSync(directory); // Atomic refusal of existing directories, files, and symlinks.
  const report: RenderReport = {
    status: 'rendering', frameCount: result.frameCount!, output: first.output,
    warnings: result.diagnostics, audio: 'none',
    ...(source.stage.image ? { background: source.stage.image } : {}),
    limitations: [source.clips.some((clip: { footLock?: boolean }) => clip.footLock)
      ? 'Experimental toe-X anchoring changes root travel; shoe roll remains.'
      : 'No horizontal foot locking or standing transitions.', 'Technical success is not motion or likeness approval.'],
  };
  if (source.clips.some((clip: { transitions?: unknown }) => clip.transitions)) {
    report.limitations.push('Standing blends match saved joint velocities at run joins and keep a toe anchored in X. Raster grounding can still change contact; this is not physical simulation or acting approval.');
  }
  if (source.clips.some((clip: { travelMode?: string }) => clip.travelMode === 'support-leg')) {
    report.limitations[0] = 'Foot locking changes root travel or leg poses according to the selected clip mode; shoe roll remains.';
    report.limitations.push('Support-leg IK releases airborne anchoring, keeps a soft support knee, and lifts released heels during recovery. Both leg chains change and hips may lower for reach. Middle-run body X follows the baseline; boundary ramps retain old start/stop motion. Shoe roll remains and unreachable targets fail.');
  }
  if (source.actors.some((actor: { character: string }) => actor.character === 'dice-dongtae-upgraded')) {
    report.limitations.push('DICE retarget preserves artwork and native bone lengths, not the donor leg angles or hip height. Extra hip lowering and measured shoe roll require playback review. Shared supportIK metrics describe the donor; diceRetarget metrics describe the delivered DICE solve.');
  }
  if (source.clips.some((clip: { action: string }) => clip.action === 'reference-run')) {
    if (source.clips.every((clip: { action: string }) => clip.action === 'reference-run')) {
      report.limitations[0] = 'Front run has in-place image-plane contacts, not scene travel or standing transitions.';
    }
    report.limitations.push('Front run preserves the saved projected gait, including axial limb foreshortening. Contact metrics use transformed model landmarks, not independent raster or real-world depth verification.');
  }
  const saveReport = () => writeFileSync(join(directory, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  saveReport();
  try {
    writeFileSync(join(directory, 'scene.json'), text, { flag: 'wx' });
    const samples = Array.from({ length: result.frameCount! }, (_, index) => sampleFrame(result.scene!, index));
    writeFileSync(join(directory, 'samples.json'), JSON.stringify({ version: 1, frameCount: result.frameCount, samples }) + '\n', { flag: 'wx' });
    report.render = JSON.parse(run(['-m', 'tools.render_scene', '--manifest', join(directory, 'samples.json'), '--out', directory]));
    const pngs = readdirSync(join(directory, 'frames')).filter(name => /^frame_\d+\.png$/.test(name));
    const svgs = readdirSync(join(directory, 'svg')).filter(name => /^frame_\d+\.svg$/.test(name));
    if (pngs.length !== result.frameCount || svgs.length !== result.frameCount) throw new Error('Rendered frame count mismatch.');
    report.status = 'frames-complete';
    saveReport();
    if (options.encode !== false) {
      const args = [join(toolkitRoot, 'tools/encode_sequence.py'), '--skill-dir', skillDir,
        '--dir', join(directory, 'frames'), '--pattern', 'frame_%04d.png', '--fps', String(first.output.fps),
        '-o', join(directory, 'scene.mp4'), '--json'];
      // Keep both the plan and the encoder's own verified output/probe data.
      writeFileSync(join(directory, 'encode-plan.json'), run([...args, '--dry-run']), { flag: 'wx' });
      writeFileSync(join(directory, 'encode-result.json'), run(args), { flag: 'wx' });
      const probe = JSON.parse(run([join(skillDir, 'probe.py'), join(directory, 'scene.mp4'), '--json']));
      writeFileSync(join(directory, 'probe.json'), JSON.stringify(probe, null, 2) + '\n', { flag: 'wx' });
      verifyProbe(probe, first.output, result.frameCount!);
      report.video = join(directory, 'scene.mp4');
      report.status = 'complete';
    }
    saveReport();
    return { ...report, directory };
  } catch (error) {
    report.status = 'failed';
    report.error = error instanceof Error ? error.message : String(error);
    saveReport();
    throw error;
  }
}

export function verifyProbe(probe: any, output: { width: number; height: number; fps: number }, frames: number): void {
  const media = probe.probe ?? probe;
  const video = media.video;
  if (!video || video.width !== output.width || video.height !== output.height ||
      video.fps !== output.fps || video.codec !== 'h264' || video.pix_fmt !== 'yuv420p' ||
      video.nb_frames !== frames || video.variable_frame_rate_suspected || media.audio ||
      !Number.isFinite(media.duration) || Math.abs(media.duration - frames / output.fps) > 1e-4) {
    throw new Error('Encoded video probe does not match the requested dimensions, duration, frame count, CFR fps, H.264/yuv420p codec or silent audio.');
  }
}
