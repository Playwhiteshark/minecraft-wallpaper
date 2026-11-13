# Product specification — Minecraft Living World video wallpaper

**Status:** approved design direction, 13 November 2026. **Not yet implemented or captured.** See [VIDEO-WALLPAPER-PLAN.md](VIDEO-WALLPAPER-PLAN.md) for the researched choice, detailed implementation file map and acceptance gates. The native Vantage renderer is superseded.

## Product

A high-quality, low-overhead video wallpaper of the user's actual Minecraft Java saved world, recorded at a fixed chosen camera in Minecraft using the user's existing shaderpack and resource packs. Lively Wallpaper is the entire playback host. Animations such as moving clouds, grass, foliage, water, flames and actual important mobs are **recorded into the video**, not independently simulated in the wallpaper.

## Scope

- Three **120-second** final loops by default (day, sunset, night), with optional fourth 120-second morning loop if it improves transitions and day/night rhythm.
- No need for camera movement; same chosen framing across segments. No new terrain reader, world converter, Vantage service, HTTP server, biome layer, mob AI, native GUI or renderer.
- Choose the clip using **current OS local time**. Optional manual override. Sunrise/sunset astronomical accuracy and weather synchronization are later optional research, not v1 requirements.
- Clips loop smoothly inside each slot; changes between different time-of-day clips may crossfade 2–5 seconds **only if** acceptable on the target machine. Preserve the current clip if the replacement fails to load.
- Video uses the desktop's **actual native resolution and aspect ratio**, baseline 30 FPS. Test GPU hardware decode, scaling and colour.
- Initial final-media budget about **500–800 MB** across the chosen 3/4 clips (quality-dependent; not a rigid maximum). Prefer a visually tested H.264/MP4 WebView2 build for compatibility; compare newer codecs in the final host before adopting them.
- No audio by default, no copyright-infringing music, no source-game assets distributed, never edit the save as part of playback.

## Preferred runtime (pending one-scene performance test)

Use a standard Lively web wallpaper with `index.html`, tiny time selector script, HTML5 video, CSS opacity transitions and Lively's optional persistent properties. It is **not** a self-hosted site: all files are local inside a conventional Lively wallpaper package.

For the lowest resource use, benchmark against Lively's default native **mpv video** playback. If WebView2's decoding or double-video transition costs too much, switch to native mpv and schedule `setwp` through Windows Task Scheduler without running a resident service. Decide using measurements rather than abstract preferences.

## Recording workflow

Capture real footage from Minecraft using OBS. Record about 125 seconds per shot if planning a 5-second loop-closure overlap. Trim/repair the intra-clip loop with FFmpeg or a video editor and encode final ~120s segments. Test leaf/water motion, cloud seam, fire animation, mob animation and time-of-day coherence. Make each recorded environment as beautiful as possible without later runtime compositing. Capture masters are private, separate from the final Lively install.

## Reliability / acceptance

**Visual**: a real recognizable saved-world composition, real animation without frozen parts or abrupt frame jump; appropriate time state after login, sleep, travel across time zones and time changes.

**Efficiency**: one active hardware-decoded video most of the time, no Minecraft/Vantage processes, no large preloaded RAM array and no unexpected network requests. Measure both plugged-in and battery power with Lively's pause settings.

**Usability**: locally importable Lively wallpaper, no separate dashboard or Python startup task if using the HTML route, simple manual override and ability to change the clips by re-encoding without modifying Lively itself.

**Limits**: real-time shader changes, moving entity AI, exact astronomical day/night, live Minecraft world updates, seasonal changes, 3D camera tours and programmable cloud overlays are out of scope. New visuals require re-recording.

## Release gates

1. One real ~2-minute loop + codec/loop seam comparison in Lively mpv and WebView2.
2. Three finalized segments + optional fourth + storage/performance data.
3. Time-based selection/transition implementation in chosen Lively route.
4. End-to-end Lively restart, paused fullscreen, battery, sleep/resume, clock/timezone tests.

Previous native-renderer technical documents are historical only:
[FULL-WORLD-ARCHITECTURE.md](FULL-WORLD-ARCHITECTURE.md) and
[WALLPAPER-RENDER-LAYERS.md](WALLPAPER-RENDER-LAYERS.md).
