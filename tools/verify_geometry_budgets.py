import math
print("=== 1. Per-tile quantisation: error in SCREEN PIXELS ===")
print("In an octree LOD, a node is refined when its projected extent exceeds P px,")
print("so quantisation error in px = P / 2^b  regardless of distance or scale.\n")
print(f"{'bits/axis':>9} {'bytes/pos':>9} | " + " | ".join(f"P={p}px" for p in (200,400,800,1600)))
for b in (8,10,11,12,14,16):
    row=" | ".join(f"{p/2**b:7.3f}px" for p in (200,400,800,1600))
    print(f"{b:>9} {3*b/8:>9.2f} | {row}")

print("\n=== 2. Same thing expressed as physical/angular error ===")
print("Tile edge L, b bits/axis -> resolution L/2^b. Angular error seen from Earth at distance D.\n")
ROOT=32768.0  # pc, cube edge covering the whole Milky Way disc with margin
for lvl in (0,4,8,10,12,14,16):
    L=ROOT/2**lvl
    for b in (10,12,16):
        res=L/2**b
        print(f"  level {lvl:2d}  edge {L:9.3f} pc  b={b:2d}  res {res:10.5f} pc = {res*206265:9.1f} AU", end="")
        # angular error if such a tile sits at distance = 4x its own edge (typical viewing)
        for D in (L*4,):
            print(f"   ang@{D:.0f}pc {math.degrees(res/D)*3600:8.2f}\"")
print()

print("=== 3. Storage tiers (verified Gaia DR3 counts) ===")
tiers=[
 ("T0 showcase: d<100pc complete + all G<6.5",     630_000),
 ("T1 near:     plx>2 mas & poe>3 (d<500pc)",   35_423_727),
 ("T2 local:    plx>1 mas & poe>3 (d<1kpc)",    98_753_042),
 ("T3 full:     poe>3  (all sky)  <-- CHOSEN", 320_489_271),
 ("T4 extended: poe>2  (all sky)",             478_659_978),
 ("   (poe>1, for reference)",                 763_609_100),
 ("   (every parallax, BJ distances)",       1_467_744_818),
]
for name,n in tiers:
    for bpp,label in ((6,"6 B/star"),(8,"8 B/star")):
        pass
    print(f"  {name:44s} {n:>13,} stars   6B: {n*6/1e6:9.1f} MB   8B: {n*8/1e6:9.1f} MB   +ids(2.5B): {n*2.5/1e6:8.1f} MB")

print("\n=== 4. Octree shape for T3 (320.5M stars, 8k pts/node target) ===")
N=320_489_271; PTS=8_000
leaves=N/PTS
print(f"  leaf nodes needed ~ {leaves:,.0f}")
print(f"  a full octree with that many leaves is ~depth {math.log(leaves)/math.log(8):.1f} if uniformly filled")
print("  (real sky is very non-uniform: Galactic plane / bulge tiles go far deeper than poles)")
tot_nodes=leaves*8/7
print(f"  total nodes incl. inner ~ {tot_nodes:,.0f}   -> avg pack payload {N*6/tot_nodes/1024:.1f} KiB/node")
print(f"  R2 free tier is 10M Class B ops/mo: at 1 GET/node a single full flythrough")
print(f"  touching all {tot_nodes:,.0f} nodes = {tot_nodes/10e6*100:.2f}% of the monthly free op budget")

print("\n=== 5. Brightness dynamic range ===")
print("  absolute G magnitude range in Gaia ~ -10 (supergiants) to +20 (faint M dwarfs)")
print(f"  = flux ratio 10^(30/2.5) = 10^{30/2.5:.0f}  -> HDR accumulation is mandatory, not optional")
for bits in (8,10,12):
    print(f"  {bits}-bit linear mag over 30 mag span -> {30/2**bits:.4f} mag/step "
          f"({(10**(0.4*30/2**bits)-1)*100:.2f}% flux step)")
