// Stage-3 hot loop: quantise -> Morton -> sort -> pack -> flux-summing LOD merge.
use rayon::prelude::*;
use std::time::Instant;

#[inline(always)]
fn split3(mut x: u64) -> u64 {
    x &= 0x1fffff;
    x = (x | (x << 32)) & 0x001f_0000_0000_ffff;
    x = (x | (x << 16)) & 0x001f_0000_ff00_00ff;
    x = (x | (x << 8))  & 0x100f_00f0_0f00_f00f;
    x = (x | (x << 4))  & 0x10c3_0c30_c30c_30c3;
    x = (x | (x << 2))  & 0x1249_2492_4924_9249;
    x
}
#[inline(always)]
fn morton(x: u64, y: u64, z: u64) -> u64 { split3(x) | (split3(y) << 1) | (split3(z) << 2) }

fn main() {
    let n: usize = std::env::args().nth(1).and_then(|s| s.parse().ok()).unwrap_or(20_000_000);

    // deterministic pseudo-random input (xorshift), same generator as the Python side
    let t = Instant::now();
    let mut xs = vec![0f32; n]; let mut ys = vec![0f32; n]; let mut zs = vec![0f32; n];
    let mut mags = vec![0f32; n]; let mut cols = vec![0u8; n];
    let mut s: u64 = 0x243F6A8885A308D3;
    for i in 0..n {
        for v in [0u8; 5] { let _ = v; }
        s ^= s << 13; s ^= s >> 7; s ^= s << 17; xs[i] = (s >> 11) as f32 / (1u64 << 53) as f32;
        s ^= s << 13; s ^= s >> 7; s ^= s << 17; ys[i] = (s >> 11) as f32 / (1u64 << 53) as f32;
        s ^= s << 13; s ^= s >> 7; s ^= s << 17; zs[i] = (s >> 11) as f32 / (1u64 << 53) as f32;
        s ^= s << 13; s ^= s >> 7; s ^= s << 17; mags[i] = (s >> 11) as f32 / (1u64 << 53) as f32 * 30.0 - 10.0;
        s ^= s << 13; s ^= s >> 7; s ^= s << 17; cols[i] = (s >> 56) as u8;
    }
    eprintln!("  [gen {:?}]", t.elapsed());

    // 1. quantise + morton
    let t = Instant::now();
    let keys: Vec<u64> = (0..n).into_par_iter().map(|i| {
        let qx = (xs[i] * 2097151.0) as u64; // 21 bits for the sort key
        let qy = (ys[i] * 2097151.0) as u64;
        let qz = (zs[i] * 2097151.0) as u64;
        morton(qx, qy, qz)
    }).collect();
    let t_morton = t.elapsed();

    // 2. sort by morton (indices, so payload follows)
    let t = Instant::now();
    let mut idx: Vec<u32> = (0..n as u32).collect();
    idx.par_sort_unstable_by_key(|&i| keys[i as usize]);
    let t_sort = t.elapsed();

    // 3. pack the 8-byte record: 36 bits pos (12/axis) | 12 mag | 8 colour | 8 flags
    let t = Instant::now();
    let packed: Vec<u64> = idx.par_iter().map(|&i| {
        let i = i as usize;
        let qx = (xs[i] * 4095.0) as u64;
        let qy = (ys[i] * 4095.0) as u64;
        let qz = (zs[i] * 4095.0) as u64;
        let qm = (((mags[i] + 10.0) / 30.0) * 4095.0) as u64;
        (qx << 52) | (qy << 40) | (qz << 28) | (qm << 16) | ((cols[i] as u64) << 8)
    }).collect();
    let t_pack = t.elapsed();

    // 4. flux-summing LOD merge: group by morton prefix, sum flux, flux-weighted colour
    let t = Instant::now();
    let shift = 42u64; // keep top 21 bits -> ~2M cells for 20M stars, ~10 per cell
    // parallel: chunk the sorted index, reduce each chunk, then stitch boundary runs
    let chunks: Vec<Vec<(u64, f64, f64)>> = idx.par_chunks(1 << 16).map(|ch| {
        let mut out: Vec<(u64, f64, f64)> = Vec::new();
        let mut run_key = keys[ch[0] as usize] >> shift;
        let (mut acc_f, mut acc_c) = (0f64, 0f64);
        for &i in ch {
            let i = i as usize;
            let k = keys[i] >> shift;
            if k != run_key { out.push((run_key, acc_f, acc_c)); acc_f = 0.0; acc_c = 0.0; run_key = k; }
            let f = 10f64.powf(-0.4 * mags[i] as f64);
            acc_f += f; acc_c += f * cols[i] as f64;
        }
        out.push((run_key, acc_f, acc_c));
        out
    }).collect();
    let mut out_flux: Vec<f64> = Vec::with_capacity(n / 8);
    let mut out_col:  Vec<f64> = Vec::with_capacity(n / 8);
    let (mut cur, mut acc_f, mut acc_c) = (u64::MAX, 0f64, 0f64);
    for ch in &chunks { for &(k, f, c) in ch {
        if k != cur { if cur != u64::MAX { out_flux.push(acc_f); out_col.push(acc_c / acc_f.max(1e-30)); }
                      cur = k; acc_f = 0.0; acc_c = 0.0; }
        acc_f += f; acc_c += c;
    }}
    out_flux.push(acc_f); out_col.push(acc_c / acc_f.max(1e-30));
    let t_merge = t.elapsed();

    println!("RUST n={}", n);
    println!("  quantise+morton  {:>8.3} s", t_morton.as_secs_f64());
    println!("  sort             {:>8.3} s", t_sort.as_secs_f64());
    println!("  pack             {:>8.3} s", t_pack.as_secs_f64());
    println!("  flux merge       {:>8.3} s", t_merge.as_secs_f64());
    println!("  TOTAL            {:>8.3} s", (t_morton+t_sort+t_pack+t_merge).as_secs_f64());
    println!("  (checksum {} {} {:.3})", packed.len(), out_flux.len(), out_flux[0]);
}
