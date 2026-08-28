# Catasterism — build steps

Companion to [PLAN.md](PLAN.md), which holds the research, the measured numbers and
the design rationale. This file is the execution order: six steps, each with the
question it answers, what it delivers, and the criteria for moving on.

**Every step must stay DR4-ready.** Gaia DR4 releases **2 December 2026** — Steps 1–3
land around then. It is the pipeline's second run, not a distant hypothetical, and it
must not be a rewrite. Concretely, in every step: the release is configuration (the
string `gaiadr3` appears exactly once in the codebase), the reference epoch is read
from that config (DR3 is J2016.0, **DR4 is J2017.5**), every stored `source_id` is
release-tagged because **ids are not stable across releases**, and the selection cut
is a parameter. Full detail in PLAN.md §9 stage 5.

**The ordering is deliberate.** Step 1 exists to answer the only question that can
kill the project, and it does so before any pipeline, tile format or catalogue work
is built on top. Everything after Step 1 is engineering toward a known destination.

---

## Performance budget

Applies to every step. Measure on a real low-end machine, not a dev box, and record
the actual number rather than a pass/fail.

| Criterion | Target | Floor |
| --- | --- | --- |
| Frame rate @1920×1080, integrated graphics | 60 fps | **30 fps** |
| First paint, 25 Mbit connection | < 2 s | < 3 s |
| Tile fetch p95, warm cache (Step 2+) | < 100 ms | < 200 ms |
| Tile fetch p95, cold (Step 2+) | < 300 ms | < 500 ms |
| Resident points | 2–5M | — |

30 fps is a hard floor, not an "optimise later": Step 4 multiplies the catalogue by
500× and only LOD stands between that and this budget.

---

## Overview

| Step | Name | Answers | Stars | Rough size |
| --- | --- | --- | --- | --- |
| **1** | Prove the render | *Does a correctly-lit star field actually look good?* | 625,679 | ~1–2 weeks |
| **2** | Tile format and streaming | *Can we stream LOD invisibly?* | 35.4M | ~2–3 weeks |
| **3** | Astrophysical correctness | *Is the data actually right?* | 35.4M | ~1–2 weeks |
| **4** | Scale to the full catalogue | *Does it hold up at 320M + 1.81B?* | 320.5M | ~1–2 weeks |
| **5** | Identity and enrichment | *Can you ask a star what it is?* | — | ~1 week |
| **6** | Context and polish | *Does it feel like a place?* | — | open-ended |

---

## Step 1 — Prove the render

**Question:** does a physically correct star field, rendered properly, actually look
good enough to build a product on?

This is a kill gate, not a formality. Everything in PLAN.md assumes the answer is
yes. If 625,679 correctly-lit stars with a working HDR pipeline and honest colours
are not compelling, then 320 million of them will not be either, and the right move
is to rethink rather than to build a pipeline.

**Dataset:** T0 — every star within 100 pc, plus every star brighter than G = 8.

```sql
WHERE (parallax > 10 AND parallax_over_error > 3) OR phot_g_mean_mag < 8
-- 625,679 stars, measured. ~5.0 MB at 8 B/star.
```

That is deliberately the smallest set that is *complete* at two things people care
about: the whole solar neighbourhood, and the entire visible sky.

**Deliverable:** a deployed GitHub Pages URL you can open and fly around in.

**Explicitly out of scope:** octree, LOD, streaming, tile format, R2, `source_id`
streams, SIMBAD, cluster coherence, dust maps, the Galaxy model. One file, loaded
once, held entirely in memory. Resist all of it — the point is to reach the visual
question as fast as possible.

**Exit criteria** — all must hold:

1. **Frame rate within the budget above** with all 625,679 stars.
2. **First paint under 3 s** on a 25 Mbit connection.
3. **The sky from Earth is recognisable.** Orion, the Big Dipper and the Southern
   Cross identifiable by eye at default exposure, side by side with a photograph.
4. **Sirius lands at 2.64 pc** in the right direction, and a handful of other known
   stars hit their catalogue distances. Position sanity, asserted in code.
5. **Flight is comfortable** from 1 AU to 100 pc without touching a speed control.
6. **It looks good.** Subjective, and the one that actually matters. Judge it on a
   real screen in a dark room, not a screenshot.
7. **DR4-ready:** `gaiadr3` appears exactly once in the codebase, and the reference
   epoch comes from config rather than a literal.
8. **The recognisable stars are present.** Sirius, Vega, Rigel and Orion's belt all
   render. Moved here from Step 3 during testing: Gaia saturates around G ≈ 3, so
   **all 25 of the brightest stars in the sky are absent from DR3**, and without them
   criterion 3 above cannot be judged at all.

Tasks: [TASKS_STEP_1.md](TASKS_STEP_1.md).

---

## Step 2 — Tile format and streaming

**Question:** can the octree LOD swap be made genuinely invisible?

The second real risk. PLAN.md §5.4 argues the swap is invisible *because* merging
conserves flux (§5.2) and quantisation error is sub-0.1 px (§4.1). That argument is
sound but untested. If stars visibly pop, twinkle or shift when a tile refines, the
whole "compression should be invisible to the user" requirement fails.

**Dataset:** T1 — `plx > 2 mas AND poe > 3`, 35,423,727 stars, 283 MB. Big enough
that LOD is mandatory, small enough to rebuild in minutes while iterating.

**Delivers:**

- **The tile format specification** (`FORMAT.md`), written to the byte before either
  the builder or the loader is coded — the full contract is in PLAN.md §5.5.
- Octree builder: Morton sort → tree → **flux-summing** inner nodes → quantise → pack.
  Python/numpy throughout — benchmarked at ~95 s for the hot loop and ~60 s for tree
  construction at the full 320.5M, against a pipeline dominated by hours of network
  transfer (PLAN.md §12.5c).
- **Code-generate the container reader and writer from one spec file** — the Python
  writer and the TypeScript reader must not drift. Note the hot record is unpacked in
  GLSL, so generate that unpacker from the same definition (PLAN.md §5.5, §12.5c).
- Streaming loader: screen-error priority queue, capped in-flight requests, velocity
  prefetch, parent-held-until-children-resident swap.
- **Cloudflare R2 bucket**, custom domain, HTTP Range requests. Required here, not
  later: T1 is 283 MB even at 8 B/star, past GitHub's 100 MB per-file hard limit
  (PLAN.md §7.2). T0 stays in the repo permanently; nothing else can.
- Service worker + IndexedDB tile cache (PLAN.md §7.4).
- Validation suite (PLAN.md §10b): flux conservation, tile checksums, golden-image
  regression, plus the round-trip and known-star checks carried forward from Step 1.
- Reserve per-star `parallax_over_error` in the record's flag bits now, so Step 6's
  uncertainty modes (PLAN.md §6.8) do not need a format change.

**Exit criteria:**

1. No visible pop in brightness, colour or position during LOD refinement — verified
   by A/B'ing frames across a refinement boundary, not by eye alone.
2. Sustained 60 fps (30 floor) while flying continuously through the densest region.
3. Nothing ever renders as a hole: a node that has not arrived shows its parent.
4. p95 tile fetch under 200 ms on a warm cache, under 500 ms cold.
5. **DR4-ready:** the pack header carries release and epoch; the tile URL path carries
   the catalogue version (`dr3-v1`); the loader refuses a version mismatch rather than
   rendering it. Acquisition is resumable and cached per release+chunk, so re-running
   for DR4 costs nothing for work already done.

---

## Step 3 — Astrophysical correctness

**Question:** is the data right, rather than merely present?

Step 2 proves the plumbing. This step proves the physics. It is separated out
because these are the errors that are **silent** — nothing looks broken, the stars
are just quietly wrong, sometimes permanently (PLAN.md L9c).

**Delivers:**

- **Extinction correction.** Subtract `A_G` when deriving absolute magnitude
  (PLAN.md §4.3). 13.9% of stars are dimmed >2.5×; skipping this bakes Earth's dust
  column into their intrinsic luminosity forever. 3D dust map for the 25.2% with no
  `ag_gspphot`.
- **Parallax zero-point correction** (Lindegren et al. 2021).
- **Distance coherence** (PLAN.md §5.3) — snap resolved binaries (El-Badry et al.)
  and cluster members to common distances. This is what stops clusters rendering as
  radial hairbrushes, and it is the largest single visual quality win available.
- ~~Bright-star patching from Hipparcos~~ — **moved to Step 1**, because without it
  Step 1's own "does the sky look right" verdict is unanswerable. Step 3 extends it
  below the naked-eye limit if the fainter tiers need it.
- **The colour fallback path** — de-reddened `bp_rp` → Teff for the 22.6% with no
  `teff_gspphot`. Load-bearing at `poe > 3`, not a corner case.
- **The linked HR diagram** (PLAN.md §4.7) — both as a feature and as the QA
  instrument that makes every error above visible at a glance.
- Epoch handling stated explicitly: DR3 is J2016.0, Hipparcos is J1991.25, and the
  bright-star patching above crosses that boundary (PLAN.md §9, stage 2 step 7).

**Exit criteria:**

1. The HR diagram shows a clean main sequence, a distinct giant branch and a
   separated white dwarf sequence — no smearing, no spurious second branch.
2. The Pleiades, Hyades and Praesepe read as compact clusters from any angle, not as
   radial streaks.
3. Every star brighter than V = 4 is present and at its catalogue distance.
4. Removing the extinction correction visibly degrades the HR diagram — proving the
   correction is actually doing something.
5. **DR4-ready:** the schema-mapping layer (source columns → canonical internal
   schema) is isolated to one module, so a DR4 rebuild touches that file and the
   release descriptor and nothing else.

---

## Step 4 — Scale to the full catalogue

**Question:** does any of this break at 320 million, and then at 1.81 billion?

**Delivers:**

- T2 (98.8M) and T3 (320.5M, 2.56 GB) built and on R2.
- The **planetarium layer**: all 1.81B sources as an all-sky HEALPix flux-map pyramid
  plus resolved bright stars (PLAN.md §3.3). Stores raw apparent `G` — no distance,
  no extinction, no correction of any kind. Exact by construction.
- Mode switching between planetarium and flight, with the flux map cross-fading out
  as the camera leaves the solar neighbourhood.
- Tier selection UI, with connection-aware defaults.
- `poe > 10` filter toggle for users who want a sharper HR diagram over more stars.
- Derived-catalogue versioning (PLAN.md §7.5): version in the pack header and the
  tile URL path; the app refuses a mismatch rather than rendering garbage.
- Zenodo archival snapshot with a DOI.

**Exit criteria:**

1. Frame rate unchanged from Step 2 and still above the 30 fps floor — LOD means catalogue size must not affect it.
2. Build completes on a laptop without exhausting RAM — HEALPix chunking caps the working set at ~104k rows (PLAN.md §9 stage 2).
3. R2 free tier not exceeded: under 10 GB stored, under 10M Class B ops/month.
4. Planetarium view matches a real all-sky photograph at matched exposure.
5. **DR4 decision made and recorded:** does DR4 replace DR3 or sit beside it? At
   `poe > 3` DR4 is ~450M stars (4.7 GB); both together are 8.1 GB of R2's 10 GB free
   tier (PLAN.md L21).

---

## Step 5 — Identity and enrichment

**Question:** can you point at a star and ask what it is?

**Delivers:**

- Cold `source_id` streams per tile, delta+varint, lazy-fetched on interaction only
  (PLAN.md §4.5).
- Click/hover picking that resolves to a real catalogue entry — including for merged
  LOD points, which carry their brightest member's `source_id`.
- Bundled name catalogue in-repo: IAU names, Bayer/Flamsteed, HIP, HD. Makes every
  recognisable star resolve instantly and offline.
- **Release-tagged ids.** `source_id` is not stable across Gaia releases (PLAN.md L20),
  so anything persisted — bookmarks, permalinks, shared links — must store the release
  alongside the id and resolve through ESA's cross-match tables, or store coordinates
  and re-resolve positionally.
- Live SIMBAD and VizieR TAP queries from the browser (both send
  `Access-Control-Allow-Origin: *` — verified, PLAN.md §8).
- Derived properties in the info panel: mass from HR position, luminosity in solar
  units with bolometric correction, distance with its uncertainty.
- Graceful "nothing catalogued" — the common case, since only 0.8% of sources have a
  SIMBAD entry.

**Exit criteria:**

1. Clicking any star returns something useful within 500 ms, or says plainly that
   nothing is catalogued.
2. Every IAU-named star resolves with no network round trip.
3. A merged LOD point resolves to its brightest real member, not to a fiction.

---

## Step 6 — Context and polish

**Question:** does it feel like a place rather than a dataset?

Open-ended, ordered by value:

- **Uncertainty visualisation** (PLAN.md §6.8) — build the loud mode where stars
  smear along their error needle, default to the ambient one.
- **The parametric Galaxy model** (PLAN.md §6.6) — exponential disc plus bulge as a
  low-frequency emissive volume, so the Galaxy looks like a galaxy from outside
  instead of ending abruptly at 2 kpc.
- Interstellar dust and nebulae as volumetric structure.
- Constellation lines and figures, on in planetarium mode.
- Guided tours — "fly to Betelgeuse", "watch the Pleiades resolve".
- Proper-motion time travel: scrub ±100,000 years and watch constellations dissolve.
  Needs `pmra`/`pmdec`/`radial_velocity` in an optional stream, +12 B/star.
- WebGPU fast path with compute-shader culling.
- VR.

---

## Notes on sequencing

**Why the tile format waits for Step 2.** It is tempting to specify it first, since
everything depends on it. But Step 1's job is to find out what the renderer actually
needs, and a format designed before the renderer exists will be wrong in ways nobody
can predict. Step 1 uses a throwaway flat file precisely so the real format can be
designed with evidence (PLAN.md §5.5).

**Why correctness (Step 3) comes after streaming (Step 2).** The astrophysical
corrections change the *values* in the pipeline, not its shape. Building them into a
pipeline whose structure is still moving means doing them twice. And Step 3's exit
criteria depend on the HR diagram, which is easier to build once tiles exist.

**Why the planetarium layer waits until Step 4.** It is a second, structurally
different data path — an angular pyramid rather than a spatial octree. Introducing it
before the primary path is stable would mean debugging two unfinished systems against
each other.

**Decisions that must be settled during Step 1**, because everything after depends on
them: flight controls (PLAN.md §6.7), client toolchain (§12.5b), the performance
budget above, and licensing (§10c).

**What could reorder this.** If Step 1 reveals the renderer is fine but flight
controls are the hard problem, insert a dedicated camera/UX step before Step 2 —
"fly around like a spaceship" is the actual brief, and no amount of catalogue work
compensates for movement that feels wrong.
