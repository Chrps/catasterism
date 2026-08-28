#!/usr/bin/env python3
"""Known-star checks: the highest value per line of code in the project.

Catches coordinate-frame errors, sign flips and unit mistakes -- the class of
bug that produces a plausible-looking but completely wrong sky (PLAN.md 10b).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

from catasterism.known_stars import ABSENT_SATURATED, PRESENT

path = Path(sys.argv[1] if len(sys.argv) > 1 else "../data/derived/dr3/t0.parquet")
t = pq.read_table(path)
sid = t.column("source_id").to_numpy(zero_copy_only=False)
get = lambda n: t.column(n).to_numpy(zero_copy_only=False)
dist, absg, teff = get("distance_pc"), get("abs_g"), get("teff_derived")
x, y, z = get("x_pc"), get("y_pc"), get("z_pc")

print(f"{'star':20} {'d found':>9} {'expected':>9} {'err':>8}  {'M_G':>6} {'Teff':>7}  status")
failures = []
for s in PRESENT:
    hit = np.flatnonzero(sid == s.source_id)
    if hit.size == 0:
        failures.append(f"{s.name}: source_id {s.source_id} not in the tier")
        print(f"{s.name:20} {'-':>9} {s.distance_pc:9.3f} {'-':>8}  {'-':>6} {'-':>7}  MISSING")
        continue
    i = int(hit[0])
    err = dist[i] - s.distance_pc
    # the Cartesian conversion must preserve the radius exactly
    radius_err = abs(np.sqrt(x[i] ** 2 + y[i] ** 2 + z[i] ** 2) - dist[i])
    ok = abs(err) <= s.tolerance_pc
    if not ok:
        failures.append(f"{s.name}: distance {dist[i]:.3f} pc, expected {s.distance_pc:.3f}")
    if radius_err > 1e-6 * dist[i]:
        failures.append(f"{s.name}: |xyz| differs from distance by {radius_err:.3e} pc")
    print(f"{s.name:20} {dist[i]:9.3f} {s.distance_pc:9.3f} {err:+8.3f}  "
          f"{absg[i]:6.2f} {teff[i]:7.0f}  {'ok' if ok else 'DISTANCE WRONG'}")

print(f"\nknown-absent (Gaia saturates on these; no DR3 identifier exists):")
for n in ABSENT_SATURATED:
    print(f"  {n}")
print(f"  -> {len(ABSENT_SATURATED)} of the brightest stars in the sky, missing.")
print("     Concrete face of the ~400-star bright gap. Step 3 patches from Hipparcos.")

print()
if failures:
    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    sys.exit(1)
print("all known-star checks passed")
