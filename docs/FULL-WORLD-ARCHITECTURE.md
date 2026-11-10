# Minecraft Living World — camera-driven native architecture

## Working definition

**Full saved-world support** is not **mandatory full-world conversion** and neither is **rendering the full world on the GPU**. The program must address every discovered generated chunk without inventing data; normal wallpaper operation should prepare only the tiles needed by the active camera and the renderer should admit only a budgeted visible subset.

The production pipeline is:

```text
Minecraft Java saved world (read only)
  → Vantage 0.15.1 native `live` (region index + on-demand real tile meshing)
  → private cache: full-world/<world-id>/live-cache/<dimension>/
  → Vantage embedded localhost HTTP server
  → Vantage native Three.js tile manager / GPU renderer
  → browser or Lively Web Page wallpaper
```

The old small-crop Python scene builder is a **legacy rollback**, not a full-world substitute.

## Reused upstream engine — no second Minecraft implementation

- **Vantage 0.15.1 (MIT):** native Java save discovery, modern Anvil/region reading, blockstate resolver, chunk meshing, texture arrays, light/biome output, caching, embedded web viewer and lazy tile HTTP production.
- **Vantage's Three.js engine:** tile priority and budgets, streaming, geometry/material construction, GPU residency, frustum-aware view planning and camera URL hashes. Our Python code does not implement those subsystems.
- **Python standard library/Tkinter:** the machine-local world registry, camera bookmarks, native process supervision, optional pinned binary download, startup shortcut and offline-export snapshots.
- **Lively:** desktop host pointing at the Vantage loopback URL.

Do not invent a replacement terrain mesher, geometry transcoder or WebGL framework to achieve basic streaming. Follow [AGENTS.md](../AGENTS.md) before any new dependency or subsystem.

## Default viewer lifecycle

1. The user registers an actual Java save and sets a named camera view. The source world must not be actively open in Minecraft.
2. Opening the browser or copying the Lively URL launches **`vantage live <save> --dimension <view> --out <cache> --host 127.0.0.1 --port 8787 --prebake off --lod on --players off`**. No `render` command and no `--radius` crop are required.
3. The native engine indexes the real save's populated chunk positions, prepares an initial tile and publishes its manifest. Later high-resolution tile requests mesh only as the camera moves; results are persisted for later requests.
4. The viewer admits only tiles within its own GPU memory and distance budgets, and can evict them independently of on-disk coverage. Low-resolution rings use upstream color-map LOD built from real baked tiles as they arrive.
5. Ordinary live mode **does not pass `--caves full`**: Vantage's default Overworld cave horizon (currently y=55) excludes unseen deep cave faces. The End and Nether use their dimension-specific reachability logic. No manual top-block-only conversion or fabricated heightmap is permitted.
6. A switch between Overworld, Nether and End starts a native `live` session for the requested dimension, retaining its cached tiles in a separate private directory.
7. A small Vantage process remains running for Lively. Optional Windows login startup invokes `--serve`; it does not trigger a complete export. Only a verified owned process may be terminated.

Camera URLs are local hash deep links. The original save, client JAR and copyright assets never go into the source repository or a remote server.

## Optional complete offline export

`VantageConverter.render` remains available when the user explicitly selects **Export full world** or calls `--build`. It renders every generated chunk of every discovered dimension (no arbitrary radius), validates real tile files, protects the last-good output through an atomic version pointer and retains failed-render diagnostics. It **does not need to finish before the live viewer can start**.

The default offline export uses upstream cave culling for surface-first output. `--build --caves-full` deliberately retains underground caves for a separate static map. A successful export is not evidence that the real-world camera view is visually correct in Lively.

The previous generic 'zero high-resolution tiles' exception came from the optional offline-output validator; it did not tell the user whether upstream reported no chunks, lacked textures or could not interpret saved blocks. Failed offline validation now includes the native log tail. The live path instead checks a real advertised tile manifest before reporting startup success and displays its native startup diagnostics on failure.

## Interface/module boundaries

| Module | Scope |
| --- | --- |
| `full_world/backend.py` | Vantage release pin/verification, selected client asset extraction, optional static export, atomic snapshot validation |
| `full_world/service.py` | Compose and supervise native `live`, verify initial manifest, per-dimension cache, owned PID and loopback viewer transport; backward-compatible static `serve` adapter |
| `full_world/config.py` | Machine-local paths, worlds, cameras, stable world-key hashing, Vantage URL hash |
| `full_world/gui.py` | Nonblocking camera-driven Open/Copy actions; optional export remains separate |
| `full_world.py` | CLI: default `--open`/`--serve` live, optional `--build` offline |
| `mww/*`, `app.py`, `web/*` | Preserved legacy crop/selected-mob implementation |

## Fidelity and deferred work

Vantage's renderer consumes genuine Minecraft model-backed mesh data; it is not Minecraft's own renderer and may require compatibility work for changed Minecraft block metadata/newer save formats. If a real save yields no mesh, read the native diagnostics and verify format support rather than filling empty space with approximate cubes.

Shader/material extensions belong behind the renderer boundary, not in NBT decoding. True occlusion culling, more sophisticated frustum priorities, multiple camera prewarming, refreshing a cache after a save changes, custom mobs and pet rings are **not** part of this minimal functional release. Underground/cave exploration is explicitly postponed; retaining the existing backend API prevents blocking it later.

## Tests and truthful acceptance

- Unit tests cover source identity, stable camera hashes, live command options, no mandatory export, single-instance reuse, optional complete export and safe ownership.
- Native CI runs the exact pinned upstream binary, exercises its embedded Three.js page, and performs both static conversion and genuine lazy tile serving from a synthetic two-chunk Anvil world.
- These prove native integration, not visual acceptance of an arbitrary 26.3 saved world. For release acceptance inspect a real camera's buildings, adjacent chunks, textures and Lively WebView; log unsupported chunk formats clearly. Never claim visual success from an HTTP status alone.
