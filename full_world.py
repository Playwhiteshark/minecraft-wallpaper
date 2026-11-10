#!/usr/bin/env python3
"""Full Minecraft world wallpaper: conversion → native Three.js viewer → Lively.

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
from full_world.service import start_viewer, stop_viewer, viewer_url


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Render every saved Minecraft chunk using native Vantage, view it in Lively.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--build", action="store_true", help="Convert registered world and start viewer")
    group.add_argument("--serve", action="store_true", help="Start the saved render's local viewer")
    group.add_argument("--stop", action="store_true", help="Stop only the viewer owned by this app")
    group.add_argument("--status", action="store_true", help="Print registered render and viewer status")
    group.add_argument("--open", action="store_true", help="Start viewer and open in browser")
    parser.add_argument("--world", type=Path, help="Register a Minecraft save folder first")
    parser.add_argument("--memory", type=int, default=768,
                        help="Offline converter memory budget in MiB (256–8192)")
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
                    "ready": bool(folder), "render": str(folder) if folder else None,
                    "url": viewer_url(state.get("port", 8787))}, indent=2))
            except ValueError:
                print("No world registered")
            return 0
        if args.build or args.serve or args.open:
            key, world, folder = current_world(state, root)
            if args.build:
                converter = VantageConverter(root)
                result = converter.render(Path(world["path"]), key,
                                          allow_download=True, memory_mib=args.memory,
                                          on_progress=print)
                folder = result.directory
            if folder is None:
                raise ValueError("No successful full-world render yet; run --build first")
            address = start_viewer(folder, state.get("port", 8787), root)
            url = camera_url(address, world["views"][0])
            print("Full-world viewer:", url)
            if args.open:
                webbrowser.open(url)
            return 0
        if args.world is not None:
            print("World registered. Run --build to convert it.")
            return 0
        from full_world.gui import main as run_gui
        run_gui()
        return 0
    except Exception as exc:
        print("Full-world error:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
