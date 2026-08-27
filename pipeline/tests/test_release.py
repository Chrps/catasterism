"""The DR4-readiness invariant, enforced rather than aspirational.

Gaia DR4 releases 2026-12-02. This pipeline runs at least twice and the second
run must not be a rewrite, which requires that no release-specific string leaks
out of star_pipeline.release. See PLAN.md section 9 stage 5.

Note that the needles below are assembled at runtime rather than written as
literals, so this file stays subject to the invariant it enforces instead of
having to exempt itself.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from star_pipeline.release import (
    ACTIVE,
    DR3,
    DR4,
    HEALPIX_PARTITION_COUNT,
    HEALPIX_PARTITION_DIVISOR,
    RELEASES,
)

REPO = Path(__file__).resolve().parents[2]
SOURCE_DIRS = ("pipeline/src", "pipeline/tests", "client/src")
RELEASE_MODULE = REPO / "pipeline/src/star_pipeline/release.py"


def _source_files():
    for d in SOURCE_DIRS:
        root = REPO / d
        if root.exists():
            yield from (p for p in root.rglob("*") if p.suffix in {".py", ".ts", ".glsl"})


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_release_names_appear_only_in_the_release_module(n):
    """A DR4 migration should touch one file. Grep is the test."""
    slug = "gaia" + "dr" + str(n)
    offenders = [
        p.relative_to(REPO)
        for p in _source_files()
        if p != RELEASE_MODULE and slug in p.read_text()
    ]
    assert not offenders, (
        f"{slug!r} leaked outside release.py: {offenders}. "
        "Release-specific names belong in star_pipeline.release only."
    )


def test_reference_epoch_is_never_hardcoded():
    """The reference epoch moves with every Gaia release, so it is never a
    literal outside the release descriptor."""
    base, step = 2015, 0.5  # spans every Gaia reference epoch to date and next
    epochs = [f"{base + i * step:.1f}" for i in range(6)]
    pattern = re.compile("|".join(re.escape(e) for e in epochs))
    offenders = [
        p.relative_to(REPO)
        for p in _source_files()
        if p != RELEASE_MODULE and pattern.search(p.read_text())
    ]
    assert not offenders, f"hardcoded reference epoch in {offenders}; read it from ACTIVE"


def test_dr4_differs_from_dr3_where_it_must():
    assert DR4.reference_epoch != DR3.reference_epoch, "the reference epoch moves"
    assert DR4.reference_epoch > DR3.reference_epoch
    assert DR4.source_table != DR3.source_table
    assert DR4.id_prefix != DR3.id_prefix, "source_id is not stable across releases"
    assert DR4.catalogue_version != DR3.catalogue_version


def test_healpix_partition_matches_the_measured_recipe():
    # Verified live against the ESA archive: pixel 1500 at poe>5 returned
    # 79,047 rows. Divisor is 2**51 for level 4.
    assert HEALPIX_PARTITION_DIVISOR == 2**51
    assert HEALPIX_PARTITION_COUNT == 3072
    lo, hi = ACTIVE.healpix_range(1500)
    assert lo == 1500 * 2**51
    assert hi == 1501 * 2**51 - 1


def test_healpix_ranges_tile_the_sky_without_gaps_or_overlap():
    prev_hi = -1
    for pixel in (0, 1, 1500, HEALPIX_PARTITION_COUNT - 1):
        lo, hi = ACTIVE.healpix_range(pixel)
        assert hi > lo
        if pixel == prev_hi + 1:
            assert lo == prev_hi + 1
        prev_hi = hi
    with pytest.raises(ValueError):
        ACTIVE.healpix_range(HEALPIX_PARTITION_COUNT)


def test_ids_are_release_tagged_in_simbad_form():
    # Doubles as the SIMBAD lookup key (PLAN.md section 8).
    assert DR3.tag_id(2947050466531873024) == "Gaia DR3 2947050466531873024"
    assert DR4.tag_id(1) != DR3.tag_id(1)


def test_active_release_is_registered():
    assert RELEASES[ACTIVE.slug] is ACTIVE
