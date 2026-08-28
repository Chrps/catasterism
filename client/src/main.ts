/**
 * Step 1: the sky from Earth, rendered honestly.
 *
 * Camera is deliberately minimal here -- look around from the Sun, nothing more.
 * Flight controls are T6, and they are the harder problem: usable motion spans
 * ~1 AU to ~100 pc, a factor of 10^7 (PLAN.md §6.7).
 */

import { load } from "./format";
import { Renderer, type CameraState, type RenderSettings } from "./renderer";

const CATALOGUE_VERSION = "dr3-v1";
const TIER = "t0";

function fail(hud: HTMLElement, message: string): never {
  hud.textContent = message;
  hud.style.color = "#f66";
  throw new Error(message);
}

/**
 * Pick an exposure that puts the sky in range on the first frame.
 *
 * Free flight spans 10^20 in apparent brightness (PLAN.md §6.1), so there is no
 * universal constant here. Aim the *bright tail* at roughly 1.0 in the
 * accumulation buffer: bright enough that the familiar stars register, dim
 * enough that they do not all saturate into white blobs.
 */
function defaultExposure(
  positions: Float32Array,
  absoluteMagnitude: Float32Array,
  count: number,
  sigmaPx: number,
  targetPeak: number,
): number {
  const sample: number[] = [];
  const stride = Math.max(1, Math.floor(count / 20000));
  for (let i = 0; i < count; i += stride) {
    const d = Math.hypot(positions[i * 3]!, positions[i * 3 + 1]!, positions[i * 3 + 2]!);
    if (d > 0) sample.push(10 ** (-0.4 * absoluteMagnitude[i]!) / (d * d));
  }
  if (sample.length === 0) return 1;
  sample.sort((a, b) => a - b);
  const bright = sample[Math.floor(sample.length * 0.9995)] ?? sample[sample.length - 1]!;
  // Aim the *peak pixel* of a bright star at targetPeak, not its total flux.
  // The kernel spreads flux over 2*pi*sigma^2, so that area has to be undone
  // here or the brightest stars come out grey.
  return (targetPeak * 2 * Math.PI * sigmaPx * sigmaPx) / Math.max(bright, 1e-30);
}

async function main(): Promise<void> {
  const hud = document.getElementById("hud");
  if (!hud) throw new Error("missing #hud");
  const canvas = document.getElementById("view");
  if (!(canvas instanceof HTMLCanvasElement)) fail(hud, "missing #view canvas");

  const gl = canvas.getContext("webgl2", { antialias: false, depth: false, alpha: false });
  if (!gl) fail(hud, "WebGL2 unavailable — this browser cannot run Catasterism");

  // Not a downgrade path: without float render targets the HDR accumulation in
  // PLAN.md §6.1 is impossible, and an LDR fallback would render a different sky.
  if (!gl.getExtension("EXT_color_buffer_float")) {
    fail(hud, "EXT_color_buffer_float unavailable — HDR accumulation impossible");
  }

  hud.textContent = "loading catalogue…";
  const started = performance.now();
  const stars = await load(`${CATALOGUE_VERSION}-${TIER}`);
  const loadMs = performance.now() - started;

  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const sizeCanvas = (): void => {
    canvas.width = Math.max(1, Math.floor(canvas.clientWidth * dpr));
    canvas.height = Math.max(1, Math.floor(canvas.clientHeight * dpr));
  };
  sizeCanvas();

  const renderer = new Renderer(gl, stars, canvas.width, canvas.height);

  const camera: CameraState = {
    position: [0, 0, 0], // at the Sun; this is the exactly-correct view (PLAN.md §2)
    yaw: 0,
    pitch: 0,
    fovYRadians: (60 * Math.PI) / 180,
  };
  const sigmaPx = 1.1;
  const settings: RenderSettings = {
    exposure: defaultExposure(stars.positions, stars.absoluteMagnitude, stars.count, sigmaPx, 3),
    saturation: 1, // physically honest default; PLAN.md §4.2
    minSizePx: 2,
    maxSizePx: 64,
    sizeGain: 5,
    sigmaPx,
  };

  let dragging = false;
  canvas.addEventListener("pointerdown", (e) => {
    dragging = true;
    canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener("pointerup", (e) => {
    dragging = false;
    canvas.releasePointerCapture(e.pointerId);
  });
  canvas.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    camera.yaw -= e.movementX * 0.003;
    const limit = Math.PI / 2 - 0.001;
    camera.pitch = Math.max(-limit, Math.min(limit, camera.pitch - e.movementY * 0.003));
  });
  window.addEventListener("keydown", (e) => {
    if (e.key === "+" || e.key === "=") settings.exposure *= 1.6;
    else if (e.key === "-" || e.key === "_") settings.exposure /= 1.6;
    else if (e.key === "[") settings.saturation = Math.max(0, settings.saturation - 0.25);
    else if (e.key === "," ) settings.sizeGain = Math.max(0, settings.sizeGain - 1);
    else if (e.key === "." ) settings.sizeGain = Math.min(32, settings.sizeGain + 1);
    else if (e.key === "]") settings.saturation = Math.min(8, settings.saturation + 0.25);
    else return;
    e.preventDefault();
  });
  window.addEventListener("resize", sizeCanvas);

  let frames = 0;
  let fpsWindowStart = performance.now();
  let fps = 0;

  const frame = (): void => {
    sizeCanvas();
    renderer.resize(canvas.width, canvas.height);
    renderer.render(camera, settings);

    frames++;
    const now = performance.now();
    if (now - fpsWindowStart >= 500) {
      fps = (frames * 1000) / (now - fpsWindowStart);
      frames = 0;
      fpsWindowStart = now;
      hud.textContent = [
        `catasterism · ${stars.manifest.catalogue_version}`,
        `${stars.count.toLocaleString()} stars · loaded in ${loadMs.toFixed(0)} ms`,
        `${fps.toFixed(0)} fps · ${canvas.width}×${canvas.height}`,
        `exposure ${settings.exposure.toExponential(2)}  [+/-]`,
        `saturation ${settings.saturation.toFixed(2)}  [ [ / ] ]`,
        `size gain ${settings.sizeGain.toFixed(0)}  [ , / . ]`,
        `drag to look around`,
      ].join("\n");
    }
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}

main().catch((e: unknown) => {
  const hud = document.getElementById("hud");
  if (hud) {
    hud.textContent = `failed: ${e instanceof Error ? e.message : String(e)}`;
    hud.style.color = "#f66";
  }
  throw e;
});
