> **ARCHIVED (13 November 2026):** This documents the previously working experimental Vantage 3D renderer. It is **not** the active wallpaper plan. The product now uses short recorded Minecraft videos in Lively with no persistent Minecraft renderer/server. See [VIDEO-WALLPAPER-PLAN.md](VIDEO-WALLPAPER-PLAN.md). Retained only for engineering reference and rollback.

---

# Wallpaper rendering layers: independent of surface selection

## Boundary contract

Shader preview, saved-mob rendering and horizon haze are **viewer-side effects**. They consume Vantage's normal tile/mesh output, native lighting data, the camera and an optional saved-entity snapshot; none knows how surface blocks were selected.

| Effect | Data consumed | Surface-agnostic integration |
| --- | --- | --- |
| Shader preview | Real block UVs, world normals, native baked sky/block light and AO | GPU-only uniforms in upstream Three.js terrain/water shaders |
| Important mobs | Saved NBT entity positions, named/tamed flags, public model descriptions, local client JAR skins | Separate Three.js scene group at exact world coordinates |
| Haze | Camera/streaming radius and sky/fog palette | Identical GPU fog transfer function for high-detail, water, and low-detail materials |

Nothing in these effects reads surface floors, cave thresholds, chunk meshing flags or terrain generator internals. The native source chunk reader, tile protocol, surface-ribbon mesher and cache remain unchanged.

## Shader preview

The look panel offers **Vanilla**, **Cinematic** and **Misty** presets plus live sun azimuth, strength, warmth and haze curve controls. The shader retains Vantage's Minecraft model textures, native block/sky light and baked AO. Directional sun-relief shading is a first visual pass: **true real-time cast shadows and volumetric lighting are not implemented**. That later shadow layer will need its own conservative caster/receiver visibility inputs and performance gates. It will not require swapping the terrain selection method.

## Important saved mobs

The world-side scanner reuses the existing read-only Anvil entity reader and ranks up to 24 model-supported mobs near the selected camera, favouring tamed and named creatures. Genuine public versioned entity model descriptions and **local** Minecraft JAR textures are passed to the independent original model-geometry adapter, now placed into the native Vantage Three.js scene.

Mobs are saved snapshots, with stable positions but no active entity AI/animation yet. If a matching real model or PNG is missing, the browser reports the absence instead of inventing cube substitutes. UUID and owner IDs never enter the locally served scene. The native server remains bound to loopback; no extra service or save upload.

## Distant haze

Haze now has an adjustable near onset and soft transfer curve. It follows the renderer's actual current view radius, with consistent fog on native terrain, water and low-resolution rings. Near geometry remains crisp and the horizon colour matches the sky; this is not an excuse to synthesize unsaved chunks.

## Tests and future shot compiler

CI includes TypeScript typechecks, Zig native meshing, Windows/Linux native packaging, browser smoke and Python model selection/privacy tests. Windows/Lively visual checks using the actual private world still require local acceptance.

The future shot compiler has a separate producer contract: camera paths + sun positions + selected important entities -> a conservative union of directly visible tiles, shadow casters/receivers, cave-mouth interiors, silhouettes and reflective context. Any replacement of the current surface-only mesher must leave these preview modules untouched.
