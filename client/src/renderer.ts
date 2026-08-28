/** Two-pass HDR star renderer. See PLAN.md §6. */

import { createHdrTarget, link, uniforms } from "./gl";
import { multiply, perspective, viewFromYawPitch, type Mat4 } from "./mat4";
import {
  STAR_FRAGMENT,
  STAR_VERTEX,
  TONEMAP_FRAGMENT,
  TONEMAP_VERTEX,
} from "./shaders";
import type { Stars } from "./format";

export interface CameraState {
  /** Position in galactic cartesian parsecs. float64 on the CPU; only the
   *  camera-relative difference is ever handed to the GPU (PLAN.md §6.3). */
  position: [number, number, number];
  yaw: number;
  pitch: number;
  fovYRadians: number;
}

export interface RenderSettings {
  exposure: number;
  saturation: number;
  minSizePx: number;
  maxSizePx: number;
  /** Pixels of sprite radius per e-fold of flux. Controls how much bigger a
   *  bright star looks than a faint one. */
  sizeGain: number;
  /** Point-spread width in pixels. A property of the optics, identical for
   *  every star; only amplitude varies. */
  sigmaPx: number;
  /** Show the sky as observed from Earth rather than intrinsic brightness.
   *  Only meaningful with the camera at Sol. */
  earthView: boolean;
}

const STAR_UNIFORMS = [
  "uViewProjection", "uCameraHi", "uCameraLo", "uExposure", "uMagMin", "uMagSpan",
  "uMagLevels", "uMinSizePx", "uMaxSizePx", "uSizeGain", "uSigmaPx", "uEarthView",
  "uPalette",
] as const;

export class Renderer {
  private readonly gl: WebGL2RenderingContext;
  private readonly starProgram: WebGLProgram;
  private readonly tonemapProgram: WebGLProgram;
  private readonly starUniforms: Record<string, WebGLUniformLocation | null>;
  private readonly tonemapUniforms: Record<string, WebGLUniformLocation | null>;
  private readonly vao: WebGLVertexArrayObject;
  private readonly emptyVao: WebGLVertexArrayObject;
  private readonly palette: WebGLTexture;
  private readonly count: number;
  private readonly magMin: number;
  private readonly magSpan: number;
  private readonly magLevels: number;

  private hdr: { framebuffer: WebGLFramebuffer; texture: WebGLTexture };
  private width = 0;
  private height = 0;

  constructor(gl: WebGL2RenderingContext, stars: Stars, width: number, height: number) {
    this.gl = gl;
    this.count = stars.count;

    const mag = stars.manifest.layout.packed_uint32.magnitude;
    this.magMin = mag.min;
    this.magSpan = mag.max - mag.min;
    this.magLevels = (1 << mag.bits) - 1;

    this.starProgram = link(gl, STAR_VERTEX, STAR_FRAGMENT);
    this.tonemapProgram = link(gl, TONEMAP_VERTEX, TONEMAP_FRAGMENT);
    this.starUniforms = uniforms(gl, this.starProgram, STAR_UNIFORMS);
    this.tonemapUniforms = uniforms(gl, this.tonemapProgram, ["uHdr", "uSaturation"]);

    // Positions and packed attributes go up as two buffers. The file interleaves
    // them; splitting once at load costs nothing and keeps the vertex layout
    // trivial. Step 2's tile format revisits this.
    const vao = gl.createVertexArray();
    if (!vao) throw new Error("createVertexArray failed");
    this.vao = vao;
    gl.bindVertexArray(vao);

    const positionBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, stars.positions, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);

    const packed = new Uint32Array(stars.count);
    for (let i = 0; i < stars.count; i++) {
      // Rebuild the packed word from the decoded fields so the GPU sees exactly
      // the layout the shader expects, independent of file interleaving.
      const magQ = Math.round(
        ((stars.absoluteMagnitude[i]! - this.magMin) / this.magSpan) * this.magLevels,
      );
      packed[i] = (magQ << 20) | (stars.colourIndex[i]! << 12) | (stars.flags[i]! << 4);
    }
    const packedBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, packedBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, packed, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(1);
    gl.vertexAttribIPointer(1, 1, gl.UNSIGNED_INT, 0, 0);

    const apparentBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, apparentBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, stars.apparentMagnitude, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(2);
    gl.vertexAttribPointer(2, 1, gl.FLOAT, false, 0, 0);

    gl.bindVertexArray(null);

    const emptyVao = gl.createVertexArray();
    if (!emptyVao) throw new Error("createVertexArray failed");
    this.emptyVao = emptyVao;

    // Palette as a 256x1 float texture. Values exceed 1.0 at both ends of the
    // Planckian locus, so it cannot be an 8-bit texture.
    const palette = gl.createTexture();
    if (!palette) throw new Error("createTexture failed");
    this.palette = palette;
    gl.bindTexture(gl.TEXTURE_2D, palette);
    const rgba = new Float32Array(stars.manifest.colour_lut.size * 4);
    for (let i = 0; i < stars.manifest.colour_lut.size; i++) {
      rgba[i * 4] = stars.palette[i * 3]!;
      rgba[i * 4 + 1] = stars.palette[i * 3 + 1]!;
      rgba[i * 4 + 2] = stars.palette[i * 3 + 2]!;
      rgba[i * 4 + 3] = 1;
    }
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA16F, stars.manifest.colour_lut.size, 1, 0,
      gl.RGBA, gl.FLOAT, rgba);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);

    this.hdr = createHdrTarget(gl, width, height);
    this.width = width;
    this.height = height;
  }

  resize(width: number, height: number): void {
    if (width === this.width && height === this.height) return;
    const gl = this.gl;
    gl.deleteFramebuffer(this.hdr.framebuffer);
    gl.deleteTexture(this.hdr.texture);
    this.hdr = createHdrTarget(gl, width, height);
    this.width = width;
    this.height = height;
  }

  render(camera: CameraState, settings: RenderSettings): void {
    const gl = this.gl;
    const aspect = this.width / Math.max(this.height, 1);

    // Near/far are generous: with camera-relative positions the depth buffer is
    // unused (stars never occlude each other), so precision here does not matter.
    const projection = perspective(camera.fovYRadians, aspect, 1e-6, 1e9);
    const view = viewFromYawPitch(camera.yaw, camera.pitch);
    const viewProjection: Mat4 = multiply(projection, view);

    // --- pass 1: accumulate flux -------------------------------------------
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.hdr.framebuffer);
    gl.viewport(0, 0, this.width, this.height);
    gl.clearColor(0, 0, 0, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);

    // Additive, because overlapping stars must sum. This is what turns a crowd
    // of unresolved stars into glow rather than a scatter of dots (PLAN.md §5.2).
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE);
    gl.disable(gl.DEPTH_TEST);

    gl.useProgram(this.starProgram);
    gl.uniformMatrix4fv(this.starUniforms["uViewProjection"]!, false, viewProjection);
    // Split in float64 on the CPU, which is the only place that precision
    // exists. Math.fround gives the float32 the GPU will actually see, so the
    // remainder is exactly what the shader needs to add back.
    const hi = camera.position.map((v) => Math.fround(v)) as [number, number, number];
    gl.uniform3f(this.starUniforms["uCameraHi"]!, hi[0], hi[1], hi[2]);
    gl.uniform3f(
      this.starUniforms["uCameraLo"]!,
      Math.fround(camera.position[0] - hi[0]),
      Math.fround(camera.position[1] - hi[1]),
      Math.fround(camera.position[2] - hi[2]),
    );
    gl.uniform1f(this.starUniforms["uExposure"]!, settings.exposure);
    gl.uniform1f(this.starUniforms["uMagMin"]!, this.magMin);
    gl.uniform1f(this.starUniforms["uMagSpan"]!, this.magSpan);
    gl.uniform1f(this.starUniforms["uMagLevels"]!, this.magLevels);
    gl.uniform1f(this.starUniforms["uMinSizePx"]!, settings.minSizePx);
    gl.uniform1f(this.starUniforms["uMaxSizePx"]!, settings.maxSizePx);
    gl.uniform1f(this.starUniforms["uSizeGain"]!, settings.sizeGain);
    gl.uniform1f(this.starUniforms["uSigmaPx"]!, settings.sigmaPx);
    gl.uniform1f(this.starUniforms["uEarthView"]!, settings.earthView ? 1 : 0);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.palette);
    gl.uniform1i(this.starUniforms["uPalette"]!, 0);

    gl.bindVertexArray(this.vao);
    gl.drawArrays(gl.POINTS, 0, this.count);
    gl.bindVertexArray(null);

    // --- pass 2: tonemap to the canvas -------------------------------------
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, this.width, this.height);
    gl.disable(gl.BLEND);

    gl.useProgram(this.tonemapProgram);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.hdr.texture);
    gl.uniform1i(this.tonemapUniforms["uHdr"]!, 0);
    gl.uniform1f(this.tonemapUniforms["uSaturation"]!, settings.saturation);

    gl.bindVertexArray(this.emptyVao);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.bindVertexArray(null);
  }
}
