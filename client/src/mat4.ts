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

/** View matrix for a camera at the origin looking down -Z, rotated by yaw/pitch.
 *  Camera *translation* is handled separately: star positions arrive already
 *  camera-relative, which is what keeps float32 precise at galactic scale. */
export function viewFromYawPitch(yaw: number, pitch: number): Mat4 {
  const cy = Math.cos(yaw), sy = Math.sin(yaw);
  const cp = Math.cos(pitch), sp = Math.sin(pitch);
  // R = Rx(pitch) * Ry(yaw), then transposed because a view matrix is the inverse
  // of the camera's world transform and rotations are orthonormal.
  return new Float32Array([
    cy, sp * sy, cp * sy, 0,
    0, cp, -sp, 0,
    -sy, sp * cy, cp * cy, 0,
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

/** Unit forward vector for a yaw/pitch, in world space. */
export function forward(yaw: number, pitch: number): [number, number, number] {
  const cp = Math.cos(pitch);
  return [-Math.sin(yaw) * cp, Math.sin(pitch), -Math.cos(yaw) * cp];
}
