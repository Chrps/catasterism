/**
 * On-screen waypoints.
 *
 * Free flight in a field with no landmarks is genuinely disorienting: every
 * direction looks the same, and a distance readout says how far you have gone
 * but not which way anything is. Each waypoint shows as a ring when it is in
 * view and an edge arrow pointing at it when it is not.
 *
 * Drawn as a DOM overlay rather than in GL. It is a handful of elements updated
 * once a frame, it wants crisp text, and keeping it outside the HDR pipeline
 * means auto-exposure cannot dim it at exactly the moment it matters most.
 */

import { multiply, perspective, viewFromYawPitch } from "./mat4";

export interface CameraView {
  position: [number, number, number];
  yaw: number;
  pitch: number;
  fovYRadians: number;
}

export interface Waypoint {
  /** Galactic cartesian parsecs. */
  position: [number, number, number];
  label: string;
  colour: string;
  /** Hide when the camera is essentially on top of it -- there is no direction
   *  to somewhere you already are, and the marker would sit uselessly under the
   *  centre of the screen. */
  hideWithinPc: number;
}

export const SOL: Waypoint = {
  position: [0, 0, 0],
  label: "Sol",
  colour: "#8ab4ff",
  hideWithinPc: 1e-9,
};

/**
 * Sagittarius A*, the compact radio source at the dynamical centre, at
 * R0 = 8178 pc (GRAVITY Collaboration 2019).
 *
 * Note it is not at exactly l=0, b=0: the IAU galactic frame was fixed in 1958,
 * before the centre had been located precisely, so Sgr A* sits at
 * l = 359.944, b = -0.046. Placing it at the frame origin instead would be a
 * third of a degree out -- small, but wrong in a way a star chart would show.
 */
export const GALACTIC_CENTRE: Waypoint = {
  position: [8177.99, -7.96, -6.59],
  label: "Galactic centre",
  colour: "#ffb26b",
  // It is 82x further than T0 reaches, so it is never somewhere you can be.
  hideWithinPc: 0,
};

/** Where a world point lands on screen, and whether it is actually visible. */
export function project(
  target: [number, number, number],
  camera: CameraView,
  width: number,
  height: number,
): { x: number; y: number; behind: boolean; onScreen: boolean } {
  // Camera-relative first, in float64, exactly as the vertex shader does it.
  const rel: [number, number, number] = [
    target[0] - camera.position[0],
    target[1] - camera.position[1],
    target[2] - camera.position[2],
  ];
  const m = multiply(
    perspective(camera.fovYRadians, width / Math.max(height, 1), 1e-6, 1e9),
    viewFromYawPitch(camera.yaw, camera.pitch),
  );
  const clip = [0, 0, 0, 0];
  for (let r = 0; r < 4; r++) {
    clip[r] = m[r]! * rel[0] + m[4 + r]! * rel[1] + m[8 + r]! * rel[2] + m[12 + r]!;
  }
  const w = clip[3]!;
  const behind = w <= 0;
  // A point behind the camera projects mirrored, so the sign has to be undone
  // before the direction is usable for an edge arrow. Skipping this sends the
  // arrow exactly the wrong way round.
  const ndcX = (clip[0]! / w) * (behind ? -1 : 1);
  const ndcY = (clip[1]! / w) * (behind ? -1 : 1);
  return {
    x: (ndcX * 0.5 + 0.5) * width,
    y: (1 - (ndcY * 0.5 + 0.5)) * height,
    behind,
    onScreen: !behind && Math.abs(ndcX) <= 1 && Math.abs(ndcY) <= 1,
  };
}

interface Slot {
  waypoint: Waypoint;
  ring: HTMLDivElement;
  arrow: HTMLDivElement;
}

export class Waypoints {
  private readonly root: HTMLDivElement;
  private readonly slots: Slot[];

  constructor(parent: HTMLElement, waypoints: readonly Waypoint[]) {
    this.root = document.createElement("div");
    this.root.style.cssText =
      "position:fixed;inset:0;pointer-events:none;font:11px/1 ui-monospace,monospace";
    this.slots = waypoints.map((waypoint) => {
      // A zero-size anchor sitting exactly on the projected point, with the ring
      // and label positioned off it independently. Centring a block that
      // *contains* the label puts the ring half a label-height too high.
      const ring = document.createElement("div");
      ring.style.cssText = `position:absolute;width:0;height:0;color:${waypoint.colour}`;
      ring.innerHTML =
        '<div style="position:absolute;left:0;top:0;width:16px;height:16px;' +
        "margin:-8px 0 0 -8px;box-sizing:border-box;border:1px solid currentColor;" +
        'border-radius:50%;opacity:.85"></div>' +
        '<span style="position:absolute;left:0;top:12px;transform:translateX(-50%);' +
        'white-space:nowrap"></span>';

      const arrow = document.createElement("div");
      arrow.style.cssText = `position:absolute;width:0;height:0;color:${waypoint.colour}`;

      this.root.append(ring, arrow);
      return { waypoint, ring, arrow };
    });
    parent.append(this.root);
  }

  update(
    camera: CameraView,
    width: number,
    height: number,
    format: (parsecs: number) => string,
  ): void {
    const dpr = width / Math.max(1, this.root.clientWidth);
    const w = width / dpr;
    const h = height / dpr;

    for (const { waypoint, ring, arrow } of this.slots) {
      const distance = Math.hypot(
        waypoint.position[0] - camera.position[0],
        waypoint.position[1] - camera.position[1],
        waypoint.position[2] - camera.position[2],
      );
      if (distance <= waypoint.hideWithinPc) {
        ring.style.display = "none";
        arrow.style.display = "none";
        continue;
      }

      const label = `${waypoint.label} · ${format(distance)}`;
      const p = project(waypoint.position, camera, width, height);

      if (p.onScreen) {
        ring.style.display = "block";
        arrow.style.display = "none";
        ring.style.left = `${p.x / dpr}px`;
        ring.style.top = `${p.y / dpr}px`;
        ring.lastElementChild!.textContent = label;
        continue;
      }

      // Off screen: clamp to the edge and point at it.
      ring.style.display = "none";
      arrow.style.display = "block";
      const angle = Math.atan2(p.y / dpr - h / 2, p.x / dpr - w / 2);
      const margin = 40;
      arrow.style.left = `${Math.max(margin, Math.min(w - margin, w / 2 + Math.cos(angle) * w))}px`;
      arrow.style.top = `${Math.max(margin, Math.min(h - margin, h / 2 + Math.sin(angle) * h))}px`;
      arrow.innerHTML =
        `<div style="position:absolute;left:0;top:0;transform:translate(-50%,-50%) ` +
        `rotate(${angle}rad);font-size:15px;line-height:1">➤</div>` +
        `<div style="position:absolute;left:0;top:11px;transform:translateX(-50%);` +
        `white-space:nowrap">${label}</div>`;
    }
  }
}
