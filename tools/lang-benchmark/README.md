# Pipeline language benchmark

Measures the Stage-3 hot loop — quantise → Morton encode → sort → pack →
flux-summing LOD merge — in Rust (rayon, 12 cores) and Python (numpy, vectorised,
single-threaded). Both produce identical group counts, so the work is equivalent.

```bash
cargo build --release && ./target/release/bench 20000000   # Rust
python3 bench.py 20000000                                  # Python
/usr/bin/time -v <either>                                  # peak RSS
```

Results on 12 cores, n = 20M:

| Stage | Rust | numpy | Rust advantage |
| --- | --- | --- | --- |
| quantise + Morton | 0.039 s | 1.223 s | 31× |
| sort | 0.941 s | 2.716 s | 2.9× |
| pack | 0.287 s | 1.104 s | 3.8× |
| flux merge | 0.313 s | 0.868 s | 2.8× |
| **total** | **1.58 s** | **5.91 s** | **3.7×** |

Peak RSS at n = 50M: Rust 1.89 GB, numpy 6.02 GB (3.2×).

## Octree construction, full scale, pure numpy

`bench_tree.py` builds the tree structure itself at n = 320,489,271 — the part people
assume needs a systems language:

```
level 4:       4,096 nodes, max  79,260 stars/node, 5.1s
level 5:      32,768 nodes, max  10,234 stars/node, 5.0s
level 6:     262,144 nodes, max   1,380 stars/node, 5.1s
full tree build: 15.3 s
```

~5 s per level. Every operation is a vectorised numpy primitive — node boundaries via
`flatnonzero` on a sorted array, counts via `diff`, flux sums via `add.reduceat`
(the §5.2 merge invariant), child masks via shift+mask, byte offsets via `cumsum`.
**There is no per-node Python loop anywhere.** A realistic 10–12 level tree is ~60 s.

**Conclusion: this does not decide the language.** Extrapolated to the full 320.5M
catalogue the whole hot loop is ~25 s in Rust and ~95 s in numpy, against a pipeline
whose real cost is ~40 GB of TAP downloads measured in hours. See PLAN.md §12.5.

Note the first numpy run was *faster* than Rust on the flux merge (0.87 s vs 1.68 s)
until the Rust merge was parallelised — vectorised numpy is not a strawman here.
