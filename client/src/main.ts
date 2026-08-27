/**
 * Step 1 skeleton: prove the deploy path end to end before any rendering work.
 *
 * The real renderer arrives in T5. Everything it needs is already decided and
 * deliberately not started here -- see TASKS_STEP_1.md.
 */

const CATALOGUE_VERSION = "dr3-v1"; // must match the pack header; see PLAN.md 7.5

function fail(hud: HTMLElement, message: string): never {
  hud.textContent = message;
  hud.style.color = "#f66";
  throw new Error(message);
}

function main(): void {
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
  if (!gl) fail(hud, "WebGL2 unavailable — this browser cannot run Star");

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
  hud.innerHTML = [
    `star · catalogue ${CATALOGUE_VERSION}`,
    `WebGL2 · ${renderer}`,
    `float render targets: ${hdr ? "yes" : "NO — HDR accumulation unavailable"}`,
    `${canvas.width}×${canvas.height}`,
  ].join("<br>");
}

main();
