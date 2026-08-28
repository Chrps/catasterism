"""Stage 3 (Step 1 form) — pack derived rows into the binary the browser loads.

**Position is float32 here, not the 12-bit fixed point of PLAN.md section 4.4.**
That is a deliberate, measured decision, and the reason is worth stating because
it is easy to read as a shortcut.

Fixed-point quantisation is *tile-relative*: error in screen pixels is
``refine_threshold / 2**bits`` regardless of scale, which is what makes 12 bits
sufficient. Step 1 has no tiles, so a single global box must span everything --
and T0 runs from the Sun at 0 pc to a bright star at 36 kpc. Measured, against
the requirement that the sky from Earth look right:

    box edge 2000 pc, 24 bits/axis -> 18.9 arcsec of error at Proxima
    box edge 70000 pc, 24 bits/axis -> 662 arcsec

Unusable at every practical bit depth, because a *fixed* absolute error subtends
its largest angle at the nearest stars. float32 has *relative* precision, so its
angular error is constant at ~0.02 arcsec from 1 pc to 36 kpc. That is the
property a single flat file needs and fixed point cannot provide.

So: float32 now, 12-bit tile-relative once the octree exists in Step 2. The
16-byte record below becomes 8 bytes there. This module is direct evidence for
why the plan insists quantisation be tile-relative rather than global.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pyarrow as pa

from .colour import build_lut, index_of_teff, worst_adjacent_delta_e
from .constants import (
    ABS_MAG_MAX,
    ABS_MAG_MIN,
    APP_MAG_MAX,
    APP_MAG_MIN,
    APP_MAGNITUDE_BITS,
    COLOUR_LUT_SIZE,
    MAGNITUDE_BITS,
)
from .release import Release
from .sun import SUN_SOURCE_ID

FORMAT_VERSION = 1
MAGIC = "CTSM"
RECORD_BYTES = 16

MAG_LEVELS = (1 << MAGNITUDE_BITS) - 1

# Bit layout of the trailing uint32. Little-endian, matching every GPU we target.
MAG_SHIFT, MAG_MASK = 20, 0xFFF
COLOUR_SHIFT, COLOUR_MASK = 12, 0xFF
FLAG_SHIFT, FLAG_MASK = 4, 0xFF

FLAG_TEFF_MEASURED = 1 << 0
"""Teff came from GSP-Phot, not from the colour fallback."""
FLAG_EXTINCTION_APPLIED = 1 << 1
"""A_G was available and subtracted. Without it the star's intrinsic
luminosity carries Earth's dust column (PLAN.md section 4.3)."""
FLAG_SYNTHETIC = 1 << 2
"""Not a Gaia source. The Sun, and later the Hipparcos bright-star patches."""

APP_MAG_LEVELS = (1 << APP_MAGNITUDE_BITS) - 1
NO_APPARENT_MAGNITUDE = 0xFFFF
"""Sentinel for a star Gaia has no G magnitude for. Distinct from a clipped
value, so the renderer can drop it from the planetarium view rather than
inventing a brightness."""


@dataclass
class EncodeResult:
    data: bytes
    manifest: dict
    dropped: int
    stats: dict = field(default_factory=dict)


def quantise_magnitude(abs_g: np.ndarray) -> np.ndarray:
    """Absolute G magnitude to 12 bits over the range in :mod:`constants`.

    0.0090 mag per step, a 0.83% change in flux -- below the point two adjacent
    stars can be told apart. 8 bits would be 0.145 mag (14% flux), which is
    visible when they sit side by side.

    Values outside the range are clipped. :func:`encode` counts how many, so a
    future release whose population runs past the range says so rather than
    silently flattening its extremes.
    """
    t = (np.asarray(abs_g, float) - ABS_MAG_MIN) / (ABS_MAG_MAX - ABS_MAG_MIN)
    return np.clip(np.rint(t * MAG_LEVELS), 0, MAG_LEVELS).astype(np.uint32)


def dequantise_magnitude(q: np.ndarray) -> np.ndarray:
    return ABS_MAG_MIN + np.asarray(q, float) / MAG_LEVELS * (ABS_MAG_MAX - ABS_MAG_MIN)


def quantise_apparent(app_g: np.ndarray) -> np.ndarray:
    """Observed apparent G to 12 bits, with a sentinel for missing values."""
    t = (np.asarray(app_g, float) - APP_MAG_MIN) / (APP_MAG_MAX - APP_MAG_MIN)
    q = np.clip(np.rint(t * APP_MAG_LEVELS), 0, APP_MAG_LEVELS).astype(np.uint16)
    return np.where(np.isfinite(app_g), q, NO_APPARENT_MAGNITUDE).astype(np.uint16)


def dequantise_apparent(q: np.ndarray) -> np.ndarray:
    q = np.asarray(q)
    value = APP_MAG_MIN + q.astype(float) / APP_MAG_LEVELS * (APP_MAG_MAX - APP_MAG_MIN)
    return np.where(q == NO_APPARENT_MAGNITUDE, np.nan, value)


def encode(table: pa.Table, release: Release) -> EncodeResult:
    col = lambda n: table.column(n).to_numpy(zero_copy_only=False).astype(np.float64)

    x, y, z = col("x_pc"), col("y_pc"), col("z_pc")
    abs_g, teff = col("abs_g"), col("teff_derived")
    source_id = table.column("source_id").to_numpy(zero_copy_only=False)

    # A star with no parallax has no position. Drop rather than invent one.
    keep = np.isfinite(x) & np.isfinite(y) & np.isfinite(z) & np.isfinite(abs_g)
    dropped = int((~keep).sum())
    x, y, z, abs_g, teff, source_id = (v[keep] for v in (x, y, z, abs_g, teff, source_id))

    temperatures, rgb = build_lut(COLOUR_LUT_SIZE)
    colour = index_of_teff(teff, temperatures).astype(np.uint32)
    mag = quantise_magnitude(abs_g)

    flags = np.zeros(len(x), dtype=np.uint32)
    measured = table.column("teff").to_numpy(zero_copy_only=False)[keep]
    flags |= np.where(np.isfinite(measured), FLAG_TEFF_MEASURED, 0).astype(np.uint32)
    a_g = table.column("extinction_g").to_numpy(zero_copy_only=False)[keep]
    flags |= np.where(np.isfinite(a_g), FLAG_EXTINCTION_APPLIED, 0).astype(np.uint32)
    flags |= np.where(source_id == SUN_SOURCE_ID, FLAG_SYNTHETIC, 0).astype(np.uint32)

    packed = (
        (mag & MAG_MASK) << MAG_SHIFT
        | (colour & COLOUR_MASK) << COLOUR_SHIFT
        | (flags & FLAG_MASK) << FLAG_SHIFT
    ).astype(np.uint32)

    # Interleaved so one GPU buffer feeds two vertex attributes with no gather.
    records = np.empty((len(x), 4), dtype=np.uint32)
    records[:, 0] = np.asarray(x, np.float32).view(np.uint32)
    records[:, 1] = np.asarray(y, np.float32).view(np.uint32)
    records[:, 2] = np.asarray(z, np.float32).view(np.uint32)
    records[:, 3] = packed

    # Observed apparent G, as a parallel plane appended after the records.
    #
    # This is the planetarium view: what an observer on Earth actually measures,
    # needing no distance estimate and no extinction correction, and therefore
    # exact (PLAN.md 4.3). It is a genuinely different image, not a re-scaling
    # of the intrinsic one -- 29,307 stars in T0 differ by more than half a
    # magnitude once Earth's dust column is put back.
    #
    # A separate plane rather than a wider record: the hot path never reads it,
    # and planar layout is where the tile format is heading anyway (PLAN.md 4.6).
    apparent = quantise_apparent(
        table.column("phot_g_mean_mag").to_numpy(zero_copy_only=False).astype(np.float64)[keep]
    )
    # The Sun is at m = -26.9 from Earth and would set the exposure for the whole
    # sky. You do not see it in a night sky view, so it is excluded here rather
    # than special-cased in the shader.
    apparent = np.where(source_id == SUN_SOURCE_ID, NO_APPARENT_MAGNITUDE, apparent).astype(np.uint16)

    manifest = {
        "magic": MAGIC,
        "format_version": FORMAT_VERSION,
        "catalogue_version": release.catalogue_version,
        "release": release.slug,
        "reference_epoch": release.reference_epoch,
        "frame": "galactic-cartesian-parsec",
        "record_bytes": RECORD_BYTES,
        "record_count": int(len(x)),
        "layout": {
            "position": "3x float32 little-endian, parsecs",
            "packed_uint32": {
                "magnitude": {"bits": MAGNITUDE_BITS, "shift": MAG_SHIFT,
                              "min": ABS_MAG_MIN, "max": ABS_MAG_MAX},
                "colour": {"bits": 8, "shift": COLOUR_SHIFT, "lut_size": COLOUR_LUT_SIZE},
                "flags": {"bits": 8, "shift": FLAG_SHIFT},
            },
        },
        "apparent_magnitude_plane": {
            "offset_bytes": int(records.nbytes),
            "bits": APP_MAGNITUDE_BITS,
            "dtype": "uint16",
            "min": APP_MAG_MIN,
            "max": APP_MAG_MAX,
            "missing": NO_APPARENT_MAGNITUDE,
            "description": "observed Gaia G from Earth; exact, uncorrected",
        },
        "colour_lut": {
            "size": COLOUR_LUT_SIZE,
            "spacing": "perceptually uniform along the Planckian locus",
            "worst_adjacent_delta_e76": round(worst_adjacent_delta_e(temperatures), 4),
            "temperatures_k": [round(float(t), 1) for t in temperatures],
            "linear_srgb": [[round(float(c), 5) for c in row] for row in rgb],
        },
    }
    clipped = int(((abs_g < ABS_MAG_MIN) | (abs_g > ABS_MAG_MAX)).sum())
    stats = {
        "magnitude_clipped": clipped,
        "teff_measured": int((flags & FLAG_TEFF_MEASURED).astype(bool).sum()),
        "extinction_applied": int((flags & FLAG_EXTINCTION_APPLIED).astype(bool).sum()),
        "synthetic": int((flags & FLAG_SYNTHETIC).astype(bool).sum()),
    }
    stats["apparent_missing"] = int((apparent == NO_APPARENT_MAGNITUDE).sum())
    manifest["magnitude_clipped"] = clipped
    return EncodeResult(records.tobytes() + apparent.tobytes(), manifest, dropped, stats)


def decode(data: bytes, manifest: dict) -> dict[str, np.ndarray]:
    """Mirror of :func:`encode`, kept adjacent to it on purpose.

    A writer and a reader of a bit-packed format drift silently, and the failure
    mode is misplaced stars that no test notices. Keeping the pair in one file
    and round-tripping them in CI is the cheap defence (PLAN.md section 5.5).
    """
    if manifest["magic"] != MAGIC:
        raise ValueError(f"not a {MAGIC} file")
    if manifest["format_version"] != FORMAT_VERSION:
        raise ValueError(f"format version {manifest['format_version']} != {FORMAT_VERSION}")
    n = manifest["record_count"]
    r = np.frombuffer(data, dtype=np.uint32, count=n * 4).reshape(-1, 4)
    packed = r[:, 3]
    plane = manifest.get("apparent_magnitude_plane")
    apparent = (
        dequantise_apparent(
            np.frombuffer(data, dtype=np.uint16, count=n, offset=plane["offset_bytes"])
        )
        if plane
        else np.full(n, np.nan)
    )
    return {
        "apparent_g": apparent,
        "x_pc": r[:, 0].view(np.float32),
        "y_pc": r[:, 1].view(np.float32),
        "z_pc": r[:, 2].view(np.float32),
        "abs_g": dequantise_magnitude((packed >> MAG_SHIFT) & MAG_MASK),
        "colour_index": ((packed >> COLOUR_SHIFT) & COLOUR_MASK).astype(np.uint8),
        "flags": ((packed >> FLAG_SHIFT) & FLAG_MASK).astype(np.uint8),
    }
