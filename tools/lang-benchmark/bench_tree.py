# The part everyone assumes needs Rust: building the octree structure itself --
# node boundaries at every level, per-node metadata, child masks, byte offsets.
# Question: does any of it resist vectorisation?
import numpy as np, time, sys
n = int(sys.argv[1]) if len(sys.argv) > 1 else 320_489_271
rng = np.random.default_rng(7)

print(f"n = {n:,} stars")
t0 = time.perf_counter()
keys = np.sort((rng.integers(0, 1 << 30, n, dtype=np.int64).astype(np.uint64)) << np.uint64(18))
mags = rng.random(n, dtype=np.float32) * 30.0 - 10.0
print(f"  [setup {time.perf_counter()-t0:.1f}s]")

MAXLVL, TARGET = 16, 8000
t = time.perf_counter()
total_nodes = 0
for lvl in range(4, MAXLVL):
    pass_t = time.perf_counter()
    shift = np.uint64(3 * (MAXLVL - lvl))
    cell = keys >> shift
    # node boundaries: pure vectorised run-length detection on a sorted array
    starts = np.flatnonzero(np.concatenate(([True], cell[1:] != cell[:-1])))
    counts = np.diff(np.append(starts, n))
    # per-node metadata: flux sum (the merge invariant), child mask, offsets
    flux = np.power(10.0, -0.4 * mags.astype(np.float64))
    node_flux = np.add.reduceat(flux, starts)
    child = (keys[starts] >> np.uint64(3 * (MAXLVL - lvl - 1))) & np.uint64(7)
    offsets = np.concatenate(([0], np.cumsum(counts[:-1]) * 8))
    total_nodes += len(starts)
    print(f"    level {lvl}: {len(starts):>11,} nodes, max {counts.max():>7,} stars/node, {time.perf_counter()-pass_t:.1f}s")
    if counts.max() < TARGET:
        print(f"  stopped at level {lvl}: max node {counts.max()} < {TARGET}")
        break
dt = time.perf_counter() - t
print(f"\n  full tree build (all levels): {dt:.1f} s")
print(f"  total nodes across levels:    {total_nodes:,}")
print(f"\n  Every operation is a vectorised numpy primitive:")
print(f"    node boundaries  -> flatnonzero on a sorted array")
print(f"    star counts      -> diff")
print(f"    flux sums        -> add.reduceat   (the sec 5.2 merge invariant)")
print(f"    child masks      -> shift + mask")
print(f"    byte offsets     -> cumsum")
print(f"  Nothing here resists vectorisation. There is no per-node Python loop.")
