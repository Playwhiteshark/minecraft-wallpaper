# Minecraft Living World — video-first plan (authoritative)

**Decision: 13 November 2026. Status: design/research only; production runtime NOT yet implemented.**

The old custom world renderer / Vantage native service is **retired as a wallpaper runtime**. We will use **Lively Wallpaper** directly, with small, fixed-camera recordings made inside the user's real Minecraft world with their actual shaders, entities, grass, water, clouds and flames. We preserve existing code in git history for reference, but do not extend it to power the wallpaper. Keep the Minecraft save, resource packs and recordings local; do not upload copyrighted game assets.

## Product and storage constraints

- **Default:** 3 x 120-second seamless loops: day, sunset/golden hour, night. A **fourth 120-second morning loop** is optional, and recommended if the sunrise/night jump is conspicuous. No 24-hour pre-render.
- **Capture:** fixed camera, true saved-world surroundings and relevant actual mobs; no camera pan required. Capture in normal Minecraft with selected shaderpack and animated environmental features. No ongoing world simulation after capture.
- **Playback:** only one short compressed clip normally active; transition may briefly overlap two clips when required. No Minecraft client, Vantage, local HTTP server, frame-streaming daemon or runtime block selector.
- **Target:** native wallpaper display dimensions/aspect ratio after measuring the actual monitor; 30 FPS as baseline. Investigate 60 FPS only after power/quality comparison.
- **Storage:** at 8/12/20 Mbps, 3 x 2min ≈ 360/540/900 MB and 4 x 2min ≈ 480/720/1,200 MB, excluding raw capture, audio, app packaging and any optional transition clips. Start with **roughly 500–800 MB combined final videos**. Test bitrate against tree leaves/grass, water, shader noise and dark gradients; use perceptual quality, not a fixed Mbps promise.
- **Codecs:** use H.264 MP4 as the **safe first test for Lively's WebView2**, which supports H.264 by default. Test H.265/HEVC or AV1 locally only if the browser/OS hardware decoder accepts them; Edge's HEVC support is conditional on a valid HEVC extension/decoder. Lively's native mpv player may support more codecs with hardware decode; check GPU Video Decode in Task Manager. Do not assume HEVC works inside WebView2 because it plays in mpv.
- **Time:** use the OS local wall clock (automatically follows travel between London/Dubai and the computer timezone) rather than forcing a 24-hour video timeline. The user may customize slots. Default illustrative 4-way slots: 06:30–09:30 morning, 09:30–17:00 day, 17:00–19:30 sunset, 19:30–06:30 night. Three-slot fallback combines morning/day. Real astronomical sunrise/sunset is postponed.
- **Pause:** work with Lively's existing power/fullscreen pause features. When paused, stop video elements; after resume, recompute the slot from current local time. Lively WebView2 can pause media automatically; its `--pause-event true` notification is available to make the state explicit.

## Existing software research and recommendation

### A. Native Lively video (mpv) + Windows Task Scheduler

What exists:
- Lively supports local MP4 and other videos directly, with mpv as its recommended/default video player and GPU decoding where available.
- Lively's `setwp --file ...` command can select the appropriate clip on the primary or chosen monitor; `seekwp` changes video playback position.
- Windows Task Scheduler can issue three/four wallpaper changes at local-time boundaries. A small PowerShell script can run on login and at time changes to select the right file. **No custom daemon.**

Benefits: smallest runtime and least work; very good fallback and baseline performance reference.

Limits: a `setwp` change is a wallpaper replacement, not a documented frame-perfect crossfade. Potential black flash, restart or visible jump must be tested. Laptop sleep, missed events, DST, time zone changes and manually switched wallpapers need explicit handling. Lively's built-in conditional playlist was still an open feature request when checked on 13 Nov 2026; do not assume it is available.

### B. Lively HTML/WebView2 with local videos and tiny JavaScript (**preferred for the intended transitions, conditional on performance test**)

Make a single Lively **web wallpaper** package. It contains an HTML page and **three/four local 2-minute video clips**, not a 3D engine. The page:
- computes the correct scene at startup and after resume using `new Date()` and a declarative local clock schedule;
- plays one muted, looped `<video>` element with `object-fit: cover` or `contain`, preserving the configured screen aspect ratio (no stretch);
- periodically checks the clock (e.g. every 30–60 seconds; not a video-frame timer);
- for scene changes, preloads the next local clip, crossfades two over 2–5 seconds via CSS opacity, then **pauses, clears and releases** the old video and returns to one active decode;
- handles failed/unsupported video codecs by staying on a valid previous scene or static fallback image rather than blanking the desktop;
- handles `visibilitychange` and optional `livelyWallpaperPlaybackChanged` pause notification; refreshes the scene on resume, sleep/wake and time-zone changes;
- allows manually forcing a segment via Lively's `LivelyProperties.json` API and reverting to automatic mode; no taskbar app or separate background process.

Benefits: one wallpaper, self-contained calendar logic and controlled compositing/crossfades, no custom native renderer/server or external scheduled script.

Limits: WebView2 carries browser overhead and crossfade briefly requires two video decoders. Hardware HEVC is **not** guaranteed in Edge/WebView2. Benchmark before deciding this is better than native mpv. It's still **using existing Lively** rather than building a wallpaper host.

**Decision gate:** First record and benchmark *one* 120-second segment in both Lively native mpv and a minimal WebView2 `<video>` page. If native mpv is visibly smoother or much lighter, use option A and accept an instantaneous switch; don't write a new video host.

Sources:
- Lively Video Guide: https://github.com/lively-community/lively/wiki/Video-Guide
- Lively Web Player: https://github.com/lively-community/lively/wiki/Web-Player
- Lively webpage video codec guide: https://github.com/lively-community/lively/wiki/Web-Guide-VI-:-Webpage-Video-Support
- Lively Web APIs and properties: https://github.com/lively-community/lively/wiki/Web-Guide-IV-:-Interaction
- Lively pause notifications: https://github.com/lively-community/lively/wiki/Web-Guide-V-:-System-Data
- Lively CLI: https://github.com/lively-community/lively/wiki/Command-Line-Controls
- Lively playlist request, not assumed implemented: https://github.com/lively-community/lively/issues/137
- Microsoft Edge codec caveats: https://learn.microsoft.com/en-us/troubleshoot/microsoft-edge/development/video-playback-issues
- Lively Performance: https://github.com/lively-community/lively/wiki/Performance

## Capture, looping and composition

1. **Shot selection:** in the actual saved Minecraft world, choose a fixed viewpoint. Check sky, terrain, key named/tamed pets, animated leaves/grass, water and fire. Keep GUI hidden, stable weather and consistent shaderpack/settings. Capture each lighting state from the *same* camera/composition. The mobs need to be in loaded/simulated range **while recording**, not while playing the wallpaper.
2. **Recording:** OBS Studio game capture is the first option, and it can record to MKV safely and remux to MP4. Capture a clean source at higher quality than the target encoded clip, preferably without audio. Capture length should include an overlap window; e.g. ~125 seconds source for a ~120-second final with ~5 seconds of loop-closure blend.
3. **Loop seam:** choose a natural seam first (stable movement). If it jumps, use head/tail overlap blending offline in FFmpeg/editor. Clouds, leaves, water and moving mobs may ghost during crossfade; validate frame 119.9s → frame 0, not just an average preview. Don't add a **runtime** 3D cloud simulator or arbitrary overlay to fix a recording issue.
4. **Scene-to-scene transition:** fixed-camera composition stays consistent, but sun and sky change; a short runtime video-to-video opacity blend might look good, but moving animals/clouds can double. Evaluate CSS crossfade against hard switch in a real Lively session. If necessary, prepare separate short transition clips offline; only after demonstrating a problem.
5. **Audio:** default muted, no copyrighted music, unnecessary soundtrack or live audio capture.
6. **Encoding:** start H.264 MP4 + yuv420p and no audio to confirm WebView2/Lively compatibility. Compare HEVC or AV1 only after hardware decode validation and measured file-size savings. Re-encode via FFmpeg only at export, retaining high-quality masters outside git.
7. **Screen shape:** target actual monitor resolution/ratio and verify crop/fit. No promise that 16:9 media fills a 16:10 display. External monitor is an optional later output profile.

Capture resources: https://obsproject.com/kb/standard-recording-output-guide ; https://obsproject.com/kb/audio-video-formats-guide ; https://ffmpeg.org/ffmpeg-filters.html#xfade

## File changes — definitive implementation map

### Planning changed immediately

| Path | Decision |
| --- | --- |
| `README.md` | Put video-first direction at top; mark old 3D launcher and docs legacy |
| `AGENTS.md` | New hard rule: reuse Lively/OBS/FFmpeg, no custom runtime renderer/3D simulations |
| `docs/PRODUCT-SPEC.md` | Replace old product goals with this small 3/4-clip wallpaper |
| `docs/RESEARCH.md` | Mark old renderer recommendation superseded; link current evidence |
| `docs/VIDEO-WALLPAPER-PLAN.md` | **This** design, capture, test gates, timelines and file map |
| `docs/FULL-WORLD-ARCHITECTURE.md` | Mark archived historical 3D design, not active runtime |
| `docs/WALLPAPER-RENDER-LAYERS.md` | Mark archived; shaders/mobs/haze now baked into footage |
| `.gitignore` | Ignore private captures, mp4/mkv/mov/webm and exported wallpaper packages |

### Future implementation (not yet coded, contingent on 1-clip benchmark)

| File | Planned responsibility |
| --- | --- |
| `wallpaper/index.html` | Single local Lively web wallpaper: one/two native HTML5 video elements |
| `wallpaper/player.js` | Time-slot selection, loop and transition state machine, pause/resume, fallback |
| `wallpaper/styles.css` | Aspect-fit and optional short opacity transition, no WebGL renderer |
| `wallpaper/schedule.json` | Declarative local-clock slots and filenames; 3 or 4 options |
| `wallpaper/LivelyInfo.json` | Standard Lively metadata / embedded web page entry |
| `wallpaper/LivelyProperties.json` | Persist automatic/manual scene and optional transition settings |
| `wallpaper/media/{day,sunset,night}.mp4` | 3 x ~120s local final clips (**ignored by git**) |
| `wallpaper/media/morning.mp4` | Optional fourth ~120s clip (**ignored by git**) |
| `scripts/encode_loops.ps1` | Thin FFmpeg commands for trim, loop closure and compression; no new video encoder |
| `scripts/check_media.py` | Optional ffprobe-based check of duration, resolution, codec, filesize and frames |
| `tests/wallpaper_schedule.test.js` | Real clock boundaries, timezone changes, startup/resume, manual override |
| `tests/video_package.test.py` | Lively bundle references and media metadata; no real footage in CI |
| `.github/workflows/tests.yml` | Eventually test only active video/player code by default; legacy 3D CI remains manual or archived |
| `scripts/lively-time-switch.ps1` | **Fallback only** if mpv + Windows Task Scheduler wins benchmark |
| `scripts/setup-schedule.ps1` | **Fallback only**, opt-in Task Scheduler registration (not a resident service) |

### Frozen, not deleted (historical 3D renderer)

`Launch.cmd`, `full_world.py`, `full_world/**`, `native/**`, `mww/**`, `web/**`, `app.py`, `Legacy-Prototype.cmd`, `.github/workflows/native-vantage-263.yml`, and historical `tests/full_world_* / tests/webgl_* / tests/test_full_world.py` are **not part of the future wallpaper runtime**. Preserve the working history as reference; do not silently delete or change the native Minecraft world, saved cameras, entity notes or previous assets. No follow-up work on the unresolved Windows Vantage port issue is needed for the video product.

## Acceptance plan and stop/go

- **M0:** one real scene at camera position in Minecraft; 120-second finished loop with a measured seam and known final filesize; one mpv and one WebView2 Lively test, GPU Video Decode observed. **No code building before M0.**
- **M1:** three finished clips, same camera/resolution, visible water/clouds/foliage/fire where present and actual important mobs; ~500–800 MB total initial goal; choose fourth morning slot only if beneficial.
- **M2:** local-clock selection in either Lively embedded JS or a tiny scheduled CLI switch, with working transitions, wake-from-sleep and DST/time-zone behavior. Test three-slot and four-slot schedules.
- **M3:** deploy as a locally installable Lively wallpaper package; benchmark at desktop, covered window, fullscreen/game, battery and plugged-in; no zombie native processes or local HTTP services.
- **M4:** optional extra camera, weather or future source re-records. No live Minecraft engine.
- **No-go / fallback:** if a WebView2 double-video crossfade is unstable/high power or HEVC codec fails, use direct Lively mpv with pre-encoded MP4 and a scheduled `setwp` command. If loop seam still ghosts, fix **offline** in capture/FFmpeg instead of building a game renderer.

**Deliverable is a Lively wallpaper and small scripts, not a standalone Minecraft Living World application.**
