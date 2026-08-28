"""Blackbody colour: Teff -> an 8-bit palette index, and the palette itself.

The palette is spaced to be **perceptually uniform** along the Planckian locus
rather than uniform in temperature. That is what makes 8 bits enough: the locus
is 160.6 dE76 long, so 256 equal steps are 0.63 dE76 apart against a
just-noticeable difference of about 2.3 -- visually lossless with 3.6x headroom.
Log-uniform spacing in Teff would put the worst step at 1.69, still under the
JND but with far less margin at the cool end where colour changes fastest.

See PLAN.md section 4.2; ``tools/verify_colour_quantisation.py`` derives the
numbers independently.
"""

from __future__ import annotations

import math

import numpy as np

from .constants import COLOUR_LUT_SIZE, TEFF_MAX_K, TEFF_MIN_K

# Planck's law constants
_H, _C, _KB = 6.62607015e-34, 2.99792458e8, 1.380649e-23

# Wyman, Sloan & Shirley multi-lobe Gaussian fits to the CIE 1931 2-degree
# colour matching functions. Accurate to ~1%, which is far below the JND and
# avoids shipping a tabulated dataset.
_XYZ_LOBES = (
    ((1.056, 599.8, 37.9, 31.0), (0.362, 442.0, 16.0, 26.7), (-0.065, 501.1, 20.4, 26.2)),
    ((0.821, 568.8, 46.9, 40.5), (0.286, 530.9, 16.3, 31.1)),
    ((1.217, 437.0, 11.8, 36.0), (0.681, 459.0, 26.0, 13.8)),
)

_SRGB_FROM_XYZ = np.array([
    [3.2406, -1.5372, -0.4986],
    [-0.9689, 1.8758, 0.0415],
    [0.0557, -0.2040, 1.0570],
])
_D65 = np.array([0.95047, 1.0, 1.08883])


def _lobe(lam: np.ndarray, w: float, mu: float, s1: float, s2: float) -> np.ndarray:
    t = (lam - mu) / np.where(lam < mu, s1, s2)
    return w * np.exp(-0.5 * t * t)


def _cmf(lam: np.ndarray) -> np.ndarray:
    return np.stack([sum(_lobe(lam, *p) for p in lobes) for lobes in _XYZ_LOBES])


def _planck(lam_nm: np.ndarray, teff: float) -> np.ndarray:
    lam = lam_nm * 1e-9
    return (2 * _H * _C**2) / lam**5 / np.expm1(_H * _C / (lam * _KB * teff))


def xyz_of_blackbody(teff: float) -> np.ndarray:
    """CIE XYZ of a blackbody at ``teff``, normalised to unit luminance."""
    lam = np.arange(360.0, 831.0)
    xyz = (_cmf(lam) * _planck(lam, teff)).sum(axis=1)
    return xyz / xyz[1]


def linear_srgb_of_blackbody(teff: float) -> np.ndarray:
    """Linear sRGB at unit luminance. Values may exceed 1 or fall below 0 --
    the Planckian locus leaves the sRGB gamut at both ends. Clamp at render
    time, not here, so the renderer can decide how to handle out-of-gamut."""
    return _SRGB_FROM_XYZ @ xyz_of_blackbody(teff)


def _lab(teff: float) -> np.ndarray:
    ratio = xyz_of_blackbody(teff) / _D65
    f = np.where(ratio > (6 / 29) ** 3, np.cbrt(ratio), ratio / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])])


def _delta_e(t1: float, t2: float) -> float:
    return float(np.linalg.norm(_lab(t1) - _lab(t2)))


def build_temperature_scale(size: int = COLOUR_LUT_SIZE, samples: int = 4096) -> np.ndarray:
    """The ``size`` temperatures whose colours are equally spaced perceptually.

    Walks the locus finely, accumulates arc length in dE76, then resamples at
    equal arc intervals. This is what buys the headroom over log-uniform.
    """
    fine = np.geomspace(TEFF_MIN_K, TEFF_MAX_K, samples)
    steps = np.array([_delta_e(a, b) for a, b in zip(fine[:-1], fine[1:])])
    arc = np.concatenate([[0.0], np.cumsum(steps)])
    return np.interp(np.linspace(0.0, arc[-1], size), arc, fine)


def build_lut(size: int = COLOUR_LUT_SIZE) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(temperatures, linear_rgb)`` for the palette."""
    temps = build_temperature_scale(size)
    rgb = np.stack([linear_srgb_of_blackbody(t) for t in temps])
    return temps, rgb


def index_of_teff(teff: np.ndarray, temperatures: np.ndarray) -> np.ndarray:
    """Nearest palette index for each temperature. Vectorised; clamps to range."""
    t = np.clip(np.asarray(teff, dtype=float), temperatures[0], temperatures[-1])
    right = np.searchsorted(temperatures, t)
    left = np.clip(right - 1, 0, len(temperatures) - 1)
    right = np.clip(right, 0, len(temperatures) - 1)
    take_left = np.abs(t - temperatures[left]) <= np.abs(temperatures[right] - t)
    return np.where(take_left, left, right).astype(np.uint8)


def worst_adjacent_delta_e(temperatures: np.ndarray) -> float:
    """Largest perceptual gap between neighbouring palette entries.

    Asserted in tests. If this creeps above the ~2.3 JND, banding becomes
    visible on smooth colour gradients and 8 bits is no longer enough.
    """
    return max(_delta_e(a, b) for a, b in zip(temperatures[:-1], temperatures[1:]))
