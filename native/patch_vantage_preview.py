#!/usr/bin/env python3
"""Wallpaper rendering additions to pinned upstream Vantage v0.15.1.

The surface/visibility mesher and tile protocol are deliberately untouched.
Only the existing GPU material settings, the demo viewer extension points and
an external model overlay are modified. A mismatched upstream source fails
closed instead of partially applying a patch.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def once(text: str, before: str, after: str, label: str) -> str:
    count = text.count(before)
    if count != 1:
        raise ValueError(f"{label}: expected exactly one upstream anchor, found {count}")
    return text.replace(before, after)


def patch_materials(text: str) -> str:
    text = once(text,
        "  uniform float uFogDensity; // atmospheric haze amount (1 = full, 0 = clear)",
        """  uniform float uFogDensity; // atmospheric haze amount (1 = full, 0 = clear)
  uniform float uMwwHazeStart; // fraction of visible radius where fog begins
  uniform float uMwwHazeCurve; // transfer curve, independent of surface mesh
  uniform float uMwwSunStrength; // directional relief, real baked AO is preserved
  uniform float uMwwSunWarmth; // sun tint, not artificial procedural terrain""",
        "terrain fragment uniforms")
    text = once(text,
        "    vec3 shade = mix(vec3(1.0), hemi, 0.16) * fshade;\n    vec3 lit = grade(base * shade * ao * lightAmt * lightCol * uExposure);",
        """    vec3 shade = mix(vec3(1.0), hemi, 0.16) * fshade;
    // Directional material preview layered OVER the faithful baked light/AO.
    // This improves depth without incorrectly claiming occlusion or cast shadows.
    float sunFacing = max(dot(N, normalize(lightDir)), 0.0);
    float sunRelief = mix(1.0, 0.78 + 0.40 * sunFacing, uMwwSunStrength);
    vec3 warmSun = mix(vec3(1.0), vec3(1.04, 0.98, 0.88), uMwwSunWarmth);
    vec3 lit = grade(base * shade * sunRelief * warmSun * ao * lightAmt * lightCol * uExposure);""",
        "terrain direction shader")
    # The original uses the same smoothstep twice (terrain + lowres), with an
    # extra water variable. Reuse identical haze logic across both GPU passes.
    old = "smoothstep(uFog.x, uFog.y, vFog) * uFogDensity"
    new = "pow(smoothstep(mix(uFog.x, uFog.y, uMwwHazeStart), uFog.y, vFog), uMwwHazeCurve) * uFogDensity"
    if text.count(old) != 3:
        raise ValueError("Expected water/terrain/lowres haze sites in pinned materials.ts")
    text = text.replace(old, new)
    text = once(text,
        "      uFogDensity: { value: 1.0 }, // atmospheric haze amount (1 = full)",
        """      uFogDensity: { value: 1.0 }, // atmospheric haze amount (1 = full)
      uMwwHazeStart: { value: 0.12 },
      uMwwHazeCurve: { value: 0.85 },
      uMwwSunStrength: { value: 0.42 },
      uMwwSunWarmth: { value: 0.22 },""",
        "terrain shader defaults")
    text = once(text,
        "      uFogDensity: t['uFogDensity']!,",
        """      uFogDensity: t['uFogDensity']!,
      uMwwHazeStart: t['uMwwHazeStart']!,
      uMwwHazeCurve: t['uMwwHazeCurve']!,""",
        "lowres shader shared haze uniforms")
    # The lowres fragment must declare the two new fields; unlike the terrain
    # shader it has a separate GLSL program.
    low_start = text.index("export function createLowresMaterial(")
    prefix, low = text[:low_start], text[low_start:]
    low = once(low, "      uniform float uFogDensity;", """      uniform float uFogDensity;
      uniform float uMwwHazeStart;
      uniform float uMwwHazeCurve;""", "lowres fragment uniform declarations")
    return prefix + low


def patch_viewer(text: str) -> str:
    text = once(text,
        "  fog?: number;\n  /** Super-/sub-sampling",
        """  fog?: number;
  /** Start of distance haze as fraction of the native streaming fog interval. */
  hazeStart?: number;
  /** Falloff exponent (lower = more atmospheric depth). */
  hazeCurve?: number;
  /** Sun-facing diffuse relief strength over native baked lighting (0..1). */
  sunStrength?: number;
  /** Warm sunlight tint (0..1). */
  sunWarmth?: number;
  /** Sun direction in degrees. Independent of terrain/cave selection. */
  sunAzimuth?: number;
  /** Super-/sub-sampling""",
        "viewer display interface")
    text = once(text,
        "  fog: 1,\n  renderScale: 1,",
        """  fog: 1,
  hazeStart: 0.12,
  hazeCurve: 0.85,
  sunStrength: 0.42,
  sunWarmth: 0.22,
  sunAzimuth: 36,
  renderScale: 1,""",
        "vanilla display defaults")
    text = once(text,
        "    this.shader.uniforms['uFogDensity']!.value = d.fog;",
        """    this.shader.uniforms['uFogDensity']!.value = d.fog;
    this.shader.uniforms['uMwwHazeStart']!.value = THREE.MathUtils.clamp(d.hazeStart, 0, 0.85);
    this.shader.uniforms['uMwwHazeCurve']!.value = THREE.MathUtils.clamp(d.hazeCurve, 0.3, 3);
    this.shader.uniforms['uMwwSunStrength']!.value = THREE.MathUtils.clamp(d.sunStrength, 0, 1);
    this.shader.uniforms['uMwwSunWarmth']!.value = THREE.MathUtils.clamp(d.sunWarmth, 0, 1);
    const az = THREE.MathUtils.degToRad(d.sunAzimuth);
    (this.shader.uniforms['lightDir']!.value as THREE.Vector3).set(
      Math.cos(az) * 0.7, 1.0, Math.sin(az) * 0.7).normalize();""",
        "viewer shader live controls")
    return text


def patch_demo(text: str) -> str:
    text = once(text,
        "import type { ViewMode } from '../src/react/index.js';",
        """import type { ViewMode } from '../src/react/index.js';
import { MwwMobLayer, MwwPreviewPanel } from './mww-preview.js';""",
        "demo imports")
    text = once(text,
        "  return (\n    <VantageViewer ref={ref} {...source} view={view}>",
        """  const wallpaper = new URLSearchParams(location.search).get('wallpaper') === '1';
  return (
    <VantageViewer ref={ref} {...source} view={view}>""",
        "demo app component")
    text = once(text,
        """      <Hud />
      <Reticle />
      <PlayerList />
      <DimensionPicker />
      <BiomeLayer legend hover defaultEnabled={biomeOpen} />
      <LightPanel />
      <SettingsPanel />
      <MapNav />
      <DepthSlider />""",
        """      <MwwMobLayer />
      <MwwPreviewPanel wallpaper={wallpaper} />
      {!wallpaper && <>
        <Hud />
        <Reticle />
        <PlayerList />
        <DimensionPicker />
        <BiomeLayer legend hover defaultEnabled={biomeOpen} />
        <LightPanel />
        <SettingsPanel />
        <MapNav />
        <DepthSlider />
      </>}""",
        "demo canvas composition")
    return text


def patch_model_adapter(source: str) -> str:
    # Reuse the existing, tested entity model baking code verbatim; adapt only
    # its global-browser wrapper into an internal Vite ESM module.
    source = once(source,
        "(() => {\n  'use strict';",
        """// @ts-nocheck — pinned shared legacy Minecraft model-baking adapter.
export const createMwwEntityGeometry = (() => {
  'use strict';""",
        "legacy model wrapper")
    source = once(source,
        "  window.MWW_ENTITY_MODELS={create};\n})();",
        """  return create;
})();""",
        "legacy model export")
    return source


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("upstream", type=Path)
    args = parser.parse_args()
    upstream = args.upstream
    source_root = Path(__file__).resolve().parents[1]
    materials = upstream / "web/src/three/materials.ts"
    viewer = upstream / "web/src/three/viewer.ts"
    demo = upstream / "web/demo/main.tsx"
    outputs = [
        (materials, patch_materials(materials.read_text(encoding="utf-8"))),
        (viewer, patch_viewer(viewer.read_text(encoding="utf-8"))),
        (demo, patch_demo(demo.read_text(encoding="utf-8"))),
        (upstream / "web/demo/mww-models.ts",
         patch_model_adapter((source_root / "web/entity-models.js").read_text(encoding="utf-8"))),
        (upstream / "web/demo/mww-preview.tsx",
         (source_root / "native/mww-preview.tsx").read_text(encoding="utf-8")),
    ]
    for dest, content in outputs:
        dest.write_text(content, encoding="utf-8")
    print("Built shader/haze UI and independent real saved-mob scene overlay on pinned Vantage viewer")


if __name__ == "__main__":
    main()
