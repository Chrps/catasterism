#!/usr/bin/env python3
"""Derive intrinsic properties for an acquired tier."""
from __future__ import annotations

import sys
from pathlib import Path

import pyarrow.dataset as ds
import pyarrow.parquet as pq

from catasterism.derive import derive
from catasterism.release import ACTIVE
from catasterism.tiers import TIERS

tier = TIERS[sys.argv[1] if len(sys.argv) > 1 else "t0"]
root = Path(sys.argv[2] if len(sys.argv) > 2 else "../data")
raw, out = root / "raw" / ACTIVE.slug / tier.slug, root / "derived" / ACTIVE.slug
out.mkdir(parents=True, exist_ok=True)

table = ds.dataset(raw, format="parquet").to_table()
print(f"read {table.num_rows:,} rows from {raw}")

table, fit, stats = derive(table)

print(f"\ncolour->Teff fit: degree {len(fit.coefficients)-1}, "
      f"{fit.n_calibrators:,} calibrators, BP-RP0 in [{fit.valid_range[0]:.2f}, {fit.valid_range[1]:.2f}]")
print(f"  residual {fit.residual_dex:.4f} dex = {(10**fit.residual_dex - 1)*100:.1f}% in Teff")
print("\nderived:")
for k, v in stats.items():
    print(f"  {k:24} {v:,}" if isinstance(v, int) else f"  {k:24} {v:.4f}")

dest = out / f"{tier.slug}.parquet"
pq.write_table(table, dest, compression="zstd")
print(f"\nwrote {dest} ({dest.stat().st_size/1e6:.1f} MB)")
