"""Constellation stick figures, resolved onto stars this catalogue actually has.

The point is verification as much as decoration. A line that lands on its star
validates coordinates, frame, epoch, magnitude, the bright-star patch and the
projection simultaneously; one that lands *beside* a star tells you which link is
wrong. See TASKS_STEP_1.md T10.

The identifier chain matters. The line data is keyed on Bright Star Catalogue
numbers, and this resolves

    HR -> HD -> HIP -> source_id -> position

entirely through catalogue cross-identifications, never by position. Matching by
coordinate across the epoch gap silently selects the wrong star, which is the
trap in PLAN.md 9 stage 2 step 7 -- and constellations are made of exactly the
bright, high-proper-motion stars where it bites hardest.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.csv as pacsv
import requests

from .acquire import TIMEOUT_SECONDS, USER_AGENT
from .release import TAP_ENDPOINT, Release

VIZIER_TAP = "https://tapvizier.cds.unistra.fr/TAPVizieR/tap/sync"
SIMBAD_TAP = "https://simbad.cds.unistra.fr/simbad/sim-tap/sync"
LINE_DATA = Path(__file__).resolve().parents[3] / "pipeline/data/ConstellationLines.csv"

ATTRIBUTION = {
    "source": "https://github.com/MarcvdSluys/ConstellationLines",
    "licence": "CC BY 4.0",
    "note": "Bright Star Catalogue numbers, resolved via HD and HIP",
}


@dataclass
class Resolved:
    """Line figures with every endpoint pinned to a star in the tier."""

    positions: list[list[float]] = field(default_factory=list)
    constellations: list[dict] = field(default_factory=list)
    unresolved: list[tuple[str, int]] = field(default_factory=list)

    @property
    def endpoint_count(self) -> int:
        return sum(len(c["lines"]) for c in self.constellations)


def _tap(url: str, query: str, session: requests.Session, key: str) -> pa.Table:
    params = {"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": query}
    if "vizier" in url:
        params = {k.lower(): v for k, v in params.items()}
    r = session.get(url, params=params, timeout=TIMEOUT_SECONDS)
    r.raise_for_status()
    if r.content.lstrip()[:1] == b"<":
        raise RuntimeError(f"{key}: TAP returned an error document")
    return pacsv.read_csv(io.BytesIO(r.content))


def read_line_data(path: Path = LINE_DATA) -> list[tuple[str, list[int]]]:
    """Each constellation is one polyline; consecutive pairs are segments.

    Paths revisit stars to draw branches -- Andromeda passes through HR 165
    three times -- so repeated numbers are meaningful, not duplicates.
    """
    out: list[tuple[str, list[int]]] = []
    with path.open() as handle:
        for row in list(csv.reader(handle))[1:]:
            if not row or not row[0].strip():
                continue
            stars = [int(c) for c in (cell.strip() for cell in row[2:]) if c]
            if len(stars) >= 2:
                out.append((row[0].strip(), stars))
    return out


def resolve(derived: pa.Table, release: Release) -> Resolved:
    """Map every line endpoint onto a star in the derived table."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    hr_hd = _tap(
        VIZIER_TAP,
        'SELECT "HR", "HD" FROM "V/50/catalog" WHERE "HD" IS NOT NULL',
        session, "HR->HD",
    )
    hd_hip = _tap(
        TAP_ENDPOINT,
        "SELECT hip, hd FROM public.hipparcos WHERE hd IS NOT NULL",
        session, "HD->HIP",
    )
    hip_gaia = _tap(
        TAP_ENDPOINT,
        f"SELECT original_ext_source_id AS hip, source_id "
        f"FROM gaia{release.slug}.hipparcos2_best_neighbour",
        session, "HIP->Gaia",
    )

    simbad_hip: dict[int, int] = {}
    to_int = lambda t, c: t.column(c).to_numpy(zero_copy_only=False)
    hr2hd = dict(zip(to_int(hr_hd, "HR").tolist(), to_int(hr_hd, "HD").tolist()))
    hd2hip = dict(zip(to_int(hd_hip, "hd").tolist(), to_int(hd_hip, "hip").tolist()))
    hip2gaia = dict(zip(to_int(hip_gaia, "hip").tolist(), to_int(hip_gaia, "source_id").tolist()))

    sid = derived.column("source_id").to_numpy(zero_copy_only=False)
    xyz = np.stack([
        derived.column(c).to_numpy(zero_copy_only=False) for c in ("x_pc", "y_pc", "z_pc")
    ], axis=1)
    index_of = {int(s): i for i, s in enumerate(sid)}

    # The HD bridge fails for a few multiples, where the Bright Star Catalogue
    # gives a combined-system HD that Hipparcos files under a component. SIMBAD
    # knows both, so it resolves the remainder directly from the HR number.
    needed = {
        hr
        for _, stars in read_line_data()
        for hr in stars
        if hd2hip.get(hr2hd.get(hr, -1)) is None
    }
    if needed:
        ids = ", ".join(f"'HR {hr}'" for hr in sorted(needed))
        rows = _tap(
            SIMBAD_TAP,
            "SELECT i1.id AS hr_id, i2.id AS hip_id FROM ident AS i1 "
            "JOIN ident AS i2 ON i1.oidref = i2.oidref "
            f"WHERE i1.id IN ({ids}) AND i2.id LIKE 'HIP %'",
            session, "HR->HIP via SIMBAD",
        )
        for hr_id, hip_id in zip(
            rows.column("hr_id").to_pylist(), rows.column("hip_id").to_pylist()
        ):
            # SIMBAD returns component designations for multiples -- "HIP 36850B"
            # for Castor B -- and the catalogue files them under the base number.
            hip_digits = re.match(r"HIP\s+(\d+)", hip_id)
            hr_digits = re.match(r"HR\s+(\d+)", hr_id)
            if hip_digits and hr_digits:
                simbad_hip.setdefault(int(hr_digits.group(1)), int(hip_digits.group(1)))

    result = Resolved()
    slot: dict[int, int] = {}

    def position_slot(hr: int) -> int | None:
        if hr in slot:
            return slot[hr]
        hip = simbad_hip.get(hr)
        if hip is None:
            hd = hr2hd.get(hr)
            hip = hd2hip.get(hd) if hd is not None else None
        if hip is None:
            return None
        # Patched stars carry -hip; Gaia stars resolve through the cross-match.
        row = index_of.get(-int(hip))
        if row is None:
            row = index_of.get(int(hip2gaia.get(int(hip), 0)))
        if row is None or not np.isfinite(xyz[row]).all():
            return None
        slot[hr] = len(result.positions)
        result.positions.append([round(float(v), 4) for v in xyz[row]])
        return slot[hr]

    for abbr, stars in read_line_data():
        lines: list[list[int]] = []
        for a, b in zip(stars[:-1], stars[1:]):
            ia, ib = position_slot(a), position_slot(b)
            for hr, i in ((a, ia), (b, ib)):
                if i is None:
                    result.unresolved.append((abbr, hr))
            if ia is not None and ib is not None and ia != ib:
                lines.append([ia, ib])
        if lines:
            result.constellations.append({"abbr": abbr, "lines": lines})
    return result
