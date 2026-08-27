"""Measure how much the Hertzsprung-Russell structure actually buys us.

The record stores (colour index, absolute magnitude) -- which ARE the two axes of an
HR diagram. Stars do not populate that plane uniformly: they pile onto the main
sequence, the giant branch and the white dwarf sequence. This script measures the
real joint entropy of the quantised (colour, magnitude) pair, to decide whether a
shared vector-quantisation codebook is worth the complexity over storing the two
fields independently.

Input: a CSV chunk from the Gaia TAP query in PLAN.md section 9.
"""
import csv, math, sys, collections

path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/c4.csv"
CBITS, MBITS = 8, 12                       # as specified in PLAN.md section 4.4
MMIN, MMAX = -10.0, 20.0                   # absolute G magnitude range
CMIN, CMAX = -1.0, 6.0                     # bp_rp range

pairs = []
with open(path) as f:
    for r in csv.DictReader(f):
        try:
            plx, g, bp_rp = float(r["parallax"]), float(r["phot_g_mean_mag"]), float(r["bp_rp"])
        except (ValueError, KeyError):
            continue
        if plx <= 0:
            continue
        M = g + 5.0 * math.log10(plx) - 10.0           # absolute G magnitude
        if not (MMIN <= M <= MMAX and CMIN <= bp_rp <= CMAX):
            continue
        ci = min((1 << CBITS) - 1, int((bp_rp - CMIN) / (CMAX - CMIN) * (1 << CBITS)))
        mi = min((1 << MBITS) - 1, int((M - MMIN) / (MMAX - MMIN) * (1 << MBITS)))
        pairs.append((ci, mi))

n = len(pairs)
if not n:
    sys.exit(f"no usable rows in {path}")

def entropy(counter):
    return -sum((c / n) * math.log2(c / n) for c in counter.values())

Hc = entropy(collections.Counter(c for c, _ in pairs))
Hm = entropy(collections.Counter(m for _, m in pairs))
Hj = entropy(collections.Counter(pairs))
occupied = len(collections.Counter(pairs))

print(f"sample: {n:,} stars from {path}")
print(f"\nallocated:            {CBITS + MBITS} bits  (colour {CBITS} + magnitude {MBITS})")
print(f"marginal entropy:     {Hc:.2f} + {Hm:.2f} = {Hc + Hm:.2f} bits")
print(f"JOINT entropy:        {Hj:.2f} bits")
print(f"mutual information:   {Hc + Hm - Hj:.2f} bits  (colour<->magnitude correlation)")
print(f"occupied cells:       {occupied:,} of {(1 << CBITS) * (1 << MBITS):,} "
      f"({occupied / ((1 << CBITS) * (1 << MBITS)) * 100:.1f}%)")
print(f"\nheadline: {CBITS + MBITS} allocated bits carry {Hj:.2f} bits of real information")
print(f"          -> ceiling for an HR codebook: {(CBITS + MBITS - Hj) / 8:.2f} bytes/star saved")
print(f"          -> at 320.5M stars that is {(CBITS + MBITS - Hj) / 8 * 320.5e6 / 1e6:.0f} MB")

# --- undersampling check -------------------------------------------------
# Plug-in entropy is biased LOW when samples/cell is small. Re-estimate on
# nested subsamples: if H still climbs with n, the full-sample number is a
# floor, not the answer.
print("\nconvergence check (plug-in entropy is biased low when undersampled):")
print(f"{'n':>10} {'stars/cell':>11} {'H_joint':>9} {'Miller-Madow':>13}")
for frac in (0.125, 0.25, 0.5, 1.0):
    k = int(n * frac)
    sub = pairs[:k]
    cnt = collections.Counter(sub)
    occ = len(cnt)
    h = -sum((c / k) * math.log2(c / k) for c in cnt.values())
    mm = h + (occ - 1) / (2 * k * math.log(2))
    print(f"{k:>10,} {k / occ:>11.1f} {h:>9.2f} {mm:>13.2f}")
