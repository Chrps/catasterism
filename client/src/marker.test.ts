import { expect, test } from "bun:test";
import { project, type CameraView } from "./marker";

const at = (position: [number, number, number], yaw = 0, pitch = 0): CameraView => ({
  position, yaw, pitch, fovYRadians: (60 * Math.PI) / 180,
});

test("a target dead ahead lands in the centre of the screen", () => {
  // Camera at +Z looking down -Z, target at the origin: straight ahead.
  const p = project([0, 0, 0], at([0, 0, 10]), 1000, 600);
  expect(p.onScreen).toBe(true);
  expect(p.behind).toBe(false);
  expect(p.x).toBeCloseTo(500, 0);
  expect(p.y).toBeCloseTo(300, 0);
});

test("a target behind the camera is reported as behind, not drawn on screen", () => {
  const p = project([0, 0, 0], at([0, 0, -10]), 1000, 600);
  expect(p.behind).toBe(true);
  expect(p.onScreen).toBe(false);
});

test("the arrow points toward the shorter turn, ahead or behind", () => {
  // A point behind the camera projects mirrored, so its sign must be undone or
  // the arrow sends you the wrong way round -- the worst possible failure for a
  // control whose entire job is "which way is home".
  //
  // The property: the side of screen must match the sign of the target's
  // view-space X, whether it is in front or behind. Camera looks down -Z at
  // yaw 0, so right is world +X.
  const cases: [string, [number, number, number], boolean, number][] = [
    ["ahead, right", [-1, 0, 10], false, +1],
    ["ahead, left", [1, 0, 10], false, -1],
    ["behind, right", [-1, 0, -10], true, +1],
    ["behind, left", [1, 0, -10], true, -1],
  ];
  for (const [label, cameraPos, expectBehind, expectedSide] of cases) {
    const p = project([0, 0, 0], at(cameraPos), 1000, 600);
    expect(p.behind, label).toBe(expectBehind);
    expect(Math.sign(p.x - 500), label).toBe(expectedSide);
  }
});

test("looking away from home puts it off screen", () => {
  const away = project([0, 0, 0], at([0, 0, 10], Math.PI), 1000, 600);
  expect(away.onScreen).toBe(false);
});
