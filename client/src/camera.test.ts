/**
 * The camera-relative subtraction, and why it is split into two float32s.
 *
 * This is the arithmetic the vertex shader performs. Getting it wrong does not
 * fail loudly -- it makes stars jitter when the camera moves slowly nearby,
 * which reads as a rendering glitch rather than a precision bug.
 */
import { expect, test } from "bun:test";
import { formatDistance } from "./camera";

/** What the shader used to do: one float32 camera uniform. */
function naive(starPc: number, cameraPc: number): number {
  return Math.fround(Math.fround(starPc) - Math.fround(cameraPc));
}

/** What it does now: (star - hi) - lo, with hi + lo carrying the camera. */
function split(starPc: number, cameraPc: number): number {
  const hi = Math.fround(cameraPc);
  const lo = Math.fround(cameraPc - hi);
  return Math.fround(Math.fround(Math.fround(starPc) - hi) - lo);
}

test("a single float32 camera quantises motion to ulp at its magnitude", () => {
  // 100 pc out, camera creeping toward a star in 0.1 AU steps.
  const star = 100.0;
  const stepPc = 0.1 / 206264.806;
  const seen = new Set<number>();
  for (let i = 0; i < 12; i++) seen.add(naive(star, 100.0 - 12 * stepPc + i * stepPc));
  // Twelve distinct camera positions collapse to far fewer rendered offsets.
  expect(seen.size).toBeLessThan(6);
});

test("the split recovers smooth motion at the same magnitude", () => {
  const star = 100.0;
  const stepPc = 0.1 / 206264.806;
  const seen = new Set<number>();
  for (let i = 0; i < 12; i++) seen.add(split(star, 100.0 - 12 * stepPc + i * stepPc));
  expect(seen.size).toBe(12); // every step is distinguishable
});

test("the split is monotonic, so approach never reverses", () => {
  const star = 250.0;
  const stepPc = 0.05 / 206264.806;
  let previous = Infinity;
  for (let i = 0; i < 40; i++) {
    const rel = split(star, star - 40 * stepPc + i * stepPc);
    expect(rel).toBeLessThanOrEqual(previous);
    previous = rel;
  }
});

test("distances are shown in the unit a human would use", () => {
  expect(formatDistance(1 / 206264.806)).toBe("1.00 AU");
  expect(formatDistance(1.3)).toContain("ly"); // Proxima reads in light years
  expect(formatDistance(250)).toContain("pc"); // beyond ~30 pc, ly stops meaning anything
  expect(formatDistance(10)).toContain("ly");
  expect(formatDistance(NaN)).toBe("—");
});
