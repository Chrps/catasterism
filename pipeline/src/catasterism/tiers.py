"""Tier definitions — which stars each build contains.

Selections are written in **canonical** column names (the keys of
:attr:`Release.columns`), never release-specific ones, so a DR4 migration is a
change to the release descriptor rather than to every tier.

Counts below were measured live against the ESA archive; see PLAN.md §1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .release import HEALPIX_PARTITION_LEVEL, Release


@dataclass(frozen=True)
class Tier:
    slug: str
    description: str
    where: str
    """ADQL predicate in canonical column names."""
    expected_rows: int
    """Measured against the live archive. A large drift means something changed."""
    healpix_level: int = HEALPIX_PARTITION_LEVEL
    """Coarser for small tiers, so they are not split into thousands of requests."""

    def resolve(self, release: Release) -> str:
        """Translate canonical column names into this release's names.

        Substitution is word-boundary anchored and single-pass. Both matter:
        naive ``str.replace`` would rewrite ``ra`` inside other identifiers, and
        a multi-pass loop could rewrite its own output (``parallax`` inside an
        already-substituted ``parallax_over_error``).
        """
        names = release.columns
        pattern = re.compile(
            r"\b(" + "|".join(re.escape(c) for c in sorted(names, key=len, reverse=True)) + r")\b"
        )
        return pattern.sub(lambda m: names[m.group(1)], self.where)


# The Step 1 showcase set: everything in the solar neighbourhood, plus everything
# a person can see. Deliberately the smallest set that is *complete* at two
# things people care about. Measured: 625,679 rows.
T0 = Tier(
    slug="t0",
    description="d < 100 pc complete, plus every star brighter than G = 8",
    where="(parallax > 10 AND parallax_over_error > 3) OR phot_g_mean_mag < 8",
    expected_rows=625_679,
    healpix_level=2,  # 192 chunks, ~3.3k rows each
)

T1 = Tier(
    slug="t1",
    description="d < 500 pc at poe > 3",
    where="parallax > 2 AND parallax_over_error > 3",
    expected_rows=35_423_727,
    healpix_level=3,
)

T3 = Tier(
    slug="t3",
    description="the full working set: poe > 3, all sky",
    where="parallax_over_error > 3",
    expected_rows=320_489_271,
)

TIERS = {t.slug: t for t in (T0, T1, T3)}

# Columns every tier fetches, in canonical names. See PLAN.md §3.
COLUMNS = (
    "source_id",
    "ra",
    "dec",
    "parallax",
    "parallax_error",
    "parallax_over_error",
    "phot_g_mean_mag",
    "bp_rp",
    "teff",
    "extinction_g",
    "reddening_bp_rp",
    "ruwe",
)
