# Catasterism — an explorable 3D map of the Gaia catalogue

**Status:** design investigation, no code yet.
**Date:** 2026-08-27.
**Scope of this document:** work out whether the idea is feasible, pick the encoding
and delivery architecture, and write down the limitations honestly before any code
is written.

Every number in §1 was measured live against the ESA Gaia Archive or the relevant
host during this investigation, not recalled. §A tells you how to reproduce them.

---

## 0. The plan in one page

Build a browser flight-sim through the Gaia DR3 stars, hosted on GitHub Pages, with
the tile data on Cloudflare R2.

| Layer | Decision |
| --- | --- |
| Source | `gaiadr3.gaia_source_lite` via TAP, chunked by HEALPix level 4 (3072 queries, ~40 GB transfer) |
| Selection | Mode-dependent: **all 1.81B** in planetarium mode (direction is exact for every source), **320M** at `poe > 3` for free flight. Tiered 0.6M → 320M, extensible to 764M |
| Position | **Tile-relative** fixed point, 12 bits/axis. Error is `refine_threshold_px / 4096` — scale-free |
| Colour | 8-bit index into a 256-entry ΔE-uniform blackbody LUT. Worst step 0.63 ΔE76, JND is 2.3 — visually lossless |
| Brightness | **Intrinsic**: absolute G magnitude, de-reddened, 12 bits over 30 mag. Planetarium layer stores raw apparent G instead — exact, uncorrected |
| Record | **8 bytes/star**, two `uint32`s, unpacked in the vertex shader |
| Identity | `source_id` in a *separate* cold stream, delta+varint, lazy-fetched per tile on interaction |
| LOD | Octree, inner nodes built by **flux-summing merge**, not random subsampling |
| Rendering | HDR additive point sprites → `rgba16float` → tonemap. Camera-relative coords. WebGL2 baseline, WebGPU fast path |
| Bonus | The stored (colour, magnitude) pair **is** an HR diagram — free linked view, and the pipeline's best QA check (§4.8) |
| Hosting | App + showcase tier on Pages; tiles on R2 (10 GB free, zero egress); Zenodo for archival. **No backend** — see §0.1 |
| Enrichment | Live SIMBAD + VizieR TAP from the browser (both send `Access-Control-Allow-Origin: *` — verified) |

The full 320M-star build is **2.56 GB** — it does not fit GitHub Pages' 1 GB site
limit, which is why the tiles live on R2. Only the 5 MB showcase tier is committed
to the repo.

**GitHub Releases as a CDN does not work.** Not for policy reasons — release assets
are served without any `Access-Control-Allow-Origin` header, so cross-origin
`fetch()` from your Pages site is blocked by the browser. Verified in §7.

### 0.1 What actually ships

Worth stating plainly, because most of this document is about the *build* and almost
none of it ships.

```
RUNTIME — what a visitor loads                      BUILD TIME — never shipped
────────────────────────────────────────            ──────────────────────────────────
TypeScript + WebGL2 bundle    ~1 MB                 Python + DuckDB pipeline
  on GitHub Pages                                     3072 TAP queries  (~40 GB)
                                                      clean / join / derive
Static binary tile files      ~3.4 GB                 Morton sort
  on Cloudflare R2                                    octree build + flux merge
                                                      quantise + pack
(optional) SIMBAD / VizieR                          runs on your laptop or in CI
  third-party, browser-direct
```

**There is no backend.** No server, no database, no API of ours, nothing to deploy or
keep alive. A visitor fetches a JavaScript bundle from one static host and binary
blobs from another. The entire pipeline — DuckDB, Python, the 40 GB of TAP traffic,
the octree builder — is an offline asset bake, the same way a game compiles textures
before shipping. None of it exists at runtime.

Three consequences worth having deliberately:

- **It cannot go down.** There is nothing to fall over. Static files on two CDNs.
- **It costs nothing.** R2's zero-egress model plus Pages' free tier, with no compute.
- **There is no scaling story**, because there is nothing to scale. Traffic is a
  bandwidth question, and R2 already answers it.

The one runtime dependency that is not a static file is the live SIMBAD and VizieR
queries in §8 — third-party TAP services called straight from the browser (both send
`Access-Control-Allow-Origin: *`, verified). Still no backend of ours, and the app
degrades to "nothing catalogued" if they are down.

#### The pipeline is not quite run-once

**Gaia DR4 lands 2 December 2026** — about three months out. It covers 66 months of
observations against DR3's 34, so parallax precision improves by roughly √(66/34) ≈
**1.4×** (proper motions improve far more, as t⁻¹·⁵).

At a fixed `poe > 3` cut that is a large gain. Interpolating the measured distribution
in §1.1, a 1.4× precision improvement pulls today's `poe > 2.1` population up past the
threshold — roughly **450M stars, up ~40% from 320M**, at identical quality.

So build the pipeline to be re-runnable and reproducible rather than as a one-shot
script. It will run again, soon, and the catalogue versioning in §7.5 exists precisely
so a DR4 rebuild can ship without breaking cached clients.

---

## 1. Verified ground truth

### 1.1 How big is the catalogue

| Quantity | Count | Note |
| --- | --- | --- |
| Gaia DR3 sources, total | 1,811,709,771 | |
| …with any parallax | 1,467,744,818 | 81.0% |
| …with **negative** parallax | 357,420,541 | 24.4% of those with parallax — unusable as a naive distance |
| `parallax_over_error > 1` | 763,609,100 | ~100% distance error |
| `parallax_over_error > 2` | 478,659,978 | ~50% |
| `parallax_over_error > 3` | **320,489,271** | ~33% — **the chosen working set** |
| `parallax_over_error > 5` | 192,208,838 | ~20% |
| `parallax_over_error > 10` | 98,346,986 | ~10% |
| `parallax_over_error > 20` | 48,874,463 | ~5% |

**Why hundreds of millions and not "billions".** The catalogue really does hold 1.81 billion sources,
and Gaia knows the *direction* to essentially all of them to sub-milliarcsecond
precision. What collapses the number is **distance**. Of the 1.47B sources with a
parallax at all, roughly **704 million have a parallax less than 1σ from zero** — those
stars are precisely located on the sky and effectively unlocated along the line of
sight. **The chosen cut is `poe > 3` — 320.5 million stars, ~33% distance error.** This is
still comfortably measurement-dominated (a Bayesian prior only starts to dominate
below poe ≈ 2), so the positions remain data rather than model. It buys 1.67× the
stars of a poe > 5 cut for one quantified cost: 0.72 mag of luminosity uncertainty
instead of 0.43 (§4.8). See §3.1 for larger tiers and §3.2 for why the right cut
differs per viewing mode.

### 1.2 Distance shells (at `parallax_over_error > 3`)

| Shell | Parallax cut | Count at poe>3 | (was, at poe>5) |
| --- | --- | --- | --- |
| d < 100 pc | > 10 mas | 573,208 | 541,958 |
| d < 500 pc | > 2 mas | 35,423,727 | 23,588,068 |
| d < 1 kpc | > 1 mas | 98,753,042 | 64,481,314 |
| d < 5 kpc | > 0.2 mas | 309,346,151 | 188,293,789 |

Two things to read off this table.

**96.5% of the usable set is inside 5 kpc**, and the Galaxy is ~30 kpc across. Gaia
maps our neighbourhood in 3D, not the Galaxy.

**Loosening the cut barely touches the near field.** Inside 100 pc the count rises
only 5.8% (541,958 → 573,208), because nearby stars have excellent parallaxes
regardless. Inside 5 kpc it rises 64%. So relaxing poe adds *distant, less certain*
stars — which is exactly where the extra 128M land, and exactly where the uncertainty
display in §2(a) earns its keep.

### 1.3 Attribute availability (within the 320.5M working set)

| Attribute | Count | Coverage |
| --- | --- | --- |
| `bp_rp` colour index | 312,260,188 | 97.4% |
| `teff_gspphot` effective temperature | 239,575,586 | **74.8%** |
| `ruwe < 1.4` (clean astrometry) | 301,041,729 | 93.9% |
| G < 12 (small-telescope visible) | 3,046,578 | |
| G < 6.5 (naked-eye visible) | 11,752 | |

Note the Teff coverage drop: 83.7% at poe > 5 → **74.8% at poe > 3**. GSP-Phot only
ran to G ≤ 19, and the stars the looser cut adds are fainter and more distant. So the
`bp_rp` fallback path in §4.2 now carries 22.6% of all stars rather than 15%, and
2.6% have neither Teff nor usable colour. **The de-reddening fallback is load-bearing
at this cut**, not a corner case — build and validate it early (§4.7 shows how).

### 1.4 Bright-star completeness — a real gap

| Cut | DR3 sources | With parallax |
| --- | --- | --- |
| G < 4 | 634 | 548 (86%) |
| G < 6.5 | 12,119 | — |

Of the 12,119 sources brighter than G = 6.5, only 11,752 pass `poe > 3`. Gaia
saturates on the brightest stars: **~400 naked-eye stars, including famous ones,
have degraded or missing astrometry.** These are exactly the stars a user will look
for first. They must be patched in from Hipparcos / the Bright Star Catalogue.

Confirmed concretely while validating T0: SIMBAD holds **no Gaia DR3 identifier at
all** for Sirius, Vega, Altair, Arcturus or Pollux. Five of the most recognisable
stars in the sky are simply not in the catalogue. Proxima Centauri and Barnard's Star
are present and validate exactly — 1.302 pc and 1.828 pc against accepted 1.301 and
1.828 — so the gap is specifically at the bright end, as predicted.

### 1.5 Acquisition cost

| Route | Transfer | Verdict |
| --- | --- | --- |
| Full `gaia_source` bulk CSV.gz from the ESA CDN | **~770 GB** (3386 files × 227.5 MB measured mean) | Infeasible to store; streamable but wasteful |
| TAP `gaia_source_lite`, 12 columns, `poe > 3`, chunked by HEALPix-4 | **~40 GB** | ✅ Recommended. 3072 queries, ~104k rows each |

One measured level-4 chunk (pixel 1500) at `poe > 5`: 79,047 rows, 9.8 MB of CSV,
124 B/row. Scaling by the 1.67× row ratio of the poe > 3 cut gives ~16 MB/chunk and
~40 GB total — still 19× cheaper than the bulk route.

---

## 2. The constraint that shapes everything

This is the most important section. Everything downstream follows from it.

**A Gaia star's position error is anisotropic by eight to nine orders of magnitude.**

For a star at 500 pc with `poe = 5`:

- **Transverse** (on-sky) error: Gaia's angular precision is ~0.02–1 mas. At 0.05 mas
  and 500 pc that is 1.2 × 10⁻⁷ pc.
- **Radial** (along the line of sight) error: 500 pc / 5 = **100 pc**.

Ratio: ~10⁸–10⁹. The uncertainty is not a fuzzy ball, it is a needle pointing at Earth.

### Consequences

**(a) The view from Earth is essentially exact. Every other view is not.**
Standing at Earth and looking out, the catalogue is perfect — constellations,
star fields, everything, to well below what the eye or any zoom level can resolve.
The moment you fly sideways, you are looking at a cloud of needles. This is not a
bug you can engineer away; it is the data. Design the product around it:

- A "planetarium" mode anchored at Earth that is honest and beautiful.
- A "flight" mode that degrades gracefully and *communicates* its own uncertainty
  (fade with parallax S/N, an optional error-needle render mode, a distance-confidence
  readout on the HUD).

**(b) Naive 3D plots of clusters and binaries look wrong.**
The Pleiades are all at ~136 pc, but each member's parallax carries independent
noise, so a naive plot smears the cluster into a radial cigar pointing at Earth.
Same for every binary: two components 0.5″ apart on the sky get placed *parsecs*
apart radially. **This is the single most visible artifact in every amateur Gaia 3D
map**, and fixing it is the highest-leverage quality work in the project. See §5.3.

**(c) The user's "merge binaries" instinct is right but the mechanism is different.**
You do not want to merge them into one point — you want to **snap them to a common
distance**, which removes the radial smear and leaves them correctly resolved on
the sky. Merging is then handled generically by the LOD (§5.2), not as a data step.

**(d) Beyond ~2 kpc, stop using parallax.**
Switch to Bailer-Jones et al. (2021) Bayesian photogeometric distances
(VizieR `I/352`), which are well-behaved where parallax is noise. And apply the
Lindegren et al. (2021) parallax zero-point correction (~−17 µas, magnitude/colour/
ecliptic-latitude dependent) — at 0.2 mas that offset is an 8% distance error.

---

## 3. Data selection and tiers

Ship several builds. The app picks one based on connection and user choice; higher
tiers stream in on top of lower ones (they are disjoint sets, so this composes).

| Tier | Selection | Stars | Geometry @8 B | + ids @2.5 B | Where |
| --- | --- | --- | --- | --- | --- |
| **T0** showcase | d < 100 pc complete + all G < 6.5 + patched bright stars | ~0.63M | 5.1 MB | 1.6 MB | In repo, on Pages |
| **T1** near | plx > 2 mas, poe > 3 (d < 500 pc) | 35.4M | 283 MB | 89 MB | R2 |
| **T2** local | plx > 1 mas, poe > 3 (d < 1 kpc) | 98.8M | 790 MB | 247 MB | R2 |
| **T3** full | **poe > 3, all sky** | **320.5M** | **2.56 GB** | 801 MB | R2 |
| **T4** extended | poe > 2, all sky | 478.7M | 3.83 GB | 1.20 GB | R2, optional |
| **P** planetarium | all 1.81B as a HEALPix flux map + resolved stars | 1.81B | ~few hundred MB | — | R2 (§3.3) |

T0 is the first-paint payload: **5.1 MB gets you every star a human has ever seen with
the naked eye, plus the complete solar neighbourhood.** That is the demo.

**What "complete" means, and where it stops.** All 625,680 stars are rendered — the
naked-eye ones are only 1.9% of them, and 67% are fainter than G = 15. Exposure
(§6.1) decides what is *visible*; nothing is dropped for being faint, and LOD merges
rather than discards (§5.2). But T0's two clauses behave differently with distance:

| Volume | Contents | Faintest |
| --- | --- | --- |
| inside 100 pc | 573,209 stars — everything Gaia sees | M_G 21.6 |
| beyond 100 pc | 51,553 stars — only G < 8 | M_G 3.0 |

So flying *within* 100 pc gives a dense, honest sky; flying *beyond* it thins to a
scatter of luminous stars. That is a property of the tier, not the renderer, and no
exposure setting fixes it. It is precisely what Step 2's T1 (35.4M) and Step 4's T3
(320.5M) are for.

Note also that "everything Gaia sees" is itself magnitude-limited at G ≈ 20.7 — inside
100 pc that reaches M_G ≈ 15.7, so late M dwarfs and brown dwarfs are missing
everywhere. There is no tier that fixes that one; it is the survey's floor.

Two changes from the earlier poe > 5 draft worth noting. The old "T3 quality:
poe > 10" tier is gone — at 98.3M stars it is now numerically indistinguishable from
T2 (d < 1 kpc, 98.8M), so it earned no separate build; keep poe > 10 as a *filter
toggle* over T3 instead. And **T1 has moved off Pages to R2**: at 283 MB, Pages'
100 GB/month soft bandwidth is only ~350 full loads, which is too thin to risk. Only
T0 stays in the repo.

### 3.1 Going bigger than T4

The cut is a dial, not a cliff, and **catalogue size does not affect frame rate** —
only 2–5M points are ever GPU-resident regardless of how many exist (§6.4). Raising
the cut costs storage and build time, nothing else:

| Cut | Stars | Distance err | Geometry @8 B | Fits R2 free tier (10 GB)? |
| --- | --- | --- | --- | --- |
| poe > 10 | 98.3M | ~10% | 787 MB | ✅ |
| poe > 5 | 192.2M | ~20% | 1.54 GB | ✅ |
| **poe > 3 (T3, chosen)** | **320.5M** | **~33%** | **2.56 GB** | ✅ |
| poe > 2 | 478.7M | ~50% | 3.83 GB | ✅ |
| poe > 1 | 763.6M | ~100% | 6.11 GB | ✅ **three-quarters of a billion stars, free** |
| all parallaxes | 1.47B | — | 11.74 GB | ❌ |

At poe > 3 the chosen build uses **26% of R2's free storage**, leaving room for the
planetarium flux map, the cold id streams and a second build generation alongside it.

The honest caveat: Bailer-Jones distances exist for all 1.47B, but **below poe ≈ 2 the
result is dominated by their Galaxy-model prior, not by Gaia's measurement.** Render
those and you are largely displaying a procedurally generated galaxy with a
Gaia-shaped veneer. That is a legitimate product choice — it looks fuller and is
correct in aggregate — but it must be labelled as a model, and it should never be
the default that a user assumes is data.

### 3.2 The cut should depend on the viewing mode

This follows directly from the anisotropy in §2, and it is easy to miss:

**Direction is exact for all 1.81 billion sources. Only radial position is uncertain.
And only camera *translation* exposes radial error.**

So:

| Mode | Camera | Correct selection |
| --- | --- | --- |
| **Planetarium** — parked at Earth, free look | rotation only | **All 1.81B.** No parallax quality needed at all; every source is in the right place on the sky |
| **Local flight** — inside a few hundred pc | translation | poe > 3, with distance coherence (§5.3) |
| **Wide flight** — kpc scale | translation | poe > 10 filter toggle over T3, plus an explicit uncertainty render |

Discarding 1.6 billion stars from the planetarium view throws away the one thing Gaia
is unambiguously excellent at. Which leads to:

### 3.3 Don't store the faint majority as individual stars

For the ~1.6B sources that are never individually resolvable on screen, individual
records are the wrong representation — 1.81B × 8 B is 14.5 GB to render what is
visually just a glow.

Instead, pre-render them into an **all-sky HEALPix flux-map pyramid**: an angular
image pyramid (level 6 → 12, say) holding summed flux and flux-weighted colour per
pixel. A few hundred MB total, LODs naturally by angular scale, and it reproduces the
Milky Way's band exactly because it is literally the integrated light of the stars
that make it.

Individual star records then only exist where a star is individually resolvable. Two
representations, one for resolved point sources and one for unresolved surface
brightness — which is also how real astronomical rendering works, and it composites
cleanly into the same HDR accumulation buffer (§6.1).

Caveat to design around: a flux map is fixed to Earth's viewpoint, so it is exact in
planetarium mode and progressively wrong as you translate. Cross-fade it out against
the parametric Galaxy model (§6.6) as the camera leaves the solar neighbourhood.

### Columns to extract

```
source_id                 -- identity, and encodes HEALPix-12 in its top 29 bits
ra, dec                   -- direction (exact for our purposes)
parallax, parallax_error  -- distance + its uncertainty
parallax_over_error       -- selection
phot_g_mean_mag           -- apparent brightness (raw, for the planetarium layer)
bp_rp                     -- colour fallback
teff_gspphot              -- colour primary (74.8% coverage at poe>3)
ebpminrp_gspphot          -- de-reddening for the bp_rp colour fallback
ag_gspphot                -- G-band extinction: MANDATORY for intrinsic luminosity (§4.3)
ruwe                      -- astrometric quality / binarity hint
```

Ten columns. Optionally `pmra`, `pmdec`, `radial_velocity` if you ever want to
animate proper motion — a lovely feature, but +12 B/star, so put it in a separate
optional stream.

---

## 4. Encoding design

### 4.1 Position — tile-relative fixed point

The key insight, and the reason this project is tractable:

> In an octree LOD, a node is refined exactly when its projected screen extent
> exceeds a threshold **P** pixels. So if positions are quantised to *b* bits per
> axis *relative to the node's own bounding box*, the quantisation error in screen
> pixels is always `P / 2^b` — **independent of distance, of scale, and of tree
> depth.**

That converts "how many bits do I need for a Galaxy-sized coordinate system" into
"how many bits do I need for a sub-pixel error", which is a much smaller number.

| bits/axis | bytes/pos | P=200px | P=400px | P=800px | P=1600px |
| --- | --- | --- | --- | --- | --- |
| 8 | 3.00 | 0.781 px | 1.562 px | 3.125 px | 6.250 px |
| 10 | 3.75 | 0.195 px | 0.391 px | 0.781 px | 1.562 px |
| **12** | **4.50** | **0.049 px** | **0.098 px** | **0.195 px** | **0.391 px** |
| 16 | 6.00 | 0.003 px | 0.006 px | 0.012 px | 0.024 px |

**Choose 12 bits/axis.** Sub-0.1 px at any sane refine threshold. Compare to the
naive alternatives: `float32[3]` is 12 B and *worse* at Galactic scale (float32 has
24 bits of mantissa but is absolute, so precision collapses far from the origin);
`float64[3]` is 24 B.

Ten bits/axis is tempting because WebGPU's `unorm10-10-10-2` and WebGL2's
`UNSIGNED_INT_2_10_10_10_REV` decode it in hardware for free. But 0.4–0.8 px of
error means stars visibly *jump* when a tile refines to the next level. Twelve bits
costs a handful of shader ALU ops to unpack and eliminates the popping. Take the
shader instructions.

Physical sanity check, root cube = 32,768 pc, 12 bits/axis:

| Tree level | Node edge | Resolution |
| --- | --- | --- |
| 4 | 2048 pc | 0.5 pc |
| 8 | 128 pc | 6,446 AU |
| 12 | 8 pc | 403 AU |
| 16 | 0.5 pc | 25 AU |

At depth 16 you are resolving positions to 25 AU — orders of magnitude finer than
the radial uncertainty from §2. The quantisation is nowhere near the accuracy
bottleneck, which is exactly the right place to be.

### 4.2 Colour — an 8-bit index, and it is provably enough

The user wants the star's *intrinsic local* colour, not its reddened
as-seen-from-Earth colour. So:

1. **Primary:** `teff_gspphot` → blackbody colour. **74.8% coverage at poe > 3.**
2. **Fallback:** de-redden `bp_rp` using `ebpminrp_gspphot` (or a 3D dust map), then
   map `(bp_rp)₀ → Teff` via an empirical relation. Covers a further **22.6%** — this
   path is load-bearing at the chosen cut, not a corner case.
3. The remaining 2.6% have neither. Render them at a neutral ~5800 K and flag it.
3. Quantise Teff to an 8-bit index into a 256-entry LUT texture.

Is 8 bits enough? I computed the Planck spectrum → CIE 1931 XYZ → CIELAB for the
2000–50,000 K range and measured the perceptual step size:

**Log-uniform spacing in Teff:**

| bits | steps | Teff step | worst adjacent ΔE76 |
| --- | --- | --- | --- |
| 5 | 32 | 10.94% | 13.65 |
| 6 | 64 | 5.24% | 6.79 |
| 7 | 128 | 2.57% | 3.39 |
| 8 | 256 | 1.27% | 1.69 |

**ΔE-uniform spacing** (allocate the 256 entries to equalise perceptual step — the
Planckian locus from 2000 K to 50,000 K is 160.6 ΔE76 long):

| bits | steps | worst step |
| --- | --- | --- |
| 6 | 64 | 2.55 ΔE76 |
| 7 | 128 | 1.26 ΔE76 |
| **8** | **256** | **0.63 ΔE76** |

The just-noticeable difference is ~2.3 ΔE76. So a **ΔE-uniform 8-bit palette is
3.6× below the visibility threshold — visually lossless with headroom**, and even
7 bits would pass. Use 8; the spare precision costs nothing and lets you extend the
range for brown dwarfs and exotica later.

Reference colours from the same computation (linear sRGB, unit luminance, then
gamma-encoded and normalised):

| Teff | sRGB | linear R,G,B |
| --- | --- | --- |
| 2500 K | `#FFA64A` | 2.043, 0.777, 0.138 |
| 3500 K | `#FFC88C` | 1.553, 0.896, 0.405 |
| 5000 K | `#FFE7D0` | 1.209, 0.962, 0.762 |
| 5772 K (Sun) | `#FFF1EA` | 1.110, 0.976, 0.912 |
| 6500 K | `#FFF9FE` | 1.042, 0.984, 1.034 |
| 9000 K | `#D6DFFF` | 0.905, 0.994, 1.343 |
| 20000 K | `#ABC1FF` | 0.751, 0.989, 1.845 |
| 50000 K | `#9CB6FF` | 0.696, 0.981, 2.085 |

**Honesty warning, and a UX decision you have to make.** Real stellar colours are
almost white. Measured CIELAB chroma relative to D65:

| Teff | C* |
| --- | --- |
| 2500 K | 81.9 |
| 4000 K | 33.6 |
| 5772 K (Sun) | **6.4** |
| 6500 K | 3.7 |
| 10000 K | 22.7 |
| 40000 K | 49.1 |

The Sun is C* = 6.4 — effectively white. A physically honest render gives you a
field of white and faintly cream dots, which reads as *less* impressive than the
saturated blue-and-orange starfields people expect. Two notes: (i) hot stars are
actually *more* saturated than warm ones, which is counter-intuitive and worth
surfacing; (ii) ship a **saturation slider** with a labelled physical default, so
the exaggeration is a user choice rather than a lie baked into the data.

### 4.3 Brightness — store intrinsic luminosity, never apparent

**The stored quantity must be a property of the star, not of where you are standing.**
Apparent magnitude is a fact about Earth; the moment the camera moves, it is wrong.
So the hot record stores **absolute G magnitude** and the renderer recomputes
apparent brightness from the live camera distance every frame.

Range ≈ −10 (supergiants) to +20 (faint M dwarfs) = 30 mag = **10¹² in flux**.

| bits | mag/step | flux step |
| --- | --- | --- |
| 8 | 0.117 | 11.4% |
| **12** | **0.0073** | **0.68%** |
| 16 | 0.00046 | 0.04% |

Eight bits is visible when two stars sit side by side. Twelve is free given the
record layout in §4.4.

#### The two corrections

Getting from "what Gaia saw" to "what the star is" takes **two** steps, and only the
first is obvious.

```
M_G  =  G  +  5·log₁₀(plx_mas)  −  10  −  A_G
        └─ observed ─┘  └─ distance modulus ─┘   └─ extinction ─┘
```

**1. Distance (obvious).** Inverse-square. Without it a nearby red dwarf and a distant
supergiant that happen to share an apparent magnitude would render identically, and
flying between them would look absurd.

**2. Extinction (easy to miss, and it bites).** Interstellar dust between Earth and the
star dims and reddens it. If you compute `M_G` from the *observed* `G` without
subtracting `A_G`, **you bake Earth's dust column into the star's intrinsic
luminosity** — and it stays there forever. Fly right up to a star behind a dust lane
and it remains dimmed by dust that is now light-years behind you. Measured scale of
the problem at the chosen cut:

| | Count | Share of T3 | Brightness factor |
| --- | --- | --- | --- |
| `ag_gspphot` available | 239,575,586 | 74.8% | — |
| A_G > 1 mag | 44,526,922 | **13.9%** | >2.5× dimmed |
| A_G > 3 mag | 4,673,186 | 1.5% | >16× dimmed |

One star in seven is dimmed by more than a factor of 2.5. This is not a rounding
error. Note that `ag_gspphot` coverage is *exactly* the same 239,575,586 sources as
`teff_gspphot` — GSP-Phot fits temperature, extinction and distance jointly, so they
arrive and go missing together. The 25.2% without it need `A_G` from a 3D dust map
along the line of sight, using the same machinery as the colour fallback in §4.2.

#### Verified: the flight record renders stars without Earth's dust

The algebra collapses neatly, and it is worth seeing because it confirms the two
corrections compose correctly. Substituting `M_G = G + 5log₁₀(plx) − 10 − A_G`
into `m = M_G + 5log₁₀(d/10)` with `d = 1000/plx` gives simply:

```
m = G − A_G
```

Measured on T0's most-reddened bright star: observed G = 4.318, A_G = 7.111, and
the recomputed apparent magnitude is −2.793 — brighter than Sirius, because 7.1
magnitudes of dust have been removed. Fly past the dust and the star really is
that bright.

That is correct for the flight record and **wrong for a view from Earth**, which
is exactly why §3.3's planetarium layer stores raw observed values instead.

#### The renderer's job

```
L      = 10^(−0.4 · M_G)                    // luminosity, from the stored 12-bit int
flux   = L / d_camera_pc²                    // inverse square, per frame
```

Equivalently `m = M_G + 5·log₁₀(d_pc/10)`, but working in linear flux is what the HDR
accumulation buffer in §6.1 wants anyway, so skip the round trip.

#### Why the planetarium layer does the opposite — and is exact

Here is the neat part. §3.2 already splits the data by viewing mode, and brightness
falls along the same seam:

| Layer | Stores | Correction needed | Error |
| --- | --- | --- | --- |
| **Flight record** (§4.4) | absolute magnitude, de-reddened | distance + extinction | inherits both (§4.8c) |
| **Planetarium layer** (§3.3) | **apparent `G` and observed `bp_rp`, raw** | **none** | **none** |

From Earth you want exactly what Earth sees — which is precisely the number Gaia
measured. So the planetarium layer stores the raw observed values and applies **no
correction at all**: no distance estimate, no extinction model, no parallax. It is
exact by construction, for all 1.81 billion sources, including the 704 million whose
distance is unknowable.

That is worth restating, because it is the strongest thing in this whole design: **the
default view of the product has zero derived quantities in it.** Every approximation
in §2, §4.2 and §4.7 only switches on once the user starts flying.

#### Two second-order notes

- **Bolometric correction.** G-band is a passband, not total output. Hot O stars
  radiate mostly in the UV, cool M dwarfs mostly in the IR, so `M_G` understates the
  true luminosity at both ends. For *rendering* this is correct — G is close to what
  the eye sees. For the info panel's "this star is N× the Sun's output", apply
  `BC(Teff)`. Derived from Teff on demand; store nothing.
- **Arriving at a star.** Inverse-square means brightness grows without bound as you
  approach. Quantified in §4.7 for the Sun, which is the first star anyone will fly
  to: it exceeds the float16 accumulation range by ~7 orders of magnitude, and becomes
  a resolved disc within 17 AU. Both need explicit handling, not a clamp.

### 4.4 The record — 8 bytes per star

Two `uint32`s, interleaved, unpacked in the vertex shader:

```
word 0:  [ x:12 | y:12 | z:8(hi) ]        -- 12 bits/axis, tile-relative unorm
word 1:  [ z:4(lo) | mag:12 | colour:8 | flags:8 ]

flags: variable | binary | teff_measured_not_estimated | cluster_member | reserved…
```

36 + 12 + 8 + 8 = 64 bits. Perfectly aligned, two hardware-native attribute fetches,
~6 shader instructions to unpack.

Aggressive variant if you need it: drop flags and go 36 + 12 = 48 bits with colour
in a parallel plane → **6 B/star**, 1.15 GB for T4. Not worth the complexity until
T4 actually needs to fit somewhere it currently doesn't.

Compare with a naive layout: `float32[3]` position + `float32[3]` colour +
`float32` magnitude = 28 B. **8 B is a 3.5× win, and more accurate.**

### 4.5 Identity — split hot and cold streams

`source_id` is 8 bytes, which would be **half the record** — and it is needed only
when the user actually clicks something. So:

- **Hot stream** (`.geo`): 8 B/star, geometry + appearance. Streamed constantly,
  uploaded straight to the GPU with zero parsing.
- **Cold stream** (`.ids`): `source_id` in the *same order* as the hot stream.
  Fetched lazily, only for the one tile under the cursor, only on interaction.

Sorted `source_id`s within a tile delta-encode beautifully; delta + varint + gzip
should land around **2.0–2.5 B/star**. Budget 2.5 B.

You cannot reconstruct `source_id` from position, incidentally, even though its top
29 bits are a HEALPix level-12 index (`source_id >> 35`) — the low 35 bits are a
running counter with no spatial meaning. But that HEALPix encoding *is* the key to
the whole acquisition pipeline (§9).

### 4.6 Compression

Quantised positions are near-incompressible (that is the point — you removed the
redundancy by hand). Two things do help:

- **Planar rather than interleaved layout per tile.** All positions, then all
  magnitudes, then all colours. Colour indices within one tile cluster hard — a tile
  inside a young cluster is almost entirely blue — so the colour plane drops to
  ~4–5 bits of entropy. Expect 8 B → ~6.5–7 B effective.
- **Brotli on the cold id streams only** (delta-encoded ids compress ~3×).

Leave the position plane raw and uncompressed. Raw means the fetched `ArrayBuffer`
goes into a GPU buffer with no decode step at all, which matters more for smooth
streaming than the 10% of bandwidth you'd save.

### 4.7 The Sun — the one star that isn't in the catalogue

Gaia cannot observe the Sun, so the single most important object in the product has
to be inserted by hand. It is also the origin, the orientation anchor, the "home"
target, and the first star anyone will fly up to. It deserves a spec.

#### Values

| Property | Value | Source |
| --- | --- | --- |
| Position | **(0, 0, 0)** by definition | see barycentre note below |
| Absolute G magnitude | **M_G = +4.67** | Casagrande & VandenBerg (2018); DR3 docs give 4.66 |
| Effective temperature | **5772 K** | IAU nominal |
| `bp_rp` | **0.82** | (BP−G) = 0.33, (G−RP) = 0.49 |
| Radius | 6.957 × 10⁸ m | IAU nominal |

**Barycentre note:** Gaia positions are barycentric, and the Sun orbits the solar
system barycentre by up to ~0.005 AU (mostly Jupiter). That is 2.4 × 10⁻⁸ pc — nine
orders of magnitude below anything visible here. Put the Sun at the origin and
forget it.

#### The Sun is unremarkable, and that is the best moment in the product

| Distance | Apparent m_G |
| --- | --- |
| 1 AU (Earth) | **−26.90** |
| 100 AU | −16.90 |
| 1 pc | −0.33 |
| 4.85 pc (nearest stars) | +3.10 |
| 10 pc | +4.67 |
| 100 pc | +9.67 |

The naked-eye limit is m ≈ +6.5, so **the Sun becomes invisible beyond 23.2 pc — just
76 light years**, a quarter of the way to T0's own 100 pc shell. Fly out seventy light
years, turn around, and home is already gone. Build that moment deliberately; it is
the entire emotional payload of the project, and it costs nothing but a "look back"
control.

#### Why the Sun is the calibration case

The Sun does not create any rendering problem that free flight does not already
create for every star — §6.1 (dynamic range) and §6.2 (the disc transition) are
general consequences of letting the camera go anywhere. But the Sun is the instance
you are **guaranteed** to hit, on the first run, before anything else is tested:

- It is where the camera starts, so the disc transition and exposure behaviour are
  exercised immediately rather than whenever someone happens to fly at a star.
- Departing it crosses 1 AU → 100 pc in one continuous motion — a factor of
  2 × 10⁷ — which is the hardest test the scale-adaptive speed model (§6.7) will get.
- Its values are known to far better precision than any Gaia source, so it is the
  only star that can serve as an absolute check on the brightness pipeline. If the
  Sun does not look right from 1 AU, from 100 AU and from 50 pc, the renderer is
  wrong and every other star is wrong too — you just cannot tell.

Calibrate on the Sun; the fixes are general.

#### Earth

Worth placing as a marker at 1 AU for the "you are here" moment, but not as a
rendered body — at parsec scale 1 AU is 1/206,265 of a parsec and Earth is
invisible by a further factor of 10⁴. Treat it as a labelled camera start position,
not geometry.

---

### 4.8 The record is already a Hertzsprung–Russell diagram

Worth making explicit, because it falls out for free: the two appearance fields in
§4.4 **are the two axes of an HR diagram.**

| HR axis | Stored field |
| --- | --- |
| x — temperature / colour | 8-bit colour index (Teff, §4.2) |
| y — luminosity | 12-bit absolute G magnitude (§4.3) |

An HR diagram *is* a scatter plot of colour against absolute magnitude, so every star
in the octree already carries its own coordinates in it. Three consequences.

**(a) A live HR diagram is a free feature.** Render a second linked view: the HR
diagram of exactly the stars currently on screen. Brush a region of the diagram →
those stars highlight in 3D; select a volume in 3D → its population lights up in the
diagram. This is the single best teaching device in observational astronomy, it needs
zero extra bytes, and it turns "pretty starfield" into "you can see the main sequence,
the red giant branch and the white dwarf sequence, and *point at where they are in
space*." Fly into an open cluster and watch its turn-off appear.

**(b) It is the sharpest QA tool in the pipeline.** Plot the HR diagram of your
derived data at every pipeline change. If the de-reddening (§4.2) or the Teff
estimation is wrong, the main sequence smears, bends, or grows a spurious second
branch — instantly and unmistakably. Given that the `bp_rp` fallback path now carries
22.6% of stars at `poe > 3` (§1.3), this check is not optional. Build it in M2, not
M6.

**(c) It shows you exactly what the poe cut costs.** Distance error propagates
straight into absolute magnitude:

```
σ_M = (5 / ln 10) · σ_π/π  =  2.171 / poe   magnitudes
```

| Cut | σ_M | Brightness error | HR main sequence looks… |
| --- | --- | --- | --- |
| poe > 3 (**chosen**) | **0.72 mag** | ×1.95 | ~0.7 mag thick |
| poe > 5 | 0.43 mag | ×1.49 | ~0.4 mag thick |
| poe > 10 | 0.22 mag | ×1.22 | crisp |
| poe > 20 | 0.11 mag | ×1.11 | textbook |

So at `poe > 3` a typical star's intrinsic luminosity is uncertain by a factor of ~2,
and the main sequence will render about 0.7 mag thick rather than as a thin line. Note
what this is *not*: the **colour axis is measured directly and stays exact** (only a
small second-order error enters via the distance-dependent extinction correction), and
**apparent brightness from Earth is also exact** — the error only appears once the
camera translates. Same anisotropy story as §2, in a different coordinate system. If
you want the crisp textbook diagram, offer a `poe > 10` toggle over T3 (§3.2) and let
the user trade stars for sharpness.

**On storing mass** — from the original brief. Don't. Gaia DR3 does publish
`mass_flame` for ~140M sources, but mass is (i) not needed for anything visual, and
(ii) largely *implied* by HR position for main-sequence stars via the mass–luminosity
relation. Derive it on demand in the info panel from the colour and magnitude you
already have, and fetch the published value live from VizieR (§8) when a user asks
for a specific star. Zero bytes in the hot stream.

**Compression: the HR structure does *not* pay for itself.** Tempting idea — stars
occupy a thin locus in the colour-magnitude plane, so a shared vector-quantisation
codebook over the joint distribution should beat storing 8 + 12 bits independently.
I measured it on a 517,042-star all-sky random sample (`tools/verify_hr_entropy.py`):

```
allocated:            20 bits
marginal entropy:     6.34 + 10.59 = 16.93 bits
JOINT entropy:        15.93 bits          <- and still climbing with sample size
mutual information:   0.99 bits
occupied cells:       116,021 of 1,048,576 (11.1%)
```

The convergence check in that script shows the plug-in estimate rising monotonically
(14.92 → 15.28 → 15.72 → 15.93 bits as n quadruples), so 15.93 is a **floor**; the
true value is likely ~16.2–16.5. Against 20 allocated bits that caps the saving at
**under 0.5 B/star, and realistically ~0.4** — for the cost of a codebook, a training
step, and an indirection in the hot path.

**Verdict: keep colour and magnitude independent.** The marginals already capture
almost all of the structure; the colour-magnitude mutual information is only ~1 bit,
because while the locus is thin *vertically* it is broad along its length. A cautionary
note on method: measuring this on a single HEALPix pixel first gave 14.22 bits and
2.24 bits of mutual information — both badly biased by undersampling (2.7 stars per
cell). All-sky sampling with a convergence check reversed the conclusion. Do that
before trusting any entropy estimate.

---

## 5. Spatial structure and LOD

### 5.1 Octree, Potree-2.0 style

- Root cube: 32,768 pc centred on the Sun (covers the Galaxy with margin).
- Target ~8,000 points/node → ~64 KB hot payload per node. Small enough that a
  fetch completes fast; large enough that per-request overhead is irrelevant.
- Measured shape for T3 (320.5M stars): ~40,000 leaves, ~46,000 nodes total. The
  real tree will be far more lopsided than uniform — Galactic-plane and bulge tiles
  go many levels deeper than polar ones — but the node *count* is the right order.
- **Single file per subtree + HTTP Range requests** for the payloads, rather than
  27,000 separate files. Range support verified on Pages, R2, HF and jsDelivr (§7).
  Keep a per-node-file fallback for hosts that misbehave.

At ~46,000 nodes, a complete flythrough touching every node once costs 0.46% of
R2's 10M-Class-B-operations monthly free allowance. Delivery ops are a non-issue.

### 5.2 Merging: sum flux, do not subsample

Standard point-cloud LOD builds inner nodes by randomly subsampling children. **For
stars that is wrong and looks wrong.** Subsampling makes every coarse level dimmer
than reality and destroys the single most important visual cue in astronomy — that
dense regions glow. The Milky Way's band exists *because* unresolved stars sum.

So when two or more stars fall in the same LOD cell, merge them into one point with:

- **flux summed** (convert magnitudes to flux, add, convert back),
- **colour = flux-weighted mean** in linear sRGB, then re-quantised to the nearest
  LUT index,
- **position = flux-weighted centroid**,
- **identity = the `source_id` of the brightest member** (so a click on a merged
  blob still resolves to a real catalogue entry).

Total flux is then conserved exactly at every LOD level, and zooming in resolves a
glow into individual stars without any brightness pop. This also *is* the answer to
the user's "merge binary systems at coarse zoom" requirement — it happens
automatically, at the right scale, with no special-casing, because the LOD cell
shrinks as you approach.

### 5.3 Distance coherence — the quality multiplier

Per §2(b), do this **before** building the tree. It is the difference between a map
that looks like a galaxy and one that looks like a hairbrush.

1. **Resolved binaries and multiples.** Take El-Badry, Rix & Heintz (2021), which
   lists ~1.3M pairs at >90% bound probability (~1.1M at >99%) within ~1 kpc.
   Assign every component the inverse-variance-weighted mean parallax of the system.
2. **Clusters.** Use a published DR3 membership catalogue (Hunt & Reffert and
   similar cover several thousand open clusters) and snap members to the cluster
   distance, optionally with a physically plausible internal spread instead of the
   measurement-noise spread.
3. **Unresolved binaries** show up as `ruwe > 1.4` and via the `non_single_star`
   flag. You cannot fix their distance, but you can flag them so the UI can say so.

Even step 1 alone visibly improves the near field. Step 2 is what makes the
Pleiades, Hyades and Praesepe look like real objects.

### 5.4 Seamless loading

The user's requirement that none of the compression be visible means:

- **Never unload a parent before its children are resident.** Render the parent
  until every child of a refined node has arrived, then swap in one frame.
- Because merging conserves flux and colour (§5.2) and quantisation error is
  sub-0.1 px (§4.1), that swap is genuinely invisible — no pop in brightness,
  colour or position. This is the payoff for getting §4.1 and §5.2 right.
- Prefetch along the velocity vector: predict the camera 1–2 s ahead and request
  those nodes first.
- Priority queue keyed on projected screen error, and cap in-flight requests
  (~6–8) so a fast flight cannot starve the nodes you need *now*.

### 5.5 The tile format is a contract, and must be written down

§4.4 defines the 8-byte *record*; §5.1 says "one file per subtree, HTTP Range".
Neither is a format. Before either the builder or the loader is coded, a standalone
versioned `FORMAT.md` must pin down:

- **Pack header** — magic, format version, **catalogue version** (§7.5), endianness,
  coordinate frame (Galactic Cartesian, pc), epoch (J2016.0, §9), root bounding box,
  quantisation parameters, colour LUT identifier.
- **Hierarchy index** — how the client learns the tree shape without downloading all
  of it. Potree 2.0's chunked hierarchy is the reference: fetch a subtree's node table
  on demand, not the whole tree up front.
- **Per-node metadata** — bounding box, point count, child mask, byte offset and
  length into the pack, and **total flux** (needed to verify the §5.2 merge invariant).
- **Plane layout** — §4.6 recommends planar over interleaved, so per-plane offsets and
  strides need pinning.
- **Compression flags** — which planes are raw (positions, for zero-copy GPU upload)
  and which are Brotli'd (cold id streams).

Two independent programs must agree on this byte for byte. **Generate the writer's and
reader's struct definitions from one source** so they cannot drift — the failure mode
when they silently disagree is misplaced stars, which is near-impossible to diagnose
from the render.

Deliberately *not* designed before the renderer exists (Step 1 uses a throwaway flat
file), because a format specified without evidence of what the renderer needs will be
wrong in unpredictable ways.

---

## 6. Rendering

### 6.1 HDR accumulation, and the true dynamic range of free flight

Thirty magnitudes of *absolute* magnitude is 10¹² in flux (§4.3). But the camera is
free, so what matters is the **apparent** range, and that is far worse.

#### The bound is set by stellar surface brightness

As you approach a star, flux grows as 1/d² — but so does its angular area, and those
cancel exactly:

```
F = L / (4π d²)          Ω = π R² / d²
B = F / Ω = L / (4π²R²) = σT⁴ / π          ← independent of d
```

**Surface brightness depends only on temperature.** That is the ceiling on any pixel,
at any distance, and it is why the range is bounded at all. Measured
(`tools/verify_sun_and_hdr.py`), at 60° FOV over 1920 px:

| Star | T (K) | W/m² per pixel at the surface |
| --- | --- | --- |
| M dwarf | 3,000 | 4.3 × 10⁻¹ |
| Sun | 5,772 | 6.0 |
| Sirius A | 9,940 | 5.2 × 10¹ |
| hot B star | 20,000 | 8.6 × 10² |
| O star | 50,000 | **3.4 × 10⁴** |

```
brightest possible pixel (O star surface):  3.36e+04 W/m²
faintest star we want visible (m = +20):    2.52e-16 W/m²
REQUIRED DYNAMIC RANGE:                     10^20.1
rgba16float provides ~10^12  ->  short by 10^8
```

So the range is **10²⁰**, not 10¹². This is a property of free flight, not of any
particular star — the Sun (§4.7) merely reaches it first.

#### Consequence: exposure multiplies *before* accumulation

Crucially, 10²⁰ is the range across **all possible camera positions**, not within any
one frame. A single frame spans far less: you are either near a star or you are not.
So:

1. **Scale flux by a per-frame exposure scalar, then accumulate.** Auto-expose from
   the previous frame's luminance histogram, with manual override. The multiply must
   happen *before* the additive blend — this is not a tonemap tweak, it changes where
   the multiply lives, and it cannot be retrofitted cheaply.
2. Additively blend exposure-scaled flux into an **`rgba16float`** target with a
   Gaussian-ish (or Airy-ish) kernel.
3. Tonemap in a full-screen pass — `1 − exp(−k·L)` or a log curve.
4. Bloom on the bright tail, which is what sells "star" rather than "dot".

Anything far below the exposure floor vanishes, which is physically correct: you
cannot see stars in daylight either.

`rgba32float` would hold the full range without exposure tricks, at 2× the bandwidth
and memory. Not worth it — auto-exposure is needed for the tonemap anyway.

Overlapping faint stars sum correctly into a glow, which is both right and the thing
that makes the Milky Way appear.

### 6.2 Sub-pixel stars: conserve flux, do not clamp brightness

Almost every star is smaller than a pixel. Drawing it as a full-brightness 1-px dot
causes aliasing and a horrible temporal shimmer as the camera moves. The fix:

```
size_px = max(desired_size_px, MIN_SIZE)          // MIN_SIZE ≈ 1.0–1.5
intensity *= (desired_size_px / size_px)²         // conserve total flux
```

A star that "wants" to be 0.1 px wide is drawn 1 px wide at 1% intensity. Total
deposited flux is unchanged, and the shimmer disappears.

#### The other end: point sprites must become discs

Free flight also means the camera can get close enough that a star subtends *more*
than a pixel, at which point a sprite is no longer a valid model of it. At 60° FOV
over 1920 px (5.454 × 10⁻⁴ rad/px), a star of radius R is resolved within
`d < 2R / 5.454e-4`:

| Star | Radius | Resolved within |
| --- | --- | --- |
| Proxima Cen | 0.15 R☉ | 2.6 AU |
| Sun | 1 R☉ | 17.1 AU |
| Sirius A | 1.71 R☉ | 29.2 AU |
| Betelgeuse | 764 R☉ | 13,028 AU (0.063 pc) |
| UY Scuti | 1700 R☉ | 28,990 AU (0.14 pc) |

Inside Uranus's orbit the Sun is a disc; Betelgeuse is a disc from a fifth of a light
year out. The transition needs a billboard disc with limb darkening, cross-fading
from the point sprite. Radius derives from Teff and luminosity (`R ∝ √L / T²`), both
already stored — **no extra bytes** — and DR3 publishes `radius_gspphot` for the same
470M sources if you prefer the measured value.

Note that the sprite clamp above and the disc transition together are what make §6.1's
bound reachable: below 1 px, flux is conserved and spread; above 1 px, per-pixel
radiance saturates at σT⁴/π. Peak pixel brightness therefore occurs exactly at the
resolution threshold.

### 6.3 Floating-point precision: camera-relative rendering

`float32` cannot represent a position 8 kpc from the origin to parsec accuracy.
Standard fix (as used by Cesium):

- Per draw call, compute `tile_origin − camera_position` **in float64 on the CPU**
  and upload the result as a `float32` uniform.
- The vertex shader then only ever works in tile-local space near the origin, where
  `float32` has plenty of relative precision.

This is not optional and it is not hard — but it has to be in the architecture from
the first commit, because retrofitting it means touching every shader.

### 6.4 Draw submission

- Screen budget: a 2560×1440 display is 3.7M pixels. Drawing more than ~5M points
  is stacking multiple points per pixel — pointless. **Target 2–5M resident points**,
  which is 16–40 MB of VRAM at 8 B/star. Trivially affordable.
- ~600 resident tiles → ~600 draw calls. Fine in WebGL2 with no state changes
  between them. If it isn't, use a slab allocator: pack many tiles into a few large
  GPU buffers and issue a handful of ranged draws. In WebGPU, one indirect draw.
- Frustum + LOD culling on the CPU over a few thousand tiles costs microseconds.
- Two-pass sprites: `gl.POINTS` for the faint majority (cheap, but note
  `gl_PointSize` has an implementation-dependent maximum), instanced quads for the
  few thousand bright stars that need a large glow kernel.

### 6.5 WebGPU or WebGL2

WebGPU now ships enabled by default in Chrome, Edge, Safari 26+, and Firefox 141+
(Windows) / 145+ (macOS Apple Silicon). But **Firefox on Linux and Chrome on
Android are still patchy**, and "a regular PC" includes those.

→ **WebGL2 is the baseline and must be fully featured. WebGPU is an opt-in fast
path** for compute-shader culling and larger buffer limits. Keep the renderer behind
an interface from day one; do not let WebGPU-only assumptions leak into the tile
format.

### 6.6 The empty-space problem

Gaia's usable 3D reach is ~2 kpc; the Galactic disc is ~30 kpc across. Fly out and
the sky goes black and wrong — you are outside the data, not outside the Galaxy.

Options, in increasing order of effort:

1. Hard-stop the camera at the edge of good data with a visible boundary. Honest,
   cheap, unsatisfying.
2. An all-sky panorama on a distant shell for the unresolved background. Looks right
   from Earth, breaks the instant you translate.
3. **A parametric Galaxy model** — exponential disc + bulge + spiral perturbation —
   rendered as a low-frequency emissive volume behind the point cloud, calibrated so
   its integrated surface brightness matches the real Milky Way. Then the Galaxy
   looks like a galaxy from outside, and the point cloud is the high-resolution
   detail near you. Clearly labelled as a model, not data.

Option 3 is the right long-term answer and a genuinely nice piece of work. Ship 1
first.

### 6.7 Camera and flight controls

"Fly around like a spaceship" is the brief, and the hard part is not the controls —
it is **scale**.

Useful motion spans ~1 AU to ~30 kpc: a factor of **6 × 10⁹**. No fixed speed works.
Fast enough to cross interstellar space makes approaching a star impossible; slow
enough to approach a star means the nearest neighbour is hours away. There is no
standard solution to copy here; this is the defining UX problem of the project.

**Speed must be derived, not set.** Candidates:

| Approach | How | Trade-off |
| --- | --- | --- |
| **Nearest-star scaling** | speed ∝ distance to closest star | Self-adjusts on approach; needs a nearest-neighbour query, which the octree gives free from Step 2. **Recommended** |
| Local-density scaling | speed ∝ mean inter-star spacing nearby | Smoother, less responsive on approach |
| Logarithmic manual control | user-driven | The escape hatch. If the user *has* to use it, the scheme has failed |

Whichever is chosen it must be **continuous** — any discrete gear change will be felt.

**Modes:**

- **Planetarium** — anchored at the Sun, rotation only. Per §2 this is the view that is
  exactly correct, and the one people recognise. **Default landing state.**
- **Free flight** — 6DOF.
- **Orbit** — examine a single star.
- **Fly-to** — smooth transitions; also the seed of guided tours.

Prototype the speed model against **departing the Sun** (§4.7): 1 AU → 100 pc in one
continuous motion is the hardest case and the first one users hit. If it feels right
there, it will feel right everywhere.

### 6.8 Visualising uncertainty

§2 establishes that radial error exceeds transverse by 10⁸–10⁹, so every star is a
needle pointing at Earth. At `poe > 3` a typical distance is uncertain by ~33% and
absolute magnitude by 0.72 mag (§4.8c). The design question is how loudly to say so.

| Option | What it looks like | Cost |
| --- | --- | --- |
| **Quiet** | Confidence figure in the HUD on selection | Trivial |
| **Ambient** | Low-confidence stars dimmer or hazier — uncertainty as texture, not a number | Small |
| **Loud** | Explicit mode: each star smeared along its error needle | Small, once `poe` is in the record |

**Recommendation: build the loud mode, default to ambient.** The loud mode is cheap
once position and `parallax_over_error` are both present, and it is the single most
interesting thing this dataset can be made to say. Defaulting to it would make the map
look broken to someone who does not yet know why.

Reserve per-star `poe` in the record's flag bits (§4.4) from the start rather than
adding it later.

---

## 7. Hosting and delivery

### 7.1 Measured host capabilities

I tested CORS and Range on each candidate.

| Host | CORS | Range | Free limits | Verdict |
| --- | --- | --- | --- | --- |
| **GitHub Pages** | `*` ✅ | 206 ✅ | 1 GB site, 100 GB/mo soft bandwidth, 10 builds/hr | ✅ App + T0/T1 |
| **GitHub Releases** | **none** ❌ | 206 ✅ | 2 GB/asset | ❌ **Unusable from a browser** |
| **Cloudflare R2** | configurable ✅ | ✅ | 10 GB storage, 1M Class A + 10M Class B ops/mo, **zero egress** | ✅ **Tiles** |
| **Hugging Face datasets** | reflected origin ✅ | 206 ✅, CloudFront | Public storage now **"best-effort"** for free accounts; egress/CDN included | ⚠️ Good backup, quota risk |
| **jsDelivr (gh)** | `*` ✅ | ✅ | **20 MB/file**, AUP forbids bulk data hosting | ❌ Too small, wrong use |
| **Cloudflare Pages** | ✅ | ✅ | 25 MB/file, 20k files/deploy | ❌ Too restrictive |
| **Zenodo** | — | not guaranteed | 50 GB/record, permanent DOI | ✅ Archival only |
| **Backblaze B2 + Cloudflare** | ✅ | ✅ | 10 GB free, free egress via Bandwidth Alliance | ✅ Viable R2 alternative |

**On GitHub Releases specifically**, since it was the original plan. A release asset
request 302-redirects to `release-assets.githubusercontent.com` (Azure Blob behind
Fastly). That final response carries `accept-ranges: bytes` and serves 206 correctly
— but it sends **no `Access-Control-Allow-Origin` header at all**, plus
`content-disposition: attachment`. So `fetch()` from your Pages origin is blocked by
the browser before you can read a byte. Verified directly. It is a poor idea, and
for a harder reason than the ToS concern.

### 7.2 Recommended topology

```
GitHub Pages  (amboltio.github.io/star or a custom domain)
├── app bundle                       ~1 MB
└── data/t0/                         ~7 MB   instant first paint, geometry + ids

Cloudflare R2  (custom domain, zero egress)
├── t1/  …   372 MB      d < 500 pc
├── t2/  …  1.04 GB      d < 1 kpc
├── t3/  …  3.36 GB      poe > 3, all sky   ← the main build
└── p/   … ~300 MB       planetarium flux map, all 1.81B sources
                          total ~5.1 GB of the 10 GB free tier

Zenodo  — versioned archival snapshot + DOI, so the derived catalogue is citable
GitHub — the generator scripts, so the whole thing is reproducible from source
```

**GitHub's 100 MB per-file hard limit decides this, not preference.** Measured
against the tiers:

| Tier | Stars | @16 B (Step 1) | @8 B (Step 2) | Committable? |
| --- | --- | --- | --- | --- |
| T0 | 623,457 | 10 MB | 5 MB | ✅ yes, permanently |
| T1 | 35.4M | 567 MB | 283 MB | ❌ blocked outright |
| T2 | 98.8M | 1.58 GB | 790 MB | ❌ |
| T3 | 320.5M | 5.13 GB | 2.56 GB | ❌ |

So **T0 lives in the repo forever and every other tier must be on R2** — and R2 is
therefore needed at **Step 2**, when T1 arrives, not Step 4 as the roadmap says.
Chunking T1 under 100 MB would technically pass but bloats history brutally, since
each rebuild stores full copies of high-entropy data that does not delta.

And **do not use Git LFS** — its free tier is 1 GB storage and 1 GB bandwidth *per
month*, which this project would exhaust in a day.

### 7.3 Bandwidth reality check

Pages now serves only the app plus a 7 MB T0, so its 100 GB/month soft limit is
~14,000 full cold loads — comfortable even under a traffic spike. Everything heavier
sits behind R2's zero-egress model, which is the actual insurance policy. This is why
T1 moved off Pages: at 283 MB it would have reduced that headroom to ~350 loads.

### 7.4 Client-side cache

A service worker plus an IndexedDB tile store, keyed by tile id **and catalogue
version** (§7.5). Revisits become instant, R2 Class B operations drop sharply, and
regions already visited work offline.

Needs an LRU eviction policy with a size cap — a thorough explorer would otherwise
cache the whole 2.56 GB catalogue into browser storage.

Cheap to design in, unpleasant to retrofit, because it changes the loader's request
path.

### 7.5 Catalogue versioning

Tiles live on R2 and the app on Pages; **they deploy independently.** Rebuild the
catalogue with a changed quantisation or colour LUT and every cached client silently
renders garbage until its cache expires.

- A catalogue version string in the pack header (§5.5) **and in the tile URL path**
  (`/v3/t3/…`).
- The app pins the version it was built against and **refuses to load a mismatch**
  rather than rendering it.
- Cache keys include it (§7.4), so a new version invalidates cleanly instead of mixing
  generations.
- Zenodo snapshots cut per version, each with a DOI.

---

## 8. Live enrichment queries

The user wanted an id usable for live lookups. `source_id` is that id, and it works
directly from a static page — I verified the CORS headers:

| Service | CORS | Works from GitHub Pages? |
| --- | --- | --- |
| **SIMBAD TAP** (`simbad.cds.unistra.fr/simbad/sim-tap/sync`) | `Access-Control-Allow-Origin: *` | ✅ Yes |
| **VizieR TAP** (`tapvizier.cds.unistra.fr/TAPVizieR/tap/sync`) | `Access-Control-Allow-Origin: *` | ✅ Yes |
| **ESA Gaia TAP** (`gea.esac.esa.int/tap-server/tap/sync`) | **no CORS headers** | ❌ **No** — needs a proxy |

So: **SIMBAD and VizieR for live queries; ESA Gaia only through a Cloudflare Worker
proxy** (or not at all — VizieR mirrors Gaia DR3 as `I/355` and Bailer-Jones
distances as `I/352`, which covers the realistic needs).

Working SIMBAD query, verified live:

```sql
SELECT b.main_id, b.otype_txt, b.sp_type, b.rvz_redshift
FROM basic AS b JOIN ident AS i ON i.oidref = b.oid
WHERE i.id = 'Gaia DR3 2947050466531873024'
```

### Set expectations correctly

**Only 14,189,652 SIMBAD objects carry a Gaia DR3 identifier at all** — that is 0.8%
of the catalogue. The overwhelming majority of clicks will legitimately return "no
further information catalogued", and the UI must say that gracefully rather than
looking broken.

Mitigation: **bundle the names.** The IAU has ~450 official star names; add
Bayer/Flamsteed designations, HIP (118k) and HD (360k) cross-ids. That is a few MB
in the repo, makes every star a user has heard of resolve instantly and offline, and
reserves the network round-trip for the genuinely obscure.

One instructive gotcha from the verification: querying SIMBAD for Sirius's
`source_id` returned `* alf CMa B` — the white dwarf companion, not Sirius A.
Gaia `source_id` ↔ catalogue-object mapping is per-component and not always the one
you expect. Show the returned identifier, don't assume it.

---

## 9. Build pipeline

### Stage 1 — Acquire (~25 GB transfer, one-off)

Exploit the fact that `source_id` encodes a HEALPix level-12 index in its top bits:

```
healpix_level_k_index = source_id / 2^(35 + 2*(12-k))
```

So level 4 (3072 pixels over the whole sky) divides by `2^51 = 2251799813685248`.
That gives 3072 spatially-contiguous chunks of ~104k rows each at `poe > 3` —
comfortably inside any TAP row cap, and naturally parallel:

```sql
SELECT source_id, ra, dec, parallax, parallax_error, parallax_over_error,
       phot_g_mean_mag, bp_rp, teff_gspphot, ag_gspphot, ebpminrp_gspphot, ruwe
FROM   gaiadr3.gaia_source_lite
WHERE  source_id BETWEEN :pix * 2251799813685248
                     AND (:pix + 1) * 2251799813685248 - 1
  AND  parallax_over_error > 3
```

Verified against pixel 1500 at `poe > 5`: 79,047 rows, 9.8 MB CSV; expect ~1.67× that
at `poe > 3`. Write each chunk straight to Parquet. Be a good citizen — a handful of concurrent connections, resume on failure,
cache aggressively so you never re-fetch.

Fallback if TAP throttles: stream all 3386 bulk `.csv.gz` files, decompress on the
fly, discard unwanted columns, never touch disk. 770 GB of transfer for ~2 GB of
output — ~1.7 h on a gigabit link. Ugly but not rate-limited.

### Stage 2 — Clean and derive

#### Why a query engine — and why partitioning weakens the argument

Three operations in this pipeline are larger than a laptop's RAM, and they are what
picks the tool:

| Operation | Scale | Why it hurts |
| --- | --- | --- |
| **Global Morton sort** | 320.5M rows | The octree needs spatial ordering. The HEALPix partitioning the data arrives in is *angular*, so it does not align with a 3D octree — a genuine global sort is unavoidable |
| **Bailer-Jones distance join** | **113.6M rows** joined against a **1.47B-row** table | 35% of the working set lies beyond 2 kpc where parallax is unreliable (measured). This is the single heaviest operation in the build |
| **Per-level LOD aggregation** | 320.5M rows, ~8 levels | `GROUP BY morton >> 3k`, summing flux and flux-weighting colour, at every tree level |

At ~50 B of intermediates per row that is ~16 GB before you start, so a naive
in-memory pipeline is out. A query engine gives you, for free:

- **Out-of-core sorts and joins for free** — it spills to disk and the query just
  works. Writing an external merge sort and a spilling hash join by hand is the
  actual alternative, and it is a week of work with subtle failure modes.
- **Native Parquet with projection and predicate pushdown** — it reads only the
  columns and row groups a query touches, straight off the 3072 chunk files, with no
  load step.
- **Zero infrastructure.** One `pip install`, no server, no cluster, no JVM. It runs
  in CI.
- **SQL suits this stage.** Stage 2 is joins, filters and derived columns — exactly
  what SQL is good at, and much less code than the dataframe equivalent.

#### But the data's own structure dissolves both hard problems

An important correction to the argument above. Out-of-core sort and join are only
unavoidable in the *naive* formulation. The catalogue's structure removes both:

- **Joins become chunk-local.** `source_id` encodes a HEALPix level-12 index in its
  top bits, so partitioning by HEALPix makes every join partition-local. The
  113.6M × 1.47B Bailer-Jones join becomes **3072 small joins that each fit in RAM**,
  and they are embarrassingly parallel. The Bailer-Jones catalogue can be partitioned
  the same way, on the same key.
- **The sort becomes bucketed.** One streaming pass assigns each star to a top-level
  octree node (~32,768 buckets at level 5, ~10k stars each), writing each bucket to
  its own file. Then sort each bucket **in memory**. This is a textbook external radix
  partition and it is maybe 100 lines.

So a query engine is a convenience here, not a necessity. **Recommendation: DuckDB
first** — SQL suits the joins and derived columns, and it reads the 3072 Parquet
chunks directly. Polars is an equally good swap if you prefer dataframes. Fall back to
explicit HEALPix-chunked processing only if either struggles on the Bailer-Jones join;
do not hand-roll before you need to.

Note that this partitioning is also what removes memory as a language argument
(§12.5c): working set is ~104k rows per chunk, not 320M.

#### Where a query engine is *not* the right tool

Stage 3 is not a SQL problem. Tree-structure bookkeeping, child masks, byte offsets,
quantisation and binary packing are imperative work. **The split is: the query engine
does the sort, the joins and the per-level aggregation; native code does the tree and
the bytes.** Do not try to build the octree in SQL.

#### Alternatives considered

| Tool | Verdict |
| --- | --- |
| **DuckDB** | **Recommended.** Most proven out-of-core engine; SQL suits joins and derived columns; reads the Parquet chunks directly |
| **Polars** | Equally good. Swap in if you prefer dataframes to SQL |
| **Hand-rolled partitioning** | Genuinely viable given the HEALPix structure above. Zero dependencies, full control, ~100 lines for the bucketed sort. Do it if the engines disappoint, not before |
| **pandas** | No. In-memory only; 320M rows will not fit |
| **Dask / Spark** | Overkill. Cluster-oriented, more moving parts, slower here |

#### Language

Python — see §12.5. This is the science stage (coordinate frames, epoch propagation,
dust maps, cross-matching) and `astropy` / `dustmaps` are the whole argument.

#### The work

1. Apply the Lindegren parallax zero-point correction.
2. Distance: parallax inside ~2 kpc; join Bailer-Jones `I/352` beyond.
3. Distance coherence — join El-Badry binaries and cluster memberships, snap
   parallaxes (§5.3).
4. Patch bright stars from Hipparcos where Gaia astrometry is saturated (§1.4).
5. Derive `M_G = G + 5·log₁₀(plx) − 10 − A_G` — **the `A_G` term is not optional**
   (§4.3) — and Teff (measured, or estimated from de-reddened `bp_rp`). Fill the 25.2%
   with no `ag_gspphot` from a 3D dust map along the line of sight.
6. Cartesian conversion: equatorial → **Galactic** Cartesian in parsecs. Use
   Galactic, not equatorial — it makes the disc lie in a plane, which every later
   visual decision benefits from.
7. **Record the epoch: Gaia DR3 positions are at J2016.0, not J2000.0.** It must be
   stated in the pack header (§5.5), and it matters far more than it looks.

   *For rendering* the effect is negligible — a few mas/yr of proper motion over a
   decade is well below anything visible. **For _matching_ it is severe**, because the
   "typical star" framing is wrong for exactly the population the near tiers are made
   of. Nearby stars move fast:

   | Star | Proper motion | Drift, J2000 → the DR3 epoch |
   | --- | --- | --- |
   | Barnard's Star | 10.36 ″/yr | **167 ″** |
   | Proxima Centauri | 3.85 ″/yr | 62 ″ |
   | Sirius | 1.34 ″/yr | 21 ″ |

   Validating T0 against J2000 reference coordinates silently matched the **wrong
   stars** — 167 ″ is enormous for a positional cross-match, and it selects a
   neighbour rather than failing. So: **match by `source_id`, never by coordinate**,
   and where a coordinate match is unavoidable, propagate the epoch first.

   This is also why Step 3's Hipparcos cross-match needs care: J1991.25 → J2016.0 is a
   25-year baseline, so Barnard's Star moves over four arcminutes across it.

### Stage 3 — Build the octree

1. Compute a 63-bit Morton key per star, sort. (DuckDB, out-of-core.)
2. Build the tree bottom-up; split any node over ~8,000 points.
3. Inner nodes by flux-summing merge (§5.2).
4. Quantise per node (§4.1–4.4), emit planar streams (§4.6).
5. Write subtree pack files + a compact binary hierarchy index.

Numpy throughout, and it is fast enough by a wide margin: the hot loop is ~95 s at
full scale and tree construction ~60 s (§12.5c), against a pipeline dominated by hours
of network transfer. Every step vectorises — there is no per-node Python loop.

The one thing to be disciplined about is the **container format**: define it once in a
spec file and code-generate both the Python writer and the TypeScript reader, so they
cannot drift (§5.5).

### Stage 4 — Publish

`rclone` to R2, T0/T1 committed to the Pages repo, Zenodo snapshot, checksums
everywhere. All of it in a GitHub Actions workflow so the build is reproducible and
nobody has to remember the steps.

### Stage 5 — Designing for DR4

**Gaia DR4 releases 2 December 2026.** Steps 1–3 land around then, so this is not a
distant hypothetical — it is the pipeline's second run, and it must not be a rewrite.

DR4 covers 66 months of observations against DR3's 34, so parallax precision improves
by roughly √(66/34) ≈ **1.4×** (proper motions improve far more, as t⁻¹·⁵).
Interpolating §1.1's measured distribution, a fixed `poe > 3` cut then admits today's
`poe > 2.1` population: roughly **450M stars, up ~40%**, at identical quality.

Six things must be built in from the start.

**1. The release is configuration, not a constant.** Table name
(`gaiadr3.gaia_source_lite` → `gaiadr4.…`), column names, and every derived constant
come from one release-descriptor file. Grep-ability is the test: `gaiadr3` should
appear exactly once in the codebase.

**2. The reference epoch changes.** DR3 is **J2016.0**; DR4 is **J2017.5** (DR2 was
J2015.5, DR1 J2015.0 — it moves every release). It already belongs in the pack header
(§5.5); it must be read from the release descriptor, never hardcoded.

**3. `source_id` is _not_ stable across releases.** ESA is explicit that source lists
"should be treated as completely independent", and that a physical source's identifier
changes in a small fraction of cases. This is the sharpest consequence, and it bites
the product, not just the pipeline:

- The cold id stream (§4.5) must be **tagged with its release** — `Gaia DR3 <id>`
  versus `Gaia DR4 <id>`. Convenient: that is exactly how SIMBAD keys them, so §8's
  queries already carry the right shape.
- **Any permalink or bookmark to a specific star breaks across releases** unless
  resolved through a cross-match. If "share a link to this star" is ever a feature,
  it must store a release-tagged id and resolve via ESA's published cross-match
  tables — or store coordinates and re-resolve positionally.
- Never assume a DR3 id and a DR4 id refer to the same object.

**4. The selection cut is a parameter.** At DR4 the same `poe > 3` gives ~450M stars
= 3.6 GB geometry + 1.1 GB ids = **4.7 GB**. Keeping DR3 alongside it (3.4 GB) totals
8.1 GB of R2's 10 GB free tier — it fits, but only just. Decide deliberately whether
DR4 replaces DR3 or sits beside it.

**5. Acquisition must be idempotent, resumable and cached.** 3072 queries is a long
run with a real chance of transient failures. Cache every response keyed by release
and chunk, so a re-run costs nothing for chunks already fetched.

**6. Isolate the schema-mapping layer.** One module maps *source catalogue columns* →
*canonical internal schema*. DR4 renames things and adds much more (notably far better
astrophysical parameters and epoch photometry). When it lands, that module should be
the only file that needs real thought.

The client side is already covered: §7.5's catalogue versioning puts the version in
both the pack header and the tile URL path, and makes the app refuse a mismatch rather
than render it. Extend the version string to name the release — `dr3-v1`, `dr4-v1`.

---

## 10. Limitations register

| # | Limitation | Severity | Mitigation |
| --- | --- | --- | --- |
| L1 | Radial position error is 10⁸–10⁹× the transverse error | **Fundamental** | Design around it: exact planetarium mode + honest uncertainty display in flight mode (§2) |
| L2 | Clusters and binaries smear radially into needles | **High, very visible** | Distance-coherence snapping before tree build (§5.3) |
| L3 | Only 320M of 1.81B stars have usable 3D *distances* (704M parallaxes are <1σ from zero) | High | Mode-dependent selection: all 1.81B in planetarium mode, poe>3 for flight (§3.2); faint majority as a flux map (§3.3) |
| L4 | 24.4% of parallaxes are negative | High | Excluded by the `poe` cut; Bailer-Jones distances if you ever want them |
| L5 | Gaia's 3D reach (~2 kpc) is ~13% of the Galaxy's radius | High | Parametric Galaxy model behind the point cloud (§6.6) |
| L6 | ~400 naked-eye stars have bad/missing Gaia astrometry | Medium, embarrassing | Patch from Hipparcos / BSC (§1.4) |
| L7 | T3 (2.56 GB) exceeds the GitHub Pages 1 GB site limit | Medium | All tiles on R2; only the 7 MB T0 on Pages (§7.2) |
| L8 | GitHub Releases sends no CORS headers | Medium | Don't use it. R2 instead (§7.1) |
| L9 | Real stellar colours are nearly white (Sun: C* = 6.4) | Medium, UX | Saturation slider, physical default, explain it (§4.2) |
| L9b | At poe>3, absolute magnitude carries σ = 0.72 mag (×1.95 in luminosity); the HR main sequence renders ~0.7 mag thick | Medium | Accepted cost of the chosen cut; offer a poe>10 sharpness toggle (§4.8) |
| L9c | 25.2% of T3 has no `ag_gspphot`; skipping extinction bakes Earth's dust column into intrinsic luminosity permanently (13.9% of stars are dimmed >2.5×) | **High, silent** | Subtract A_G always; 3D dust map for the gap; validate on the HR diagram (§4.3, §4.8b) |
| L10 | 30 magnitudes of dynamic range | Medium | HDR `rgba16float` accumulation + tonemap (§6.1) |
| L11 | `float32` breaks down at Galactic scale | Medium | Camera-relative rendering, in from commit 1 (§6.3) |
| L12 | Sub-pixel stars alias and shimmer | Medium | Size clamp with flux conservation (§6.2) |
| L13 | Only 0.8% of stars have a SIMBAD entry | Medium, UX | Bundle IAU/Bayer/HIP/HD names; graceful "nothing catalogued" (§8) |
| L14 | ESA Gaia TAP has no CORS | Low | Use VizieR/SIMBAD, or a Worker proxy (§8) |
| L15 | WebGPU still patchy on Firefox/Linux and Android | Low | WebGL2 baseline, WebGPU opt-in (§6.5) |
| L16 | Pages' 100 GB/mo ≈ 400 T1 loads | Low until viral | Anything popular goes behind R2's zero egress (§7.3) |
| L17 | Gaia is incomplete in crowded fields and at G < 3 | Low | Document it; overlay a known-object catalogue for cluster cores |
| L18 | HF free public storage is now "best-effort" | Low | R2 primary, HF as backup only |
| L19 | Git LFS free tier is 1 GB/month bandwidth | Low | Never put tiles in Git LFS |
| L20 | `source_id` is not stable across Gaia releases; permalinks to a star break at DR4 | Medium, product-facing | Release-tag every stored id; resolve via ESA cross-match tables, or store coordinates and re-resolve (§9 stage 5) |
| L21 | DR4 (2 Dec 2026) grows the `poe>3` set to ~450M; with DR3 retained that is 8.1 GB of R2's 10 GB free tier | Medium | Decide replace-vs-coexist before building; selection cut stays a parameter (§9 stage 5) |

---

## 10b. Validation and QA

§4.8b proposes the HR diagram as the pipeline's QA instrument, which is the sharpest
single check available — but it is one check, and a visual one. The full suite:

| Check | Catches | From |
| --- | --- | --- |
| **HR diagram inspection** | de-reddening and Teff errors — the main sequence smears, bends or grows a second branch | Step 2 |
| **Known-star assertions** in CI | coordinate-frame errors, sign flips, unit mistakes — the failures that produce a plausible-looking but *wrong* sky. Sirius at 2.64 pc in the right direction, plus a set of well-known stars against catalogue values | Step 1 |
| **Encode → decode round-trip** | writer/reader drift (§5.5). Positions within the quantisation step, colour and magnitude indices exact | Step 1 |
| **Flux conservation** | asserts a parent node's total flux equals the sum of its children's. This is the invariant that makes LOD swaps invisible (§5.2); if it breaks, brightness pops and the cause is not obvious | Step 2 |
| **Tile checksums** | corruption in transit or in the build | Step 2 |
| **Golden-image regression** | shader regressions, which no unit test will catch. Fixed camera pose, diff against a stored frame within tolerance | Step 2 |

The known-star assertions are the highest value per line of code, and belong in Step 1
before there is anything complicated to debug.

---

## 10c. Licensing and attribution

Three separately-licensed things, and one of them constrains the product.

| What | Licence |
| --- | --- |
| Code | **MIT** |
| Derived catalogue (tiles) | **CC BY-NC 4.0** — cannot be more permissive than its source |
| Underlying Gaia data | **CC BY-NC 3.0 IGO** (ESA/Gaia/DPAC) |

**The NonCommercial term is real and it shapes the project.** ESA's archive terms
require written authorisation *before* "any use or application that directly or
indirectly generates a financial gain" (data.licences@esa.int). So: no ads, no
paid tier, no sponsorship, no selling tiles — and the derived catalogue stays NC,
because we cannot grant rights we were not given. The terms also forbid implying
ESA endorsement.

**Open-sourcing is not required.** The licence obliges attribution and
non-commercial use, not publication. Making the repository public is a choice.

The ESA/Gaia/DPAC acknowledgement is an obligation and belongs **in the UI**, not
only the README — the data is the product. Full text and the third-party
catalogue credits are in `ATTRIBUTION.md`; check each third-party catalogue's own
licence before redistributing its values in the tiles, as they are not covered by
the Gaia terms.

---

## 11. Roadmap

> Superseded by `STEPS.md`, which expands this into six steps with entry and exit
> criteria. Kept here because the reasoning behind the ordering still applies.

**M1 — Prove the render (1–2 weeks).** T0 only, 0.6M stars, single file, no LOD.
WebGL2, HDR accumulation, camera-relative coords, flux-conserving sprites, free
flight. *Goal: does 0.6M stars with correct brightness actually look good?* Answer
that before building any pipeline. If M1 isn't beautiful, more stars won't fix it.

**M2 — Pipeline and octree (2–3 weeks).** Acquire T1 (35.4M), DuckDB clean, octree
build, seamless streaming. *Goal: prove the LOD swap is invisible.* Add the linked
HR-diagram view here — it is the cheapest and sharpest QA tool you will have (§4.8).

**M3 — Quality (1–2 weeks).** Distance coherence for binaries and clusters, bright
star patching, ΔE-uniform colour LUT, saturation control. *Goal: the Pleiades look
like the Pleiades.*

**M4 — Scale (1–2 weeks).** T2–T3 on R2, Range-request packs, prefetch along the
velocity vector, tier selection UI.

**M5 — Enrichment (1 week).** Cold id streams, click-to-identify, bundled names,
live SIMBAD/VizieR panel, derived mass from HR position (§4.8).

**M6 — Context (open-ended).** Parametric Galaxy model, dust, proper-motion time
travel, constellation lines, tours ("fly to Betelgeuse").

Deliberate ordering: **M1 answers the only question that can kill the project.**
Everything after it is engineering with a known destination.

---

## 12. Decisions

Items marked **DECIDED** are settled; the rest still need your call.

1. **Coordinate frame** — Galactic Cartesian (recommended, disc lies flat) or
   equatorial (matches raw catalogue, easier to cross-check)?
2. **Which tier is the default load?** T1 at 283 MB is a real commitment on a phone
   tether. Auto-detect via the Network Information API, or ask?
3. **How loud should the uncertainty be?** Quiet (a HUD confidence number) or loud
   (distant stars visibly smeared along their error needle)? This is a product
   identity choice, and the honest option is genuinely more interesting.
4. **Colour default** — physically accurate (mostly white) or exaggerated? Default
   matters more than the slider.
4b. **Is the linked HR diagram a headline feature or a dev tool?** It costs nothing
   either way, but "headline feature" means UI budget for brushing and linked
   selection, which is real work (§4.8a).
5. **Pipeline language — DECIDED 2026-08-27: Python throughout.** Settled by
   measurement, not preference. I argued for Rust twice — on performance and on
   sharing the codec with the client via WASM — and benchmarking killed both
   arguments (§12.5c). The full pipeline at 320.5M stars runs
   in **under three minutes** in pure numpy — against ~40 GB of TAP downloads measured
   in hours. Python also owns the parts that actually matter: `astroquery` for TAP,
   `astropy` for coordinate frames and epoch propagation, `dustmaps` for the 3D dust
   map, `matplotlib` for the HR diagram QA that §10b calls the sharpest instrument in
   the pipeline.

   Rust for the encoder remains a legitimate *preference*, but not an evidenced
   need — recorded here as considered and declined.
   The seam is clean — Stage 2 hands Stage 3 a sorted Parquet file — so the polyglot
   cost is low if you want it, and the encoder is the most self-contained and most
   enjoyable piece to write in Rust. It also becomes the right call if in-browser or
   Worker-side tile generation ever becomes a goal. Just do not believe it is
   necessary: it is not.

5b. **Client toolchain.** Recommendation: **TypeScript + Bun + raw WebGL2**, no 3D
   framework. Raw WebGL2 because everything distinctive here cuts against a scene
   graph — packed vertex formats (§4.4), pre-accumulation exposure (§6.1),
   camera-relative float64→float32 transforms (§6.3), manual tile buffer management.
   Three.js would be fought more than used; revisit only if VR arrives. Bun over
   Vite because it collapses runtime, package manager, bundler and test runner into
   one tool, and Vite's main advantage — its framework plugin ecosystem — is unused
   when there is no framework.
5c. **The measurements.** `tools/lang-benchmark/` implements the Stage-3 hot loop —
   quantise → Morton → sort → pack → flux-summing merge — in both languages. Rust uses `rayon`
   across 12 cores; Python uses vectorised numpy, single-threaded. Both produce
   identical group counts.

   | Stage (n = 20M) | Rust | numpy | Rust advantage |
   | --- | --- | --- | --- |
   | quantise + Morton | 0.039 s | 1.223 s | 31× |
   | sort | 0.941 s | 2.716 s | 2.9× |
   | pack | 0.287 s | 1.104 s | 3.8× |
   | flux merge | 0.313 s | 0.868 s | 2.8× |
   | **total** | **1.58 s** | **5.91 s** | **3.7×** |

   Peak RSS at n = 50M: Rust 1.89 GB, numpy 6.02 GB — 3.2×.

   And `bench_tree.py` builds the tree structure itself at the full 320.5M, in pure
   numpy: **15.3 s** across three levels (~5 s each), so a realistic 10–12 level tree
   is ~60 s. Every operation is a vectorised primitive — boundaries via `flatnonzero`
   on a sorted array, flux sums via `add.reduceat`, child masks via shift+mask, byte
   offsets via `cumsum`. **There is no per-node Python loop anywhere.** Tree
   construction, the step most likely to be assumed to need a systems language, does
   not.

   **Three conclusions follow:**

   - **Speed is not an argument.** Extrapolated to 320.5M the whole hot loop is ~25 s
     in Rust against ~95 s in numpy. The pipeline's real cost is ~40 GB of TAP
     downloads, measured in *hours*. Saving 70 seconds is noise. (And before the Rust
     merge was parallelised, numpy *won* that stage 0.87 s to 1.68 s — vectorised
     numpy is not a strawman.)
   - **Memory is not an argument either.** 3.2× matters only if you process 320M rows
     in one pass — which you must not do anyway, because the HEALPix partitioning that
     makes the joins tractable (§9 stage 2) also caps working set at ~104k rows per
     chunk. At that size the difference is irrelevant.
   - **The WASM argument is real, narrower than I stated, and has a better
     substitute.** The hot record is
     unpacked in the **GLSL vertex shader** (§4.4), with positions going to the GPU
     zero-copy (§4.6) — so the record bit-layout is shared between a Rust writer and a
     *shader* reader, and WASM cannot help. What WASM genuinely shares is the
     **container** format: pack header, hierarchy index, node offsets and lengths, and
     the varint id streams. That is real drift risk — but the better fix is to define
     the format once in a spec file and **code-generate both the Python writer and the
     TypeScript reader**. That keeps the client reader native TS: no WASM bundle, no
     init step, no JS↔WASM boundary to parse a few hundred bytes of header. For a
     container this small, WASM was overkill.

5d. **What choosing Rust anyway would cost.** Four things, none blocking — worth
   knowing if you take the preference route:

   | Cost | Severity | Mitigation |
   | --- | --- | --- |
   | **No `astropy`.** ICRS → Galactic is a fixed 3×3 rotation you implement yourself | Low | ~15 lines, well documented. The known-star assertions (§10b) catch a wrong matrix immediately — this is exactly what they are for |
   | **No `dustmaps`.** Step 3's 3D dust map ships as FITS/HDF5; `fitsio` (128k downloads) and `hdf5` (1.7M) are thinner than the Python equivalents | **Medium — the real gap** | Pre-convert the dust map to Parquet **once**, with Python, and have Rust read that. A one-off, and it makes the pipeline faster anyway |
   | **Slower exploratory iteration.** Looking at distributions and sanity-checking is genuinely nicer in a notebook | Low | Keep a small Python side-channel for QA and plotting only. Nothing ships, so it cannot rot the build |
   | **Compile times** while iterating on the builder | Low | Develop against one HEALPix chunk (~104k rows), not the full set |

   Crate availability checked: `polars` 0.55, `duckdb` 1.1, `parquet` 59.2,
   `rayon` 1.12, `bytemuck` 1.25, `cdshealpix` 0.9, `wasm-bindgen` 0.2 — all current.
   `cdshealpix` comes from CDS, the same group that runs VizieR and SIMBAD.
6. **R2 account** — this needs a Cloudflare account with a payment method on file
   even to stay inside the free tier. Fine to start Pages-only through M3.

---

## 13. Feasibility verdict

**Yes, and the numbers are more comfortable than they look.**

- 5.1 MB gets every naked-eye star and the complete 100 pc neighbourhood.
- 8 bytes/star, from a naive 28, with *better* accuracy than `float32` absolute
  coordinates.
- The chosen 320M-star catalogue is 2.56 GB — a quarter of R2's free tier, delivered
  with zero egress cost. Even 764M stars (`poe > 1`) is 6.1 GB and still free.
- Only 2–5M points are ever GPU-resident, which is 16–40 MB of VRAM. Any laptop
  from the last decade will hold 60 fps.
- LOD tile fetches consume 0.46% of R2's monthly free operation budget.

The hard problems are not the ones the brief anticipated. Compression is basically
solved by §4.1's scale-free quantisation insight. The real work is **(a)** the
anisotropic-error artifact that makes naive Gaia 3D maps look like hairbrushes
(§2, §5.3), **(b)** HDR brightness done correctly (§6.1–6.2), and **(c)** the fact
that Gaia's 3D map ends 2 kpc out while the Galaxy continues for 15 more (§6.6).

Build M1 first. It costs a week and it answers the only question that matters.

---

## A. Reproducing the measurements

**Catalogue counts** — anonymous TAP, no account needed:

```bash
q() { curl -s -G "https://gea.esac.esa.int/tap-server/tap/sync" \
  --data-urlencode "REQUEST=doQuery" --data-urlencode "LANG=ADQL" \
  --data-urlencode "FORMAT=csv" --data-urlencode "QUERY=$1" | tail -1; }

q "SELECT COUNT(*) FROM gaiadr3.gaia_source_lite"
q "SELECT COUNT(*) FROM gaiadr3.gaia_source_lite WHERE parallax_over_error>5"
q "SELECT COUNT(*) FROM gaiadr3.gaia_source_lite WHERE parallax<0"
```

**Bulk-download size** — the ESA CDN's HTML index is JS-driven; the underlying
bucket speaks S3 XML:

```bash
curl -s "https://gaia.eu-1.cdn77-storage.com/?prefix=Gaia/gdr3/gaia_source/&delimiter=/&max-keys=1000"
# 1000 files, 227.52 GB  ->  mean 227.5 MB  ->  x3386 files = ~770 GB
```

**CORS and Range on a candidate host:**

```bash
curl -sL -D - -o /dev/null "$URL" -H "Origin: https://x.example" -H "Range: bytes=0-99" \
  | grep -iE "HTTP/|accept-ranges|content-range|access-control"
```

**Colour and geometry maths** — the scripts that produced the ΔE, chroma, pixel-error
and storage tables are committed alongside this document, so every table in §4 and
§5 stays checkable:

```bash
python3 tools/verify_colour_quantisation.py            # blackbody sRGB, dE76 steps, chroma
python3 tools/verify_geometry_budgets.py               # px error, tier sizes, octree shape
python3 tools/verify_hr_entropy.py sample_allsky.csv   # HR joint entropy + bias check
```

## B. References

- [Gaia DR3 overview](https://www.cosmos.esa.int/web/gaia/dr3) · [Gaia Archive](https://gea.esac.esa.int/archive/) · [bulk download CDN](https://cdn.gea.esac.esa.int/Gaia/gdr3/)
- [Gaia DR3: Summary of content and survey properties](https://www.aanda.org/articles/aa/full_html/2023/06/aa43940-22/aa43940-22.html) (A&A 2023)
- [Gaia DR3: Apsis I — methods and content](https://www.aanda.org/articles/aa/full_html/2023/06/aa43688-22/aa43688-22.html) — GSP-Phot, 470M sources with Teff
- [Lindegren et al. 2021 — parallax zero-point](https://www.aanda.org/articles/aa/full_html/2021/10/aa40862-21/aa40862-21.html)
- [Bailer-Jones et al. 2021 — distances to 1.47 billion stars](https://iopscience.iop.org/article/10.3847/1538-3881/abd806) · VizieR `I/352`
- [El-Badry, Rix & Heintz 2021 — a million binaries from Gaia EDR3](https://academic.oup.com/mnras/article/506/2/2269/6131876)
- [SIMBAD TAP](https://simbad.cds.unistra.fr/simbad/sim-tap) · [VizieR TAP](https://tapvizier.cds.unistra.fr/TAPVizieR/tap/)
- [Potree](https://github.com/potree/potree) — the octree-plus-byte-ranges pattern
- [Charlie Hoey's Gaia DR1 WebGL map](https://cdn.charliehoey.com/threejs-demos/gaia_dr1.html) — prior art, ~2M stars
- [GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits) · [Cloudflare R2 pricing](https://developers.cloudflare.com/r2/pricing) · [Hugging Face storage limits](https://huggingface.co/docs/hub/storage-limits) · [jsDelivr terms](https://www.jsdelivr.com/terms)
- [WebGPU implementation status](https://github.com/gpuweb/gpuweb/wiki/Implementation-Status)
