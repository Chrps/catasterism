/**
 * Step 1 skeleton: prove the deploy path end to end before any rendering work.
 *
 * The real renderer arrives in T5. Everything it needs is already decided and
 * deliberately not started here -- see TASKS_STEP_1.md.
 */

import { load, apparentMagnitude } from "./format";

const CATALOGUE_VERSION = "dr3-v1"; // must match the pack header; see PLAN.md 7.5
const TIER = "t0";

function fail(hud: HTMLElement, message: string): never {
  hud.textContent = message;
  hud.style.color = "#f66";
  throw new Error(message);
}

async function main(): Promise<void> {
  const hud = document.getElementById("hud");
  if (!hud) throw new Error("missing #hud");

  const canvas = document.getElementById("view");
  if (!(canvas instanceof HTMLCanvasElement)) fail(hud, "missing #view canvas");

  // WebGL2 is the baseline and must stay fully featured; WebGPU is an opt-in
  // fast path later. See PLAN.md 6.5.
  const gl = canvas.getContext("webgl2", {
    antialias: false, // we accumulate into our own HDR target (PLAN.md 6.1)
    depth: false, // stars are additive point sprites; nothing occludes
    alpha: false,
  });
  if (!gl) fail(hud, "WebGL2 unavailable — this browser cannot run Catasterism");

  // rgba16float accumulation is required, not optional: free flight spans 10^20
  // in apparent brightness (PLAN.md 6.1).
  const hdr = gl.getExtension("EXT_color_buffer_float");

  const resize = (): void => {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.floor(canvas.clientWidth * dpr);
    canvas.height = Math.floor(canvas.clientHeight * dpr);
    gl.viewport(0, 0, canvas.width, canvas.height);
  };
  window.addEventListener("resize", resize);
  resize();

  gl.clearColor(0, 0, 0, 1);
  gl.clear(gl.COLOR_BUFFER_BIT);

  const renderer = gl.getParameter(gl.RENDERER) as string;
  hud.textContent = "loading catalogue…";

  const started = performance.now();
  const stars = await load(`${CATALOGUE_VERSION}-${TIER}`);
  const elapsed = performance.now() - started;

  // The catalogue stores intrinsic brightness, so apparent magnitude must be
  // recomputed from wherever the camera is (PLAN.md §4.3). The camera is at the
  // Sun for now, which makes this the sky as seen from Earth.
  let brightest = Infinity;
  for (let i = 0; i < stars.count; i++) {
    const d = Math.hypot(
      stars.positions[i * 3]!,
      stars.positions[i * 3 + 1]!,
      stars.positions[i * 3 + 2]!,
    );
    if (d > 0) {
      const m = apparentMagnitude(stars.absoluteMagnitude[i]!, d);
      if (m < brightest) brightest = m;
    }
  }

  const lut = stars.manifest.colour_lut;
  hud.innerHTML = [
    `catasterism · ${stars.manifest.catalogue_version} · ${stars.manifest.frame}`,
    `${stars.count.toLocaleString()} stars · ${stars.manifest.record_bytes} B each · ${elapsed.toFixed(0)} ms`,
    `palette ${lut.size} entries, worst step ${lut.worst_adjacent_delta_e76} ΔE76`,
    `brightest from Sol: m_G ${brightest.toFixed(2)}`,
    `WebGL2 · ${renderer}`,
    `float targets: ${hdr ? "yes" : "NO — HDR accumulation unavailable"}`,
  ].join("<br>");
}

main().catch((e: unknown) => {
  const hud = document.getElementById("hud");
  if (hud) {
    hud.textContent = `failed: ${e instanceof Error ? e.message : String(e)}`;
    hud.style.color = "#f66";
  }
  throw e;
});
