"""Known-star checks, run against derived data when it exists.

Skipped when the tier has not been built, so CI stays green on a fresh clone;
the full run is `python validate_known_stars.py`.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from catasterism.known_stars import ABSENT_SATURATED, PRESENT

DERIVED = Path(__file__).resolve().parents[2] / "data/derived/dr3/t0.parquet"
pytestmark = pytest.mark.skipif(
    not DERIVED.exists(), reason="t0 not built; run acquire_t0.py then derive_t0.py"
)


@pytest.fixture(scope="module")
def rows():
    import pyarrow.parquet as pq

    t = pq.read_table(DERIVED)
    by_id = {}
    sid = t.column("source_id").to_pylist()
    cols = {n: t.column(n).to_pylist() for n in
            ("distance_pc", "abs_g", "teff_derived", "x_pc", "y_pc", "z_pc")}
    wanted = {s.source_id for s in PRESENT}
    for i, s in enumerate(sid):
        if s in wanted:
            by_id[s] = {n: cols[n][i] for n in cols}
    return by_id


@pytest.mark.parametrize("star", PRESENT, ids=lambda s: s.name)
def test_reference_star_distance(rows, star):
    """Catches unit errors and sign flips in the parallax->distance conversion."""
    assert star.source_id in rows, f"{star.name} missing from the tier"
    d = rows[star.source_id]["distance_pc"]
    assert abs(d - star.distance_pc) <= star.tolerance_pc, (
        f"{star.name}: {d:.3f} pc, expected {star.distance_pc:.3f}"
    )


@pytest.mark.parametrize("star", PRESENT, ids=lambda s: s.name)
def test_cartesian_preserves_radius(rows, star):
    """Catches frame errors in the ICRS -> Galactic Cartesian conversion."""
    r = rows[star.source_id]
    radius = math.sqrt(r["x_pc"] ** 2 + r["y_pc"] ** 2 + r["z_pc"] ** 2)
    assert abs(radius - r["distance_pc"]) < 1e-6 * r["distance_pc"]


@pytest.mark.parametrize("star", PRESENT, ids=lambda s: s.name)
def test_reference_star_is_physically_sensible(rows, star):
    """Both references are nearby M dwarfs: faint and cool. Catches a missing
    extinction term or a broken colour->Teff fallback, which would move these."""
    r = rows[star.source_id]
    assert 10.0 < r["abs_g"] < 16.0, f"{star.name}: M_G {r['abs_g']:.2f} is not an M dwarf"
    assert 2500.0 < r["teff_derived"] < 3800.0, f"{star.name}: Teff {r['teff_derived']:.0f} K"


def test_the_bright_gap_is_documented():
    """These are absent because Gaia saturates. Recorded so a future release
    that adds them is noticed rather than silently changing the sky."""
    assert len(ABSENT_SATURATED) >= 5
