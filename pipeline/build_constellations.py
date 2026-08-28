#!/usr/bin/env python3
"""Resolve constellation line figures onto stars in a derived tier."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pyarrow.parquet as pq

from catasterism.constellations import ATTRIBUTION, resolve
from catasterism.release import ACTIVE
from catasterism.tiers import TIERS

tier = TIERS[sys.argv[1] if len(sys.argv) > 1 else "t0"]
src = Path(sys.argv[2] if len(sys.argv) > 2 else "../data/derived") / ACTIVE.slug / f"{tier.slug}.parquet"
out = Path(sys.argv[3] if len(sys.argv) > 3 else "../client/public")

r = resolve(pq.read_table(src), ACTIVE)
payload = {
    "catalogue_version": ACTIVE.catalogue_version,
    "frame": "galactic-cartesian-parsec",
    "attribution": ATTRIBUTION,
    "positions": r.positions,
    "constellations": r.constellations,
}
dest = out / f"{ACTIVE.catalogue_version}-constellations.json"
dest.write_text(json.dumps(payload, separators=(",", ":")) + "\n")

print(f"  {len(r.constellations)} constellations, {r.endpoint_count:,} segments")
print(f"  {len(r.positions):,} distinct stars referenced")
if r.unresolved:
    missing = sorted(set(r.unresolved))
    print(f"\n  {len(missing)} endpoints did not resolve to a star in the tier:")
    for abbr, hr in missing[:20]:
        print(f"    {abbr}  HR {hr}")
    print("  (a missing endpoint is a data gap worth knowing about, not a silent skip)")
print(f"\n  wrote {dest} ({dest.stat().st_size/1024:.0f} KB)")
