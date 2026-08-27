"""Dynamic range and the point->disc transition under free flight.

Neither is Sun-specific: a free camera can sit anywhere relative to any star, so both
apply generally. The Sun is simply the instance you are guaranteed to hit first, and
the only star whose values are known well enough to calibrate the pipeline against.

Three questions:
  1. How bright does the Sun look from various distances? (calibration reference)
  2. At what distance does a star stop being a point sprite and become a disc?
  3. What dynamic range does free flight require, and does it fit rgba16float?
"""
import math

PC_M    = 3.0856775814913673e16
AU_M    = 1.495978707e11
RSUN_M  = 6.957e8
SIGMA   = 5.670374419e-8
M_G_SUN = 4.67                 # absolute Gaia G magnitude (Casagrande & VandenBerg 2018)
FOV_DEG, WIDTH_PX = 60.0, 1920
px_rad = math.radians(FOV_DEG) / WIDTH_PX
px_sr  = px_rad ** 2

def apparent(M, d_pc):
    return M + 5.0 * math.log10(d_pc / 10.0)

print("=== 1. The Sun's apparent magnitude with distance (calibration reference) ===")
for label, d_pc in [("1 AU (Earth)", AU_M / PC_M), ("100 AU", 100 * AU_M / PC_M),
                    ("0.1 pc", 0.1), ("1 pc", 1.0), ("4.85 pc (nearest stars)", 4.85),
                    ("10 pc", 10.0), ("100 pc", 100.0)]:
    print(f"  {label:24s} m_G = {apparent(M_G_SUN, d_pc):+8.2f}")
print("  naked-eye limit is m ~ +6.5: the Sun disappears from view beyond ~50 pc")

print("\n=== 2. Point sprite -> resolved disc threshold ===")
print(f"  at {FOV_DEG:.0f} deg FOV over {WIDTH_PX} px: {px_rad:.3e} rad/pixel")
print(f"  a star of radius R subtends >1 px when d < 2R / {px_rad:.3e}\n")
for name, r_rsun in [("Proxima Cen", 0.15), ("Sun", 1.0), ("Sirius A", 1.71),
                     ("Betelgeuse", 764.0), ("UY Scuti", 1700.0)]:
    d_pc = (2 * r_rsun * RSUN_M / px_rad) / PC_M
    print(f"  {name:14s} R={r_rsun:7.2f} Rsun -> resolved within "
          f"{d_pc:10.3e} pc = {d_pc * PC_M / AU_M:9.1f} AU")

print("\n=== 3. Dynamic range required by free flight ===")
print("  Surface brightness B = sigma*T^4/pi is INDEPENDENT of distance:")
print("    F = L/(4 pi d^2),  Omega = pi R^2/d^2  ->  B = F/Omega = sigma T^4 / pi")
print("  So peak per-pixel radiance is bounded by TEMPERATURE alone -- which is the")
print("  only reason the range is bounded at all.\n")
print(f"  pixel solid angle: {px_sr:.3e} sr\n")
print(f"  {'star':16} {'T (K)':>8} {'W/m2 per pixel at surface':>27}")
for name, T in [("M dwarf", 3000), ("Sun", 5772), ("Sirius A", 9940),
                ("hot B star", 20000), ("O star", 50000)]:
    print(f"  {name:16} {T:>8} {SIGMA * T ** 4 / math.pi * px_sr:>27.3e}")

F16_RANGE = 65504.0 / 5.96e-8                 # incl. subnormals
bright = SIGMA * 50000 ** 4 / math.pi * px_sr # hottest star's surface, one pixel
faint  = 2.518e-8 * 10 ** (-0.4 * 20)         # a star at m = +20, one pixel
need   = bright / faint
print(f"\n  brightest possible pixel (O star surface): {bright:.3e} W/m2")
print(f"  faintest star we want visible (m = +20):   {faint:.3e} W/m2")
print(f"  REQUIRED DYNAMIC RANGE: 10^{math.log10(need):.1f}")
print(f"  rgba16float provides:   10^{math.log10(F16_RANGE):.1f}"
      f"  -> short by 10^{math.log10(need) - math.log10(F16_RANGE):.1f}")
print("\n  -> flux MUST be scaled by a per-frame exposure scalar BEFORE accumulation.")
print("     That range spans all camera positions; any ONE frame spans far less,")
print("     which is exactly what a per-frame exposure scalar exploits. Anything")
print("     below the exposure floor vanishes -- correct, since you cannot see")
print("     stars in daylight either.")
