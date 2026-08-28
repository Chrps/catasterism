/**
 * Camera and flight controls.
 *
 * The hard part is not the controls, it is **scale**. Usable motion spans ~1 AU
 * to ~100 pc in this tier alone, a factor of 10^7, and 6x10^9 in the full
 * product. No fixed speed works: fast enough to cross interstellar space makes
 * approaching a star impossible, slow enough to approach a star leaves the
 * nearest neighbour hours away. See PLAN.md §6.7.
 *
 * The answer here is `dr/dt = k * r`, with `r` the distance to the nearest star.
 * Three properties follow, and together they are why one control covers the
 * whole range:
 *
 *  * **Travel time depends only on the log of the distance ratio.** The Sun's
 *    surface to Proxima and Proxima to the edge of T0 differ by a factor of 80
 *    in distance but only 3x in time.
 *  * **It is continuous.** No gear changes, so nothing to feel.
 *  * **It self-adjusts on approach.** Fly at a star and speed falls off with
 *    the gap, which is what makes arriving possible without touching a control.
 */

import { basis } from "./mat4";

const PC_PER_AU = 1 / 206264.806;
const LY_PER_PC = 3.261563;

/** Floor on the speed scale: about 2 AU. Without it, sitting exactly on a star
 *  puts the nearest distance at zero and the camera can never leave. */
const NEAREST_FLOOR_PC = 1e-5;
/** Ceiling, so speed stays sane in genuinely empty space. */
const NEAREST_CEILING_PC = 500;

/** Frames between full nearest-star scans. A scan is a brute-force pass over
 *  every star -- exact, ~2 ms, and cheap enough at this rate. Step 2's octree
 *  turns it into a real query. */
const SCAN_INTERVAL_FRAMES = 4;

export type Mode = "planetarium" | "flight";

export interface NearestStar {
  index: number;
  distancePc: number;
}

/** How many of the brightest stars to track when setting auto-exposure.
 *  Using the single brightest lets one freak object -- a heavily de-reddened
 *  star, or whichever one you happen to be flying at -- dictate the whole sky.
 *  Taking the Nth brightest is robust to that at no real cost. */
const BRIGHT_RANK = 48;

export class Camera {
  /** float64 throughout. Only the camera-relative difference reaches the GPU,
   *  which is what keeps float32 adequate at galactic scale (PLAN.md §6.3). */
  position: [number, number, number] = [0, 0, 0];
  yaw = 0;
  pitch = 0;
  fovYRadians = (60 * Math.PI) / 180;
  mode: Mode = "planetarium";

  /** Multiplier on the speed law. 3/s puts the Sun's surface about 5 seconds
   *  from the edge of T0. Adjustable in flight, because the right value is a
   *  matter of feel and nobody can pick it from arithmetic. */
  speedGain = 3;

  /** Held-boost multiplier. The exponential law is excellent at arriving
   *  somewhere and deliberately unhurried at leaving, so a temporary multiplier
   *  covers "get me across this gap now" without compromising the approach. */
  boostFactor = 6;
  boosting = false;

  nearest: NearestStar = { index: -1, distancePc: NEAREST_FLOOR_PC };

  /** Apparent flux of the BRIGHT_RANK-th brightest star from here, in the same
   *  units the shader uses. Drives auto-exposure. */
  brightFlux = 1;

  private frame = 0;
  private smoothedNearestPc = NEAREST_FLOOR_PC;
  private readonly positions: Float32Array;
  private readonly luminosity: Float32Array;
  private readonly count: number;
  private readonly top = new Float64Array(BRIGHT_RANK);

  constructor(positions: Float32Array, absoluteMagnitude: Float32Array, count: number) {
    this.positions = positions;
    this.count = count;
    // Precomputed once: the scan runs several times a second over every star,
    // and a pow() inside that loop would be the whole cost.
    this.luminosity = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      this.luminosity[i] = 10 ** (-0.4 * absoluteMagnitude[i]!);
    }
  }

  /** Distance from the Sun, which sits at the origin. */
  get distanceFromSolPc(): number {
    const [x, y, z] = this.position;
    return Math.hypot(x, y, z);
  }

  /** Metres per second is meaningless here; this is parsecs per second. */
  get speedPcPerSecond(): number {
    return this.speedGain * this.smoothedNearestPc * (this.boosting ? this.boostFactor : 1);
  }

  /**
   * One pass over every star, producing both the nearest neighbour (for speed)
   * and the bright tail (for exposure). Doing them together matters: the loop
   * is the expensive part and the second result is nearly free.
   */
  private scan(): void {
    const [cx, cy, cz] = this.position;
    const p = this.positions;
    const lum = this.luminosity;
    const top = this.top;
    top.fill(0);
    let cutoff = 0; // smallest flux currently in the top list
    let best = Infinity;
    let bestIndex = -1;

    for (let i = 0; i < this.count; i++) {
      const dx = p[i * 3]! - cx;
      const dy = p[i * 3 + 1]! - cy;
      const dz = p[i * 3 + 2]! - cz;
      const d2 = dx * dx + dy * dy + dz * dz;
      if (d2 < best) {
        best = d2;
        bestIndex = i;
      }
      const flux = lum[i]! / Math.max(d2, 1e-12);
      if (flux > cutoff) {
        // Insertion into a 48-slot descending list. The test above fails for
        // almost every star, so this costs nothing in the common case.
        let j = BRIGHT_RANK - 1;
        while (j > 0 && top[j - 1]! < flux) {
          top[j] = top[j - 1]!;
          j--;
        }
        top[j] = flux;
        cutoff = top[BRIGHT_RANK - 1]!;
      }
    }

    this.nearest = { index: bestIndex, distancePc: Math.sqrt(best) };
    this.brightFlux = Math.max(top[BRIGHT_RANK - 1]!, 1e-30);
  }

  /**
   * @param move  local-space direction, components in [-1, 1]:
   *              x right, y up, z forward.
   * @param dt    seconds since the previous frame.
   */
  update(move: [number, number, number], dt: number): void {
    if (this.frame % SCAN_INTERVAL_FRAMES === 0) this.scan();
    this.frame++;

    const clamped = Math.min(
      Math.max(this.nearest.distancePc, NEAREST_FLOOR_PC),
      NEAREST_CEILING_PC,
    );
    // Smooth in log space: the quantity spans decades, so a linear filter would
    // be dominated by whichever end it happened to start from.
    const blend = 1 - Math.exp(-dt * 6);
    this.smoothedNearestPc = Math.exp(
      Math.log(this.smoothedNearestPc) +
        (Math.log(clamped) - Math.log(this.smoothedNearestPc)) * blend,
    );

    if (this.mode === "planetarium") return;

    const [mx, my, mz] = move;
    if (mx === 0 && my === 0 && mz === 0) return;

    const step = this.speedPcPerSecond * dt;
    // Same basis the view matrix uses, so movement matches what is on screen.
    const { right, up, forward } = basis(this.yaw, this.pitch);
    for (let i = 0; i < 3; i++) {
      this.position[i] = this.position[i]! + (forward[i]! * mz + right[i]! * mx + up[i]! * my) * step;
    }
  }

  look(deltaX: number, deltaY: number, sensitivity = 0.0022): void {
    this.yaw -= deltaX * sensitivity;
    const limit = Math.PI / 2 - 0.001;
    this.pitch = Math.max(-limit, Math.min(limit, this.pitch - deltaY * sensitivity));
  }

  returnHome(): void {
    this.position = [0, 0, 0];
    this.mode = "planetarium";
  }
}

/**
 * Distance in whichever unit a human would actually use at that scale.
 *
 * AU inside the solar system, light years out to the nearby stars because that
 * is the unit people have a feel for, parsecs beyond ~30 pc because that is
 * where the catalogue's own unit takes over and light-year counts stop meaning
 * anything.
 */
export function formatDistance(parsecs: number): string {
  if (!Number.isFinite(parsecs)) return "—";
  const au = parsecs / PC_PER_AU;
  if (au < 1000) return `${au.toFixed(au < 10 ? 2 : 0)} AU`;
  const ly = parsecs * LY_PER_PC;
  if (ly < 100) return `${ly.toFixed(ly < 10 ? 2 : 1)} ly`;
  if (parsecs < 1000) return `${parsecs.toFixed(parsecs < 100 ? 1 : 0)} pc`;
  return `${(parsecs / 1000).toFixed(2)} kpc`;
}
