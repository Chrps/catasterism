/**
 * Reader for the catasterism star binary — the mirror of `catasterism.encode`.
 *
 * A writer and a reader of a bit-packed format drift silently, and the failure
 * mode is misplaced stars that no test notices. Two defences:
 *
 *  1. **Every layout constant comes from the manifest**, never from a literal
 *     here. Shifts, masks, magnitude range and record size are all read from
 *     the JSON the encoder emitted, so they cannot disagree with it.
 *  2. The Python round-trip test covers the same bit layout, so a change that
 *     breaks one side fails CI before it ships.
 *
 * See PLAN.md §5.5.
 */

export interface Manifest {
  magic: string;
  format_version: number;
  catalogue_version: string;
  release: string;
  reference_epoch: number;
  frame: string;
  record_bytes: number;
  record_count: number;
  layout: {
    packed_uint32: {
      magnitude: { bits: number; shift: number; min: number; max: number };
      colour: { bits: number; shift: number; lut_size: number };
      flags: { bits: number; shift: number };
    };
  };
  colour_lut: {
    size: number;
    worst_adjacent_delta_e76: number;
    temperatures_k: number[];
    linear_srgb: number[][];
  };
}

export interface Stars {
  count: number;
  /** Galactic Cartesian parsecs, interleaved xyz — ready for a GPU buffer. */
  positions: Float32Array;
  /** Absolute G magnitude, dequantised. Apparent brightness is the renderer's
   *  job: it depends on where the camera is (PLAN.md §4.3). */
  absoluteMagnitude: Float32Array;
  colourIndex: Uint8Array;
  flags: Uint8Array;
  /** Linear sRGB per palette entry. Perceptually uniform along the Planckian
   *  locus, so 8 bits is visually lossless. */
  palette: Float32Array;
  manifest: Manifest;
}

const EXPECTED_MAGIC = "CTSM";
const EXPECTED_VERSION = 1;

function mask(bits: number): number {
  return (1 << bits) - 1;
}

export function decode(buffer: ArrayBuffer, manifest: Manifest): Stars {
  if (manifest.magic !== EXPECTED_MAGIC) {
    throw new Error(`not a ${EXPECTED_MAGIC} file (got ${manifest.magic})`);
  }
  if (manifest.format_version !== EXPECTED_VERSION) {
    throw new Error(
      `format version ${manifest.format_version}, this client reads ${EXPECTED_VERSION}`,
    );
  }

  const n = manifest.record_count;
  const stride = manifest.record_bytes / 4;
  if (buffer.byteLength !== n * manifest.record_bytes) {
    throw new Error(
      `expected ${n * manifest.record_bytes} bytes, got ${buffer.byteLength}`,
    );
  }

  const words = new Uint32Array(buffer);
  const floats = new Float32Array(buffer);

  // Positions are already interleaved xyz in the file, but every fourth word is
  // the packed attributes, so they need compacting before a GPU upload.
  const positions = new Float32Array(n * 3);
  const absoluteMagnitude = new Float32Array(n);
  const colourIndex = new Uint8Array(n);
  const flags = new Uint8Array(n);

  const m = manifest.layout.packed_uint32;
  const magMask = mask(m.magnitude.bits);
  const magLevels = magMask;
  const magSpan = m.magnitude.max - m.magnitude.min;

  for (let i = 0; i < n; i++) {
    const base = i * stride;
    positions[i * 3] = floats[base]!;
    positions[i * 3 + 1] = floats[base + 1]!;
    positions[i * 3 + 2] = floats[base + 2]!;

    const packed = words[base + 3]!;
    const q = (packed >>> m.magnitude.shift) & magMask;
    absoluteMagnitude[i] = m.magnitude.min + (q / magLevels) * magSpan;
    colourIndex[i] = (packed >>> m.colour.shift) & mask(m.colour.bits);
    flags[i] = (packed >>> m.flags.shift) & mask(m.flags.bits);
  }

  const palette = new Float32Array(manifest.colour_lut.size * 3);
  manifest.colour_lut.linear_srgb.forEach((rgb, i) => {
    palette[i * 3] = rgb[0]!;
    palette[i * 3 + 1] = rgb[1]!;
    palette[i * 3 + 2] = rgb[2]!;
  });

  return { count: n, positions, absoluteMagnitude, colourIndex, flags, palette, manifest };
}

export async function load(stem: string): Promise<Stars> {
  const [manifest, buffer] = await Promise.all([
    fetch(`./${stem}.json`).then((r) => {
      if (!r.ok) throw new Error(`${stem}.json: ${r.status}`);
      return r.json() as Promise<Manifest>;
    }),
    fetch(`./${stem}.bin`).then((r) => {
      if (!r.ok) throw new Error(`${stem}.bin: ${r.status}`);
      return r.arrayBuffer();
    }),
  ]);
  return decode(buffer, manifest);
}

/** Apparent magnitude from the camera. The renderer's whole job, in one line. */
export function apparentMagnitude(absMag: number, distanceParsecs: number): number {
  return absMag + 5 * Math.log10(distanceParsecs / 10);
}
