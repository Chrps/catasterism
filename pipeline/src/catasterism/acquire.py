"""Stage 1 — pull a tier from the ESA Gaia archive.

Partitioned by HEALPix, because ``source_id`` encodes a level-12 index in its
top bits. That buys three things at once: requests small enough to retry
cheaply, joins that stay chunk-local later in the pipeline, and a natural
resume point.

Acquisition is **idempotent and cached**: a chunk already on disk is not
refetched. Gaia DR4 lands 2026-12-02 and this will run again, so a re-run must
cost nothing for work already done (PLAN.md §9 stage 5).
"""

from __future__ import annotations

import io
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq
import requests

from .release import TAP_ENDPOINT, Release, healpix_count
from .tiers import COLUMNS, Tier

USER_AGENT = "catasterism/0.1 (+https://github.com/Chrps/catasterism)"
MAX_ATTEMPTS = 5
BACKOFF_SECONDS = 3.0
TIMEOUT_SECONDS = 600


@dataclass(frozen=True)
class ChunkResult:
    pixel: int
    path: Path
    rows: int
    cached: bool


def build_query(release: Release, tier: Tier, pixel: int) -> str:
    """ADQL for one HEALPix partition of a tier."""
    lo, hi = release.healpix_range(pixel, tier.healpix_level)
    select = ", ".join(release.columns[c] for c in COLUMNS)
    return (
        f"SELECT {select} FROM {release.source_table} "
        f"WHERE source_id BETWEEN {lo} AND {hi} AND ({tier.resolve(release)})"
    )


def _fetch_csv(query: str, session: requests.Session) -> bytes:
    """One sync TAP request, with retries. Returns raw CSV bytes."""
    last: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            r = session.get(
                TAP_ENDPOINT,
                params={
                    "REQUEST": "doQuery",
                    "LANG": "ADQL",
                    "FORMAT": "csv",
                    "QUERY": query,
                },
                timeout=TIMEOUT_SECONDS,
            )
            r.raise_for_status()
            body = r.content
            # The archive reports some failures as a 200 with an XML error body.
            if body.lstrip()[:1] == b"<":
                raise RuntimeError(f"TAP returned an error document: {body[:200]!r}")
            return body
        except Exception as exc:  # noqa: BLE001 - retry anything transient
            last = exc
            if attempt < MAX_ATTEMPTS:
                time.sleep(BACKOFF_SECONDS * attempt)
    raise RuntimeError(f"TAP request failed after {MAX_ATTEMPTS} attempts") from last


def _to_table(csv_bytes: bytes, release: Release) -> pa.Table:
    """Parse CSV and rename release columns to canonical names immediately.

    Renaming here means nothing downstream ever sees a release-specific name.
    """
    table = pacsv.read_csv(io.BytesIO(csv_bytes))
    actual_to_canonical = {release.columns[c]: c for c in COLUMNS}
    return table.rename_columns(
        [actual_to_canonical.get(n, n) for n in table.column_names]
    )


def acquire_chunk(
    release: Release,
    tier: Tier,
    pixel: int,
    out_dir: Path,
    session: requests.Session,
) -> ChunkResult:
    """Fetch one chunk, or return the cached one untouched."""
    path = out_dir / f"{pixel:05d}.parquet"
    if path.exists():
        return ChunkResult(pixel, path, pq.ParquetFile(path).metadata.num_rows, True)

    table = _to_table(_fetch_csv(build_query(release, tier, pixel), session), release)
    tmp = path.with_suffix(".parquet.partial")
    pq.write_table(table, tmp, compression="zstd")
    tmp.rename(path)  # atomic: a killed run never leaves a half-written chunk
    return ChunkResult(pixel, path, table.num_rows, False)


def acquire(
    release: Release, tier: Tier, out_dir: Path
) -> Iterator[ChunkResult]:
    """Fetch every chunk of a tier, yielding as each completes."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    for pixel in range(healpix_count(tier.healpix_level)):
        yield acquire_chunk(release, tier, pixel, out_dir, session)
