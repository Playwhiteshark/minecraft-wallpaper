# Existing software, technical research and build-vs-integrate decision

**Reviewed:** 2026-11-09. **Research status:** source-checked candidates, not yet benchmarked or installed for this project. Read [product specification](PRODUCT-SPEC.md) for binding requirements.

## Summary

There is **no reason to build another full Minecraft world reader or general-purpose 3D map engine before testing existing ones**. BlueMap, Vantage and Worldlens already cover real-world-save ingestion and varying forms of 3D presentation. Minecraft-as-wallpaper mods cover genuine live Minecraft visuals but fail the zero-running-game constraint. Lively already exists as the desktop wallpaper host. The proposed novelty is **curated cinematic presentation, base-size framing, important mob fidelity, safe automatic incremental refresh, POIs and low always-on cost**.

**Default experiment:** test **BlueMap** and **Vantage** directly on a safe snapshot of a small real-world region and determine which supplies the best geometry and shortest integration path. If either already does the full job with minimal configuration and existing add-ons, **prefer integration/configuration to writing a standalone rendering engine**.

## Comparison matrix

| Candidate | Already available | Potential benefit | Constraints/unverified | Role |
| --- | --- | --- | --- | --- |
| [BlueMap](https://github.com/BlueMap-Minecraft/BlueMap) | Real world-save -> browser-viewable surface 3D geometry; dedicated standalone CLI; web 3D viewer | Mature offline source extraction; possible incremental rendering | Cinematic light and pet support not guaranteed; web resources/server/scene cropping to test | Leading 3D geometry foundation |
| [Vantage](https://vantage.beacon-mc.io/) / [source](https://github.com/thoughts-on-things/vantage-mc) | Native world converter, browser 3D view, static outputs, LOD, flight/lighting controls | Fast world-to-map workflow and potentially very compact geometry | Published FPS/render-time numbers are *marketing claims*, not measured wallpaper results; static serverless Lively embed and mobs unverified | Competing / possibly faster foundation |
| [Worldlens](https://github.com/Ding-Ding-Projects/worldlens) | Local offline world renderer and Electron 3D viewer based on BlueMap, with a working render/update workflow | Existing Windows-oriented integration and reference architecture | Heavy general map desktop app; backend uses upstream Java for working local rendering, packaging/renderer footprint not measured | Reference or potential integration |
| [BlueMapEntities](https://github.com/BlueMap-Minecraft/BlueMapEntities) | Addon for rendering static entity models with BlueMap updates | Key possible answer to pet fidelity | Requires validating offline operation and **specific vanilla mob types/variants**; README's 'all vanilla mobs' is broader than evidence for our target species | Entity experiment |
| [MinePaperEngine](https://modrinth.com/mod/ocmh3Jqh) | Turns live Minecraft into wallpaper | Real Minecraft lighting, camera and actual mob animation | Keeps the client/game running; docs explicitly say wallpaper mode does not pause game | Rejected as primary architecture |
| [Dynamic Kabegami](https://www.curseforge.com/minecraft/mc-mods/dynamic-kabegami) | Fabric mod making a running Minecraft session a Windows wallpaper | Native, authentic game visuals | Also still runs Minecraft | Rejected as primary architecture |
| [Chunky](https://github.com/chunky-dev/chunky) | Standalone offline path-traced render of Minecraft saves, command-line scene rendering | Beautiful still frames, high-quality reference images | Not an interactive fast 3D view; cannot render all entities; can be memory/CPU intensive while rendering | Optional quality benchmark / still fallback |
| [Replay Mod](https://www.replaymod.com/docs/) | Camera-path keyframes and video export from game recordings | Authentic animated pets, cinematic camera motions and shaders during episodic capture | Requires in-game capture/replay and export; does not automatically reconstruct new world state into existing footage | Optional cinematic video path |
| [Lively Wallpaper](https://github.com/lively-community/lively) | Already installed host: HTML/WebGL, video, playback/pause management and static fallback | No new wallpaper-hosting application needed | Local web asset behaviour and existing user customization require testing | Fixed display host |

**Links above are primary developer/project pages where available.** Verify concrete builds, licensing and current compatibility before importing code or bundling dependencies.

## Detailed observations

### BlueMap

BlueMap documents standalone command-line use, independent of a running server. It reads world files, precomputes 3D geometry and displays the result in a browser. The standalone setup documents a Java 21+ prerequisite and separates command-line render from starting its built-in web server. See [official standalone installation guide](https://github.com/BlueMap-Minecraft/BlueMapWiki/blob/master/wiki/getting-started/Installation.md).

Potential use: the offline renderer feeds a **bounded region / base view**; Lively hosts a web scene or adapted viewer. Determine whether BlueMap itself supports the required region limit, incremental block changes and exposure of geometry in the simplest portable way, rather than assuming every feature exists in CLI mode.

Open visual questions: lighting realism, terrain/building textures, leaves, glass, chests/block entities, caves and view angles suited to wallpaper composition. An all-world terrain map is not enough.

### Vantage

Its [public site](https://vantage.beacon-mc.io/) advertises a native Zig-backed converter, map as static output files, tile streaming, LOD, free flight and daytime/nighttime lighting controls. It also advertises very fast render and viewer performance. These are **vendor claims until verified**; they are not our measured results, particularly not Lively power use. It specifically supports user-supplied player models via JSON, not documented faithful support for happy ghasts, horses, cats or dogs.

Potential use: ingest the base's actual world-save geometry and display small static tiles in an adapted scene; add selected entity model overlays separately.

### Worldlens

The [repo](https://github.com/Ding-Ding-Projects/worldlens) describes an offline desktop application, a browser 3D scene, local world rendering and CLI/watch pathways. Its own documentation states that working local rendering uses upstream BlueMap Java as the operational fallback while an alternative renderer is still being validated. Do not treat its longer feature list as proof that a lightweight Lively wallpaper can be produced with no overhead. It may be more useful as a ready desktop map reference than as a dependency.

### Important pets and BlueMapEntities

There are five prominent currently selected entities: two **happy ghasts**, one **horse**, one **wolf/dog** and one **cat**.

The [BlueMapEntities source](https://github.com/BlueMap-Minecraft/BlueMapEntities) claims support for vanilla entities and variants and says entities are static, moving only on map updates. The project describes Fabric/NeoForge and server/plugin installation pathways; this is **not proof** that a standalone BlueMap CLI render automatically gets all entity data.

The [released entity model list](https://github.com/BlueMap-Minecraft/BlueMapEntities/releases) and version compatibility need to be checked on the specific release and game version, not inferred from its broad README. At this research point **no complete set of the five requested animal models is verified**. Preserve that uncertainty; one screenshot with a cat model is insufficient.

A possible solution is a separate tiny **entity-overlay** stage: read selected entity NBT and stable identifiers from a consistent save snapshot; resolve type, variant, location and orientation; render imported/supplied accurate models on top of extracted geometry, updating positions only after new saved-world data. Idle motion would be visually procedural and never invoke Minecraft simulation. The issue to test is fidelity of models (especially happy ghasts) rather than the feasibility of drawing generic moving shapes.

### Lively display and the video trade-off

[Lively performance documentation](https://github.com/lively-community/lively/wiki/Performance) describes pausing during fullscreen application use and configurable pause rules for other focused applications and battery. [Lively source](https://github.com/lively-community/lively) supports web wallpapers and videos. These features make an HTML/WebGL wallpaper viable *in principle*, but GPU/VRAM use of WebGL and any local server process must be tested on the actual PC.

A **pre-rendered video** is frequently simple to show and can be hardware-decoded, but an MP4 is fundamentally a flat image sequence and cannot recreate true geometry from mouse parallax. It must be re-rendered when the actual base changes; Replay Mod is a capture tool rather than a guaranteed unattended world-to-video pipeline. We should keep video as a quality/fidelity fallback instead of assuming it is the easiest *automated* option.

Some Lively installations include separate desktop wallpaper persistence customizations. **Do not reapply, replace or modify Lively DLLs as part of this project.** Verify static fallback and virtual-desktop switching only as compatibility checks.

### Geometry and the user's occlusion insight

The user explicitly prefers excluding irrelevant blocks **from the persistent scene data**, not merely avoiding drawing them every frame. The rigorous way to do this is:

1. Select POI/base radius or tightly curated bounds plus visually useful surroundings.
2. Decode only the selected chunks (or allow an existing renderer to do so), not the entire world by default.
3. Generate optimized surfaces/meshes that omit opaque internal faces. Preserve needed transparency, water, foliage and visible interiors.
4. Retain the **union of surfaces potentially visible through the permitted parallax/orbit camera envelope**, even if occluded at any one pose.
5. At runtime apply frustum culling, LOD and optional material batching/tile streaming; test whether further occlusion culling actually helps at small scene size.
6. Update only dirty sections and relevant moved entity overlays where compatible with converter output.

Strictly storing *only the currently visible faces* is incompatible with a camera that can reveal previously hidden sides; cull for the **possible view range**, not a single frame. It may be better to persist a few extra surfaces than continuously re-decode chunks for a 2-degree mouse movement.

## Specific experiments, ordered by risk

1. **Compatibility and baseline:** identify actual Minecraft Java data version, mods/resource packs, Lively version and world ownership; work only on a verified copy/snapshot. Document the tested versions.
2. **Native import:** compare BlueMap CLI and Vantage conversion on one same selected region, including interior/transparent/chest fidelity and true geometry/perspective. Do not render whole world by default.
3. **Pet proof:** show the two happy ghasts, horse, cat and wolf/dog in correct saved positions/models. Test BlueMapEntities if compatible; otherwise separate overlay. No hard dependency on an unverified addon.
4. **Lively proof:** package an interactive HTML scene and check whether all assets work locally without resident server; test parallax and pauses.
5. **Visual proof:** side-by-side real frames of live-3D approach vs one captured Replay Mod/shader video and Chunky reference. Evaluate lighting, sky, water, visible mobs and overall polish.
6. **Auto-refresh proof:** make one small saved block change and move one pet, close the world, run an incremental refresh, and show updated Lively scene automatically without data loss. Record elapsed time, changes detected and failure fallback.
7. **Performance proof:** measure idle/visible/foreground/fullscreen/battery CPU, GPU, VRAM/RAM and power. The converter is only allowed transiently on update; compare static video consumption and WebGL consumption separately.
8. **Ownership proof:** demonstrate source save remains untouched, stage cleanup on failure/cancel, and uninstall/upgrade preserves user-owned world data, cameras and selected POIs.

**Go/no-go:** If existing renderer + small local integration meets the acceptance scenario, do that. If it cannot display important pets or produce a sufficiently cinematic scene without huge cost, switch candidate or use a video mode, rather than shipping a feature that is aesthetically equivalent to a mediocre world map.

## Rejected assumptions / unknowns

- Unknown: BlueMap/Vantage are compatible with the user's exact version and saved modded blocks.
- Unknown: important saved mobs (particularly happy ghasts) are covered by an existing offline entity plugin.
- Unknown: plain Lively local web assets can load every format without a local HTTP server.
- Unknown: an accurate map renderer can achieve shader-level cinematic quality at a low wallpaper budget.
- Unknown: the best world-exit trigger that needs no always-running watcher or invasive Minecraft mod.
- Unknown: which actual GPU/power cost is acceptable to user; benchmark rather than invent numbers.
- Rejected: any design that runs the game behind the desktop all day.
- Rejected: whole-world renders as a default for a tiny base.
- Rejected: silent automatic writes to the user's Minecraft world or Lively installation.
- Rejected: writing our own full map renderer merely because the project has a new name.

*Research reflects documentation available as of 2026-11-09, not a completed technical evaluation or hardware benchmark.*


## Research update — 2026-11-09: lean reuse is feasible, avoid full applications

**Recommendation (conditional on testing):** Keep the standalone **minecraft-wallpaper** repository, but build only the custom wallpaper scene, world/POI selection, entity overlay and safe batch refresher. **Do not** reimplement a general Minecraft world reader/mesher, install full Worldlens or run Minecraft/Java/server continuously. Prefer a small existing conversion binary used only at refresh time and a bundled static Three.js Lively wallpaper at display time.

### Strongest reuse case: Vantage packages

Vantage explicitly publishes a split viewer architecture: a **zero-dependency tile decoder** `@thoughts-on-things/vantage-mc/core`, a **framework-agnostic Three.js renderer** `@thoughts-on-things/vantage-mc/three`, and optional React components. The documented API allows generating one textured tile, calling `buildTerrain()` on the parsed Vantage tile/texture data, and adding `terrain` and `water` directly to our own Three.js scene. A broader `TileManager` supports bounded tile residency, byte limits, distance-based priorities and cache eviction. This is **direct composability**, not merely code we could copy by reverse-engineering.

The viewer is documented as **render-on-demand**, drawing for camera/input/data changes plus about **10 fps when animated water/lava textures are visible**, rather than needing a constant high-FPS redraw loop. This is promising for parallax, but the actual Lively/browser process cost must be measured.

- [Vantage web package and vanilla JS API](https://github.com/thoughts-on-things/vantage-mc/blob/main/web/README.md)
- [Vantage memory-bounded streaming architecture](https://github.com/thoughts-on-things/vantage-mc/blob/main/docs/streaming.md)
- [Vantage source (MIT)](https://github.com/thoughts-on-things/vantage-mc)
- [Vantage CLI and single-binary usage](https://vantage.beacon-mc.io/)

Vantage is a **young and relatively little-used repository**; this is a strong architectural fit, *not* a claim of proven correctness or security. Pin a reviewed source commit, review the binary/build chain and use isolated CI builds rather than silently running unknown prebuilt downloads. We have **not measured the Windows CLI binary size**, scene assets or performance. The desktop wrapper, local server, React UI, multiplayer services, server plugins and developer toolchains are **not runtime dependencies we should adopt** unless proven necessary.

### BlueMap fallback: small CLI, possibly larger prerequisites

BlueMap v5.29's standalone CLI jar is approximately **7.3 MB** and its webapp zip approximately **1.5 MB** according to the published release file listing. Its GitHub release describes support for **Minecraft Java 1.13.2–26.3** for the CLI and identifies **Java 25** as its current release target; older wiki installation text still says Java 21. Therefore check actual installed JRE compatibility before using it; do **not** install another Java runtime solely on the assumption the jar itself is tiny.

BlueMap's actual output, world assets, Java runtime (if absent), and map database/tiles may dominate its footprint. Avoid a resident BlueMap webserver. BlueMap 5.29 improves changed-region detection and transactional map writes, but those updates alone are not a complete safe wallpaper refresh pipeline.

- [BlueMap v5.29 release and compatibility](https://github.com/BlueMap-Minecraft/BlueMap/releases/tag/v5.29)
- [BlueMap v5.29 CLI file-size listing](https://sourceforge.net/projects/bluemap.mirror/files/v5.29/) (third-party exact mirror, corroborated by GitHub's release listing)
- [BlueMap CLI docs](https://github.com/BlueMap-Minecraft/BlueMapWiki/blob/master/wiki/getting-started/Installation.md)

### Avoid Worldlens as a direct installed dependency

The Worldlens project publicly describes a roughly **692 MiB Windows installer** and working local rendering using a Java BlueMap process, with its independent TypeScript mesher not yet driving actual local product rendering. Its frontend architecture can still be studied selectively under MIT, but **do not install or package its Electron desktop app** for this narrow wallpaper need.

- [Worldlens project site](https://ding-ding-projects.github.io/worldlens/)
- [Worldlens source and licence](https://github.com/Ding-Ding-Projects/worldlens)

### Pets remain the important exception

BlueMapEntities' README broadly claims vanilla mob support and variants but does not establish the exact **two happy ghasts, horse, wolf/dog and cat** as a verified full offline CLI pipeline. A version-specific supported-model list can be narrower than the README. Nor does Vantage's existing *player models* demonstrate pet-model support. **Do not assume all five pets work without custom integration**. A small local entity NBT extractor + pinned model overlay remains the likely bespoke requirement, with faithful saved-state appearance and a few restrained visual-only idle effects.

### Licence and security constraints

BlueMap, Vantage, Worldlens and BlueMapEntities currently advertise **MIT** licences. Copying/deriving code is allowed with proper notices, but copying every source file or bundling entire packages is not operationally necessary. Reuse APIs or a small reviewed subset, then maintain attribution and a dependency inventory. **Minecraft assets are third-party IP**: preferably load/extract them from the user's existing Minecraft installation, do not commit or publicly distribute copied game textures/models without checking their terms.

The user's concern is not merely source file size: **count all runtime/development/download artifacts** (binary + Java/Node/Zig toolchains + Minecraft resource extraction + generated scene geometry + textures + two-scene atomic update staging + caches). Build-time toolchains should be confined to CI or disposable project build environments, rather than installed globally to run wallpaper updates.

### Practical storage and performance acceptance gate

Before setting numeric limits, measure Vantage static extraction on a bounded actual base region, both cold and changed-block refresh, and test direct local HTML loading in the user's existing Lively. A lightweight architecture should have **no resident Java, Node, Python server, Zig compiler, Electron wrapper, Minecraft game/client or world-mapping daemon**. The display may still use a Lively web-renderer subprocess; that is normal and must be measured, not described as zero cost. Prefer a single owned current scene plus a temporary next-scene staging copy; avoid indefinite old-scene archives. The Minecraft world remains untouched.

**Decision rule:** If a pinned Vantage converter and small Three.js wrapper meet visual, entity and performance requirements, use them. If it does not, test BlueMap CLI; only consider a new renderer after both prove inadequate. Preserve video as a high-quality alternative if it outperforms live geometry in subjective quality or running cost. No software installation or live-world mutation is authorised by this research.



## Visual and interior feasibility addendum — 2026-11-09

**Clarified product priority:** live Three.js/WebGL with shallow camera parallax and small interactions **first**, attractive **shader-quality appearance is mandatory**, and rendered video is contingency only. The intended look is the user's Minecraft save as shown with shaders, not an expectation that a Minecraft shaderpack can be copied directly into Three.js. Shaderpacks depend on Minecraft-specific render passes and shader loaders. A bespoke lightweight wallpaper look may use baked diffuse/indirect lighting and ambient occlusion, static shadows, ambient/daylight terms and selective tone mapping/atmosphere; avoid costly gameplay-specific effects, general path tracing, reflections and volumetric passes unless measured impact warrants them. Different dawn/day/night looks may need separately precomputed lighting presets and more disk. Soft/dynamic animal shadow approximations may still be useful.

**Why map tools might lose rooms:** Minecraft map pipelines can aggressively suppress dark/hidden cave geometry or optimise for top-down viewpoints. [BlueMap's cave-rendering explanation](https://bluemap.bluecolored.de/community/CaveRendering.html) describes removing cave surfaces based on sunlight/height conditions and possible dark rendered holes; [current map configuration](https://bluemap.bluecolored.de/wiki/configs/Maps.html) documents cave detection/removal and render masks. Even above-ground enclosed corridors may require extraction retaining their inward-facing surfaces, roof, ceiling, floor and furnishings. Confirm actual output with a camera **inside a closed test room**, not merely with the exterior map visible.

**Vantage has a useful but not yet proven option:** its official [site](https://vantage.beacon-mc.io/) documents `vantage render <save> --caves full` for cave-ready output, with a disk footprint trade-off. Test whether this also preserves the **interiors of human-made base structures**, including corridors and ceilings, at the user's saved camera level. It is not enough to show a sliced cave map with missing roof geometry; the wallpaper must allow ordinary contained indoor shots with intact walls and ceilings. If no candidate supports such extraction while staying bounded, change meshing mode for selected rooms rather than rendering the entire world.

**Lighting implementation path:** [Three.js MeshPhongMaterial.lightMap](https://threejs.org/docs/pages/MeshPhongMaterial.html) supports pre-baked illumination via a second UV set. Geometry converted from Vantage/BlueMap may not include suitable second UVs or per-block lightmap atlases, so confirm **asset/UV compatibility and preprocessing/storage cost** before promising baked GI. Alternative cheap approximations (per-vertex lighting, Minecraft saved light levels, vertex AO, fixed sunlight and tone mapping) may be more practical for Minecraft's blocky surfaces. Compare visually against a **same-shot shadered Minecraft reference** before deciding.

**Camera planning is different from world navigation:** plan future locations as *site → exterior/room/corridor/threshold zones → user-curated shots → safe transitions*. Camera envelopes and paths require the union of geometry visible along the path; this is more than exterior occlusion culling but much less than loading a whole world. Validate path clearance against stored block occupancy at refresh time; no runtime Minecraft collision engine, player AI or free roam is needed. Prefer fading between shots rather than squeezing a camera through blocked/narrow interiors. Details in the [product specification](PRODUCT-SPEC.md#future-location-and-camera-design--not-part-of-the-first-prototype).

**Feasibility gates:** (1) offline local-asset Lively load, (2) a small lit synthetic room proving inner surfaces, (3) one bounded real world scene with convincing shader-inspired light compared to a user-approved same-shot reference, (4) exact five pet models/locations, and (5) performance budget. Do not mistake a successful imported terrain map for a completed wallpaper.

## Current Minecraft compatibility review — 2026-11-09

This is a **technical compatibility record**, not an assertion that all modern Minecraft rendering is supported. Reference version: [Minecraft Java 26.3](https://www.minecraft.net/en-us/article/minecraft-java-edition-26-3), with [26.4 development snapshots](https://feedback.minecraft.net/hc/en-us/sections/360002267532-Snapshot-Information-and-Changelogs) noted separately.

| Area | Current v0.1 behaviour | Compatibility boundary |
| --- | --- | --- |
| World file paths | Both older `region/` and Java 26.1+ `dimensions/minecraft/<dimension>/region/`, plus `players/data/` and `singleplayer_uuid` | Custom mod dimensions are not selectable in the UI |
| Anvil chunk NBT | Reads selected modern `sections[].block_states` and 64-bit packed indices | Designed for Java 1.18+ only; rare LZ4, custom compression or oversized external chunks are not generally supported |
| Block palettes | Accepts pre-26.3 `Name`/`Properties` and Java 26.3 `id`/`properties` and shorthand/default-state palette variants; uses each chunk's own `DataVersion` | Minecraft **block** palettes retain their documented minimum **four bits per state**; do not confuse this with different biome palette packing |
| Entities | Bounded scan of saved entity region files, select named animal IDs and basic positions | Not authoritative models, variants, inventory, equipment, animation, or pinned instance tracking |
| 26.4 snapshot changes | Does not inspect chunk status or biome palettes for rendering | 26.4 changes to chunk `status` and biome resolution are not current blockers, but biome-dependent shading needs a separate future implementation |
| Materials | Minecraft-installed block PNGs when available, fallback colours and a basic opaque/alpha distinction | No full block-state model graph, per-quad UV/material pass, biome-specific colours, or Minecraft shaderpacks |
| Camera/lighting | One selected shot's orbit/parallax and simple procedural light | Proper indoor scenes require independent lighting and complete interior-facing geometry, then safe transitions between named shots |

**Architectural risk worth resolving before expanding features:** the minimal mesh encoder currently assumes six cube faces with a few shape variants and writes fixed-size face records to a tightly matched WebGL viewer. Simply adding more hardcoded block names will not achieve proper stairs, doors, foliage, glass, complex block entities or shader-style lighting. Real-world visual comparison should determine whether this backend remains a useful lightweight foundation or a replaceable scene-conversion adapter should use an existing model-aware renderer. Preserve the Lively/UI/scene-selection parts while changing only the conversion and scene-data format as needed. Do not build a second full Minecraft engine.

**Future-safe data contract:** a versioned offline scene may need geometry/material attributes, alpha-cutout/translucent classification, optional baked light/AO, bounded room-interior surfaces, selected stable entity IDs (retained locally), and camera pose/target information per shot. The current scene schema is explicitly v1; an incompatible future schema should be versioned, not silently interpreted as old cube records.

**Refresh integrity:** the original save is read-only. Current refresh uses a lock check and source file metadata before/after extraction and preserves the prior scene script on extraction failure. This is a **best-effort consistency check**, not a verified atomic snapshot of a live-changing save; the game should be closed. Larger multi-asset scenes will need generation-level validation and atomic publication rather than a collection of unrelated file overwrites. This requirement matters to a stable future experience more than supporting every unusual region compression method.

Sources: [Mojang 26.1 storage changes](https://www.minecraft.net/en-us/article/minecraft-java-edition-26-1), [Mojang 26.3 release](https://www.minecraft.net/en-us/article/minecraft-java-edition-26-3), [Mojang 26.3 Snapshot 7 block-state changes](https://feedback.minecraft.net/hc/en-us/articles/47877771669133-Minecraft-Java-Edition-26-3-Snapshot-7), [Minecraft chunk format](https://minecraft.wiki/w/Chunk_format), [Anvil region file format](https://minecraft.wiki/w/Region_file_format), [Lively CLI webpage reload](https://github.com/lively-community/lively/wiki/Command-Line-Controls).
