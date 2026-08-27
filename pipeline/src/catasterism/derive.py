"""Stage 2 — turn what Gaia observed into what a star intrinsically is.

Two rules govern everything here (PLAN.md §4.3):

* **Store intrinsic properties, never apparent ones.** Apparent magnitude is a
  fact about standing on Earth and is wrong the moment the camera moves.
* **Subtract extinction.** Skipping ``A_G`` bakes Earth's dust column into a
  star's intrinsic luminosity permanently. Nothing looks broken; the stars are
  just quietly wrong. This is the silent error.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pyarrow as pa
from astropy.coordinates import SkyCoord
from astropy import units as u

# Fallback Teff for stars with neither a measured value nor a usable colour.
NEUTRAL_TEFF_K = 5800.0
COLOUR_FIT_DEGREE = 5


@dataclass(frozen=True)
class ColourTeffFit:
    """log10(Teff) as a polynomial in de-reddened BP-RP.

    Calibrated on this very dataset rather than an external table: roughly 75%
    of stars carry both a measured Teff and a colour, which is ample to fit the
    relation and apply it to the remaining quarter. Self-consistent, and its
    residual is a directly checkable number.
    """

    coefficients: np.ndarray
    valid_range: tuple[float, float]
    residual_dex: float
    n_calibrators: int

    def __call__(self, bp_rp0: np.ndarray) -> np.ndarray:
        clipped = np.clip(bp_rp0, *self.valid_range)
        return 10.0 ** np.polyval(self.coefficients, clipped)


def fit_colour_teff(bp_rp0: np.ndarray, teff: np.ndarray) -> ColourTeffFit:
    ok = np.isfinite(bp_rp0) & np.isfinite(teff) & (teff > 0)
    x, y = bp_rp0[ok], np.log10(teff[ok])
    lo, hi = float(np.nanpercentile(x, 0.1)), float(np.nanpercentile(x, 99.9))
    inside = (x >= lo) & (x <= hi)
    coeffs = np.polyfit(x[inside], y[inside], COLOUR_FIT_DEGREE)
    residual = float(np.std(y[inside] - np.polyval(coeffs, x[inside])))
    return ColourTeffFit(coeffs, (lo, hi), residual, int(inside.sum()))


def derive(table: pa.Table) -> tuple[pa.Table, ColourTeffFit, dict]:
    """Add distance, intrinsic magnitude, Teff and Galactic Cartesian position."""
    col = lambda n: table.column(n).to_numpy(zero_copy_only=False).astype(np.float64)

    parallax = col("parallax")
    g = col("phot_g_mean_mag")
    bp_rp = col("bp_rp")
    teff_measured = col("teff")
    a_g = col("extinction_g")
    e_bp_rp = col("reddening_bp_rp")

    # Distance. Valid only where parallax is positive; T0's selection guarantees
    # that for the d<100pc half but not for the bright half, where Gaia
    # saturates and some parallaxes are missing or negative.
    with np.errstate(divide="ignore", invalid="ignore"):
        distance_pc = np.where(parallax > 0, 1000.0 / parallax, np.nan)

    # Absolute magnitude, extinction removed. The A_G term is not optional.
    a_g_filled = np.where(np.isfinite(a_g), a_g, 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        abs_g = g + 5.0 * np.log10(parallax) - 10.0 - a_g_filled
    abs_g = np.where(parallax > 0, abs_g, np.nan)

    # De-reddened colour, then Teff: measured where available, fitted otherwise.
    bp_rp0 = bp_rp - np.where(np.isfinite(e_bp_rp), e_bp_rp, 0.0)
    fit = fit_colour_teff(bp_rp0, teff_measured)
    teff = np.where(np.isfinite(teff_measured) & (teff_measured > 0), teff_measured, np.nan)
    from_colour = np.isnan(teff) & np.isfinite(bp_rp0)
    teff = np.where(from_colour, fit(bp_rp0), teff)
    neutral = np.isnan(teff)
    teff = np.where(neutral, NEUTRAL_TEFF_K, teff)

    # ICRS -> Galactic Cartesian, parsecs. Galactic so the disc lies in a plane,
    # which every later visual decision benefits from. astropy rather than a
    # hand-rolled matrix: it gets the frame definition right, and Step 3 will
    # cross-match Hipparcos at a different epoch through the same machinery.
    gal = SkyCoord(
        ra=col("ra") * u.deg, dec=col("dec") * u.deg, frame="icrs"
    ).galactic
    l, b = gal.l.radian, gal.b.radian
    x = distance_pc * np.cos(b) * np.cos(l)
    y = distance_pc * np.cos(b) * np.sin(l)
    z = distance_pc * np.sin(b)

    stats = {
        "rows": table.num_rows,
        "teff_measured": int(np.isfinite(teff_measured).sum()),
        "teff_from_colour": int(from_colour.sum()),
        "teff_neutral": int(neutral.sum()),
        "extinction_available": int(np.isfinite(a_g).sum()),
        "extinction_gt_1mag": int((a_g_filled > 1.0).sum()),
        "no_distance": int((~np.isfinite(distance_pc)).sum()),
        "median_a_g": float(np.nanmedian(a_g)) if np.isfinite(a_g).any() else 0.0,
    }

    out = table.append_column("distance_pc", pa.array(distance_pc))
    for name, values in (
        ("abs_g", abs_g), ("teff_derived", teff), ("bp_rp0", bp_rp0),
        ("x_pc", x), ("y_pc", y), ("z_pc", z),
    ):
        out = out.append_column(name, pa.array(values))
    return out, fit, stats
