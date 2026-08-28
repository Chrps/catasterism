/**
 * Cross-language round trip. The Python encoder wrote the file; this decodes it
 * and prints a fingerprint that `pipeline/tests/test_encode.py` compares against
 * its own. If the two implementations ever disagree about the bit layout, the
 * fingerprints diverge and CI says so -- which is the only reliable defence
 * against a writer and reader drifting apart (PLAN.md 5.5).
 */
import { expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { decode, apparentMagnitude, type Manifest } from "./format";

const STEM = "public/dr3-v1-t0";
const manifest = JSON.parse(readFileSync(`${STEM}.json`, "utf8")) as Manifest;
const bytes = readFileSync(`${STEM}.bin`);
const stars = decode(
  bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer,
  manifest,
);

test("decodes every record", () => {
  expect(stars.count).toBe(manifest.record_count);
  expect(stars.positions.length).toBe(stars.count * 3);
});

test("the Sun is at the origin and flagged synthetic", () => {
  // Gaia cannot observe the Sun, so it is inserted by the pipeline.
  const FLAG_SYNTHETIC = 1 << 2;
  let found = -1;
  for (let i = 0; i < stars.count; i++) {
    if ((stars.flags[i]! & FLAG_SYNTHETIC) !== 0) { found = i; break; }
  }
  expect(found).toBeGreaterThanOrEqual(0);
  expect(stars.positions[found * 3]).toBe(0);
  expect(stars.positions[found * 3 + 1]).toBe(0);
  expect(stars.positions[found * 3 + 2]).toBe(0);
  // The calibration reference: M_G 4.67 means m_G -26.90 from 1 AU.
  expect(stars.absoluteMagnitude[found]!).toBeCloseTo(4.67, 2);
  expect(apparentMagnitude(stars.absoluteMagnitude[found]!, 1 / 206264.806)).toBeCloseTo(-26.9, 1);
});

test("palette is perceptually uniform and complete", () => {
  expect(stars.palette.length).toBe(manifest.colour_lut.size * 3);
  expect(manifest.colour_lut.worst_adjacent_delta_e76).toBeLessThan(2.3); // JND
});

test("fingerprint matches the Python encoder", () => {
  // Deterministic reduction over the whole file. Printed so the Python side can
  // assert the same numbers.
  let px = 0, mag = 0, colour = 0, flags = 0;
  for (let i = 0; i < stars.count; i++) {
    px += stars.positions[i * 3]!;
    mag += stars.absoluteMagnitude[i]!;
    colour += stars.colourIndex[i]!;
    flags += stars.flags[i]!;
  }
  const fp = {
    count: stars.count,
    sum_x: +px.toFixed(3),
    sum_abs_g: +mag.toFixed(2),
    sum_colour_index: colour,
    sum_flags: flags,
  };
  // Hardcoded on purpose: if the encoder changes, this and the Python side must
  // be updated together, which is what keeps the two implementations honest.
  console.log("TS fingerprint:", JSON.stringify(fp));
  expect(fp).toEqual({
    count: 625049,
    sum_x: 17473423.431,
    sum_abs_g: 7244935.6,
    sum_colour_index: 75684316,
    sum_flags: 441317,
  });
});
