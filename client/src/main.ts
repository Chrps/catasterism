/**
 * Step 1: the sky from Earth, rendered honestly.
 *
 * Camera is deliberately minimal here -- look around from the Sun, nothing more.
 * Flight controls are T6, and they are the harder problem: usable motion spans
 * ~1 AU to ~100 pc, a factor of 10^7 (PLAN.md §6.7).
 */

import { Camera, formatDistance } from "./camera";
import { load } from "./format";
import { Renderer, type RenderSettings } from "./renderer";

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

  const camera = new Camera(stars.positions, stars.count);

  // Overridable from the query string: ?saturation=4&exposure=1e5. Makes a
  // particular view shareable, and lets the headless harness exercise settings
  // that would otherwise need a keypress.
  const params = new URLSearchParams(window.location.search);
  const param = (name: string, fallback: number): number => {
    const raw = params.get(name);
    if (raw === null) return fallback;
    const value = Number(raw);
    return Number.isFinite(value) ? value : fallback;
  };

  const sigmaPx = param("sigma", 1.1);
  const baseExposure = defaultExposure(
    stars.positions, stars.absoluteMagnitude, stars.count, sigmaPx, 3,
  );
  const settings: RenderSettings = {
    exposure: param("exposure", baseExposure),
    saturation: param("saturation", 1), // physically honest default; PLAN.md §4.2
    minSizePx: 2,
    maxSizePx: 64,
    sizeGain: param("sizegain", 5),
    sigmaPx,
  };

  // --- input -------------------------------------------------------------
  const held = new Set<string>();
  const AXES: Record<string, [number, number, number]> = {
    w: [0, 0, 1], s: [0, 0, -1],
    a: [-1, 0, 0], d: [1, 0, 0],
    " ": [0, 1, 0], shift: [0, -1, 0],
  };

  // Pointer lock for flight, drag for a quick look around without committing.
  let dragging = false;
  canvas.addEventListener("pointerdown", (e) => {
    if (camera.mode === "flight") { void canvas.requestPointerLock(); return; }
    dragging = true;
    canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener("pointerup", (e) => {
    dragging = false;
    if (canvas.hasPointerCapture(e.pointerId)) canvas.releasePointerCapture(e.pointerId);
  });
  canvas.addEventListener("pointermove", (e) => {
    if (document.pointerLockElement === canvas || dragging) camera.look(e.movementX, e.movementY);
  });

  window.addEventListener("keyup", (e) => held.delete(e.key.toLowerCase()));
  window.addEventListener("blur", () => held.clear());
  window.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const key = e.key.toLowerCase();
    if (key in AXES) { held.add(key); e.preventDefault(); return; }
    switch (key) {
      case "z": settings.exposure /= 1.6; break;
      case "x": settings.exposure *= 1.6; break;
      case "c": settings.saturation = Math.max(0, settings.saturation - 0.25); break;
      case "v": settings.saturation = Math.min(8, settings.saturation + 0.25); break;
      case "b": settings.sizeGain = Math.max(0, settings.sizeGain - 1); break;
      case "n": settings.sizeGain = Math.min(32, settings.sizeGain + 1); break;
      case "f":
        camera.mode = camera.mode === "flight" ? "planetarium" : "flight";
        if (camera.mode !== "flight" && document.pointerLockElement === canvas) {
          document.exitPointerLock();
        }
        break;
      case "h": camera.returnHome(); break;
      case "r":
        settings.exposure = baseExposure;
        settings.saturation = 1;
        settings.sizeGain = 5;
        break;
      default: return;
    }
    e.preventDefault();
    refreshHud();
  });
  window.addEventListener("resize", sizeCanvas);

  // --- loop --------------------------------------------------------------
  let frames = 0;
  let fpsWindowStart = performance.now();
  let fps = 0;
  let previous = performance.now();

  const row = (label: string, value: string, keys: string): string =>
    `${label.padEnd(11)}${value.padEnd(14)}${keys}`;

  const refreshHud = (): void => {
    const flying = camera.mode === "flight";
    hud.textContent = [
      `catasterism · ${stars.manifest.catalogue_version}`,
      `${stars.count.toLocaleString()} stars · loaded in ${loadMs.toFixed(0)} ms`,
      `${fps.toFixed(0)} fps · ${canvas.width}×${canvas.height}`,
      "",
      row("mode", flying ? "flight" : "planetarium", "f"),
      row("from Sol", formatDistance(camera.distanceFromSolPc), ""),
      row("nearest", formatDistance(camera.nearest.distancePc), ""),
      row("speed", `${formatDistance(camera.speedPcPerSecond)}/s`, ""),
      "",
      row("move", flying ? "wasd space shift" : "—", ""),
      row("look", flying ? "mouse" : "drag", ""),
      row("home", "", "h"),
      "",
      row("exposure", settings.exposure.toExponential(2), "z / x"),
      row("saturation", settings.saturation.toFixed(2), "c / v"),
      row("star size", settings.sizeGain.toFixed(0), "b / n"),
      row("reset view", "", "r"),
    ].join("\n");
  };

  const frame = (): void => {
    const now = performance.now();
    const dt = Math.min((now - previous) / 1000, 0.1); // clamp, so a stall never teleports
    previous = now;

    const move: [number, number, number] = [0, 0, 0];
    for (const key of held) {
      const axis = AXES[key];
      if (axis) { move[0] += axis[0]; move[1] += axis[1]; move[2] += axis[2]; }
    }
    camera.update(move, dt);

    sizeCanvas();
    renderer.resize(canvas.width, canvas.height);
    renderer.render(camera, settings);

    frames++;
    if (now - fpsWindowStart >= 250) {
      fps = (frames * 1000) / (now - fpsWindowStart);
      frames = 0;
      fpsWindowStart = now;
      refreshHud();
    }
    requestAnimationFrame(frame);
  };
  refreshHud();
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
