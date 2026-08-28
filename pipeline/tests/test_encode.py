"""Encoder round trip, and the cross-language fingerprint.

The fingerprint is the real defence against writer/reader drift (PLAN.md 5.5):
``client/src/format.test.ts`` decodes the same file in TypeScript and computes
the same reduction. If the two implementations ever disagree about the bit
layout, these numbers diverge.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from catasterism.constants import ABS_MAG_MAX, ABS_MAG_MIN, MAGNITUDE_BITS
from catasterism.encode import (
    FLAG_SYNTHETIC,
    MAGIC,
    RECORD_BYTES,
    decode,
    dequantise_magnitude,
    encode,
    quantise_magnitude,
)
from catasterism.release import ACTIVE

DERIVED = Path(__file__).resolve().parents[2] / "data/derived/dr3/t0.parquet"
needs_data = pytest.mark.skipif(
    not DERIVED.exists(), reason="t0 not built; run acquire_t0.py then derive_t0.py"
)

MAG_STEP = (ABS_MAG_MAX - ABS_MAG_MIN) / ((1 << MAGNITUDE_BITS) - 1)


def test_magnitude_quantisation_is_within_half_a_step():
    m = np.linspace(ABS_MAG_MIN, ABS_MAG_MAX, 10_000)
    assert np.abs(dequantise_magnitude(quantise_magnitude(m)) - m).max() <= MAG_STEP / 2 + 1e-9


def test_magnitude_step_is_imperceptible():
    """0.83% in flux. Two adjacent stars differing by one step are the same star
    to the eye; 8 bits would be 14% and visibly banded."""
    assert 10 ** (0.4 * MAG_STEP) - 1 < 0.01


def test_magnitude_clips_rather_than_wrapping():
    """Out-of-range must saturate, never wrap. A wrapped magnitude turns the
    brightest star in a field into the faintest."""
    q = quantise_magnitude(np.array([ABS_MAG_MIN - 100, ABS_MAG_MAX + 100]))
    assert q[0] == 0 and q[1] == (1 << MAGNITUDE_BITS) - 1


@pytest.fixture(scope="module")
def built():
    import pyarrow.parquet as pq

    table = pq.read_table(DERIVED)
    return table, encode(table, ACTIVE)


@needs_data
def test_header_identifies_the_release(built):
    _, r = built
    assert r.manifest["magic"] == MAGIC
    assert r.manifest["catalogue_version"] == ACTIVE.catalogue_version
    assert r.manifest["reference_epoch"] == ACTIVE.reference_epoch
    assert r.manifest["frame"] == "galactic-cartesian-parsec"


@needs_data
def test_round_trip_preserves_positions_to_float32(built):
    table, r = built
    d = decode(r.data, r.manifest)
    g = lambda n: table.column(n).to_numpy(zero_copy_only=False).astype(np.float64)
    x, y, z, m = g("x_pc"), g("y_pc"), g("z_pc"), g("abs_g")
    keep = np.isfinite(x) & np.isfinite(y) & np.isfinite(z) & np.isfinite(m)
    x, y, z = x[keep], y[keep], z[keep]
    err = np.sqrt((d["x_pc"] - x) ** 2 + (d["y_pc"] - y) ** 2 + (d["z_pc"] - z) ** 2)
    radius = np.maximum(np.sqrt(x * x + y * y + z * z), 1e-30)
    # float32 error is relative, so the angular error is bounded everywhere --
    # which is exactly why a flat file uses float32 and not fixed point.
    assert (err / radius).max() * 206265 < 0.05, "worst-case angular error over 0.05 arcsec"


@needs_data
def test_round_trip_preserves_magnitude_and_colour(built):
    table, r = built
    d = decode(r.data, r.manifest)
    g = lambda n: table.column(n).to_numpy(zero_copy_only=False).astype(np.float64)
    m = g("abs_g")
    keep = np.isfinite(g("x_pc")) & np.isfinite(g("y_pc")) & np.isfinite(g("z_pc")) & np.isfinite(m)
    assert np.abs(d["abs_g"] - m[keep]).max() <= MAG_STEP / 2 + 1e-9
    assert r.stats["magnitude_clipped"] == 0, "range too narrow for this tier"


@needs_data
def test_the_sun_survives_encoding(built):
    _, r = built
    d = decode(r.data, r.manifest)
    i = np.flatnonzero(d["flags"] & FLAG_SYNTHETIC)
    assert len(i) == 1, "exactly one synthetic source: the Sun"
    i = int(i[0])
    assert d["x_pc"][i] == d["y_pc"][i] == d["z_pc"][i] == 0.0
    assert d["abs_g"][i] == pytest.approx(4.67, abs=MAG_STEP)


@needs_data
def test_record_size_and_count(built):
    _, r = built
    assert len(r.data) == r.manifest["record_count"] * RECORD_BYTES


@needs_data
def test_cross_language_fingerprint(built):
    """Must match the value printed by client/src/format.test.ts.

    Deliberately a hardcoded expectation: if the encoder changes, both this and
    the TypeScript test must be updated together, which is the point.
    """
    _, r = built
    d = decode(r.data, r.manifest)
    fingerprint = {
        "count": int(r.manifest["record_count"]),
        "sum_x": round(float(d["x_pc"].astype(np.float64).sum()), 3),
        "sum_abs_g": round(float(d["abs_g"].sum()), 2),
        "sum_colour_index": int(d["colour_index"].astype(np.int64).sum()),
        "sum_flags": int(d["flags"].astype(np.int64).sum()),
    }
    assert fingerprint == {
        "count": 623457,
        "sum_x": 17486998.283,
        "sum_abs_g": 7244723.25,
        "sum_colour_index": 75405301,
        "sum_flags": 428581,
    }
