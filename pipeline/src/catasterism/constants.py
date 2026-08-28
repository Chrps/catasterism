"""Physical constants and the Sun.

Release-independent. Anything that changes between Gaia releases belongs in
:mod:`catasterism.release`, not here.
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
# Measured against T0 rather than assumed: real values run -13.44 to +21.64, so
# the -10..+20 range PLAN.md quotes as typical is too narrow to encode without
# clipping. 37 magnitudes over 12 bits is 0.0090 mag per step (0.83% in flux),
# still far below the point two adjacent stars can be told apart.
#
# Note the bright tail is partly spurious: T0's G<8 clause admits saturated
# stars whose poor parallaxes yield impossibly luminous M_G. Step 3's Hipparcos
# patching is what fixes those, not a wider range.
ABS_MAG_MIN, ABS_MAG_MAX = -15.0, 22.0

# Observed apparent G, for the planetarium view. This is what Gaia measured from
# Earth -- dust and all -- and is therefore exact, needing no distance estimate
# and no extinction correction (PLAN.md 4.3). T0's real range is 1.73 to 21.31
# once the hand-inserted Sun is excluded; the bounds below leave headroom for
# brighter stars that later tiers or the Hipparcos patch will add.
APP_MAG_MIN, APP_MAG_MAX = -2.0, 22.0
APP_MAGNITUDE_BITS = 12
