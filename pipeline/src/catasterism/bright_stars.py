"""Patch the bright stars Gaia cannot see.

Gaia saturates around G ~ 3, so the stars that *define* constellations are
precisely the ones it measures worst or not at all. Measured against Hipparcos:

    Hp < 3.0    108 of  165 stars have no Gaia DR3 counterpart   (65%)
    Hp < 4.5    311 of  837                                      (37%)
    Hp < 6.5  1,596 of 7,982                                     (20%)

Every one of the 25 brightest stars in the sky is absent -- Sirius, Vega, Rigel,
Betelgeuse, Aldebaran. Orion's belt survives as one star of three. Without this
patch the question "does the sky look right" cannot be answered at all, which is
why it belongs in Step 1 rather than Step 3.

Two transformations are needed, and both are **fitted on stars where we have
both catalogues** rather than taken from a paper. That makes them
self-consistent with this data and gives a residual that is a checkable number.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
import pyarrow as pa
from astropy import units as u
from astropy.coordinates import SkyCoord
import pyarrow.csv as pacsv
import requests

from .acquire import TIMEOUT_SECONDS, USER_AGENT
from .encode import FLAG_SYNTHETIC
from .release import TAP_ENDPOINT, Release

HIPPARCOS_EPOCH = 1991.25
"""van Leeuwen (2007) re-reduction. Positions must be propagated from here to
the release's own epoch before they can be compared with Gaia's."""

DEFAULT_MAGNITUDE_LIMIT = 6.5
"""The naked-eye limit. Beyond it Gaia's coverage is good and the patch would
be adding stars that are already there."""

FLAG_PATCHED = 1 << 3
"""From Hipparcos, not Gaia. Distinct from FLAG_SYNTHETIC (the Sun) so the two
kinds of non-Gaia source stay tellable apart."""

# Bright stars Gaia cannot place.
#
# Two cases, and the second is easy to miss: a star with no Gaia counterpart at
# all, and a star that HAS one but with no parallax. The second still has no
# usable position, so it is dropped at encoding and vanishes from the render
# exactly as if it were absent -- 185 stars brighter than Hp 6.5 are in that
# state. Patching only the first case leaves holes in constellations whose stars
# appear, from the outside, to be present.
_MISSING_QUERY = """
SELECT h.hip, h.ra, h.dec, h.plx, h.pm_ra, h.pm_de, h.hp_mag, h.b_v, o.vmag
FROM public.hipparcos_newreduction AS h
LEFT OUTER JOIN {xmatch} AS x ON h.hip = x.original_ext_source_id
LEFT OUTER JOIN {source} AS g ON g.source_id = x.source_id
LEFT OUTER JOIN public.hipparcos AS o ON h.hip = o.hip
WHERE h.hp_mag < {limit} AND h.plx > 0
  AND o.vmag IS NOT NULL AND h.b_v IS NOT NULL
  AND (x.source_id IS NULL OR g.parallax IS NULL)
"""

# Stars in BOTH catalogues, used to calibrate the colour transformation.
_CALIBRATION_QUERY = """
SELECT o.vmag, h.b_v, g.phot_g_mean_mag
FROM public.hipparcos_newreduction AS h
JOIN {xmatch} AS x ON h.hip = x.original_ext_source_id
JOIN {source} AS g ON g.source_id = x.source_id
JOIN public.hipparcos AS o ON h.hip = o.hip
WHERE h.hp_mag < 8.5 AND o.vmag IS NOT NULL AND h.b_v IS NOT NULL
  AND g.phot_g_mean_mag IS NOT NULL
"""


@dataclass(frozen=True)
class ColourTransform:
    """``G - V`` as a cubic in ``B - V``, fitted on the overlap."""

    coefficients: np.ndarray
    sigma_mag: float
    n_calibrators: int
    n_clipped: int

    def to_g(self, vmag: np.ndarray, b_v: np.ndarray) -> np.ndarray:
        return vmag + np.polyval(self.coefficients, np.clip(b_v, -0.4, 2.5))


def _query(sql: str, session: requests.Session) -> pa.Table:
    response = session.get(
        TAP_ENDPOINT,
        params={"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": sql},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    if response.content.lstrip()[:1] == b"<":
        raise RuntimeError(f"TAP error: {response.content[:200]!r}")
    return pacsv.read_csv(io.BytesIO(response.content))


def fit_colour_transform(table: pa.Table) -> ColourTransform:
    """Fit ``G - V`` against ``B - V``, clipping the tail.

    The raw scatter is 0.30 mag, but 7.3% of it is variables, unresolved
    binaries and bad Hipparcos photometry. One sigma-clip pass brings the
    residual to about 0.04 mag, which is 4% in flux and invisible in a
    starfield -- this patch exists to put Sirius back in the sky, not to do
    photometry.
    """
    col = lambda n: table.column(n).to_numpy(zero_copy_only=False).astype(np.float64)
    v, b_v, g = col("vmag"), col("b_v"), col("phot_g_mean_mag")
    ok = np.isfinite(v) & np.isfinite(b_v) & np.isfinite(g) & (b_v > -0.4) & (b_v < 2.5)
    x, y = b_v[ok], (g - v)[ok]

    coeffs = np.polyfit(x, y, 3)
    residual = y - np.polyval(coeffs, x)
    mad = np.median(np.abs(residual - np.median(residual))) * 1.4826
    keep = np.abs(residual - np.median(residual)) < 3 * mad

    coeffs = np.polyfit(x[keep], y[keep], 3)
    final = y[keep] - np.polyval(coeffs, x[keep])
    return ColourTransform(coeffs, float(final.std()), int(keep.sum()), int((~keep).sum()))


def teff_from_b_v(b_v: np.ndarray) -> np.ndarray:
    """Ballesteros (2012), treating the star as two blackbodies through B and V.

    Checked against ``teff_gspphot`` for 27,321 stars in both catalogues: 8.8%
    scatter with a +0.4% median bias. That is roughly seven steps of the 256-entry
    colour palette -- coarser than a GSP-Phot temperature, and far better than
    the alternative of having no star there at all.
    """
    x = 0.92 * np.asarray(b_v, dtype=float)
    return 4600.0 * (1.0 / (x + 1.70) + 1.0 / (x + 0.62))


def propagate(ra_deg, dec_deg, pm_ra_mas_yr, pm_dec_mas_yr, years: float):
    """Move positions along their proper motion. ``pm_ra`` includes cos(dec).

    Hipparcos is epoch J1991.25; the target epoch comes from the release
    descriptor, and for DR3 the baseline is roughly a quarter century. Most
    bright stars barely move over that, but the ones that do move a lot --
    Arcturus covers 56 arcseconds -- and mixing epochs is how a cross-match
    silently selects the wrong star (PLAN.md 9, stage 2 step 7).
    """
    dec = np.asarray(dec_deg, dtype=float)
    cos_dec = np.cos(np.radians(dec))
    ra = np.asarray(ra_deg, dtype=float) + (
        np.asarray(pm_ra_mas_yr, dtype=float) * years / 3.6e6
    ) / np.where(np.abs(cos_dec) < 1e-6, 1e-6, cos_dec)
    return ra % 360.0, dec + np.asarray(pm_dec_mas_yr, dtype=float) * years / 3.6e6


def fetch(release: Release, limit: float = DEFAULT_MAGNITUDE_LIMIT):
    """Return ``(missing_stars, colour_transform)`` for this release."""
    xmatch = f"{release.slug and 'gaia' + release.slug}.hipparcos2_best_neighbour"
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    calibration = _query(
        _CALIBRATION_QUERY.format(xmatch=xmatch, source=release.source_table), session
    )
    missing = _query(
        _MISSING_QUERY.format(xmatch=xmatch, source=release.source_table, limit=limit),
        session,
    )
    return missing, fit_colour_transform(calibration)


def append_to(
    derived: pa.Table, missing: pa.Table, transform: ColourTransform, release: Release
) -> pa.Table:
    """Append the patched stars to a derived table, matching its schema."""
    rows = to_rows(missing, transform, release)
    n = len(rows["ra"])

    l = np.radians(rows["l"])
    b = np.radians(rows["b"])
    d = rows["distance_pc"]
    columns: dict[str, np.ndarray] = {
        # Negative ids: cannot collide with Gaia's positive ones or the Sun's
        # zero, and -hip keeps the Hipparcos identity recoverable.
        "source_id": -rows["hip"].astype(np.int64),
        "ra": rows["ra"],
        "dec": rows["dec"],
        "parallax": rows["parallax"],
        "parallax_error": np.full(n, np.nan),
        "parallax_over_error": np.full(n, np.nan),
        "phot_g_mean_mag": rows["phot_g_mean_mag"],
        "bp_rp": np.full(n, np.nan),
        "teff": np.full(n, np.nan),        # not a GSP-Phot value; derived below
        "extinction_g": np.full(n, np.nan),
        "reddening_bp_rp": np.full(n, np.nan),
        "ruwe": np.full(n, np.nan),
        "distance_pc": d,
        "abs_g": rows["abs_g"],
        "teff_derived": rows["teff"],
        "bp_rp0": np.full(n, np.nan),
        "x_pc": d * np.cos(b) * np.cos(l),
        "y_pc": d * np.cos(b) * np.sin(l),
        "z_pc": d * np.sin(b),
    }
    extra = pa.table(
        {name: pa.array(columns[name], type=derived.schema.field(name).type)
         for name in derived.column_names}
    )
    return pa.concat_tables([derived, extra])


def to_rows(missing: pa.Table, transform: ColourTransform, release: Release) -> dict:
    """Convert Hipparcos rows into the derived schema, in canonical columns."""
    col = lambda n: missing.column(n).to_numpy(zero_copy_only=False).astype(np.float64)
    v, b_v, plx = col("vmag"), col("b_v"), col("plx")

    years = release.reference_epoch - HIPPARCOS_EPOCH
    ra, dec = propagate(col("ra"), col("dec"), col("pm_ra"), col("pm_de"), years)

    g = transform.to_g(v, b_v)
    teff = teff_from_b_v(b_v)
    distance = 1000.0 / plx
    # No extinction term: Hipparcos gives none, and these stars are bright and
    # mostly nearby, so the dust column is small. Stated rather than hidden --
    # it means their absolute magnitudes are slightly too faint.
    abs_g = g + 5.0 * np.log10(plx) - 10.0

    # ICRS -> galactic, the same conversion derive.py performs for Gaia rows.
    gal = SkyCoord(ra=ra * u.deg, dec=dec * u.deg, frame="icrs").galactic

    return {
        "hip": missing.column("hip").to_numpy(zero_copy_only=False),
        "l": gal.l.degree,
        "b": gal.b.degree,
        "ra": ra,
        "dec": dec,
        "parallax": plx,
        "phot_g_mean_mag": g,
        "vmag": v,
        "bp_rp": np.full(len(v), np.nan),
        "teff": teff,
        "distance_pc": distance,
        "abs_g": abs_g,
        "flags": np.full(len(v), FLAG_PATCHED, dtype=np.uint32),
    }
