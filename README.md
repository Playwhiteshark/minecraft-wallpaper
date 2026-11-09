# Minecraft Living World Wallpaper

A small **working starter** for Windows: transform a bounded part of a Minecraft Java world into a shader-inspired **live 3D wallpaper** with parallax, saved camera shots, simple resident-animal models, and optional refresh through Windows Task Scheduler. It reuses your existing **Lively Wallpaper**; Minecraft does not stay running.

> **Status: v0.1 starter, not a shaderpack-equivalent release.** The complete basic pipeline has passed automated tests using an original synthetic Minecraft Java fixture and a real WebGL2 renderer smoke test. **Your actual world, Minecraft version, and Lively installation have not been tested here.** Expect missing or simplified block models and low-poly animal representations.

## Run it

Requires **Windows, Python 3.10+ with Tkinter**, Minecraft Java Edition 1.18+ save data, including the 26.1 world-folder layout, a modern browser with WebGL2, and the Lively version you already use. No pip install, Node, Java server, game mod, npm dependencies, external map software, or new background service is required for this starter.

1. Keep Minecraft **closed**. Clone this repository into a permanent project folder (for example `%USERPROFILE%\CODING STUFF\minecraft-wallpaper`) and update it from `main` with `git pull --ff-only`.
2. Double-click **`Launch.cmd`**, or run `py -3 app.py` from PowerShell.
3. Choose your world from the drop-down or **Browse world** (the selected folder must contain `level.dat`). CurseForge/custom-launcher worlds can be selected by folder.
4. Use **player position** or **world spawn** as a starting point, then enter the *actual X/Y/Z of your base*. Set a radius (start at 16–24), lighting, and **Auto-frame** distance.
5. Optionally choose an already-installed Minecraft version JAR to use its native block textures. Nothing is downloaded; without one, the viewer uses simple colours.
6. Click **Refresh scene**, then **Open 3D preview**. Move the mouse for parallax; in browser preview, drag to orbit and scroll to zoom. Try adjusting yaw, pitch, or radius if the base is not visible.
7. For Lively, open **Open wallpaper folder** and import its **`index.html`** using Lively's standard Add Wallpaper UI. In Lively's library, locate the imported project folder. Back in the control panel, click **Connect Lively copy** and select that project folder. This opt-in action authorizes updates only to the marked `scene-data.js` file in that particular imported project. A future Refresh updates that file and requests a Lively web-wallpaper reload. If the import is linked rather than copied, the generated output itself may already be the active source.

Lively's exact project import and page reload behavior **must be verified on your machine**. This program neither installs Lively nor modifies its binaries, registry entries, or unrelated wallpaper customizations.

## First-run verification

1. Install or verify Python 3.10+ with Tkinter and Git for Windows. From a PowerShell terminal in this clone run `py -3 --version`, then `.\Launch.cmd`. No `pip install` is required to use the app.
2. Close Minecraft entirely. In the control panel choose a Java world, select the correct dimension and use player/spawn location as a **starting** position; overwrite X/Y/Z with the real centre of your base if different.
3. Set radius **16–24** initially, select **golden** or **day** lighting, and choose **Auto-frame**. If you have an installed Minecraft version JAR, optionally select it to enable familiar textures.
4. Click **Refresh scene**. The status should report a nonzero block/face count for an occupied area. Click **Open 3D preview**. Check the ground/builds, mouse parallax, drag orbit and wheel zoom; adjust Y/camera pitch or radius if the camera points away from the build.
5. Import the generated `wallpaper/index.html` into Lively only after the preview works. If Lively copies the files into its own project folder, use **Connect Lively copy** to select that imported project, then click Refresh again and **Reload Lively**.
6. Before enabling any scheduler, test one safe refresh: close Minecraft, make a visible world change in-game, save and exit, return to the app and click **Refresh scene**. Verify the displayed scene changes and the original save still works. The separate **Weekly refresh** button is optional and not required for basic testing.

**If anything fails:** copy the error text/status and report which step, game version, dimension, X/Y/Z, radius and texture-JAR choice were used. Do not upload the world save or private coordinates into public GitHub issues. Test in the browser before troubleshooting Lively; the two failure modes are different.

## What the first version does

- **World and shot UI:** select Java save, dimension (Overworld/Nether/End), base centre, radius, vertical bounds, yaw/pitch/distance, lighting (golden/day/night), include important animals; save, duplicate and remove named shots. Only the **selected** shot is exported per refresh; automated switching and corridor tours are future work.
- **Read-only world import:** read modern Anvil `.mca` chunks around the selected area, decode block-state palettes, extract selected entities from separate entity-region files. Supports a deliberately limited 1.18+ vanilla-oriented block/texture subset; unsupported modded blocks render as simple fallback cubes.
- **Offline converter:** strip invisible opaque block faces, pack compact mesh records, and load a small set of block textures from a chosen existing version JAR (or fallback colours). Preserve enclosed-room inner faces and roof geometry rather than requiring a surface-only map export.
- **WebGL2 scene:** load through ordinary local `script` files (no localhost webserver or `fetch`), draw at low frame rate with sunshine, ambient/directional shading, local lantern/torch light approximation, fog/tone mapping, actual mouse parallax, and simplified 3D animal shapes. This is a *shader-inspired effect*, **not Iris/Complementary/BSL shaderpack execution**.
- **Safe refresh:** skip unchanged source when using `--refresh`; refuse likely active worlds, verify source file metadata before/after processing, validate output before replacing the generated scene script, retain one previous script. The original world is never written by the converter.
- **Lively refresh and scheduling:** opt-in user-selected imported Lively project synchronization; Lively CLI web-page reload request when available. Optional **Weekly refresh** button creates one user-scoped Sunday 15:00 Task Scheduler action, which runs once and exits. No watcher or permanent server.

## Limitations / important warnings

- **Visual fidelity:** full custom block models (stairs, rails, redstone, chest/bed block entities, foliage transparency, biome-specific colour, water optics), lightmaps/soft shadow baking, precise mob variants/textures/animation, and shaderpack accuracy are not yet implemented. A few block shapes are approximated. Important animals (two happy ghasts, horse, wolf, cat) are displayed as recognisable low-poly models where saved entity data is available, **not authentic Minecraft meshes**.
- **World formats:** Minecraft Java Anvil saves from 1.18+; folder lookup now supports 26.1's `players/data/` and `dimensions/minecraft/<dimension>/` structure. The new `singleplayer_uuid` reference in `level.dat` selects the correct player record.  External-chunk and newer compression variants, older palette formats, Bedrock, unusual mods, custom world heights, and advanced resource packs have not been verified. Exiting Minecraft before refresh is mandatory; the lock probe and file-stat comparison are conservative **best-effort**, not a snapshot guarantee against all concurrent writers.
- **World coordinates:** player position may not be your base. No whole-world discovery or automatic base detection. Select an actual block area and check the result.
- **Size:** maximum selected radius is 48 blocks and maximum mesh is 370,000 faces. Large scenes may have greater CPU/VRAM usage. Performance on your actual laptop/Lively is **unmeasured**.
- **Automation:** weekly schedule is opt-in and checks a saved-world snapshot only when invoked; it is not an on-world-close event hook. A scheduled task depends on the source checkout/Python paths remaining stable. Use **Remove weekly task** before moving the checkout.
- **Local Lively import:** after importing HTML, Lively may make its own managed copy. **Connect Lively copy** only after inspecting the imported project's folder; the control panel verifies a unique marker before updating only `scene-data.js`. Your other wallpapers and Lively customizations are not touched. If auto-reload is unverified, use Lively's reload option manually.

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
