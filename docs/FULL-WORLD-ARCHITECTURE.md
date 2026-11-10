# Full saved-world application architecture

## Purpose and completion boundary

The new **Launch.cmd → full_world.py** entrypoint is a separate full-world application. Its conversion and GPU renderer are intentionally borrowed from maintained upstream Vantage, rather than rebuilding Minecraft's world-format, meshing, block-model, biome, lighting, tile-streaming or shader subsystems again.

The following are not the same milestone:
1. A custom NBT → small HTML crop (old legacy proof of concept).
2. Vantage successfully emits genuine full-world, textured chunk tiles and its native Three.js viewer draws them.
3. The real user's actual Minecraft save looks acceptable inside **Lively**, including multi-chunk joins, buildings/interiors and camera positions.

The code implements 2's integration path; 3 still requires acceptance on the actual Windows computer. **Do not claim a complete visual acceptance without that.**

## Dependency boundary (highest engineering priority)

- Vantage native version **0.15.1**, MIT: official Windows/Linux release archive, pinned SHA-256, fetched to private application storage on a user-triggered build. Runtime executable includes both offline converter and small local viewer.
- Vantage's **own Three.js renderer**, lighting, texture-array and chunk management. We do not fork its 3D geometry or invent our own shader implementation. Upstream uses actual Minecraft block models and assets; differences from newer saves are compatibility bugs to verify, not to patch via a fake grey heightfield.
- Python 3.10+ standard library: local configuration, GUI, release installation, process management and safe snapshot switching. Python does not run while the wallpaper displays.
- Lively Wallpaper is the desktop host. It subscribes to the loopback URL; a tiny native viewer process persists for streaming, **not** a separate Minecraft instance, Node server or another mapping desktop application.
- Alternative: minecraft-block-reader + block-model-renderer + Three.js, which is strong for blockstate fidelity and modular scene integration; do not add it alongside Vantage unless a real incompatibility warrants swapping the conversion adapter. Running two Minecraft mesh generators in parallel would be unnecessary overhead.

## Module map

| Module | Responsibility | Swap boundary |
|---|---|---|
| full_world/backend.py | Download verified native backend, convert all saved chunks, validate output, atomic publish | Converter adapter |
| full_world/config.py | Local world registry by canonical path hash, cameras, dimension, startup prefs | Config service |
| full_world/service.py | Start/stop loopback-only embedded native viewer, login startup opt-in | Viewer transport |
| full_world/gui.py | Small Windows control panel and user flows | Front-end UI |
| full_world.py | GUI and headless build/serve/stop/status entrypoint | CLI facade |
| app.py / mww/* / web/* | **Legacy only** — small-crop renderer and custom mob selection, kept for rollback | Future entity overlay extraction |

## Concrete data flow

1. User registers a real save (contains level.dat) and chooses **Build full saved world**.
2. The converter finds/extracts Minecraft textures locally, reads existing Anvil regions and blockstates, and writes a Vantage world index, per-dimension manifests, genuine high-resolution .vtile meshes and .vtexarr texture arrays. **No --radius limit.**
3. Only after verifying real geometry files and unchanged source metadata does the controller atomically publish a new versioned snapshot. The last-good snapshot stays intact on any failure.
4. An embedded Vantage HTTP viewer binds to **127.0.0.1:8787**. All chunk fetching is loopback-local. The native viewer streams tiles around the camera under its own memory budgets rather than keeping every explored chunk on the GPU.
5. Lively is configured once with the local Web Page URL; saved camera bookmarks produce shareable camera URL hashes. On Windows login, an **optional**, user-controlled Startup shortcut restarts the small viewer against the last-good snapshot.
6. No world data or Minecraft assets are sent to a cloud service or committed to GitHub. The source save is never written by the application.

## Safe snapshots

Versions live under private state/full-world/<world-key>/versions/<version-id>. The pointer current.json identifies the active version. A conversion writes to .building-* staging, verifies tile output, checks the source's region-file metadata, then renames that staging directory into an immutable version before updating the pointer. A failed run leaves the previous version and server running. Old versions are retained for manual rollback rather than silently deleted.

The separate public source repository contains only code, tests and general docs; no user world names, save paths, coordinates, entity UUIDs or copyrighted Mojang assets.

## Engine trade-offs and future interfaces

- **Accuracy:** Vantage is a Minecraft-specific renderer, much closer than the old fallback-cube converter. It retains native block geometry, texture selection, biome identity, saved light/AO and cave coverage, with chunk-aware boundary meshing. It is still a map engine, not Minecraft gameplay; redstone/ticking, dynamic entities, Java-only renderer quirks and fresh 26.3 block/model variants may differ.
- **Shaders:** Vantage builds Three.js materials and exposes biome/fog/light shader uniforms. A later shader enhancement should extend/replace *materials and post-processing* or swap the viewer adapter; do not modify NBT parsing for every lighting change. Iris/Complementary shaderpacks are not drop-in compatible.
- **Small mob rings and actual entity overlays:** deferred. The existing legacy saved-mob reader, model adapter and local-client-JAR skins can become an independent overlay adapter. Vantage's embedded viewer will need a documented extension hook or a custom Three.js host before claiming those overlays work in the full-world program.
- **Resource use:** heavy work is offline conversion; after completion only the small native viewer and Lively GPU/WebView are resident. World size affects disk output; GPU residency is limited by upstream streaming budgets.
- **Incremental refresh:** this first backend rebuilds the world into a new version. Content-hash incremental tiles and background scheduling are future performance improvements. Never replace a working snapshot during a failed rebuild.

## Verification

Automated tests check world identity, camera hash, no-radius converter command, valid tile output, stable rollback on conversion failure, SHA pin, refusal to kill foreign processes and legacy crop non-regression. CI should also execute the exact official native binary's help path on Windows/Linux. A real-world Lively screenshot/check is required separately.

User-facing limitations: user must add the Lively Web Page URL once, optional login startup is opt-in, and selected pet overlays aren't in the new native viewer yet. The old custom prototype is still available through Legacy-Prototype.cmd.
