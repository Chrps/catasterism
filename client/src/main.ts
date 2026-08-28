/**
 * Step 1: the sky from Earth, rendered honestly.
 *
 * Camera is deliberately minimal here -- look around from the Sun, nothing more.
 * Flight controls are T6, and they are the harder problem: usable motion spans
 * ~1 AU to ~100 pc, a factor of 10^7 (PLAN.md §6.7).
 */

import { Camera, formatDistance } from "./camera";
import { load } from "./format";
import { GALACTIC_CENTRE, SOL, Waypoints } from "./waypoints";
import { Renderer, type RenderSettings } from "./renderer";

const CATALOGUE_VERSION = "dr3-v1";
const TIER = "t0";

function fail(hud: HTMLElement, message: string): never {
  hud.textContent = message;
  hud.style.color = "#f66";
  throw new Error(message);
}

/**
 * Exposure that puts the current view in range.
 *
 * No fixed value survives flying at a star: at 1 AU the Sun is 4x10^10 times
 * brighter than the sky, whiting out every pixel it touches. So exposure has to
 * track the view rather than the catalogue -- aim the *bright tail* at a target
 * peak and recompute as the camera moves.
 *
 * Anything far below the resulting floor then vanishes, which is correct. You
 * cannot see stars in daylight either (PLAN.md 6.1).
 */
function exposureFor(brightFlux: number, sigmaPx: number, targetPeak: number): number {
  // Aim the *peak pixel* of a bright star at targetPeak, not its total flux:
  // the kernel spreads flux over 2*pi*sigma^2, and not undoing that area leaves
  // the brightest stars grey.
  return (targetPeak * 2 * Math.PI * sigmaPx * sigmaPx) / Math.max(brightFlux, 1e-30);
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
  const waypoints = new Waypoints(document.body, [SOL, GALACTIC_CENTRE]);

  const camera = new Camera(stars.positions, stars.absoluteMagnitude, stars.count);

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

  // Aim the camera from the query string, in degrees. Lets a specific patch of
  // sky be reproduced exactly, which is what the comparison against a real star
  // chart needs.
  camera.yaw = (param("yaw", 0) * Math.PI) / 180;
  camera.pitch = (param("pitch", 0) * Math.PI) / 180;
  camera.fovYRadians = (param("fov", 60) * Math.PI) / 180;

  const sigmaPx = param("sigma", 1.1);
  const TARGET_PEAK = 3;
  // The Earth view's brightnesses are fixed -- they do not change as the camera
  // moves, because they are what Gaia measured from one place. So its exposure
  // reference is computed once rather than tracked.
  const earthBright = ((): number => {
    const flux: number[] = [];
    for (let i = 0; i < stars.count; i++) {
      const m = stars.apparentMagnitude[i]!;
      if (Number.isFinite(m)) flux.push(10 ** (-0.4 * m));
    }
    flux.sort((a, b) => b - a);
    return flux[Math.min(47, flux.length - 1)] ?? 1;
  })();
  // A manual trim on top of the automatic value, rather than an absolute
  // setting -- otherwise the user is fighting the auto-exposure rather than
  // steering it.
  let exposureBias = param("bias", 1);
  // Remembers what saturation was before snapping to the physically accurate
  // value, so t is a toggle rather than a one-way trip.
  let saturationBeforeTrue = 2;
  const fixedExposure = params.has("exposure") ? param("exposure", 1) : null;

  const settings: RenderSettings = {
    exposure: 1,
    // Physically accurate is 1.0 and reads almost white (the Sun is CIELAB
    // C* 6.4). 2.0 keeps the real ordering of colours while making the blue and
    // amber ends actually legible -- exaggeration as a labelled choice, never
    // baked into the data (PLAN.md §4.2). Press c to see the honest version.
    saturation: param("saturation", 2),
    minSizePx: 2,
    maxSizePx: 64,
    sizeGain: param("sizegain", 1),
    sigmaPx,
    earthView: params.get("earth") === "1",
  };

  // --- input -------------------------------------------------------------
  const held = new Set<string>();
  const AXES: Record<string, [number, number, number]> = {
    w: [0, 0, 1], s: [0, 0, -1],
    a: [-1, 0, 0], d: [1, 0, 0],
    e: [0, 1, 0], " ": [0, 1, 0],
    q: [0, -1, 0],
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

  window.addEventListener("keyup", (e) => {
    held.delete(e.key.toLowerCase());
    if (e.key === "Shift") camera.precise = false;
  });
  window.addEventListener("blur", () => {
    held.clear();
    camera.precise = false;
  });
  window.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === "Shift") { camera.precise = true; refreshHud(); return; }
    const key = e.key.toLowerCase();
    if (key in AXES) { held.add(key); e.preventDefault(); return; }
    switch (key) {
      case "z": exposureBias /= 1.6; break;
      case "x": exposureBias *= 1.6; break;
      case "c": settings.saturation = Math.max(0, settings.saturation - 0.25); break;
      case "v": settings.saturation = Math.min(8, settings.saturation + 0.25); break;
      // Snap to physically accurate colour. Real stars are nearly white -- the
      // Sun sits at CIELAB C* 6.4 -- so 1.0 looks washed out next to what people
      // expect. Worth being able to see the truth in one keystroke rather than
      // stepping there and losing your place.
      case "t":
        if (settings.saturation === 1) {
          settings.saturation = saturationBeforeTrue;
        } else {
          saturationBeforeTrue = settings.saturation;
          settings.saturation = 1;
        }
        break;
      case "b": settings.sizeGain = Math.max(0, settings.sizeGain - 1); break;
      case "n": settings.sizeGain = Math.min(32, settings.sizeGain + 1); break;
      case "f":
        camera.mode = camera.mode === "flight" ? "planetarium" : "flight";
        if (camera.mode !== "flight" && document.pointerLockElement === canvas) {
          document.exitPointerLock();
        }
        break;
      // Fly rather than teleport: the journey is the part worth seeing.
      case "h": camera.flyTo(SOL.position); break;
      case "g": camera.flyTo(GALACTIC_CENTRE.position); break;
      // The Earth view only means anything from Earth, so it takes you there.
      case "p":
        settings.earthView = !settings.earthView;
        if (settings.earthView) camera.flyTo(SOL.position);
        break;
      case ",": camera.speedGain = Math.max(0.25, camera.speedGain / 1.5); break;
      case ".": camera.speedGain = Math.min(64, camera.speedGain * 1.5); break;
      case "r":
        exposureBias = 1;
        settings.saturation = 2;
        settings.sizeGain = 1;
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
    `${label.padEnd(11)}${value.padEnd(20)}${keys}`;

  const refreshHud = (): void => {
    const flying = camera.mode === "flight";
    hud.textContent = [
      `catasterism · ${stars.manifest.catalogue_version}`,
      `${stars.count.toLocaleString()} stars · loaded in ${loadMs.toFixed(0)} ms`,
      `${fps.toFixed(0)} fps · ${canvas.width}×${canvas.height}`,
      "",
      row("view", settings.earthView ? "as seen from Earth" : "intrinsic", "p"),
      row("mode", flying ? "flight" : "planetarium", "f"),
      row("from Sol", formatDistance(camera.distanceFromSolPc), ""),
      row("nearest", formatDistance(camera.nearest.distancePc), ""),
      // yaw and pitch ARE galactic longitude and latitude now that up is the
      // north galactic pole, so the camera can just say where it is looking.
      row(
        "looking at",
        `l ${(((camera.yaw * 180) / Math.PI) % 360 + 360) % 360 | 0}°  b ${((camera.pitch * 180) / Math.PI).toFixed(0)}°`,
        "",
      ),
      row("speed", `${formatDistance(camera.speedPcPerSecond)}/s${camera.precise ? "  precise" : ""}`, ""),
      row("speed gain", camera.speedGain.toFixed(2), ", / ."),
      "",
      row("move", flying ? "wasd  q/e" : "—", ""),
      row("precision", flying ? "hold shift" : "—", ""),
      row("fly to", "Sol / centre", "h / g"),
      row("look", flying ? "mouse" : "drag", ""),
      row("home", "", "h"),
      "",
      row("exposure", `${settings.exposure.toExponential(1)} ${fixedExposure === null ? "auto" : "fixed"}`, ""),
      row("brightness", `${exposureBias.toFixed(2)}x`, "z / x"),
      row(
        "saturation",
        `${settings.saturation.toFixed(2)}${settings.saturation === 1 ? " accurate" : ""}`,
        "c / v · t",
      ),
      row("star size", settings.sizeGain.toFixed(0), "b / n"),
      row("reset view", "", "r"),
    ].join("\n");
  };

  const frame = (): void => {
    const now = performance.now();
    const dt = Math.min((now - previous) / 1000, 0.1); // clamp, so a stall never teleports
    previous = now;

    const move: [number, number, number] = [0, 0, 0];
    // Any manual input cancels an automatic flight -- being unable to take back
    // control mid-journey is far more annoying than having to press the key again.
    if (camera.autoFlying && held.size > 0) camera.cancelFlyTo();
    for (const key of held) {
      const axis = AXES[key];
      if (axis) { move[0] += axis[0]; move[1] += axis[1]; move[2] += axis[2]; }
    }
    camera.update(move, dt);

    // Auto-exposure follows the camera. Smoothed in log space because it spans
    // decades, and slowly enough that a bright star entering the view dims the
    // sky over about a second rather than snapping.
    const bright = settings.earthView ? earthBright : camera.brightFlux;
    const wanted = fixedExposure ?? exposureFor(bright, sigmaPx, TARGET_PEAK) * exposureBias;
    const adapt = 1 - Math.exp(-dt * 2.5);
    settings.exposure = Math.exp(
      Math.log(settings.exposure) + (Math.log(wanted) - Math.log(settings.exposure)) * adapt,
    );

    sizeCanvas();
    renderer.resize(canvas.width, canvas.height);
    renderer.render(camera, settings);
    waypoints.update(camera, canvas.width, canvas.height, formatDistance);

    frames++;
    if (now - fpsWindowStart >= 250) {
      fps = (frames * 1000) / (now - fpsWindowStart);
      frames = 0;
      fpsWindowStart = now;
      refreshHud();
    }
    requestAnimationFrame(frame);
  };
  // Seed from the first scan so the opening frame is not a white flash.
  camera.update([0, 0, 0], 1 / 60);
  settings.exposure =
    fixedExposure ??
    exposureFor(settings.earthView ? earthBright : camera.brightFlux, sigmaPx, TARGET_PEAK) *
      exposureBias;
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
