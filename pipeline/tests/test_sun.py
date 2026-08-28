"""The Sun is the only star whose true values we know independently of Gaia,
which makes it the one absolute check on the brightness pipeline.
"""

from __future__ import annotations

import math

import numpy as np
import pyarrow as pa
import pytest

from catasterism.constants import SUN_ABS_G_MAG, SUN_TEFF_K
from catasterism.sun import (
    AU_PC,
    SUN_SOURCE_ID,
    apparent_magnitude,
    insert_sun,
    luminosity_solar,
    radius_solar,
    sun_row,
)


def test_apparent_magnitude_from_earth():
    """The calibration check. If this drifts, every star's brightness is wrong
    and no other star can tell you so."""
    assert apparent_magnitude(SUN_ABS_G_MAG, AU_PC) == pytest.approx(-26.90, abs=0.01)


def test_absolute_magnitude_is_apparent_at_ten_parsecs():
    """The definition of absolute magnitude; catches a wrong distance modulus."""
    assert apparent_magnitude(SUN_ABS_G_MAG, 10.0) == pytest.approx(SUN_ABS_G_MAG)


def test_sun_leaves_naked_eye_visibility_inside_the_t0_shell():
    """The 'look back' moment: home vanishes well before the edge of T0."""
    limit = 10.0 * 10.0 ** ((6.5 - SUN_ABS_G_MAG) / 5.0)
    assert limit == pytest.approx(23.2, abs=0.1)
    assert limit < 100.0, "the Sun must vanish inside T0's own 100 pc shell"


def test_inverse_square_law():
    """Ten times further is five magnitudes fainter, exactly."""
    near, far = apparent_magnitude(SUN_ABS_G_MAG, 10.0), apparent_magnitude(SUN_ABS_G_MAG, 100.0)
    assert far - near == pytest.approx(5.0)


def test_solar_values_are_self_consistent():
    """Anchors the luminosity and radius relations at exactly 1.0."""
    assert luminosity_solar(SUN_ABS_G_MAG) == pytest.approx(1.0)
    assert radius_solar(SUN_ABS_G_MAG, SUN_TEFF_K) == pytest.approx(1.0)


def test_radius_relation_is_documented_as_approximate():
    """Sirius A is within ~15%; Betelgeuse is not. The relation omits the
    bolometric correction, so cool giants come out far too small -- recorded
    here so the disc transition (T5) does not adopt it blindly."""
    assert radius_solar(1.43, 9940) == pytest.approx(1.50, abs=0.05)
    assert radius_solar(-5.85, 3600) < 0.5 * 750, "cool-giant radii are badly underestimated"


def test_vectorises():
    """Used per-star over hundreds of millions of rows, so it must be array-safe."""
    d = np.array([1.0, 10.0, 100.0])
    assert apparent_magnitude(SUN_ABS_G_MAG, d).shape == (3,)


def _fake_table():
    row = sun_row()
    return pa.table({k: pa.array([1.0 if k != "source_id" else 12345], type=pa.float64() if k != "source_id" else pa.int64())
                     for k in row})


def test_insert_sun_appends_one_row_at_the_origin():
    t = insert_sun(_fake_table())
    assert t.num_rows == 2
    i = t.column("source_id").to_pylist().index(SUN_SOURCE_ID)
    for axis in ("x_pc", "y_pc", "z_pc", "distance_pc"):
        assert t.column(axis).to_pylist()[i] == 0.0


def test_insert_sun_refuses_to_collide():
    """source_id 0 is a sentinel; DR3 has no source below 1000. If a release
    ever did, silently overwriting it would be much worse than failing."""
    row = sun_row()
    t = pa.table({k: pa.array([SUN_SOURCE_ID if k == "source_id" else 1.0],
                              type=pa.int64() if k == "source_id" else pa.float64())
                  for k in row})
    with pytest.raises(ValueError, match="collides"):
        insert_sun(t)


def test_sun_row_invents_nothing():
    """Observational columns must be NaN, not fabricated. The Sun has no Gaia
    astrometry and its ra/dec from Earth changes daily."""
    row = sun_row()
    for k in ("ra", "dec", "parallax", "parallax_over_error", "ruwe"):
        assert math.isnan(row[k]), f"{k} should be NaN, not invented"
    # the honest exception: this column holds what an Earth observer measures
    assert row["phot_g_mean_mag"] == pytest.approx(-26.90, abs=0.01)
