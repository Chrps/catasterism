"""The Sun — the one star that is not in the catalogue.

Gaia cannot observe the Sun, so the most important object in the product has to
be inserted by hand. It is the origin, the orientation anchor, the "home"
target, and the first star anyone flies to.

It is also the **calibration reference**. Its values are known far better than
any Gaia source, so it is the only star that can check the brightness pipeline
absolutely: if the Sun does not come out at m_G = -26.90 from 1 AU, the
magnitude machinery is wrong and every other star is wrong too -- you just
cannot tell from the others.

See PLAN.md section 4.7.
"""

from __future__ import annotations

import numpy as np
import pyarrow as pa

from .constants import (
    AU_M,
    PC_M,
    SUN_ABS_G_MAG,
    SUN_BP_RP,
    SUN_TEFF_K,
)

SUN_SOURCE_ID = 0
"""Sentinel. Verified safe: Gaia DR3 contains no source_id below 1000, so this
cannot collide with a real source. Release-tagging (``Release.tag_id``) still
applies -- a client must not treat id 0 as a catalogue entry."""

AU_PC = AU_M / PC_M


def apparent_magnitude(abs_mag, distance_pc):
    """Apparent magnitude of a source of absolute magnitude ``abs_mag``.

    The renderer's whole job, in one line: brightness is a property of where you
    are standing, which is exactly why the catalogue stores the absolute value
    (PLAN.md section 4.3).
    """
    return abs_mag + 5.0 * np.log10(np.asarray(distance_pc, dtype=float) / 10.0)


def luminosity_solar(abs_g):
    """Luminosity in solar units, from absolute G magnitude.

    Approximate: it ignores the bolometric correction, so it understates hot and
    cool stars, which radiate largely outside the G band. Exact for the Sun by
    construction, which is what makes it useful as a calibration check.
    """
    return 10.0 ** (-0.4 * (np.asarray(abs_g, dtype=float) - SUN_ABS_G_MAG))


def radius_solar(abs_g, teff_k):
    """Radius in solar units, from ``L = 4 pi R^2 sigma T^4``.

    Feeds the point-sprite to resolved-disc transition (PLAN.md section 6.2),
    which needs a radius for every star -- and gets one for free from two values
    already stored, rather than another four bytes per record.

    **Accuracy degrades away from solar temperature**, because
    :func:`luminosity_solar` omits the bolometric correction. Measured against
    accepted values:

    ========================  ==========  ==========  =========
    star                      predicted   accepted    error
    ========================  ==========  ==========  =========
    Sun (5772 K)              1.00 Rsun   1.00 Rsun   exact
    Sirius A (9940 K)         1.50 Rsun   1.71 Rsun   -12%
    Betelgeuse (3600 K)        327 Rsun    750 Rsun   -56%
    ========================  ==========  ==========  =========

    Fine for a sprite-size heuristic near solar Teff; badly wrong for cool
    giants, which radiate mostly in the infrared where G does not look. Before
    the disc transition ships (T5), prefer DR3's measured ``radius_gspphot``
    where present and apply a BC(Teff) relation otherwise -- Betelgeuse
    rendering at less than half its true size is the kind of error a viewer
    notices without being able to name.
    """
    lum = luminosity_solar(abs_g)
    return np.sqrt(lum) * (SUN_TEFF_K / np.asarray(teff_k, dtype=float)) ** 2


def sun_row() -> dict[str, float]:
    """The Sun as one row of the derived schema.

    Observational columns are NaN rather than invented: the Sun has no Gaia
    astrometry, and its ra/dec as seen from Earth changes daily, so any value
    would be a fiction. ``phot_g_mean_mag`` is the honest exception -- it is
    what an observer on Earth actually measures, which is precisely the quantity
    that column holds.
    """
    return {
        "source_id": SUN_SOURCE_ID,
        "ra": float("nan"),
        "dec": float("nan"),
        "parallax": float("nan"),
        "parallax_error": float("nan"),
        "parallax_over_error": float("nan"),
        "phot_g_mean_mag": float(apparent_magnitude(SUN_ABS_G_MAG, AU_PC)),
        "bp_rp": SUN_BP_RP,
        "teff": SUN_TEFF_K,
        "extinction_g": 0.0,  # nothing between us and it
        "reddening_bp_rp": 0.0,
        "ruwe": float("nan"),
        "distance_pc": 0.0,
        "abs_g": SUN_ABS_G_MAG,
        "teff_derived": SUN_TEFF_K,
        "bp_rp0": SUN_BP_RP,
        "x_pc": 0.0,
        "y_pc": 0.0,
        "z_pc": 0.0,
    }


def insert_sun(table: pa.Table) -> pa.Table:
    """Append the Sun to a derived table, failing loudly on a collision."""
    sid = table.column("source_id").to_numpy(zero_copy_only=False)
    if (sid == SUN_SOURCE_ID).any():
        raise ValueError(
            f"source_id {SUN_SOURCE_ID} already present; the Sun sentinel collides"
        )
    row = sun_row()
    missing = set(table.column_names) - set(row)
    if missing:
        raise ValueError(f"sun_row is missing derived columns: {sorted(missing)}")
    extra = pa.table(
        {name: pa.array([row[name]], type=table.schema.field(name).type)
         for name in table.column_names}
    )
    return pa.concat_tables([table, extra])
