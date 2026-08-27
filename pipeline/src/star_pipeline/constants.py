"""Physical constants and the Sun.

Release-independent. Anything that changes between Gaia releases belongs in
:mod:`star_pipeline.release`, not here.
"""

from __future__ import annotations

PC_M = 3.0856775814913673e16
AU_M = 1.495978707e11
RSUN_M = 6.957e8
SIGMA_SB = 5.670374419e-8

# --- The Sun -------------------------------------------------------------
# Gaia cannot observe the Sun, so it is inserted by hand. It is the origin, the
# orientation anchor, the "home" target, and the calibration reference for the
# whole brightness pipeline -- its values are known far better than any Gaia
# source, so if the Sun renders wrong, every star is wrong and you cannot tell
# from the others. See PLAN.md section 4.7.
#
# Position is exactly the origin: Gaia is barycentric and the Sun orbits the
# barycentre by ~0.005 AU = 2.4e-8 pc, nine orders below anything visible.
SUN_ABS_G_MAG = 4.67      # Casagrande & VandenBerg (2018); DR3 docs give 4.66
SUN_TEFF_K = 5772.0       # IAU nominal
SUN_BP_RP = 0.82          # (BP-G) = 0.33, (G-RP) = 0.49
SUN_POSITION_PC = (0.0, 0.0, 0.0)

# --- Colour palette ------------------------------------------------------
# 8-bit index into a dE-uniform blackbody LUT. Measured worst adjacent step is
# 0.63 dE76 against a JND of ~2.3, i.e. visually lossless with 3.6x headroom.
# See PLAN.md section 4.2 and tools/verify_colour_quantisation.py.
TEFF_MIN_K, TEFF_MAX_K = 2000.0, 50000.0
COLOUR_LUT_SIZE = 256

# --- Record quantisation -------------------------------------------------
# 8-byte record: 36 bits position (12/axis, tile-relative) | 12 mag | 8 colour
# | 8 flags. 12 bits/axis keeps quantisation error under 0.1 px at any sane LOD
# refine threshold, because tile-relative error in pixels is threshold / 2**bits
# regardless of scale. See PLAN.md sections 4.1 and 4.4.
POSITION_BITS_PER_AXIS = 12
MAGNITUDE_BITS = 12
COLOUR_BITS = 8
FLAG_BITS = 8
ABS_MAG_MIN, ABS_MAG_MAX = -10.0, 20.0
