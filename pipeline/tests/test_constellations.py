"""Constellation figures: the data, and the identifier chain that resolves it."""

from __future__ import annotations

from catasterism.constellations import ATTRIBUTION, LINE_DATA, read_line_data


def test_line_data_is_vendored_and_attributed():
    """CC BY 4.0 requires attribution, and vendoring keeps the build
    reproducible and the provenance visible in the repo."""
    assert LINE_DATA.exists(), "constellation line data is not vendored"
    assert ATTRIBUTION["licence"] == "CC BY 4.0"
    assert "github.com" in ATTRIBUTION["source"]


def test_covers_the_whole_sky():
    data = read_line_data()
    assert len(data) >= 88, "the IAU recognises 88 constellations"
    abbrs = {abbr for abbr, _ in data}
    for expected in ("Ori", "UMa", "Cas", "Cyg", "Sco", "Cru"):
        assert expected in abbrs


def test_paths_revisit_stars_to_draw_branches():
    """Andromeda passes through the same star three times. Repeated numbers are
    meaningful, so anything that de-duplicates them silently loses branches."""
    stars = dict(read_line_data())["And"]
    assert len(stars) > len(set(stars))


def test_every_constellation_has_at_least_one_segment():
    for abbr, stars in read_line_data():
        assert len(stars) >= 2, f"{abbr} cannot form a line"
