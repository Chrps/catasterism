/**
 * The "where is home" indicator.
 *
 * Free flight in a field with no landmarks is genuinely disorienting: every
 * direction looks the same, and the distance readout tells you how far you have
 * gone but not which way back. So Sol gets a marker -- on screen when it is in
 * view, and an edge arrow pointing at it when it is not.
 *
 * Drawn as a DOM overlay rather than in GL. It is two elements updated once a
 * frame, it needs crisp text, and keeping it out of the HDR pipeline means it
 * cannot be dimmed by auto-exposure -- which would defeat the point at exactly
 * the moment it matters most.
 */

import { multiply, perspective, viewFromYawPitch } from "./mat4";

export interface MarkerTarget {
  /** World position in galactic cartesian parsecs. */
  position: [number, number, number];
  label: string;
}

export interface CameraView {
  position: [number, number, number];
  yaw: number;
  pitch: number;
  fovYRadians: number;
}

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
  // A point behind the camera projects to a mirrored position, so its sign has
  // to be undone before the direction is usable for an edge arrow.
  const ndcX = (clip[0]! / w) * (behind ? -1 : 1);
  const ndcY = (clip[1]! / w) * (behind ? -1 : 1);
  return {
    x: (ndcX * 0.5 + 0.5) * width,
    y: (1 - (ndcY * 0.5 + 0.5)) * height,
    behind,
    onScreen: !behind && Math.abs(ndcX) <= 1 && Math.abs(ndcY) <= 1,
  };
}

export class HomeMarker {
  private readonly root: HTMLDivElement;
  private readonly dot: HTMLDivElement;
  private readonly arrow: HTMLDivElement;

  constructor(parent: HTMLElement) {
    this.root = document.createElement("div");
    this.root.style.cssText =
      "position:fixed;inset:0;pointer-events:none;font:11px/1 ui-monospace,monospace;color:#8ab4ff";

    // A zero-size anchor sitting exactly on the projected point, with the ring
    // and the label positioned off it independently. Centring a block that
    // *contains* the label instead puts the ring half a label-height too high,
    // which reads as the marker missing the star it is pointing at.
    this.dot = document.createElement("div");
    this.dot.style.cssText = "position:absolute;width:0;height:0";
    this.dot.innerHTML =
      '<div style="position:absolute;left:0;top:0;width:16px;height:16px;margin:-8px 0 0 -8px;' +
      'box-sizing:border-box;' +
      'border:1px solid currentColor;border-radius:50%;opacity:.85"></div>' +
      '<span style="position:absolute;left:0;top:12px;transform:translateX(-50%);' +
      'white-space:nowrap"></span>';

    this.arrow = document.createElement("div");
    this.arrow.style.cssText = "position:absolute;width:0;height:0";

    this.root.append(this.dot, this.arrow);
    parent.append(this.root);
  }

  update(camera: CameraView, width: number, height: number, distanceLabel: string): void {
    // At the origin there is no direction to home, and the marker would sit
    // under the crosshair being useless.
    const atHome = Math.hypot(...camera.position) < 1e-9;
    if (atHome) {
      this.dot.style.display = "none";
      this.arrow.style.display = "none";
      return;
    }

    const dpr = width / Math.max(1, this.root.clientWidth);
    const p = project([0, 0, 0], camera, width, height);
    const cssX = p.x / dpr;
    const cssY = p.y / dpr;
    const w = width / dpr;
    const h = height / dpr;

    if (p.onScreen) {
      this.dot.style.display = "block";
      this.arrow.style.display = "none";
      this.dot.style.left = `${cssX}px`;
      this.dot.style.top = `${cssY}px`;
      this.dot.lastElementChild!.textContent = `Sol · ${distanceLabel}`;
      return;
    }

    // Off screen: clamp to the edge and point at it.
    this.dot.style.display = "none";
    this.arrow.style.display = "block";
    const cx = w / 2;
    const cy = h / 2;
    const angle = Math.atan2(cssY - cy, cssX - cx);
    const margin = 34;
    const x = Math.max(margin, Math.min(w - margin, cx + Math.cos(angle) * w));
    const y = Math.max(margin, Math.min(h - margin, cy + Math.sin(angle) * h));
    this.arrow.style.left = `${x}px`;
    this.arrow.style.top = `${y}px`;
    this.arrow.innerHTML =
      `<div style="position:absolute;left:0;top:0;transform:translate(-50%,-50%) ` +
      `rotate(${angle}rad);font-size:15px;line-height:1">➤</div>` +
      `<div style="position:absolute;left:0;top:11px;transform:translateX(-50%);` +
      `white-space:nowrap">Sol · ${distanceLabel}</div>`;
  }
}
