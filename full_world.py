#!/usr/bin/env python3
"""Minecraft wallpaper: live saved-world tile streaming → Three.js → Lively.

By default opens the control panel; flags enable one-shot automation and an
opt-in Windows login viewer. No Minecraft client/server, Node or Zig install.
"""
from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

from full_world.backend import VantageConverter
from full_world.config import (camera_url, current_world, load_state,
                               register_world, save_state, state_dir)
from full_world.service import start_live_viewer, stop_viewer, viewer_url


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Stream actual saved-world chunks on demand with Vantage and Lively.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--build", action="store_true", help="Optional offline export of all saved chunks")
    group.add_argument("--serve", action="store_true", help="Start the saved world's on-demand native viewer")
    group.add_argument("--stop", action="store_true", help="Stop only the viewer owned by this app")
    group.add_argument("--status", action="store_true", help="Print registered render and viewer status")
    group.add_argument("--diagnose", action="store_true", help="Inspect actual saved chunks around the first camera (read-only)")
    group.add_argument("--open", action="store_true", help="Start viewer and open in browser")
    parser.add_argument("--world", type=Path, help="Register a Minecraft save folder first")
    parser.add_argument("--jar", type=Path, help="Optional installed Minecraft client JAR")
    parser.add_argument("--caves-full", action="store_true", help="Keep all underground caves in optional offline export")
    parser.add_argument("--memory", type=int, default=768,
                        help="Native tile-worker memory budget in MiB (256–8192)")
    args = parser.parse_args(argv)
    root = state_dir()
    state = load_state(root)
    if args.world is not None:
        register_world(state, args.world)
        save_state(state, root)
    try:
        if args.stop:
            print("Stopped owned viewer" if stop_viewer(root) else "No owned viewer to stop")
            return 0
        if args.status:
            try:
                key, world, folder = current_world(state, root)
                print(json.dumps({
                    "world": world["name"], "path": world["path"],
                    "requires_full_conversion": False, "offline_export": str(folder) if folder else None,
                    "url": viewer_url(state.get("port", 8787))}, indent=2))
            except ValueError:
                print("No world registered")
            return 0
        if args.diagnose:
            from full_world.diagnostics import inspect_near_camera
            key, world, _ = current_world(state, root)
            view = world["views"][0]
            report = inspect_near_camera(
                Path(world["path"]), view.get("dimension", "overworld"),
                float(view["x"]), float(view["z"]))
            print(json.dumps(report, indent=2))
            print("Legend: # saved, . absent, C/c camera chunk. "
                  "Saved chunks are not necessarily readable or rendered correctly.")
            return 0
        if args.build or args.serve or args.open:
            key, world, folder = current_world(state, root)
            jar = args.jar or (Path(world["jar"]) if world.get("jar") else None)
            if args.build:
                converter = VantageConverter(root)
                result = converter.render(
                    Path(world["path"]), key, allow_download=True,
                    memory_mib=args.memory, client_jar=jar,
                    caves_full=args.caves_full, on_progress=print)
                print("Optional offline export:", result.directory)
                return 0
            view = world["views"][0]
            address = start_live_viewer(
                Path(world["path"]), key, view.get("dimension", "overworld"),
                state.get("port", 8787), root, client_jar=jar,
                memory_mib=args.memory, allow_download=True)
            url = camera_url(address, view)
            print("Live, on-demand viewer:", url)
            if args.open:
                webbrowser.open(url)
            return 0
        if args.world is not None:
            print("World registered. Run --open to view it; --build is an optional offline export.")
            return 0
        from full_world.gui import main as run_gui
        run_gui()
        return 0
    except Exception as exc:
        print("Full-world error:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
