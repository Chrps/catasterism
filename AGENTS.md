# Catasterism

A browser flight-sim through the Gaia DR3 catalogue: 320 million stars you can
fly around, hosted as static files with no backend.

**Read [PLAN.md](PLAN.md) before making design decisions.** Every number in it
was measured against the live ESA archive or the relevant host, not recalled,
and several obvious-seeming ideas are already ruled out there with evidence.
[STEPS.md](STEPS.md) is the execution order; [TASKS_STEP_1.md](TASKS_STEP_1.md)
is what we are doing now.

## Environment

All agent work is expected to run inside the dev container in
`.devcontainer/` — an isolated sandbox with only this repository mounted, no
host filesystem access, and no elevated privileges. Because the blast radius is
limited to this repo, Claude Code is normally run there with permission prompts
disabled:

```bash
./.devcontainer/run.sh claude
```

That starts Claude Code in **auto** permission mode; `.claude/settings.json`
sets the same default for the VS Code extension, which is installed *into* the
container (a devcontainer gets its own extension host and does not inherit the
host's extensions).

Do not add mounts pointing outside this repository, and do not add credentials
to the container image or to tracked files. Secrets belong in a gitignored
`.env`.

## Layout

```
pipeline/     Python (package `catasterism`). Offline bake:
              Gaia TAP -> clean/derive -> octree -> tiles.
              Never ships. Runs on a laptop or in CI.
client/       TypeScript + Bun + raw WebGL2. The only thing a visitor loads.
tools/        Verification scripts backing the numbers in PLAN.md. Keep runnable.
```

## Conventions that actually matter

**Python for the pipeline, TypeScript for the client. No 3D framework.**
Both were decided by measurement, not taste — see PLAN.md §12.5 and the
benchmarks in `tools/lang-benchmark/`. Raw WebGL2 because packed vertex formats,
pre-accumulation exposure and camera-relative transforms all cut against a scene
graph. Reaching for Three.js when WebGL2 gets awkward is the wrong instinct; it
will get awkward, and that is the part a scene graph makes harder.

**No Gaia release name outside `catasterism.release`.** Gaia DR4 lands
2026-12-02, so this pipeline runs at least twice and the second run must not be a
rewrite. Table names, the reference epoch (it moves every release) and column
mappings all live in that one module. `pipeline/tests/test_release.py` enforces
this — it is a real test, not a note.

**`source_id` is not stable across Gaia releases.** ESA treats source lists as
independent between releases. Anything persisted — ids, bookmarks, links — must
be release-tagged via `Release.tag_id()`.

**Store intrinsic properties, never apparent ones.** Absolute magnitude, not
apparent; de-reddened colour, not observed. Apparent brightness is a fact about
standing on Earth and is wrong the moment the camera moves. The one exception is
the planetarium layer, which stores raw observed values precisely because it is
anchored at Earth — and is therefore exact.

**Subtract extinction (`A_G`) when deriving absolute magnitude.** Skipping it
bakes Earth's dust column into a star's intrinsic luminosity permanently. 13.9%
of stars are dimmed by more than 2.5×. This is the silent error; nothing looks
broken.

**Flux is conserved, everywhere.** LOD merging sums flux rather than
subsampling, because dense regions must glow — that is what the Milky Way *is*.
A parent node's total flux equals the sum of its children's, and this is
asserted, not assumed. Break it and brightness pops on every LOD swap.

## Traps

- **Adding more stars because it looks sparse.** *Inside the complete volume*
  this is a rendering problem — exposure, bloom, sprite kernel — not a data one.
  Fix the render. But check which volume you are in first: T0 is complete only
  inside 100 pc; beyond that it holds nothing fainter than G = 8, so it really
  is sparse out there and no exposure setting fixes it. That is what Step 2's
  tiers are for.
- **Confusing "naked-eye" with "rendered".** Everything in a tier is rendered;
  exposure decides what is *visible*, not what exists. Only 1.9% of T0 is
  naked-eye visible and 67% is fainter than G = 15. Faint stars are never
  dropped — LOD merges them into glow with flux conserved.
- **Treating exposure and the point→disc transition as Sun-specific.** They are
  general consequences of free flight; the Sun is just where you notice first.
- **Building the tile format before the renderer exists.** Deliberately deferred
  to Step 2 so it can be designed with evidence. Step 1 uses a flat file.
- **Git LFS.** Never. Its free tier is 1 GB/month of bandwidth; tiles go to R2.
- **Anything that earns money.** Gaia data is CC BY-NC 3.0 IGO. No ads, no paid
  tier, no sponsorship — ESA requires written permission first, and "indirectly
  generates a financial gain" is broad. See ATTRIBUTION.md.

## Running things

```bash
cd pipeline && python -m pytest -q     # includes the DR4-readiness invariant
cd client   && bun run typecheck       # strict TS, no emit
cd client   && bun run build           # -> client/dist, what Pages serves
python3 tools/verify_*.py              # re-derive PLAN.md's tables
```

Work goes on a branch and lands via pull request; never push to `main`.
