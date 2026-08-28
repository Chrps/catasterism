#!/usr/bin/env python3
"""Derive intrinsic properties for an acquired tier."""
from __future__ import annotations

import sys
from pathlib import Path

import pyarrow.dataset as ds
import pyarrow.parquet as pq

from catasterism import bright_stars
from catasterism.derive import derive
from catasterism.release import ACTIVE
from catasterism.sun import SUN_SOURCE_ID, apparent_magnitude, insert_sun
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

# Gaia saturates on the brightest stars, so the ones that define constellations
# are exactly the ones it measures worst or not at all. Patch them from
# Hipparcos before the Sun goes in.
print("\nfetching bright stars Gaia cannot see...")
missing, transform = bright_stars.fetch(ACTIVE)
print(f"  {missing.num_rows:,} Hipparcos stars brighter than Hp {bright_stars.DEFAULT_MAGNITUDE_LIMIT}")
print(f"  with no Gaia DR3 counterpart at all")
print(f"  V->G fitted on {transform.n_calibrators:,} stars in both catalogues,")
print(f"    {transform.n_clipped:,} outliers clipped, residual {transform.sigma_mag:.3f} mag")
table = bright_stars.append_to(table, missing, transform, ACTIVE)
print(f"  patched in; table now {table.num_rows:,} rows")

# Gaia cannot observe the Sun, so it is inserted here rather than fetched.
table = insert_sun(table)
print(f"\ninserted the Sun as source_id {SUN_SOURCE_ID}: "
      f"m_G {apparent_magnitude(4.67, 1.0 / 206264.806):.2f} from 1 AU, "
      f"invisible beyond {10 * 10 ** ((6.5 - 4.67) / 5):.1f} pc")
print(f"total {table.num_rows:,} rows")

dest = out / f"{tier.slug}.parquet"
pq.write_table(table, dest, compression="zstd")
print(f"\nwrote {dest} ({dest.stat().st_size/1e6:.1f} MB)")
