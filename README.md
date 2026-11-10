# Minecraft Living World Wallpaper

## Native camera-driven living-world viewer (default)

**New baseline:** Minecraft Java save → verified Minecraft-26.3-compatible Vantage v0.15.1 `live` native tile producer → upstream Three.js viewer → Lively Wallpaper. The viewer indexes the generated chunks in the save, **bakes high-resolution geometry only as tiles are requested**, caches the result and allows the upstream renderer to decide what is visible/resident on the GPU. There is **no required whole-world conversion**, no 8-block sampled substitute terrain and no fixed crop radius.

This reuses Vantage's own world reader, block models, textures, mesher, tile protocol, tile streaming, lighting and WebGL renderer instead of inventing substitutes. Upstream's default cave horizon removes deeply hidden cave geometry from normal Overworld tiles; subterranean exploration is postponed. Initial live mode does not prebake unvisited chunks in the background. A low-resolution overview is progressively assembled **from requested real tiles** using Vantage's native LOD system, not from an invented coarse terrain sheet.

**Current verification:** Automated unit tests and a native CLI integration test exercise the code, but visual acceptance of the actual user's saved world in Windows/Lively remains separate. If upstream Vantage cannot read a recent Minecraft chunk format or find compatible client assets, the app must show native diagnostics rather than display fake terrain.

### Start on Windows

Close Minecraft before opening the save in this wallpaper app, then update your existing Git checkout:

~~~powershell
cd "$env:USERPROFILE\\CODING STUFF\\minecraft-wallpaper"
git pull --ff-only
.\Launch.cmd
~~~

The selected saved world carries over from the earlier app when possible. Choose or edit a **Camera Location** (world coordinates and dimension), then click **Open live viewer**. The launcher installs the SHA-256-pinned, MIT-licensed Vantage compatibility build on first use if it is missing. The `vantage live` process streams only requested chunk tiles, into a local private per-dimension cache under the app state directory. Selecting a different dimension restarts the native stream for that dimension without discarding previous caches.

### Surface-first 3D geometry (default live wallpaper)

The current compatibility build applies two narrowly scoped native patches to the unchanged Vantage pipeline:

- [26.3 palette decoder](native/patch_vantage_263.py) recognizes compact TAG_String blocks, renamed id/properties compounds, **and the empty-key block ID compound form**. Missing this last form could silently drop saved chunks and leave disconnected vertical columns.
- [Surface ribbon mesher](native/patch_vantage_surface.py) adds optional \`--surface-depth 16\` to **Overworld live viewing only**. It emits faces only near the actual topmost block of each X/Z column, extending down when lower adjacent saved terrain exposes a genuine cliff. It never fabricates topsoil, fills empty chunks, or creates artificial bottom faces. The existing native block grid is still read for lighting, model resolution and hidden-face culling.

The default is a 16-block-deep surface ribbon, not a full-height terrain extrusion; deep caves and underground exploration are deferred. This is **geometry suppression**, not an implementation of Minecraft's entire world generation system. A separate native engine version and local cache namespace prevent reuse of previous empty or full-height tiles.

The native CI test now creates two adjacent real Minecraft DataVersion 5023 chunks (including the empty-key compound palette encoding), checks nonzero geometry from both native and live paths, and asserts that surface live tiles have fewer vertices than the full-depth offline rendering. The original Vantage embedded Three.js renderer remains unchanged.

### Minecraft 26.3 compatibility (zero vertices / empty sky)

The official upstream Vantage **0.15.1** executable predates Minecraft 26.3 Snapshot 7's block-state storage change: vanilla chunk palettes can now contain compact string block IDs and compounds with `id`/`properties`, whereas upstream expects `Name`/`Properties`. Upstream [issue #103](https://github.com/thoughts-on-things/vantage-mc/issues/103) documents the exact symptom: recognized chunks silently mesh into air. Our **`0.15.1-mww263.1`** compatibility build keeps the same upstream native reader, renderer and web frontend and patches only the 26.3 palette interpretation (see [native patch](native/patch_vantage_263.py)).

The binaries are built from the [pinned upstream v0.15.1 Git commit](https://github.com/thoughts-on-things/vantage-mc/tree/953f0ac78d62de751a935b8e8d5be2d711d6fd56), include its MIT license, and are independently SHA-256-pinned in the Python downloader. [Build workflow](.github/workflows/native-vantage-263.yml) runs native Zig decoder tests plus a synthetic Minecraft 26.3 **real conversion and live tile test that asserts nonzero vertices** before release publication.

**After a `git pull`**, close Minecraft and click **Open live viewer** once. The app obtains the patched native executable automatically. A newly versioned cache prevents reuse of empty VTL tiles produced by the original 0.15.1 decoder; you do not need to delete your existing saved world, old caches, or successful offline exports. Visual fidelity in your actual save still requires inspecting the new viewer; no tool here accesses the private save remotely.

There is **no mandatory Build button**. **Export full world (optional)** retains Vantage's normal offline `render` capability for a static map and still uses atomic last-good snapshot publishing. An offline export does not replace the live wallpaper process. Full hidden cave coverage is opt-in on the command line.

In Lively, use **Copy Lively Web URL**, then **Add Wallpaper → Web Page** and paste the local camera URL. The native Vantage web server binds to **127.0.0.1:8787**; the control panel can close while Vantage stays alive. The optional **Start at Windows login** option restarts the camera-driven `live` viewer (not a world export). This is not an HTTP-accessible public web service.

When the camera still shows missing terrain, run `py -3 full_world.py --diagnose`. It prints a 13×13 grid of **actual saved** Anvil chunks around the current camera: `#` present, `.` absent, and `C` or `c` marking the camera's chunk. This reads only the native region location tables; it never modifies the save or substitutes invented terrain. A dense saved grid with visible gaps indicates another decoder/renderer problem rather than absent chunks.

### Commands

~~~powershell
py -3 full_world.py --open        # Live streaming; opens the browser
py -3 full_world.py --serve       # Live streaming; suitable for login startup
py -3 full_world.py --status
py -3 full_world.py --diagnose    # Read-only saved chunk coverage around the camera
py -3 full_world.py --stop
py -3 full_world.py --build       # Optional full saved-world offline export
py -3 full_world.py --build --caves-full # Optional deep caves in offline export
~~~

`--jar` specifies the installed local Minecraft client JAR for native texture extraction; otherwise Vantage discovers installed vanilla assets itself. `--memory` bounds Vantage's tile working sets, not the GPU's tile cache. The default live mode never sends save files or Minecraft textures to the cloud.

### Accuracy and implementation boundaries

- **Real saved-world geometry:** native Minecraft-compatible block models, state-dependent textures, lighting and biome shading, subject to the pinned Vantage version's format coverage.
- **Camera-driven work:** no forced conversion of every saved chunk; requests are served from real Anvil regions and cached. Vantage's own renderer performs distance/memory-residency planning. Extra frustum/occlusion optimizations can be added later without changing the world reader.
- **Surface-first:** no `--caves full` in the live path. Existing native cave culling protects ordinary surface scenes; caves and underground slice support remain future opt-ins.
- **Unchanged legacy prototype:** the earlier small crop renderer and its selected-mob features remain separately launchable as **Legacy-Prototype.cmd**. The full native viewer does not yet integrate the custom mob overlays, shader presets, or pet circles.
- **Source safety:** the original save stays read-only; only local cache/output directories change. The renderer's live process does not run a Minecraft client.
- **Known limit:** a `live` session opens a single dimension at a time; camera changes between dimensions restart that session. The local `live` stream doesn't automatically watch edits to a world while Minecraft is open.

Architecture and precise boundaries: [Full-world architecture](docs/FULL-WORLD-ARCHITECTURE.md). The highest engineering rule remains reuse of proven maintained code: [AGENTS.md](AGENTS.md).

---

## Preserved legacy cropped-scene prototype

The text below documents the older experimental app (**Legacy-Prototype.cmd** or **py -3 app.py**). It remains available for the original mob selector and as a rollback. The small crop and custom rendering engine are *not* the full-world application above.

An older **cropped starter** for Windows: transform a bounded part of a Minecraft Java world into a shader-inspired **live 3D wallpaper** with parallax, saved camera shots, simple resident-animal models, and optional refresh through Windows Task Scheduler. It reuses your existing **Lively Wallpaper**; Minecraft does not stay running.

> **Status: bounded prototype, not yet a complete Minecraft-world pipeline.** The application can read a small saved-world crop and render it in Lively, but it does **not** index/convert/load and navigate an entire saved world through reusable chunk tiles. The old sparse coarse-landscape experiment was visually incorrect and is now disabled in the control panel, including for older saved shots. Versioned saved-world chunk tiling, independent camera locations and material/renderer boundaries are required before calling the minimal product architecture complete.

## Run the legacy prototype

Requires **Windows, Python 3.10+ with Tkinter**, Minecraft Java Edition 1.18+ save data, including the 26.1 world-folder layout, a modern browser with WebGL2, and the Lively version you already use. No pip install, Node, Java server, game mod, npm dependencies, external map software, or new background service is required for this starter.

1. Keep Minecraft **closed**. Clone this repository into a permanent project folder (for example `%USERPROFILE%\CODING STUFF\minecraft-wallpaper`) and update it from `main` with `git pull --ff-only`.
2. Double-click **`Launch.cmd`**, or run `py -3 app.py` from PowerShell.
3. Choose your world from the drop-down or **Browse world** (the selected folder must contain `level.dat`). CurseForge/custom-launcher worlds can be selected by folder.
4. Use **player position** or **world spawn** as a starting point, then enter the *actual X/Y/Z of your base*. Set the current limited near-base radius (start at 16–24), lighting, and **Auto-frame** distance. The misleading **Surroundings** control has been withdrawn until genuine saved-world chunk tiling is available.
5. For native block **and mob** textures, choose a locally installed Minecraft version JAR matching your world (otherwise the app tries to discover one). Only Mojang textures already present in that JAR are read; no Minecraft client is launched. On the first **Refresh scene**, v0.3 may download small, versioned entity **model descriptions** from the public minecraft-entity-models repository into your private application cache; these are then reused offline.
6. Click **Choose saved mobs…** to scan the bounded saved region, then choose creatures from the named/tamed-first list. If a named animal is missing, use **Find named creature anywhere in saved world…** to search indexed saved entity chunks outside that radius. A matching creature can become its own camera shot without moving the original base shot. A per-shot selection survives entity-list reordering. Use **Automatic** to retain the old nearby-mob behaviour. Click **Refresh scene**, then **Open 3D preview**. Move the mouse for parallax; in browser preview, drag to orbit and scroll to zoom. The viewer initially frames **exposed terrain surfaces**, not the last saved player's Y coordinate (which may be high in the air). Use the small **All** button in the preview to widen the shot to include saved animals at different elevations; use **Base** to return to the scenic terrain view. The preview label shows **blocks and visible mesh faces separately**. If terrain still does not appear, report the block/face counts and selected Y/height range before changing settings.
7. For Lively, open **Open wallpaper folder** and import its **`index.html`** using Lively's standard Add Wallpaper UI. In Lively's library, locate the imported project folder. Back in the control panel, click **Connect Lively copy** and select that project folder. This opt-in action authorizes updates to our marked `scene-data.js` and the verified `viewer.js` in that specific imported project. A subsequent Refresh copies the owned HTML, renderer, mob-model adapter and scene data, then requests a Lively web-wallpaper reload. If the import is linked rather than copied, the generated output itself may already be the active source.

Imported-copy synchronization and automatic page reload must still be checked on the target Lively installation. This program neither installs Lively nor modifies its binaries, registry entries, or unrelated wallpaper customizations.


### Mob model data and privacy

The saved-mob scan reads nearby `entities/*.mca` records **locally** and does not contact the internet. Selection keys (UUIDs when available) are stored only in private per-shot configuration, scoped to the registered world's canonical path rather than its display name. The rendered `scene-data.js` contains selected *render positions* and model/variant data but no mob/owner UUIDs. Two worlds with the same visible title cannot share selection keys accidentally.

On user-triggered GUI refresh, missing model JSONs are fetched once from `InventivetalentDev/minecraft-entity-models`'s versioned `26.1.2` branch. Only generic Minecraft model IDs are requested; no world data is uploaded. The JSON is cached in `<application data>/mob-models/26.1.2/`. The actual entity textures, including the selected colour of a happy-ghast harness equipped in its saved `equipment.body` slot, are read from the **user's own** Minecraft client JAR and embedded in their own generated wallpaper; copyrighted assets are not distributed in this repository. The emitted wallpaper works offline and requires no Node, Java or 3D engine process. If either models or skins are unavailable, the status shows an issue and the renderer does not claim that a coloured box is a real mob model.

The model dataset is currently `26.1.2`, while newer Minecraft saves such as `26.3` may contain changes not reflected by that extracted model snapshot. Validate your important creatures visually before treating this as fully faithful. Explicitly chosen mobs outside the detailed block radius may not fit the current camera; the preview's **All** framing currently adjusts vertical extent primarily, with more sophisticated framing planned.

## First-run verification

1. Install or verify Python 3.10+ with Tkinter and Git for Windows. From a PowerShell terminal in this clone run `py -3 --version`, then `.\Launch.cmd`. No `pip install` is required to use the app.
2. Close Minecraft entirely. In the control panel choose a Java world, select the correct dimension and use player/spawn location as a **starting** position; overwrite X/Y/Z with the real centre of your base if different.
3. Set radius **16–24** initially, select **golden** or **day** lighting, and choose **Auto-frame**. If you have an installed Minecraft version JAR, optionally select it to enable familiar textures.
4. Click **Refresh scene**. The status should report a nonzero block/face count for an occupied area. Click **Open 3D preview**. Check the ground/builds, mouse parallax, drag orbit and wheel zoom; adjust Y/camera pitch or radius if the camera points away from the build.
5. Import the generated `wallpaper/index.html` into Lively only after the preview works. If Lively copies the files into its own project folder, use **Connect Lively copy** to select that imported project, then click Refresh again and **Reload Lively**.
6. Before enabling any scheduler, test one safe refresh: close Minecraft, make a visible world change in-game, save and exit, return to the app and click **Refresh scene**. Verify the displayed scene changes and the original save still works. The separate **Weekly refresh** button is optional and not required for basic testing.

**If anything fails:** copy the error text/status and report which step, game version, dimension, X/Y/Z, radius and texture-JAR choice were used. Do not upload the world save or private coordinates into public GitHub issues. Test in the browser before troubleshooting Lively; the two failure modes are different.

## What the first version does

- **World and shot UI:** select Java save, dimension (Overworld/Nether/End), base centre, radius, vertical bounds, yaw/pitch/distance, lighting (golden/day/night), and selected saved mobs by stable UUID when available; save, duplicate and remove named shots. Only the **selected** shot is exported per refresh; automated switching and corridor tours are future work.
- **Read-only world import:** read modern Anvil `.mca` chunks around the selected area, decode block-state palettes, extract selected entities from separate entity-region files. Supports a deliberately limited 1.18+ vanilla-oriented block/texture subset; unsupported modded blocks render as simple fallback cubes.
- **Offline converter:** strip invisible opaque block faces, pack compact mesh records, and load a small set of block textures from a chosen existing version JAR (or fallback colours). Preserve enclosed-room inner faces and roof geometry rather than requiring a surface-only map export.
- **Postponed coarse-surroundings prototype:** the old 8-block sampling layer remains in source history for reference, but the application forces it off. It does **not** constitute a rendered Minecraft world or a general chunk loader. Proper full-resolution saved chunk geometry and independently loadable tiles are the next foundational milestone.
- **WebGL2 scene:** load through ordinary local `script` files (no localhost webserver or `fetch`), draw at low frame rate with sunshine, ambient/directional shading, local lantern/torch light approximation, fog/tone mapping, actual mouse parallax, and user-selected UV-textured Minecraft entity meshes when model data and native PNGs are present. This is a *shader-inspired effect*, **not Iris/Complementary/BSL shaderpack execution**.
- **Safe refresh:** skip unchanged source when using `--refresh`; refuse likely active worlds, verify source file metadata before/after processing, validate output before replacing the generated scene script, retain one previous script. The original world is never written by the converter.
- **Lively refresh and scheduling:** opt-in user-selected imported Lively project synchronization; Lively CLI web-page reload request when available. Optional **Weekly refresh** button creates one user-scoped Sunday 15:00 Task Scheduler action, which runs once and exits. No watcher or permanent server.

## Limitations / important warnings

- **Visual fidelity:** full custom block models (stairs, rails, redstone, chest/bed block entities, foliage transparency, biome-specific colour, water optics), lightmaps/soft shadow baking, and shaderpack accuracy remain unimplemented. v0.3 supports real hierarchical Minecraft entity geometry and locally sourced entity PNGs when available, but complex model passes/attachments and some baby/special variants are incomplete. It does **not** claim pixel-perfect Minecraft entity rendering until validated on a real save; unresolvable mobs are reported rather than silently portrayed as authentic.
- **World formats:** Minecraft Java Anvil saves from 1.18+; Java 26.3 string/empty-key/id block-state palette forms are recognised, but accurate models for every new block are not guaranteed. ; folder lookup now supports 26.1's `players/data/` and `dimensions/minecraft/<dimension>/` structure. The new `singleplayer_uuid` reference in `level.dat` selects the correct player record.  External-chunk and newer compression variants, older palette formats, Bedrock, unusual mods, custom world heights, and advanced resource packs have not been verified. Exiting Minecraft before refresh is mandatory; the lock probe and file-stat comparison are conservative **best-effort**, not a snapshot guarantee against all concurrent writers.
- **World coordinates:** player position may not be your base, especially if you logged out in midair. On-demand named-entity discovery can search saved entity region indexes, but there is still no automatic base discovery or whole-world *terrain* rendering. The viewer can reframe its camera around the **extracted** terrain but cannot recover ground blocks entirely outside the selected vertical extraction range; adjust the selected centre Y and below/above range if needed.
- **Size:** only a small near-base block region is drawn in detail (radius capped at 48 blocks, mesh at 370,000 faces). Previously saved coarse-surroundings settings are ignored and no longer produce the incorrect grey sheet. The rest of the generated world is **still not present** in the wallpaper; a chunk-based scene architecture is required. Large scenes may have greater conversion/runtime cost; sustained performance with the new layer is **unmeasured**.
- **Automation:** weekly schedule is opt-in and checks a saved-world snapshot only when invoked; it is not an on-world-close event hook. A scheduled task depends on the source checkout/Python paths remaining stable. Use **Remove weekly task** before moving the checkout.
- **Local Lively import:** after importing HTML, Lively may make its own managed copy. **Connect Lively copy** only after inspecting the imported project's folder; the control panel verifies an owned project and its renderer before updating only the owned `index.html`, `viewer.js`, `entity-models.js` and `scene-data.js`. Your other wallpapers and Lively customizations are not touched. If auto-reload is unverified, use Lively's reload option manually.

## Command line

```powershell
py -3 app.py                 # GUI
py -3 app.py --refresh       # changed files only, prints result
py -3 app.py --refresh --force
py -3 app.py --preview       # open previously generated scene
```

## Where files live

- **Source checkout:** wherever you extracted/cloned this repository, preferably `%USERPROFILE%\CODING STUFF\minecraft-wallpaper`.
- **User-owned state/output (Windows):** `%USERPROFILE%\COMPUTER STUFF\Minecraft Living World Wallpaper\` containing `config.json`, generated `wallpaper/` files, and `scene-data.previous.js` for one-step rollback. These survive uninstall/deletion of the source checkout unless **you explicitly delete** them.
- **Original world + installed client version jar:** read-only, never copied into the repository or automatically shared.
- **Optional Lively imported project:** only user-selected, verified MWW-owned `scene-data.js` is rewritten; it remains Lively-managed and should be removed through Lively, not guessed filesystem deletion.
- **Caches/staging:** per-file temporary data inside the owned output/config folder, removed after success and normally failure; no hidden model downloads or external asset cache. Failure diagnostics are printed in the GUI/CLI rather than accumulated in a log.

Source files are public. **Do not commit `config.json`, Minecraft saves, generated scenes, entity coordinates/UUIDs, client assets or screenshots exposing private locations.** The `.gitignore` excludes common generated paths.

## Testing and verification

```bash
python -m pytest -q         # developer/CI-only pytest dependency
node --check web/viewer.js  # optional developer syntax check
```

The synthetic fixture tests assert: block palette decoding, valid world and entity import (including five animals), texture extraction, browser scene-data generation, changed-file no-op, rollback on corrupt input, safe Lively folder ownership, invalid bounds rejection, and no source save mutation. A Chromium/Xvfb WebGL2 smoke test successfully compiled/drew the generated scene with no JavaScript/GL errors. This **does not replace target Windows + Lively + actual Minecraft save testing**.

## Project docs

- [Product requirements](docs/PRODUCT-SPEC.md)
- [Technical research / reuse options](docs/RESEARCH.md)
- [GitHub issue tracker](https://github.com/Playwhiteshark/minecraft-wallpaper/issues)

### Minecraft 26.1 save compatibility

Minecraft Java 26.1 moved the Overworld, Nether and End chunk/entity directories under `dimensions/minecraft/` and the per-player data to `players/data/`. The 26.1 `level.dat` `singleplayer_uuid` reference identifies the local player; older worlds continue to use embedded `Data.Player` or `playerdata/`. This application reads either layout without moving or rewriting files. The old 1.18+ block-palette extractor remains limited and real-world rendering must be validated against the selected game version.
