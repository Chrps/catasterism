# Same Stage-3 hot loop, numpy-vectorised. This is the FAIR Python comparison --
# no naive loops anywhere.
import numpy as np, time, sys

n = int(sys.argv[1]) if len(sys.argv) > 1 else 20_000_000

t = time.perf_counter()
rng = np.random.default_rng(12345)
xs = rng.random(n, dtype=np.float32)
ys = rng.random(n, dtype=np.float32)
zs = rng.random(n, dtype=np.float32)
mags = rng.random(n, dtype=np.float32) * 30.0 - 10.0
cols = rng.integers(0, 256, n, dtype=np.uint8)
print(f"  [gen {time.perf_counter()-t:.3f}s]", file=sys.stderr)

def split3(x):
    x = x & 0x1fffff
    x = (x | (x << 32)) & 0x001f00000000ffff
    x = (x | (x << 16)) & 0x001f0000ff0000ff
    x = (x | (x << 8))  & 0x100f00f00f00f00f
    x = (x | (x << 4))  & 0x10c30c30c30c30c3
    x = (x | (x << 2))  & 0x1249249249249249
    return x

# 1. quantise + morton
t = time.perf_counter()
qx = (xs * 2097151.0).astype(np.uint64)
qy = (ys * 2097151.0).astype(np.uint64)
qz = (zs * 2097151.0).astype(np.uint64)
keys = split3(qx) | (split3(qy) << np.uint64(1)) | (split3(qz) << np.uint64(2))
t_morton = time.perf_counter() - t

# 2. sort
t = time.perf_counter()
idx = np.argsort(keys, kind="stable")
t_sort = time.perf_counter() - t

# 3. pack
t = time.perf_counter()
px = (xs[idx] * 4095.0).astype(np.uint64)
py = (ys[idx] * 4095.0).astype(np.uint64)
pz = (zs[idx] * 4095.0).astype(np.uint64)
pm = (((mags[idx] + 10.0) / 30.0) * 4095.0).astype(np.uint64)
packed = ((px << np.uint64(52)) | (py << np.uint64(40)) | (pz << np.uint64(28))
          | (pm << np.uint64(16)) | (cols[idx].astype(np.uint64) << np.uint64(8)))
t_pack = time.perf_counter() - t

# 4. flux-summing LOD merge, vectorised via reduceat on the sorted run boundaries
t = time.perf_counter()
sk = keys[idx] >> np.uint64(42)
bounds = np.flatnonzero(np.concatenate(([True], sk[1:] != sk[:-1])))
flux = np.power(10.0, -0.4 * mags[idx].astype(np.float64))
out_flux = np.add.reduceat(flux, bounds)
out_col = np.add.reduceat(flux * cols[idx].astype(np.float64), bounds) / np.maximum(out_flux, 1e-30)
t_merge = time.perf_counter() - t

print(f"PYTHON/numpy n={n}")
print(f"  quantise+morton  {t_morton:>8.3f} s")
print(f"  sort             {t_sort:>8.3f} s")
print(f"  pack             {t_pack:>8.3f} s")
print(f"  flux merge       {t_merge:>8.3f} s")
print(f"  TOTAL            {t_morton+t_sort+t_pack+t_merge:>8.3f} s")
print(f"  (checksum {len(packed)} {len(out_flux)} {out_flux[0]:.3f})")
