"""Gaia data-release descriptors.

**This is the only module in the codebase that names a Gaia data release.**
Everything release-specific lives here: table names, reference epoch, column
names, selection cuts. Nothing else should contain the string ``gaiadr3``.

Gaia DR4 releases 2026-12-02, so this pipeline runs at least twice and the second
run must not be a rewrite. See PLAN.md section 9 stage 5. Two facts drive the
design of this file:

* **The reference epoch changes every release.** DR1 J2015.0, DR2 J2015.5,
  DR3 J2016.0, DR4 J2017.5. It is never a constant.
* **``source_id`` is not stable across releases.** ESA treats source lists as
  completely independent; a physical source's identifier changes in a small
  fraction of cases. Anything persisted must be release-tagged, which is what
  :attr:`Release.id_prefix` is for.

The invariant is enforced by ``tests/test_release.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

TAP_ENDPOINT = "https://gea.esac.esa.int/tap-server/tap/sync"

# source_id encodes a HEALPix level-12 index in its top bits:
#     healpix_level_k = source_id // 2 ** (35 + 2 * (12 - k))
# Level 4 gives 12 * 4**4 = 3072 all-sky chunks of ~104k rows at poe > 3, which
# is both a comfortable TAP page size and the partition that makes the joins in
# PLAN.md section 9 stage 2 fit in memory.
HEALPIX_PARTITION_LEVEL = 4
SOURCE_ID_HEALPIX_LEVEL = 12


def healpix_divisor(level: int = HEALPIX_PARTITION_LEVEL) -> int:
    """Divide a ``source_id`` by this to get its HEALPix index at ``level``."""
    if not 0 <= level <= SOURCE_ID_HEALPIX_LEVEL:
        raise ValueError(f"level {level} outside 0..{SOURCE_ID_HEALPIX_LEVEL}")
    return 2 ** (35 + 2 * (SOURCE_ID_HEALPIX_LEVEL - level))


def healpix_count(level: int = HEALPIX_PARTITION_LEVEL) -> int:
    """Number of all-sky partitions at ``level``."""
    return 12 * 4**level


HEALPIX_PARTITION_DIVISOR = healpix_divisor()
HEALPIX_PARTITION_COUNT = healpix_count()


@dataclass(frozen=True)
class Release:
    """Everything that changes between Gaia data releases."""

    slug: str
    """Short name used in tile URLs and catalogue versions, e.g. ``dr3``."""

    source_table: str
    """Fully qualified TAP table to select from."""

    reference_epoch: float
    """Julian year of the catalogue's reference epoch. Goes in the pack header."""

    id_prefix: str
    """SIMBAD-style identifier prefix. ``source_id`` is NOT stable across
    releases, so every persisted id must carry this."""

    catalogue_version: str
    """Version string embedded in the pack header and the tile URL path. The
    client refuses to load a mismatch rather than rendering it (PLAN.md 7.5)."""

    columns: dict[str, str] = field(default_factory=dict)
    """Canonical internal name -> release-specific column name. This is the
    schema-mapping layer; DR4 renames things and adds more."""

    def healpix_range(
        self, pixel: int, level: int = HEALPIX_PARTITION_LEVEL
    ) -> tuple[int, int]:
        """Inclusive ``source_id`` bounds for one HEALPix partition.

        Level 4 (3072 chunks) suits the full catalogue. Small tiers use a
        coarser level so they are not split into thousands of tiny requests.
        """
        count = healpix_count(level)
        if not 0 <= pixel < count:
            raise ValueError(f"pixel {pixel} outside 0..{count - 1} at level {level}")
        divisor = healpix_divisor(level)
        lo = pixel * divisor
        return lo, lo + divisor - 1

    def tag_id(self, source_id: int) -> str:
        """Release-tagged identifier, e.g. ``Gaia DR3 2947050466531873024``.

        This is also exactly how SIMBAD keys them, so it doubles as the live
        lookup key (PLAN.md section 8).
        """
        return f"{self.id_prefix} {source_id}"


# Canonical column names used everywhere downstream. Keys are internal names;
# values are what the release calls them.
_DR3_COLUMNS = {
    "source_id": "source_id",
    "ra": "ra",
    "dec": "dec",
    "parallax": "parallax",
    "parallax_error": "parallax_error",
    "parallax_over_error": "parallax_over_error",
    "phot_g_mean_mag": "phot_g_mean_mag",
    "bp_rp": "bp_rp",
    "teff": "teff_gspphot",
    "extinction_g": "ag_gspphot",
    "reddening_bp_rp": "ebpminrp_gspphot",
    "ruwe": "ruwe",
}

DR3 = Release(
    slug="dr3",
    source_table="gaiadr3.gaia_source_lite",
    reference_epoch=2016.0,
    id_prefix="Gaia DR3",
    catalogue_version="dr3-v1",
    columns=_DR3_COLUMNS,
)

# Stub, so the shape is proven rather than aspirational. Fill in when DR4 lands
# on 2026-12-02 and confirm the column names against the DR4 data model -- the
# epoch is already known to differ.
DR4 = Release(
    slug="dr4",
    source_table="gaiadr4.gaia_source_lite",
    reference_epoch=2017.5,
    id_prefix="Gaia DR4",
    catalogue_version="dr4-v1",
    columns=dict(_DR3_COLUMNS),
)

RELEASES = {r.slug: r for r in (DR3, DR4)}
ACTIVE = DR3
"""The release this build targets. Changing this line is most of a DR4 migration."""
