# Engineering rules — Minecraft Living World, video-first

**Current authoritative direction: 13 November 2026.** See [docs/VIDEO-WALLPAPER-PLAN.md](docs/VIDEO-WALLPAPER-PLAN.md) and [docs/PRODUCT-SPEC.md](docs/PRODUCT-SPEC.md). These rules supersede earlier native-renderer instructions preserved in git history.

## 1. Reuse the existing wallpaper and capture stack (highest priority)

**Do not build or maintain another Minecraft rendering engine or wallpaper host.** Lively Wallpaper runs the final wallpaper; Minecraft with the user's installed shaders is the one-time recording environment; OBS records footage; FFmpeg/ffprobe are used for offline loop preparation and inspection.

Build only the small unsupported glue (optional Lively webpage clock scheduler / CSS crossfade / LivelyProperties and offline encoding scripts). Before each custom feature, verify Lively already supports it. Do not add a persistent Python/C++/Zig background process, on-device Minecraft simulation, Vantage streaming or HTTP server.

## 2. Product contract and storage

- **Three 120-second loops** by default: day, sunset, night; optional fourth morning clip. No 24-hour video render, full-world background conversion or real-time game simulation.
- Fixed chosen camera and genuine real Minecraft visuals, including actual animated grass/leaves, clouds, water, fire, lighting and relevant saved pets/mobs present at capture.
- Native target screen resolution/aspect ratio and 30 FPS baseline; test 60 FPS only when worth the overhead.
- Aim for **~500–800 MB** of final media, optimizing perceptual quality and validating loop seams. Source masters and proprietary game assets stay outside git.
- Test H.264 MP4 first for Lively HTML/WebView2; do not assume browser HEVC support. Verify hardware decode/performance for chosen format. Compare with native Lively mpv baseline.
- Use the **OS local clock**. Respect travel, timezone and sleep/resume, avoid hardwired timezone and daytime assumptions. Manual overrides should be optional.

## 3. Minimal Lively integration, not a second application

Prefer a single Lively HTML wallpaper with local videos, a tiny independent `player.js`, a declarative `schedule.json`, `LivelyInfo.json` and optional `LivelyProperties.json` **only if** it benchmarks acceptably. Don't introduce a frontend framework or separate live web server for four video elements. One video plays normally; temporary second video only during short transitions. Do not download data or render any Minecraft geometry at runtime.

**Fallback:** Lively's default mpv video player controlled by Windows Task Scheduler with `setwp` CLI. No daemon. Lively's automatic conditional playlist is not assumed to exist until verified released. Preserve Lively's power/fullscreen pause and force clock resync on resume.

## 4. Looping, editing and composition

- Capture real high-quality footage with a stable shot in Minecraft. Never fake entities, landscapes, clouds or geometry to cover source limitations.
- Check the exact final frame-to-first-frame seam. Use a short **offline** overlap blend if necessary and inspect ghosting with moving pets and clouds. Keep cross-scene transitions separate from intra-scene loop seam editing.
- Do not insert copyrighted music; clips should default to muted.
- Only improve live compositing if a real observed visual problem remains after offline capture/export. No decorative runtime shader/cloud system by default.

## 5. Source safety, preservation and tests

- Treat the existing `full_world.py`, `full_world/**`, `native/**`, `mww/**`, `web/**`, `Launch.cmd`, old 3D tests and related workflows as **archived experiments**, not active product modules. Preserve git history and user saves; do not delete legacy source without separate justification.
- Keep video files and captures local and gitignored. Do not commit world saves, entity records, UUIDs, skin assets, Minecraft resource files, personal paths, recordings or huge exports.
- Tests prioritize scheduler boundaries, manual override, time-zone/sleep/resume handling, Lively package references, correct aspect scaling, missing-media fallback and playback/memory/battery benchmarks. Do not claim a new runtime exists until end-to-end Lively validation on real footage succeeds.
- After the one-clip mpv vs WebView2 benchmark, record the choice and update this plan; don't implement both production paths.

## Historical mistakes to avoid

Earlier iterations reinvented Minecraft terrain reading/meshing and built a native Vantage tile server to recreate visuals Minecraft already produces accurately, with repeated version and process-lifecycle problems. Those achievements remain in git as a reference, but the product now only needs **good recordings, clean looping, time-aware selection and efficient video playback**. Reusing proven tools and respecting full-pipeline visual acceptance remain non-negotiable.
