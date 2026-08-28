/**
 * Constellation stick figures.
 *
 * As much a verification tool as decoration: a line that lands on its star
 * validates coordinates, frame, epoch, magnitude, the bright-star patch and the
 * projection all at once. One that lands *beside* a star shows which link is
 * wrong (TASKS_STEP_1.md T10).
 *
 * Drawn as a single SVG path rather than 734 elements. Updating that many DOM
 * nodes per frame is slow; one path attribute is not. And SVG rather than GL for
 * the same reason as the waypoints: these must not be dimmed by auto-exposure,
 * and they want crisp edges rather than bloom.
 */

import { project, type CameraView } from "./waypoints";

export interface ConstellationData {
  attribution: { source: string; licence: string };
  /** Galactic cartesian parsecs, one entry per referenced star. */
  positions: [number, number, number][];
  constellations: { abbr: string; lines: [number, number][] }[];
}

/**
 * The figures are an accident of where Earth happens to be, so they dissolve as
 * you leave. Fading them out says that better than switching them off: you get
 * to watch a constellation stop being one.
 */
const FADE_START_PC = 2;
const FADE_END_PC = 40;

export class Constellations {
  private readonly svg: SVGSVGElement;
  private readonly path: SVGPathElement;
  private readonly segments: [number, number][];
  private readonly positions: [number, number, number][];
  visible = true;

  constructor(parent: HTMLElement, data: ConstellationData) {
    this.positions = data.positions;
    this.segments = data.constellations.flatMap((c) => c.lines);

    this.svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    this.svg.setAttribute("style",
      "position:fixed;inset:0;width:100%;height:100%;pointer-events:none");
    this.path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    this.path.setAttribute("fill", "none");
    this.path.setAttribute("stroke", "#5f7fbf");
    this.path.setAttribute("stroke-width", "1");
    this.svg.append(this.path);
    parent.append(this.svg);
  }

  get segmentCount(): number {
    return this.segments.length;
  }

  update(camera: CameraView, width: number, height: number): void {
    const distance = Math.hypot(...camera.position);
    const fade =
      1 - Math.min(1, Math.max(0, (distance - FADE_START_PC) / (FADE_END_PC - FADE_START_PC)));

    if (!this.visible || fade <= 0.01) {
      this.svg.style.display = "none";
      return;
    }
    this.svg.style.display = "block";
    this.svg.style.opacity = (fade * 0.55).toFixed(3);

    // Project once per star, not once per endpoint: the figures revisit stars to
    // draw branches, so a naive pass would project some of them three times.
    const dpr = width / Math.max(1, this.svg.clientWidth || width);
    const screen = this.positions.map((p) => project(p, camera, width, height));

    let d = "";
    for (const [a, b] of this.segments) {
      const pa = screen[a]!;
      const pb = screen[b]!;
      // Either endpoint behind the camera makes the projected segment
      // meaningless -- it would streak across the view from the wrong side.
      if (pa.behind || pb.behind) continue;
      d += `M${(pa.x / dpr).toFixed(1)} ${(pa.y / dpr).toFixed(1)}`
        + `L${(pb.x / dpr).toFixed(1)} ${(pb.y / dpr).toFixed(1)}`;
    }
    this.path.setAttribute("d", d);
  }
}

export async function load(stem: string): Promise<ConstellationData> {
  const response = await fetch(`./${stem}.json`);
  if (!response.ok) throw new Error(`${stem}.json: ${response.status}`);
  return (await response.json()) as ConstellationData;
}
