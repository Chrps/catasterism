# Step 1 — Prove the render

**Goal:** find out whether a physically correct star field, rendered properly, looks
good enough to build a product on. See [STEPS.md](STEPS.md) for where this sits;
[PLAN.md](PLAN.md) for the research behind every decision below.

**Deliverable:** a deployed GitHub Pages URL you can open and fly around in.

**Dataset:** 625,679 stars — everything within 100 pc, plus everything brighter than
G = 8. ~5 MB.

**Not in this step:** octree, LOD, streaming, tile format, R2, `source_id` streams,
SIMBAD, cluster coherence, dust maps, the Galaxy model, proper motion. One file,
loaded once, held in memory. The point is to reach the visual question fast.

Nine tasks: T1–T4 build the data, T5–T7 build the client, T8–T9 deliver the verdict.

**Four decisions must be settled here**, because everything after depends on them:
flight controls (T6), client toolchain (T1), the performance budget (T8), and
licensing (T1).

---

## T1 — Repo foundation

Set up the project so everything after it has somewhere to land.

- Dev container (repo-only mount, non-root, no host access) — the repo already
  carries `CLAUDE.md` → `AGENTS.md` for this.
- **Pipeline language: Python** (PLAN.md §12.5, benchmarked in §12.5c). Not a default
  — a measured decision. The full pipeline runs in under three minutes at 320.5M in
  pure numpy, against ~40 GB of TAP downloads measured in hours, and `astroquery`,
  `astropy`, `dustmaps` and `matplotlib` are exactly what the science stages need.
  Rust for the encoder remains a legitimate preference (§12.5d lists what it costs),
  but the benchmarks do not require it.
- **Client toolchain**, then commit to it. Recommendation: **TypeScript + Bun + raw
  WebGL2**, no 3D framework (PLAN.md §12.5b). Raw WebGL2 because packed vertex
  formats, pre-accumulation exposure and camera-relative transforms all cut against a
  scene graph. Bun because it collapses runtime, package manager, bundler and test
  runner into one tool, and there is no framework for Vite's plugin ecosystem to
  serve. (The pipeline is Python — separate decision, above.)
- GitHub Actions → Pages deployment on push to `main`.
- **Licensing and attribution** — a real obligation, not paperwork (PLAN.md §10c):
  the ESA/Gaia/DPAC acknowledgement **in the UI**, not just the README; CC-BY-4.0 for
  the derived catalogue; MIT or Apache-2.0 for the code.
- **DR4 readiness from commit one** (PLAN.md §9 stage 5). Gaia DR4 lands
  **2 December 2026**, roughly when Step 3 finishes — this pipeline runs twice, and
  the second run must not be a rewrite. Put the release name, table name, reference
  epoch (DR3 = J2016.0, DR4 = J2017.5) and selection cut in **one release-descriptor
  file**. The test is grep: `gaiadr3` should appear exactly once in the codebase.
- `tools/` holds four verification scripts from the design phase — keep them runnable,
  they back the numbers in PLAN.md.

**Done when:** an empty page deploys to Pages from a push, in a container, and
`grep -r gaiadr3` returns exactly one hit.

---

## T2 — Acquire and derive the T0 catalogue

One throwaway script producing one file. Correctness matters; elegance does not.

- Pull from ESA TAP (PLAN.md §9). Small enough for a handful of queries — no HEALPix
  chunking needed at this size.

  ```sql
  SELECT source_id, ra, dec, parallax, parallax_over_error,
         phot_g_mean_mag, bp_rp, teff_gspphot, ag_gspphot, ebpminrp_gspphot, ruwe
  FROM   gaiadr3.gaia_source_lite
  WHERE  (parallax > 10 AND parallax_over_error > 3) OR phot_g_mean_mag < 8
  ```

  Table name, epoch and the `poe` cut come from the release descriptor (T1), not from
  literals in this query.

- Derive absolute magnitude **including the extinction term** —
  `M_G = G + 5·log₁₀(plx) − 10 − A_G` (PLAN.md §4.3). Get this right now; it is the
  silent error, and Step 1 is where the habit is set.
- Derive Teff: `teff_gspphot` where present, de-reddened `bp_rp` otherwise, neutral
  ~5800 K as last resort.
- Convert equatorial → **Galactic Cartesian, parsecs**. Galactic, not equatorial, so
  the disc lies in a plane (PLAN.md §9, stage 2). Use `astropy` rather than a
  hand-written rotation — it handles the frame definition and epoch propagation
  correctly, which matters at Step 3 when Hipparcos (J1991.25) is cross-matched
  against DR3 (J2016.0). T8's known-star assertions verify it either way.
- **Patch the bright stars Gaia cannot see** — task T3b. Originally Step 3; moved
  here once testing showed the sky cannot be judged without it.
- The Sun is task T3 — it needs more than a row in a table.

**Done when:** a Parquet/CSV file of ~625,679 rows exists, and spot-checking Sirius,
Vega, Betelgeuse and Proxima against SIMBAD agrees on distance and magnitude.

---

## T3b — Patch the bright stars Gaia cannot see

Gaia saturates around G ≈ 3, so the stars that *define* constellations are exactly
the ones it measures worst or not at all. Measured against Hipparcos:

| | missing from Gaia DR3 |
| --- | --- |
| Hp < 3.0 | **108 of 165 (65%)** |
| Hp < 4.5 | 311 of 837 (37%) |
| Hp < 6.5 | 1,596 of 7,982 (20%) |

All 25 of the brightest stars in the sky are absent, and Orion's belt survives as
one star of three. This was Step 3 work until testing showed that T9's verdict —
"does the sky look right" — cannot be reached without it.

- Use **`gaiadr3.hipparcos2_best_neighbour`**, ESA's own cross-match, rather than
  matching by position. Positional matching across a 25-year epoch gap silently
  selects the wrong star, which is exactly the trap in PLAN.md §9 stage 2 step 7.
- **Fit the colour transformations on the overlap**, not from a paper: 44,034 stars
  are in both catalogues, which is ample to calibrate V + B−V → G and gives a
  residual you can check. Sigma-clip first — 7.3% of the sample is variables,
  unresolved binaries and bad photometry, and leaving them in inflates the scatter
  from 0.04 mag to 0.30.
- Propagate positions from Hipparcos's J1991.25 to the release epoch.
- Carry them as **negative `source_id`** (`-hip`), which cannot collide with Gaia's
  positive ids or the Sun's zero, and keeps the catalogue identity recoverable.

**Done when:** Sirius, Vega, Rigel, Betelgeuse and all three belt stars render at
roughly their real brightness.

---

## T3 — Add the Sun

Gaia cannot observe the Sun, so the most important object in the product has to be
inserted by hand. It is the origin, the orientation anchor, the "home" target, and the
first star anyone will fly to. Full spec in **PLAN.md §4.7**; the work is:

- **Insert it at the origin** with real values: M_G = +4.67, Teff 5772 K,
  bp_rp = 0.82, R = 6.957 × 10⁸ m. (Gaia positions are barycentric and the Sun orbits
  the barycentre by ~0.005 AU = 2.4 × 10⁻⁸ pc — ignore it.)
- **Use it to calibrate the renderer.** The Sun creates no rendering problem that free
  flight does not already create for every star — unbounded apparent brightness
  (PLAN.md §6.1) and the point→disc transition (§6.2) are general, and T5 handles them
  generally. What makes the Sun special is that it is the instance you are
  *guaranteed* to hit: it is where the camera starts, so both behaviours are exercised
  on the first run, and its values are known far more precisely than any Gaia source,
  so it is the only absolute check on the brightness pipeline. If the Sun looks wrong,
  every star is wrong and you cannot tell from the others.
- **Build the "look back" moment.** The Sun drops below naked-eye visibility beyond
  ~50 pc, inside T0's own shell. Fly out thirty light years, turn around, and home is
  an unremarkable dot. That is the emotional payload of the whole project and it costs
  one control.
- Place **Earth** as a labelled camera start position at 1 AU, not as geometry — at
  parsec scale it is invisible by a factor of ~10⁹.

`tools/verify_sun_and_hdr.py` computes the magnitudes, disc thresholds and dynamic
range and is the reference.

**Done when:** the Sun renders correctly from Earth's distance, from 100 AU, and from
50 pc; and flying from 1 AU to 100 pc does not blow out or black out the display.

---

## T4 — Encode to the binary format

The 8-byte record from PLAN.md §4.4, minus the parts LOD would need.

- Generate the **256-entry ΔE-uniform blackbody colour LUT** as a PNG or raw texture.
  `tools/verify_colour_quantisation.py` already computes the colours and proves 8 bits
  is below the visibility threshold — reuse it rather than reinventing.
- Quantise: 12 bits/axis position, 12-bit absolute magnitude, 8-bit colour index,
  8 bits flags. Since there is no octree yet, quantise against **one global bounding
  box** rather than per-tile. Note this is the one case where PLAN.md §4.1's scale-free
  argument does *not* apply — a single 200 pc box at 12 bits gives ~0.05 pc
  resolution, which is fine here and would not be at Galactic scale.
- Write the loader-side unpacking as a documented mirror of the writer. These two
  drift; keep them adjacent and test them against each other.

**Done when:** a ~5 MB binary file round-trips through encode → decode with position
error under the quantisation step and exact colour/magnitude indices.

---

## T5 — Renderer core

The heart of the step. Everything here is from PLAN.md §6 and none of it is optional.

- **HDR accumulation with pre-accumulation exposure.** Free flight means the camera
  can sit anywhere relative to any star, so the *apparent* range is bounded only by
  stellar surface brightness — measured at **10²⁰**, against float16's 10¹²
  (PLAN.md §6.1). Multiply flux by a per-frame exposure scalar **before** the additive
  blend into `rgba16float`, then tonemap (`1 − exp(−k·L)`). The order matters and
  cannot be retrofitted cheaply. Auto-expose from the previous frame's histogram with
  manual override.
- **Point sprites must become discs** as the camera closes in — 17.1 AU for the Sun,
  13,000 AU for Betelgeuse (PLAN.md §6.2). Billboard disc with limb darkening,
  cross-fading from the sprite. Radius derives from Teff and luminosity; no extra
  bytes.
- **Flux-conserving point sprites:** clamp sprite size to ~1–1.5 px minimum and scale
  intensity by `(desired/clamped)²`. Without this, sub-pixel stars alias and shimmer
  as the camera moves — and almost every star is sub-pixel.
- **Camera-relative rendering:** compute `object_origin − camera_position` in float64
  on the CPU, upload as a float32 uniform. Build it in from the first commit; it
  touches every shader and is miserable to retrofit.
- **Per-frame brightness from camera distance:** `flux = 10^(−0.4·M_G) / d²`. This is
  the whole reason absolute magnitude is stored.
- Two-pass sprites: `gl.POINTS` for the faint majority, instanced quads for the few
  thousand bright stars needing a large glow kernel.
- Bloom on the bright tail — it is what makes a dot read as a star.

**Done when:** 625,679 stars render at 60 fps (30 fps floor) at 1920×1080 on
integrated graphics, with no shimmer while moving, and brightness responding correctly
to approach.

---

## T6 — Camera and flight controls

PLAN.md never addressed this, and it is the actual brief. Budget real time for it.

- **Scale-adaptive speed** is the hard problem: usable motion spans ~1 AU to ~100 pc,
  a factor of ~10⁷ in this step alone and 6 × 10⁹ in the full product. A fixed speed
  is unusable at both ends. Options and the recommendation are in PLAN.md §6.7 —
  derive speed from distance to the nearest star, keep it continuous, and prototype
  against departing the Sun, the hardest case and the one users hit first.
- 6DOF flight plus an orbit mode for examining a single star.
- **A planetarium mode** anchored at the Sun, rotation only. Per PLAN.md §2 this is
  the view that is exactly correct, and it is also the one people will recognise. It
  should be the default landing state.
- Smooth "fly to" transitions — needed for T8's evaluation, and the seed of Step 6's
  tours.
- Do not build a speed slider and call it solved. If the user has to manage speed
  manually, the control scheme has failed.

**Done when:** you can fly from Earth's surface view out past 100 pc and back,
stopping to examine individual stars, without ever thinking about speed.

---

## T7 — Orientation and framing

Small, but the difference between a point cloud and a place.

- Place Earth/the Sun visibly, and show where the camera is relative to it.
- A HUD reading distance from Sol in AU / ly / pc as appropriate to scale.
- Exposure control, and the **colour saturation slider** from PLAN.md §4.2 — with the
  physically accurate default. Stars really are nearly white (the Sun is C\* = 6.4);
  exaggeration should be the user's choice, not baked into the data.
- A "return to Earth" control. People fly off and get lost; this is not optional.

**Done when:** you always know where you are and which way home is.

---

## T8 — Deploy and measure

Against STEPS.md's exit criteria, on real hardware, not a dev machine.

- The full performance budget in STEPS.md: **60 fps target, 30 floor** at 1920×1080 on integrated graphics; first paint under 3 s on a throttled 25 Mbit connection. Record actual numbers, not pass/fail.
- Position assertions in CI: Sirius at 2.64 pc in the right direction, plus a handful
  of other known stars against their catalogue values. These catch coordinate-frame
  errors, sign flips and unit mistakes — the failures that produce a plausible-looking
  but wrong sky (PLAN.md §10b). Highest value per line of code in the whole project.
- Sky comparison: screenshot the Earth view against an all-sky photograph at matched
  exposure. Orion, the Big Dipper and the Southern Cross should be identifiable.
- Test on at least one low-end laptop and one high-DPI display.

**Done when:** every criterion is measured and recorded, pass or fail.

---

## T9 — The verdict

The kill gate. Give it a real session, not a glance.

Look at it on a good screen in a dark room and answer honestly:

- Does the sky from Earth look *right* — not merely plausible?
- Is flying through it compelling, or is it a spreadsheet in 3D?
- Do the colours read as beautiful at the physically accurate setting, or does it only
  work exaggerated? (Either answer is fine. Knowing which is the point.)
- Is 625,679 stars visibly sparse? If so, does that argue for more stars — or for
  better rendering of the ones already there?

Then decide: **proceed to Step 2, iterate on Step 1, or rethink.**

Write the answer down, with screenshots. Step 2 through Step 6 are weeks of pipeline
work whose entire justification is that this step said yes.

---

## Things that will be tempting and should be resisted

- Adding more stars because it looks sparse. Sparseness at this size is usually a
  *rendering* problem — exposure, bloom, sprite kernel — not a data one. Fix the
  render first; you can always add stars later, and Step 4 will add 500× more.
- Building the octree early because the tile format seems obviously needed. It is
  needed — in Step 2, designed against a renderer that exists. See STEPS.md, "Notes
  on sequencing".
- Reaching for Three.js when raw WebGL2 gets awkward. It will get awkward. The HDR
  pipeline and custom vertex formats are exactly what a scene graph makes harder.
- Treating the exposure and disc-transition work as Sun-specific. They are general
  consequences of free flight; the Sun is just where you notice them first.
- Polishing the UI. Nobody is judging chrome at this step; they are judging stars.
