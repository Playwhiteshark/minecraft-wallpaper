# Engineering rules — Minecraft Living World Wallpaper

## 1. REUSE EXISTING MAINTAINED CODE FIRST (highest priority)

Before implementing a parser, renderer, model resolver, mesher, asset packer, tile streamer, world scanner, or UI subsystem, **find and evaluate existing maintained libraries and applications that already solve it**. Prefer importing, wrapping, or adapting an existing implementation over writing a replacement. Only write custom code for glue, genuinely unsupported requirements, or when demonstrated integration/size/runtime/license overhead clearly outweighs reuse. Record the upstream candidate, why it was chosen or rejected, the pinned version, its license, and the boundary to our code. Never reinvent a complicated Minecraft subsystem solely to avoid a small build-time dependency.

Treat runtime and build-time overhead separately. A one-time native converter or build tool is acceptable; avoid an always-running Minecraft client/server, unnecessary daemon, whole desktop app, or renderer duplication. Do not claim "zero dependency" as a quality metric if accuracy and completeness suffer.

## 2. PROVE THE WHOLE REAL PRODUCT, NOT A TOY PIPELINE

Success means **real save → discovered saved world/chunks → actual geometry/texture → loadable multi-chunk scene → final 3D renderer → Lively desktop**. A synthetic success, HTML mock-up, texture-less boxes, or 24-block floating island is *not* the product. Verify the actual Lively path after automated checks. Distinguish known verified stages, untested integration, and visual acceptance explicitly.

## 3. STICK TO SCOPE AND PRODUCT TRUTH

The user postponed 8-block sampled terrain/LOD and cosmetic shaders. Keep this experiment disabled and do not describe it as surroundings. Prioritise complete basic functionality and modular boundaries; shaders, pet highlight rings, performance optimizations and fancy visual effects follow. A camera's view must use actual saved chunks and preserve real coordinates; unexplored world remains missing rather than fabricated.

## 4. FULL COVERAGE DOES NOT MEAN FULL PREBAKE OR GPU RESIDENCY

Normal wallpaper operation must use the existing Vantage `live` pipeline: index accessible real generated chunks, bake only camera-requested tiles, retain disk cache, let upstream Three.js stream a memory-bounded relevant set. Do **not** make a complete offline export a prerequisite. Do not force `--caves full` for outdoor wallpaper scenes; use native hidden-cave culling by default, and preserve optional deep-cave support without fabricating coarse geography. A successful HTTP page or an empty tile manifest is **not** proof of successful world rendering. Always include native converter logs for zero-tile failures and verify a genuine tile request.

**Surface rendering is a separate requirement from cave culling.** Vantage's `--caves` flag removes unlit cave faces but still emits full-height sunlit stone walls at exposed chunk edges. Normal Overworld wallpaper mode must keep only genuine surface-facing geometry and a shallow, terrain-aware skirt (currently `--surface-depth 16`); source 3D blocks stay available for true lighting and occlusion, without fabricating bottom faces. Reuse the native Vantage mesher rather than replacing it, and prove both (a) adjacent saved chunks contribute real mesh and (b) deep-wall vertex count falls in surface mode. Compact Minecraft 26.3 palettes include lower-case `id/properties`, TAG_String, and empty-key compound IDs. Never mistake successful conversion or a nonzero global vertex count for complete coverage around the actual camera. Use the read-only chunk coverage diagnostic before blaming unsaved terrain on decoding.

### Wallpaper effects must never depend on the surface-selection method

Shader/material previews (including sunlight appearance), camera-distance haze and important saved-mob rendering are **independent renderer/scene layers**. They may consume a tile's real normals, native lighting/AO, world coordinates, camera and selected entity snapshot, but may **not** read surface-depth, cave selection flags, mesh preparer internals, or fabricate terrain to make an effect work. Future shot-aware visibility/shadow selection must be replaceable behind the existing tile producer interface without rewriting effects. Saved mobs use real local client JAR textures and versioned vanilla geometry descriptions; missing assets must warn and stay missing, never render made-up substitutes. A directional shader preview is not evidence of true cast shadows; name the limitation explicitly until actual shadow-caster tests pass. See docs/WALLPAPER-RENDER-LAYERS.md.

**Native renderer lifecycle:** Vantage runs as a detached loopback process only because Lively Wallpaper needs to survive the control panel closing. A normal preview must be stopped on window close unless the user explicitly enables persistent Lively mode. Upgrading the pinned engine must never strand a listener on port 8787. Recover detached/old processes only by verifying actual TCP ownership, the executable under this app's private `engines/vantage-*` directory, loopback host, exact requested port and a native cache under this app's `full-world` directory. NEVER kill based on port, process name, page contents or an unverified PID. If process termination fails, preserve the ownership record; don't claim success. Test on both Windows and Linux.

## 5. MODULE OWNERSHIP AND SAFE UPDATES

Keep world reading/conversion, resource packs/materials, scene package/manifest, camera/config, renderer adapter, Lively host, and optional mobs independently replaceable. Never commit user save data, coordinates, identity keys, Mojang assets, or personal operational/agent notes. Leave private coordination in personal-ops. Don't alter source worlds. Keep last-good output; run automated cross-platform + browser tests and minimise manual acceptance asks.

## Why these rules exist

Prior versions repeatedly invented Minecraft NBT/heightmap and geometry code despite mature alternatives; reported that an 8-block sampled disconnected grey sheet counted as 128-block landscape; confused a small WebGL prototype with end-to-end validation; and added many special-case patches instead of replacing the wrong abstraction. These are recorded here as general software lessons, not hidden project instructions or personal information.
