/** GLSL for the two-pass HDR star pipeline. See PLAN.md §6.1–6.3. */

/**
 * Pass 1 — deposit each star's exposure-scaled flux into the HDR buffer.
 *
 * Three things here are load-bearing and easy to get subtly wrong:
 *
 * **Camera-relative positions.** The subtraction happens before anything else,
 * so the rest of the pipeline works in small numbers near the origin where
 * float32 has precision to spare (PLAN.md §6.3).
 *
 * **Exposure multiplies here, before the additive blend, not in the tonemap.**
 * Free flight spans 10^20 in apparent brightness and float16 holds 10^12, so
 * the scaling has to happen before accumulation or the buffer saturates or
 * underflows (PLAN.md §6.1).
 *
 * **Flux is conserved across sprite size.** The kernel is normalised by its own
 * area, so making a star's sprite bigger spreads its light rather than adding
 * any. That is what lets sprite size vary with brightness without lying about
 * how much light a star emits (PLAN.md §6.2).
 */
export const STAR_VERTEX = /* glsl */ `#version 300 es
precision highp float;

layout(location = 0) in vec3 aPositionParsec;   // galactic cartesian, absolute
layout(location = 1) in uint aPacked;           // mag | colour | flags

uniform mat4 uViewProjection;
// The camera position is split into two float32s. A single one is not enough:
// at 100 pc its ulp is 1.6 AU, so camera motion finer than that vanishes in the
// subtract and the view stalls then jumps. (starPos - hi) cancels the shared
// magnitude exactly, and subtracting lo restores the fine offset.
uniform vec3 uCameraHi;
uniform vec3 uCameraLo;
uniform float uExposure;
uniform float uMagMin;
uniform float uMagSpan;
uniform float uMagLevels;
uniform float uMinSizePx;
uniform float uMaxSizePx;
uniform float uSizeGain;

out float vFlux;      // total light this sprite must deposit
out vec3 vColour;     // linear sRGB, unit luminance
out float vSizePx;

uniform sampler2D uPalette;

void main() {
  // Camera-relative first: everything downstream stays near the origin.
  vec3 rel = (aPositionParsec - uCameraHi) - uCameraLo;
  float distancePc = length(rel);

  uint magQ = (aPacked >> 20) & 0xFFFu;
  uint colourIndex = (aPacked >> 12) & 0xFFu;

  float absMag = uMagMin + (float(magQ) / uMagLevels) * uMagSpan;

  // Luminosity from absolute magnitude, then inverse square. This is the whole
  // reason the catalogue stores the intrinsic value: apparent brightness is a
  // property of where the camera is, recomputed every frame (PLAN.md §4.3).
  float luminosity = pow(10.0, -0.4 * absMag);
  float flux = luminosity / max(distancePc * distancePc, 1e-12);

  vFlux = flux * uExposure;

  // Sprite size grows with brightness, logarithmically -- which is linear in
  // magnitude, the scale brightness actually lives on. A power law does not
  // work here: over the ~20 decades of flux free flight spans, any exponent
  // small enough to keep faint stars at one pixel leaves bright ones there too.
  //
  // Flux stays conserved because the fragment kernel divides by its own area,
  // so a larger sprite spreads the same light rather than adding any. What the
  // extra area buys is that a bright star saturates a visibly larger core once
  // tonemapped, which is how brightness reads on a screen with 8 bits of output
  // and 20 decades of input.
  vSizePx = clamp(uMinSizePx + uSizeGain * log(1.0 + vFlux), uMinSizePx, uMaxSizePx);

  vColour = texelFetch(uPalette, ivec2(int(colourIndex), 0), 0).rgb;

  gl_Position = uViewProjection * vec4(rel, 1.0);
  gl_PointSize = vSizePx;
}
`;

export const STAR_FRAGMENT = /* glsl */ `#version 300 es
precision highp float;

in float vFlux;
in vec3 vColour;
in float vSizePx;

uniform float uSigmaPx;

out vec4 fragColour;

const float PI = 3.14159265359;

void main() {
  // The point-spread function is a property of the optics, not of the star, so
  // sigma is FIXED and only the amplitude varies. That is what makes a bright
  // star read as an intense point with a halo rather than a large soft blob:
  // its core saturates while the Gaussian wings stay above the visible
  // threshold further out.
  //
  // Sprite size still grows with brightness (see the vertex shader) but only to
  // give those wings room -- it does not widen the star.
  //
  // The kernel is normalised by its own area, so the integral is 1 and the star
  // deposits exactly vFlux however many pixels it covers (PLAN.md 6.2).
  vec2 d = (gl_PointCoord - 0.5) * vSizePx;
  float r2 = dot(d, d);
  float kernel = exp(-r2 / (2.0 * uSigmaPx * uSigmaPx))
               / (2.0 * PI * uSigmaPx * uSigmaPx);

  fragColour = vec4(vColour * vFlux * kernel, 1.0);
}
`;

/**
 * Pass 2 — tonemap the accumulated flux into something a display can show.
 *
 * `1 - exp(-L)` because it is monotonic, saturates gracefully, and never clips
 * hard: a star a thousand times brighter than another still reads as brighter
 * rather than both landing on pure white.
 */
export const TONEMAP_VERTEX = /* glsl */ `#version 300 es
precision highp float;
out vec2 vUv;
void main() {
  // Fullscreen triangle from gl_VertexID -- no buffer needed.
  vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
  vUv = p;
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}
`;

export const TONEMAP_FRAGMENT = /* glsl */ `#version 300 es
precision highp float;

in vec2 vUv;
uniform sampler2D uHdr;
uniform float uSaturation;
out vec4 fragColour;

void main() {
  vec3 hdr = max(texture(uHdr, vUv).rgb, 0.0);

  // Real stellar colours are almost white -- the Sun sits at CIELAB C* 6.4.
  // Exaggeration is a user choice with a physically honest default of 1.0,
  // never something baked into the data (PLAN.md §4.2).
  float luma = dot(hdr, vec3(0.2126, 0.7152, 0.0722));
  hdr = mix(vec3(luma), hdr, uSaturation);

  vec3 mapped = vec3(1.0) - exp(-max(hdr, 0.0));
  fragColour = vec4(pow(mapped, vec3(1.0 / 2.2)), 1.0);  // gamma encode
}
`;
