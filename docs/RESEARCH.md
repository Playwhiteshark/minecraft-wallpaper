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

There is an existing user-specific Lively **Desktop Picture persistence** compatibility patch, with independent recovery/health documentation in the private [personal-ops customization record](https://github.com/Playwhiteshark/personal-ops/tree/main/customizations/lively-desktop-picture). **Do not reapply, replace or modify the patched Lively DLL as part of this project.** Verify static fallback and virtual-desktop switching as a compatibility test only.

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
