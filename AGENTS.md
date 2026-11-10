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

## 5. MODULE OWNERSHIP AND SAFE UPDATES

Keep world reading/conversion, resource packs/materials, scene package/manifest, camera/config, renderer adapter, Lively host, and optional mobs independently replaceable. Never commit user save data, coordinates, identity keys, Mojang assets, or personal operational/agent notes. Leave private coordination in personal-ops. Don't alter source worlds. Keep last-good output; run automated cross-platform + browser tests and minimise manual acceptance asks.

## Why these rules exist

Prior versions repeatedly invented Minecraft NBT/heightmap and geometry code despite mature alternatives; reported that an 8-block sampled disconnected grey sheet counted as 128-block landscape; confused a small WebGL prototype with end-to-end validation; and added many special-case patches instead of replacing the wrong abstraction. These are recorded here as general software lessons, not hidden project instructions or personal information.
