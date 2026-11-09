# Product specification — Minecraft Living World Wallpaper

**Status:** concept agreed in direction; unimplemented. **Last research review:** 2026-11-09. **Owner:** this standalone repository, not Desktop Tools or personal-ops.

## Overall objective

> Turn my actual Minecraft world into a beautiful, lightweight, self-updating desktop environment that feels alive. Focus first on the evolving home base and its meaningful inhabitants, then expand to other points of interest. Use subtle cinematic movement and preferably real 3D parallax, while keeping Minecraft and its simulation closed except when I am actually playing.

### Non-negotiables

- **Source fidelity:** all buildings, terrain and significant resident mobs derive from real world-save data or faithful captured game footage, not an imagined recreation.
- **No continuous Minecraft:** no always-open Java client, server tick loop, physics engine, heavy Minecraft shaders, mob AI or game window.
- **Seamless freshness:** periodically and ideally after safely closing a world, refresh only changed data with no routine manual re-recording.
- **Shader-quality desktop presentation:** the target is the user's actual world as it looks *with attractive Minecraft shaders*, not a simple 3D map with flat lighting. Cinematic sunlight/soft shadows, baked ambient occlusion and diffuse/indirect illumination, sky, subtle atmosphere and correct block materials must be designed from the start, with inexpensive real-time effects added only when visually worthwhile. No promise that Minecraft shaderpacks can run directly in Three.js.
- **Power efficiency:** no unnecessary always-on processor; Lively is already present and owns actual display and pausing.
- **Safe, reversible:** never modify the original Minecraft save; preserve last good wallpaper on error; no silent installation or patching of other software.

## Starting scene and growth

The initial real base is very small (approximately a bed/chests and little built structure). It has **five important resident mobs: two happy ghasts, one horse, one dog (wolf), and one cat**. In a scene this small, the animals can be more visually important than the architecture. They should not disappear because a generic map exporter ignores entities. The first wallpaper must be composed for the *current* base rather than an assumed future castle.

As the base becomes bigger, camera framing and scene extents should scale. The user should be able to choose/pin a **base centre, subject area, preferred view and meaningful entities**. Automatic base-size inference may use changed chunks, player-supplied bounds or build/POI clustering, but should not confuse nearby terrain with the base or suddenly shift the composition. Provide manual correction and preserve an approved framing.

Additional areas of interest (POIs) should later have names, custom bounds, cameras/paths, optional selected mobs and time-of-day presets. A curated rotation of locations should be possible.

## Preferred experiences

### Primary: live parallax diorama — the intended product

A lightweight **live 3D** wallpaper with meaningful camera parallax and small interactions is the design goal, **not merely an optional enhancement over a video**. The original Minecraft world and gameplay simulation need not be running. Static terrain, room geometry and light can be preprocessed at refresh time, while camera movement and selective small visual effects run in the Lively viewer.

**Shader-quality rendering is a requirement.** Rather than trying to transplant an Iris/OptiFine shaderpack unchanged, create a **wallpaper-specific rendering profile** inspired by the user's shadered Minecraft reference: baked static lighting, indirect/ambient light, soft/static contact shadows, correct daylight/night palette, tone mapping and restrained atmosphere. Avoid gameplay-dependent shader passes, player/hand/first-person effects, expensive accurate reflections, heavy volumetric lighting, moving sun-shadow updates, shadowing of unseen entire world regions, etc. For the five key animals, add lightweight per-entity local contact shadow/illumination where useful. Details and trade-offs must be measured on the actual Lively viewer.

One challenge: light baking gives best results for a specific time of day. Treat **day/dusk/night as separate baked light profiles** or restricted lighting presets where needed, not an assumed free dynamic sun with fully accurate moving shadows. Every new scene generation may include a few lightweight lighting variants if rendering and storage cost justify them.

Define at least one user-approved **shadered Minecraft reference screenshot from the same camera/time-of-day**. A map viewer that is geometrically correct but aesthetically flat **does not pass the visual acceptance gate**.

### Alternative: cinematic rendered video

A **pre-extracted, renderer-ready 3D scene** displayed in Lively via web technologies (subject to feasibility), where mouse movement causes shallow perspective shift. A slowly moving camera, atmospheric effects and restrained entity idle animation may run on the desktop, but the wallpaper must be able to pause or reduce activity when hidden.

This is an offline display of geometry, *not* Minecraft gameplay. It need not support changing blocks, opening inventories, collisions, AI or simulated day/night progression.

### Alternative: cinematic rendered video

A video/loop mode can give authentic game visuals and movement, especially for complex mobs and shaders. It remains a **contingency**, not a second equally preferred product direction; use it if live 3D cannot meet appearance and performance requirements after an honest prototype. The video is encoded after a one-time capture/rendering job and decoded by Lively while displayed. It **cannot provide real geometric mouse parallax**. Auto-updating recorded footage is harder than updating extracted geometry; that gap must be acknowledged and measured.

A mixed system may use live 3D for most days and selected high-quality video loops for visual showcase shots. Do not make both formats mandatory for initial release.

## Future location and camera design — not part of the first prototype

An evolving home base should become a **curated network of architectural spaces**, not a single enormous POI or an automatically roaming spectator camera:

- **Site / POI:** a named, bounded world area, e.g. *Home Base*, *Village*, *Castle*; initially only one small base. Each site can hold multiple connected **zones**.
- **Zone:** an *exterior*, *courtyard*, *room*, *corridor*, *staircase*, *entrance/threshold* or other area. Zones carry geometric bounds, available atmosphere, notable subjects (including pinned animals) and one or more shots. Rooms and corridors are not automatically separate top-level POIs.
- **Shot / viewpoint:** a deliberately composed camera pose, look-at target, field of view, allowed **parallax envelope**, focus subject, exposure/lighting profile and possible slow camera movement. Every shot has a stable identifier so updates don't randomly change its framing.
- **Transition / connection:** a declared, camera-safe path between shots/zones or an intentional cinematic cut/crossfade. For a future long hall, slow movement down the corridor may be appropriate; for obstructed or physically separated rooms, a short cut may look better and use fewer resources.

**Potential future shot types:** an exterior establishing shot of the base; a close-up of the two happy ghasts; a slow, shallow glide along a lantern-lit corridor; the reveal as the corridor enters an enchanting room; a stable room composition showing chests, furnishings or pets; a doorway/threshold shot overlooking a courtyard; a staircase upward to a roof viewpoint. A very small base should simply have one or two good shots, not an artificially generated tour.

**Camera planning:** start with user-selected/pinned shots. Later, the software may *propose* shots from scene geometry and named zones, scoring subject visibility, sensible framing, usable lighting, camera clearance, collision-free line-of-sight and path continuity. It must **not** wander blindly through walls or depend on gameplay pathfinding. Validate a camera trajectory offline against the stored block/occupancy geometry and a specified clearance margin; use a cut or fade if a safe attractive path doesn't exist. User-approved shots stay stable between refreshes until blocked/invalidated; then report the conflict and fall back to a known-good shot instead of silently retargeting the view.

**Interior data is a first-class requirement.** A map renderer's open-air exterior mesh or cave-cutting mode may remove walls/floors/ceilings of enclosed rooms. Future corridor/room shots require their **interior-facing surfaces, transparent and emissive blocks, furnishings and saved door states** even if invisible from the exterior. Extraction should use the union of surfaces reachable from *the allowed camera envelopes*, not only surfaces visible from above. This may require full/cave-aware geometry in selected zones, plus a different bounded meshing mode for interior areas. Prove that an enclosed synthetic room and, later, an actual saved enclosed build render correctly *before* committing the whole extractor design.

**Rendering cost:** store geometry for the active zone and view envelope, with limited preload for the next transition; prefer offline baked light and spatial/room visibility lists, distance/frustum culling and capped texture/material cost. A corridor does not require continuously loaded geometry for every other room. Only active and near-future shots need expensive assets. Do not claim the game world's entire block or entity data is held in memory.

**Small interaction scope:** mouse movement gives subtle physical parallax; a direct click/gesture may select the next shot/POI or pause an idle camera movement. Do not build first-person controls, a game-style navigation system, pathfinding or room editor merely to obtain a wallpaper tour. Avoid interactions that require the user to focus the desktop or fight with desktop icons.

This network is a **future capability**. P0 and P1 should implement one excellent camera and the geometry constraints needed for later interiors, not a whole camera planner or discovery algorithm.

## Functional requirements

1. **World attachment** — select a local Java world; verify edition/version/data format and locate assets. Keep world path and personal location information strictly machine-local.
2. **Safe snapshot/read** — when Minecraft has closed and saves are settled, read a safe snapshot or otherwise guarantee consistent files. Never alter the authoritative save. For scheduled checks, skip active/partially saved worlds.
3. **Scene extraction** — extract **only selected POI/base areas**. Precompute geometry, materials and, as practical, light/sky/water data. Reuse or adapt existing tooling before developing our own world decoder.
4. **Limited geometry** — do not eagerly store unrelated world regions or hidden internal block faces. Combine spatial selection, meshing, face removal, frustum/distance culling, optional LOD and camera-envelope visibility. **Do not claim to store strictly visible-at-this-instant geometry:** parallax requires nearby newly revealed surfaces; store the *union needed by allowed camera paths*.
5. **Important entities** — use a user-defined allowlist/pinning mechanism, preferably stable entity identifiers. Render appropriate models and variants at their last saved positions. First step may be static; later gentle animations (floating happy ghasts, cat breathing, horse idle) may be procedural and strictly visual. Rendering model variants and saved locations must be verified with actual data. Never implement AI, pathfinding or world ticking.
6. **Scene direction** — persist configurable camera pose(s), subject crop/zoom, preferred lighting/time-of-day, POI tour sequence and optional idle parallax strength. Prioritise natural visual quality at small and large base sizes.
7. **Refresh** — support manually initiated refresh first, then an optional **world-exit refresh** and weekly/every-few-days schedule. Coalesce triggers, skip unchanged content, avoid redundant work, budget CPU/RAM while foreground tasks run, and update changed regions/entities rather than full rerender when feasible.
8. **Atomic publish** — build and validate a new scene into owned temporary storage, then switch Lively/scene reference atomically. If extraction fails or detects an unsupported version, preserve existing working scene and emit a bounded diagnostic.
9. **Lively presentation** — use the existing Lively wallpaper application, native pause rules and static wallpaper fallback. Do not patch Lively just to launch this. Test compatibility with the user's **separate existing Lively Desktop Picture persistence/virtual desktop patch** without modifying it.
10. **Simple controls** — select world, add scene/POI, change camera, pin entities, choose video/3D, Refresh Now, view last successful refresh and diagnostic. Avoid a complicated game-like editor if a few saved camera controls suffice.

## Update strategy

Suggested priority:

1. **On-demand refresh** establishes correctness.
2. **Scheduled refresh** via one narrowly-scoped task (e.g., weekly/periodically) checks saved-world changes and exits quickly when nothing changed. A scheduled task is not a background game or persistent file watcher.
3. **On-world-exit** may use a well-scoped optional client-side lifecycle hook or a launcher integration that triggers after a completed save and full close. *Do not* create an always-running poller solely to detect a closed game. If seamless exit detection requires disproportionate complexity, schedule-only refresh is acceptable initially.

Rendering jobs should be bounded, low priority where appropriate, cancellable/retryable, and only run one at a time. Keep a last-good scene and one staging scene. Protect the source world from mutation and avoid snapshotting while Minecraft is actively writing.

## Renderer hypothesis (not a decision)

- **First examine BlueMap and Vantage** as offline world-to-3D pipelines; Worldlens as a related working desktop reference. Compare quality, entity integration, local static files, region selection, version compatibility, and conversion time.
- Use a lightweight web 3D frontend (e.g., existing viewer adapted to Lively, or small Three.js/WebGL scene) if it provides acceptable cinematic quality and predictable GPU use.
- A continuously running world map server is undesirable. Confirm whether Lively can host required assets as local/static HTML or whether a minimal local server truly is needed. Server/network design must not be hidden background resource use.
- Prefer minimal integration and reuse to a fork/rewrite of a complex renderer.

[Research and references](RESEARCH.md).

## Performance acceptance, measured rather than assumed

Benchmark on the actual target PC and actual Minecraft world, not generic render demos. Measure **visible**, **other window focused**, **fullscreen game**, **battery**, and **paused/static fallback** conditions. Record CPU, GPU/VRAM, RAM, frame cadence, perceived smoothness and power/battery trend. Measure cold-start scene load and refresh work separately. Leave hard numeric caps unset until an observed baseline is available; aim for negligible paused cost and low visible cost.

## Lifecycle, storage and privacy

This standalone application owns its source, issues and releases. **Local Windows Tools** may later expose a narrow on-demand launch/status action via Projects Index; it does not own source data or schedule arbitrary processes. **Lively Wallpaper** remains the display host.

- **World save (user data):** read-only, user-chosen, not committed, not owned/disposable.
- **Machine configuration (user data):** world path, selected POIs, coordinates/cameras, entity IDs, refresh cadence and modes; outside any replaceable installed runtime.
- **Generated scene/video (retained artifacts):** owned bounded output area with clear replacement and cleanup policy.
- **Intermediates/cache:** app-owned and disposable only after validated ownership.
- **Logs/diagnostics:** app-specific bounded size/retention; never hide failures or sweep unrelated files.
- **Source checkout:** prefer `%USERPROFILE%\CODING STUFF\minecraft-wallpaper` on this machine; keep absolute paths out of portable Git.
- **No-debris rule:** clean owned temporary snapshots/staging on success/failure/cancellation, never delete user saves, unpublished work or unknown files.

Before implementing a filesystem or Lively integration, define these paths and lifecycle rules precisely, including installation/upgrade/uninstall behaviour. Preserve existing user-owned Lively settings and libraries.

## Exclusions

- Playing Minecraft from the wallpaper.
- Physics, redstone simulation, mob AI, pathfinding or server simulation.
- Rendering the whole explored world continuously.
- Hidden resident background management services without a genuine continuous requirement.
- Replacing the user's Lively installation or altering unrelated Lively customization.
- Automatically downloading/sharing world saves or POI data.

## Acceptance scenario

With the game **closed**, a user sees a **shader-quality**, well-composed live-3D scene of their currently small base and the important five pets in Lively, compared to a real Minecraft shader reference. Real mouse parallax works **or**, if its performance/quality is worse, an explicitly chosen attractive video loop remains available. A saved block change and a saved pet-position change become visible after an appropriate safe refresh. Other world regions are not eagerly loaded. A failed refresh leaves the last good scene intact; pausing/foreground/battery handling works correctly. The original Minecraft world remains unchanged.

## Open product decisions

- Preferred camera behaviour: shallow mouse parallax, autonomous slow orbit, POI tour, or combination?
- When visual quality and power conflict, which takes precedence?
- What entity visual fidelity is mandatory at launch: static recognisable forms or animated variants?
- Is on-close refresh worth a very small optional Minecraft client mod, or is a periodic update enough?
- Which world Java version/mod loader/resource packs are authoritative for initial tests?

*This is a design specification, not a claim of implemented functionality.*
