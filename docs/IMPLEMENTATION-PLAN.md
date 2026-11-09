# Implementation plan — one working pipeline

**Status:** plan only; no application code or Windows automation installed. **Owner:** `Playwhiteshark/minecraft-wallpaper`. This document is the sole code/build plan; [PRODUCT-SPEC](PRODUCT-SPEC.md) owns requirements and [RESEARCH](RESEARCH.md) owns technical evidence. **Updated:** 2026-11-09.

## Engineering approach

Apply the useful AgentVerse retrospective lessons *without* its team-scale ceremony:

- **One canonical running product.** No alternate frontends, duplicate runners, "integration agents", or parallel implementations of the conversion pipeline.
- **One coding agent at a time**, one bounded issue/branch/PR, merge after real checks. No swarm or multiple task owners. Use Codex or GitHub Copilot for a scoped task; review the results and retain human control of Lively and world-data operations.
- **Vertical slice first.** Get **one real bounded scene from a world save visible in Lively with Minecraft closed** before adding controls, entity animation, multiple cameras or auto-refresh. A synthetic scene only tests the renderer, not the user requirement.
- **Real end-to-end evidence** beats passing helper tests. Need a reproducible single-scene smoke test, a changed-block update, a moved-entity update and a failed-refresh rollback. Use the initial sample as a regression fixture, not proof that arbitrary worlds work.
- **Minimal documentation.** Keep README, AGENTS, product spec, research and this plan, plus narrow issues. No redundant handoffs, enormous agent logs, fake status dashboards or copied GitHub Copilot instruction mirrors.
- **Source and storage ownership.** No user worlds, private coordinates, entity UUIDs or Minecraft asset copies in this public repository. Retained scene data must not be inside Local Windows Tools' replaceable runtime.

## Chosen preliminary stack (conditional on short preflight)

| Job | Default | Not in resident runtime |
| --- | --- | --- |
| Scene geometry conversion | Existing **Vantage native CLI**, pinned version/source and reviewed build provenance; fallback BlueMap CLI only if needed | Minecraft game, server, Java/Vantage converter, Zig toolchain |
| Wallpaper viewer | **TypeScript + Three.js + Vantage's `core` and `three` APIs**, compiled to a static HTML/JS Lively package | React, Electron, Node service, development server |
| Small orchestrator | **Windows PowerShell 5.1-compatible refresh script** calling one converter, checking snapshots/manifest and swapping validated output | Permanent watcher, resident PowerShell/Python process |
| Pets | Later **minimal offline entity reader + accurate model/variant overlay**; choose implementation/runtime only after verifying entity format and existing reusable code | Mob AI/physics/pathfinding/game ticks |
| Host | Existing **Lively Wallpaper** and its pause/input callbacks | Another wallpaper host or modification of the user's Lively DLL |
| Development | Node + Vite/tsc + one small test runner in local checkout or CI **build-time only** | Globally installed new runtime/toolchains solely for wallpaper display |

These are *provisional choices*, not a claim that Vantage's Windows CLI or Lively local-file loading is compatible. The proof gate may change the converter while preserving the rest.

### Critical first risk: Lively offline asset loading

Vantage's stock web viewer uses `fetch()` for `.vtile` / `.vtexarr`; a `file://` Lively web wallpaper may reject cross-origin `fetch` and ES modules. **Do not assume stock Vantage will work by copying `index.html` into Lively.** The first spike must prove a **static, offline, non-server asset path** in the actual installed Lively web engine.

Candidates, test in order:

1. Normal Lively imported static HTML bundle with packaged Vantage tile and texture assets; test whether its web engine provides safe custom-scheme asset access.
2. If blocked, **build-time packaged scene asset modules** (JS-loaded binary data) passed directly to Vantage `parseTile`, `parseTextureArray` and `buildTerrain`, with no `fetch()`; keep bounded tiles and shared textures. For larger scenes, lazy-load smaller script modules rather than embedding the entire world at startup.
3. Reject solutions that require dangerous browser `--allow-file-access-from-files`, blanket CORS disabling, global security changes or a hidden always-on localhost server. If neither works at sensible size, make an explicit product decision before further coding.

Test with the user's **current Lively web engine**. Offline normal-browser behaviour is only a preliminary test, not proof that Lively handles its custom scheme the same way.

## Single data flow

```text
Minecraft Java save (read-only; authoritative)
    |
    |  only after safe close / scheduled skipped-if-busy check
    v
short-lived consistent snapshot of selected world files
    |
    v
Vantage converter (bounded POI region; exits)
    |     [P0/P1: block/terrain mesh + texture output]
    |     [P2: separate selective entity extractor/overlay]
    v
staging scene generation  <--- private local camera/POI config
    |  validate manifest, asset sizes, formats, bounds, and scene preview
    v
atomic current-scene pointer switch, last-good retained
    |
    v
Lively HTML/Three.js scene (camera, parallax, pets, pause)
```

Do **not** commit or automatically upload the source save, snapshot, world coordinates, generated asset files or entity identifiers. Extraction must explicitly bound the world to the selected base/POI; if the chosen converter cannot do bounded export, measure and revise the converter choice rather than silently rendering all explored chunks.

## Proposed minimal source layout

```text
README.md
AGENTS.md
docs/
  PRODUCT-SPEC.md
  RESEARCH.md
  IMPLEMENTATION-PLAN.md
wallpaper/
  index.html                 # single Lively entry point
  src/main.ts                # single composition root; no alternate apps
  src/world-scene.ts         # load validated bounded geometry into Three.js
  src/camera.ts              # saved pose, shallow mouse parallax, composition
  src/lively.ts              # pause/resume, input/settings adapter
  src/entities.ts            # added in P2; models and visual-only idle
refresh/
  Refresh-Scene.ps1          # single explicit refresh entry point
  ...                       # only split helpers once actually warranted
tests/
  ...                       # tests of manifests, geometry import, refresh swap
.github/workflows/ci.yml    # compile, type-check, focused automated tests
.gitignore                  # exclude all generated scenes/world data/caches
```

Avoid premature `services/`, `adapters/`, `providers/`, shared plugin frameworks, generic 3D engines, multiple CLI entrypoints or a complex settings application. The exact filenames may adapt to verified upstream APIs. Keep current-to-proposed interface surface small:

- `loadScene(sceneAssets) -> Three.Group` (frontend, from preprocessed geometry);
- `setCameraPose(pose)` and `setParallax(normalizedMouse)` (frontend presentation);
- `refreshScene(world, bounds, output) -> validated generation | failure` (bounded batch task, never modifies world);
- `publishValidatedGeneration(generation)` (last-good preservation).

## Local data contract (do not select or create physical paths before implementation)

- **Read-only user data:** selected original world save.
- **User-owned config:** world binding, named POIs, bounds, camera settings, entity pins, user cadence; private, local.
- **Generated artifacts:** active `scene` directory plus verified last-good generation; old generations may be cleaned **only** when ownership is proven and they are no longer active/in use.
- **Temporary files/cache:** one per-refresh owned staging/snapshot folder, deleted on success/failure/cancellation (retain only deliberate minimum diagnostics).
- **Logs:** bounded, app-owned diagnostic file/report for genuinely failed jobs only; document safe exact removal.
- **Repo source:** under `%USERPROFILE%\CODING STUFF\minecraft-wallpaper` if a checkout is installed.
- **Installed wallpaper:** via Lively's supported import mechanism, not direct edits into its settings/library without validation.

For future `.local-windows-tools.json` integration, classify `logs/cache/state/configuration/artifacts/userData` explicitly. Local Windows Tools/Projects Index is only a possible launcher/index; it must not own this project's user's world or application data.

## Implementation order and acceptance gates

### P0 — Preflight and a lightweight offline rendering spike

**Output:** a synthetic geometry test scene running with mouse parallax, and a documented trial of the *actual* Vantage tile decoder + renderer under local static HTML/Lively constraints.

- Read a pinned Vantage `core`/`three` API/version and licence; choose smallest import set. Confirm the native CLI's Windows binary availability, precise output format and bounded-area controls.
- Add TypeScript/Vite + Three.js minimal app, **no React/Electron**. Build one canonical static `index.html`; no runtime npm.
- Test raw imported geometry and packaged assets without a live webserver. Support paused/no-activity behaviour via Lively callbacks. No camera free-fly UI yet.
- Run ordinary browser preview and a **user/local Lively smoke test**. If Lively-only testing isn't possible from cloud CI, report **unverified** and do not claim gate completion.
- Track package bytes, installed binary bytes and generated-scene bytes. No arbitrary app/system installation.

**Gate:** scene visibly renders, actual 3D camera viewpoint changes, no Minecraft/Node/server resident during display; offline Lively load validated. A synthetic cube alone does not meet the *real-world* acceptance gate.

### P1 — One real saved-world base scene (first real vertical slice)

**Output:** an actual user's small base, cropped deliberately, viewable as a pleasing perspective scene while Minecraft is closed.

- Operate on a verified safe snapshot. Read-only world input; produce **one** bounded render generation from Vantage (BlueMap fallback on failure).
- Bridge generated tiles/texture arrays to `loadScene`, apply one saved camera pose, usable light/fog/sky, and shallow parallax.
- Document pixel-equivalent comparison against a screenshot of the same area so block geometry, transparency, water and chests are not silently incorrect.
- Check bounds/scale: bed and chests must be recognisable; do not frame the whole continent.

**Gate:** real base visible, no simulation or resident converter; verified screenshot from actual Lively; inspect GPU/CPU when visible and paused. A mocked scene is not acceptance.

### P2 — Pets are meaningful, not incidental

**Output:** two happy ghasts, horse, wolf/dog and cat in their **saved positions**, with credible appearances.

- Prove entity export/format for the exact Minecraft version first; determine whether existing BlueMapEntities parts can be reused under compatible licence. Otherwise create the smallest offline NBT-to-overlay extraction helper.
- Pin selected entities by stable UUID when valid; preserve variants, facing/pose and world coordinate transform. Static representation first; optional gentle animation only after correctness.
- On a controlled save, relocate one pet and regenerate; prove correct movement and avoid duplicate/disappearing entities.
- Keep entity overlay independent of geometry converter output so terrain backend can switch without rewriting pet models.

**Gate:** all five selected residents recognisable in the actual scene. Never claim full mob animation or AI.

### P3 — Safe refresh and last-good swap

**Output:** one `Refresh-Scene.ps1` command changes the wallpaper after a world-save change, without modifying the original world.

- Snapshot only when game is not writing; initially manual invocation after close.
- Preflight world version, known paths, changed regions/checkpoints, source fingerprint; skip unchanged.
- Run at most one conversion at a time with explicit resource/time bounds and readable error.
- Validate output before swap. Use a versioned/atomic pointer or equivalent that is safe when Lively holds old files open; test live scene reload. Preserve prior known-good generation on errors or incompatible data.
- Verify failure injection (missing converter/corrupt tile/interrupted job) and exact temporary cleanup. No accumulation of old world snapshots.

**Gate:** change one block, refresh, updated scene appears; failed render leaves previous working scene and original world untouched.

### P4 — Scene direction and multiple POIs

**Output:** user can add a base/POI and choose camera/lighting, without starting Minecraft or opening a large map application.

- Keep settings UI small and explicit (single local config or tiny on-demand editor), not a new desktop dashboard.
- Bounds set manually first; auto-frame from observed scene content, then conservative base-growth assistance with user correction.
- Optionally rotate between named scenic locations. Keep each scene's tile budget bounded and load only active/near-next assets.
- Add selective entity idle, shader-like sky/water effects **only** if power and visual quality justify them.
- If necessary, add optional pre-rendered video scene type. This is a fallback, not a second simultaneously maintained application.

### P5 — Automatic updates and distribution (last)

- After P3 works, enable periodic Scheduled Task (e.g., every few days) with read-only safety gates; no scheduler until user opts in.
- Evaluate exit-trigger without always-running watchers: tiny optional Minecraft client lifecycle mod, or owned launcher/exit hook. Reject permanent process polling.
- Package static wallpaper with only needed viewer bundle and bounded output; build converter in CI or use a verified pinned release, never install global Zig/Java/Node just for runtime without approval.
- Benchmark visible/paused/fullscreen/focus/battery, disk footprint incl. old generations, startup time and update-time memory. Preserve existing Lively Desktop Picture compatibility patch.
- Document explicit install, refresh, disable, reset, uninstall, and preservation of world/POI user data.

## Automated verification (small but meaningful)

- `npm run typecheck`, `npm run test`, `npm run build` for the wallpaper frontend; test suite should be small and directly tied to behavior.
- Test pure camera transforms and clamped parallax, scene manifest version/path validation and tile-decoder compatibility with a **license-safe generated fixture** (do not commit the user's world).
- Script-level tests on generated temporary directories for unchanged/changed fingerprint, rejected in-use world, missing/corrupt output, repeat refresh, rollback and owned scratch cleanup.
- Actual Windows + Lively + Minecraft-world tests are **manual/target-machine gates**, cannot be replaced by CI green badges.
- Preview screenshot/short capture alongside actual action path whenever assessing aesthetics. Compare visible result, not just correct function returns.

## Copilot delegation contract

**One Copilot task at a time**. The first reasonable delegation is P0's contained offline Lively prototype. Do **not** assign "build the whole app" or trigger five parallel PRs. A delegated issue must state exact scope, files/entrypoint, no Windows/world mutations, upstream versions, quality gate, tests and which local Lively checks remain unverified.

The user's connected GitHub tooling can create and review issues/PRs, but **Copilot cloud-task execution is account/permission dependent**. GitHub supports assigning an issue to `Copilot`, which opens a PR; a GitHub API endpoint exists but may require user-token permissions not available to the installed GitHub connector. Do not claim delegation succeeded without GitHub confirming the assignment/session. User can select **Assignees → Copilot** from a prepared issue. No tasks should be assigned automatically merely because this plan exists.

**Definition of done for each PR:** one canonical runner preserved; relevant tests reported with actual commands/outcomes; build output size measured where relevant; new dependencies and licence notices recorded; no user data, secret or stale temp files; no claim of local Lively validation if it wasn't performed; docs updated only for verified changed behaviour. Merge to `main` after review.

## Stop / reconsider rules

- If one of BlueMap/Vantage already provides adequate wallpaper result with negligible glue, prefer using that rather than more source.
- If the current Lively build cannot load static geometry securely without a server or enormous embedded assets, stop and compare alternatives instead of weakening browser security.
- If entity fidelity cannot be achieved without importing an entire Minecraft runtime, decide whether a video fallback has better practical value.
- If visual/idle resource cost remains comparable to simply running Minecraft, the live 3D approach has missed its core requirement. Use pre-rendered video.
