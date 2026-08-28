/** Minimal column-major 4x4 maths. Hand-rolled to avoid a dependency for ~60 lines. */

export type Mat4 = Float32Array;

export function perspective(fovYRadians: number, aspect: number, near: number, far: number): Mat4 {
  const f = 1 / Math.tan(fovYRadians / 2);
  const nf = 1 / (near - far);
  return new Float32Array([
    f / aspect, 0, 0, 0,
    0, f, 0, 0,
    0, 0, (far + near) * nf, -1,
    0, 0, 2 * far * near * nf, 0,
  ]);
}

/**
 * World up is **+Z**, the north galactic pole -- not +Y.
 *
 * The catalogue is standard galactic cartesian: +X toward the centre, +Y toward
 * l = 90, +Z toward the north pole. Treating +Y as up lays the Milky Way across
 * the screen vertically and makes "look straight up" point *along* the plane
 * rather than out of it. Every star map ever drawn puts galactic north up.
 *
 * With this basis, yaw and pitch are exactly galactic longitude and latitude.
 */
export const WORLD_UP: readonly [number, number, number] = [0, 0, 1];

/** Orthonormal camera basis: right, up, forward. */
export function basis(yaw: number, pitch: number): {
  right: [number, number, number];
  up: [number, number, number];
  forward: [number, number, number];
} {
  const f = forward(yaw, pitch);
  // Standard lookAt construction. Pitch is clamped short of the poles by the
  // camera, so the cross product never degenerates.
  const z: [number, number, number] = [-f[0], -f[1], -f[2]];
  let rx = WORLD_UP[1] * z[2] - WORLD_UP[2] * z[1];
  let ry = WORLD_UP[2] * z[0] - WORLD_UP[0] * z[2];
  let rz = WORLD_UP[0] * z[1] - WORLD_UP[1] * z[0];
  const n = Math.hypot(rx, ry, rz) || 1;
  rx /= n; ry /= n; rz /= n;
  return {
    right: [rx, ry, rz],
    up: [z[1] * rz - z[2] * ry, z[2] * rx - z[0] * rz, z[0] * ry - z[1] * rx],
    forward: f,
  };
}

/** View matrix for a camera at the origin. Translation is handled separately:
 *  star positions arrive already camera-relative, which is what keeps float32
 *  precise at galactic scale. */
export function viewFromYawPitch(yaw: number, pitch: number): Mat4 {
  const { right: r, up: u, forward: f } = basis(yaw, pitch);
  return new Float32Array([
    r[0], u[0], -f[0], 0,
    r[1], u[1], -f[1], 0,
    r[2], u[2], -f[2], 0,
    0, 0, 0, 1,
  ]);
}

export function multiply(a: Mat4, b: Mat4): Mat4 {
  const out = new Float32Array(16);
  for (let c = 0; c < 4; c++) {
    for (let r = 0; r < 4; r++) {
      let s = 0;
      for (let k = 0; k < 4; k++) s += a[k * 4 + r]! * b[c * 4 + k]!;
      out[c * 4 + r] = s;
    }
  }
  return out;
}

/** Unit forward vector: yaw is galactic longitude, pitch is galactic latitude. */
export function forward(yaw: number, pitch: number): [number, number, number] {
  const cp = Math.cos(pitch);
  return [cp * Math.cos(yaw), cp * Math.sin(yaw), Math.sin(pitch)];
}
