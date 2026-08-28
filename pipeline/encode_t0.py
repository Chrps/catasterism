#!/usr/bin/env python3
"""Encode a derived tier into the binary the browser loads."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pyarrow.parquet as pq

from catasterism.encode import encode
from catasterism.release import ACTIVE
from catasterism.tiers import TIERS

tier = TIERS[sys.argv[1] if len(sys.argv) > 1 else "t0"]
src = Path(sys.argv[2] if len(sys.argv) > 2 else "../data/derived") / ACTIVE.slug / f"{tier.slug}.parquet"
out = Path(sys.argv[3] if len(sys.argv) > 3 else "../client/public")
out.mkdir(parents=True, exist_ok=True)

result = encode(pq.read_table(src), ACTIVE)
stem = f"{ACTIVE.catalogue_version}-{tier.slug}"
(out / f"{stem}.bin").write_bytes(result.data)
(out / f"{stem}.json").write_text(json.dumps(result.manifest, indent=2) + "\n")

n = result.manifest["record_count"]
print(f"{stem}: {n:,} records, {len(result.data)/1e6:.2f} MB ({len(result.data)//n} B/star)")
print(f"  dropped {result.dropped:,} rows with no usable position")
for k, v in result.stats.items():
    print(f"  {k:22} {v:,}")
print(f"  colour LUT worst step {result.manifest['colour_lut']['worst_adjacent_delta_e76']} dE76")
print(f"  -> {out/f'{stem}.bin'}  +  {stem}.json")
