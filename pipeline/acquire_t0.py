#!/usr/bin/env python3
"""Fetch the T0 showcase tier. Resumable: re-running skips cached chunks."""
from __future__ import annotations

import sys
import time
from pathlib import Path

from catasterism.acquire import acquire
from catasterism.release import ACTIVE, healpix_count
from catasterism.tiers import TIERS

tier = TIERS[sys.argv[1] if len(sys.argv) > 1 else "t0"]
out = Path(sys.argv[2] if len(sys.argv) > 2 else "data/raw") / ACTIVE.slug / tier.slug
total_chunks = healpix_count(tier.healpix_level)

print(f"{ACTIVE.slug}/{tier.slug}: {tier.description}")
print(f"expecting ~{tier.expected_rows:,} rows across {total_chunks} chunks -> {out}\n")

rows = cached = 0
started = time.perf_counter()
for r in acquire(ACTIVE, tier, out):
    rows += r.rows
    cached += r.cached
    if r.pixel % 16 == 0 or r.pixel == total_chunks - 1:
        el = time.perf_counter() - started
        print(f"  {r.pixel + 1:>4}/{total_chunks}  {rows:>9,} rows  {el:6.1f}s", flush=True)

drift = (rows - tier.expected_rows) / tier.expected_rows
print(f"\ndone: {rows:,} rows ({cached} chunks cached) in {time.perf_counter()-started:.1f}s")
print(f"expected {tier.expected_rows:,}, drift {drift:+.3%}")
if abs(drift) > 0.01:
    print("WARNING: >1% drift from the measured count — check the selection", file=sys.stderr)
    sys.exit(1)
