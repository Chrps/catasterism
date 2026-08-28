"""Reference stars for validating the pipeline end to end.

Matched by ``source_id``, never by coordinate. Coordinate matching fails badly
on exactly the stars this catalogue is full of: Barnard's Star moves 10.4
arcsec/year, so over the 16 years between the J2000 epoch and DR3's reference
epoch (see ``Release.reference_epoch``) its position shifts by 167 arcsec --
a mismatch large enough to silently select a different star.

The absent list is as important as the present one. Gaia saturates on the
brightest stars, so several of the most famous stars in the sky have no DR3
entry whatsoever -- verified against SIMBAD, which holds no Gaia DR3 identifier
for any of them. They are the concrete face of the ~400-star bright gap in
PLAN.md 1.4, and they are why Step 3 patches from Hipparcos.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReferenceStar:
    name: str
    source_id: int
    distance_pc: float
    tolerance_pc: float


# Present in DR3, with an accepted distance to check against.
PRESENT = (
    ReferenceStar("Proxima Centauri", 5853498713190525696, 1.301, 0.02),
    ReferenceStar("Barnard's Star", 4472832130942575872, 1.828, 0.02),
)

# Absent from DR3 because Gaia saturates on them. SIMBAD holds no Gaia DR3
# identifier for any of these. If a future release adds one, the test that
# asserts their absence will fail -- which is the point: we want to be told.
ABSENT_SATURATED = (
    "Sirius (alf CMa)",
    "Vega (alf Lyr)",
    "Altair (alf Aql)",
    "Arcturus (alf Boo)",
    "Pollux (bet Gem)",
)
