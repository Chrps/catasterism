import { expect, test } from "bun:test";
import { basis, forward } from "./mat4";
import { project, type CameraView } from "./marker";

const at = (position: [number, number, number], yaw = 0, pitch = 0): CameraView => ({
  position, yaw, pitch, fovYRadians: (60 * Math.PI) / 180,
});

test("yaw and pitch are galactic longitude and latitude", () => {
  // The catalogue is standard galactic cartesian: +X toward the centre,
  // +Y toward l = 90, +Z toward the north pole.
  const centre = forward(0, 0);
  expect(centre[0]).toBeCloseTo(1);
  expect(centre[2]).toBeCloseTo(0);

  const l90 = forward(Math.PI / 2, 0);
  expect(l90[1]).toBeCloseTo(1);

  // The fix this test exists for: "straight up" must leave the plane, not run
  // along it. With +Y as up it pointed at l=90, b=0 -- along the Milky Way.
  const up = forward(0, Math.PI / 2 - 1e-6);
  expect(up[2]).toBeCloseTo(1);
});

test("the camera's up axis is the north galactic pole", () => {
  for (const [yaw, pitch] of [[0, 0], [1.2, 0.4], [-2.0, -0.7]] as [number, number][]) {
    const { right, up, forward: f } = basis(yaw, pitch);
    // Screen-up must have a positive component toward galactic north wherever
    // the camera is pointing, or the Milky Way ends up sideways.
    expect(up[2]).toBeGreaterThan(0);
    // Orthonormal basis.
    expect(Math.hypot(...right)).toBeCloseTo(1);
    expect(right[0] * f[0] + right[1] * f[1] + right[2] * f[2]).toBeCloseTo(0);
    expect(up[0] * f[0] + up[1] * f[1] + up[2] * f[2]).toBeCloseTo(0);
    // Right is horizontal in galactic terms: it never tilts out of the plane.
    expect(right[2]).toBeCloseTo(0);
  }
});

test("a target dead ahead lands in the centre of the screen", () => {
  // Camera on the -X side looking toward +X, target at the origin.
  const p = project([0, 0, 0], at([-10, 0, 0]), 1000, 600);
  expect(p.onScreen).toBe(true);
  expect(p.behind).toBe(false);
  expect(p.x).toBeCloseTo(500, 0);
  expect(p.y).toBeCloseTo(300, 0);
});

test("a target behind the camera is reported as behind", () => {
  const p = project([0, 0, 0], at([10, 0, 0]), 1000, 600);
  expect(p.behind).toBe(true);
  expect(p.onScreen).toBe(false);
});

test("the arrow points toward the shorter turn, ahead or behind", () => {
  // A point behind the camera projects mirrored, so its sign must be undone or
  // the arrow sends you the wrong way round -- the worst possible failure for a
  // control whose only job is "which way is home".
  //
  // At yaw 0 the camera looks along +X and screen-right is -Y, so a target with
  // a negative relative Y must land on the right, in front or behind.
  const cases: [string, [number, number, number], boolean, number][] = [
    ["ahead, right", [-10, 1, 0], false, +1],
    ["ahead, left", [-10, -1, 0], false, -1],
    ["behind, right", [10, 1, 0], true, +1],
    ["behind, left", [10, -1, 0], true, -1],
  ];
  for (const [label, cameraPos, expectBehind, expectedSide] of cases) {
    const p = project([0, 0, 0], at(cameraPos), 1000, 600);
    expect(p.behind, label).toBe(expectBehind);
    expect(Math.sign(p.x - 500), label).toBe(expectedSide);
  }
});

test("looking away from home puts it off screen", () => {
  expect(project([0, 0, 0], at([-10, 0, 0], Math.PI), 1000, 600).onScreen).toBe(false);
});
