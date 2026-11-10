"""Simple desktop controller for the real full-world backend and Lively.

No rendering implementation lives here. The UI delegates to VantageConverter,
the private world registry and the native viewer service.
"""
from __future__ import annotations

import os
import threading
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from .backend import ConversionError, VantageConverter
from .config import (camera_url, current_world, default_state, load_state,
                     register_world, save_state, state_dir)
from .service import (set_login_startup, start_viewer, stop_viewer,
                      viewer_url)


def migrate_selected_legacy_world(state: dict):
    """Reuse existing world choice if it exists; preserve the legacy UI/config."""
    if state.get("worlds"):
        return
    try:
        import app
        legacy = app.load_config()
        path = Path(legacy.get("world") or "")
        if not path.is_dir() or not (path / "level.dat").is_file():
            return
        key, world = register_world(state, path)
        shot = legacy["shots"][legacy.get("selected", 0)]
        home = world["views"][0]
        for field in ("x", "y", "z"):
            home[field] = float(shot.get(field, home[field]))
        home["name"] = str(shot.get("name") or "Home")
        home["distance"] = max(8, float(shot.get("distance", 120)))
        home["rotation"] = float(shot.get("yaw", 40)) * 3.141592653589793 / 180
        home["tilt"] = float(shot.get("pitch", 25)) * 3.141592653589793 / 180
        save_state(state)
    except (ValueError, KeyError, OSError, IndexError, TypeError):
        return  # Old config is optional and is never mutated.


def main():
    root_dir = state_dir()
    registry = load_state(root_dir)
    migrate_selected_legacy_world(registry)
    converter = VantageConverter(root_dir)
    root = tk.Tk()
    root.title("Minecraft Living World — Full World")
    root.geometry("940x710")
    root.minsize(780, 610)
    bg, fg = "#101c2a", "#eef3fa"
    root.configure(bg=bg)
    style = ttk.Style()
    if "clam" in style.theme_names():
        style.theme_use("clam")
    style.configure(".", font=("Segoe UI", 10), background=bg, foreground=fg)
    style.configure("TLabel", background=bg, foreground=fg)
    style.configure("TButton", padding=(12, 8))
    style.configure("TEntry", fieldbackground="#263647", foreground=fg)
    style.configure("TCombobox", fieldbackground="#263647", foreground=fg)
    style.configure("TCheckbutton", background=bg, foreground=fg)

    selected_world = tk.StringVar()
    selected_view = tk.StringVar()
    fields = {k: tk.StringVar() for k in
              ("x", "y", "z", "distance", "rotation", "tilt")}
    startup = tk.BooleanVar(value=bool(registry.get("startup", False)))
    status = tk.StringVar(value="Ready. A full-world render includes every saved chunk, not an 8-block terrain approximation.")
    info = tk.StringVar(value="No world selected")
    busy = [False]
    world_entries = []
    view_entries = []

    def save():
        save_state(registry, root_dir)

    def world_labels():
        nonlocal world_entries
        world_entries = [(key, world) for key, world in registry["worlds"].items()]
        world_entries.sort(key=lambda item: (item[1]["name"].casefold(),
                                               item[1]["path"].casefold()))
        return [f'{world["name"]}  —  {world["path"]}' for _, world in world_entries]

    def show_world():
        labels = world_labels()
        world_combo["values"] = labels
        key = registry.get("active")
        for i, (identifier, world) in enumerate(world_entries):
            if identifier == key:
                selected_world.set(labels[i])
                break
        else:
            selected_world.set("")
        refresh_views()

    def refresh_views():
        view_entries.clear()
        try:
            _, world, current = current_world(registry, root_dir)
            info.set(f'World: {world["name"]} · {"Rendered" if current else "Needs rendering"} · {world["path"]}')
            view_entries.extend(world.get("views", []))
            view_combo["values"] = [view["name"] for view in view_entries]
            if view_entries:
                selected_view.set(view_entries[0]["name"])
                load_view()
        except ValueError:
            view_combo["values"] = []
            selected_view.set("")

    def load_view(_event=None):
        for view in view_entries:
            if view["name"] == selected_view.get():
                for key, var in fields.items():
                    var.set(str(view.get(key, 0)))
                return

    def persist_view():
        key, world, _ = current_world(registry, root_dir)
        name = selected_view.get()
        view = next((v for v in world.get("views", []) if v["name"] == name), None)
        if not view:
            raise ValueError("Select or create a camera view")
        for field, var in fields.items():
            view[field] = float(var.get())
        # Force numeric and camera validation before writing.
        camera_url(viewer_url(registry.get("port", 8787)), view)
        save()
        return view

    def select_world(_event=None):
        value = selected_world.get()
        for index, (key, _) in enumerate(world_entries):
            if value == world_combo["values"][index]:
                registry["active"] = key
                save()
                refresh_views()
                return

    def register(path):
        try:
            key, _ = register_world(registry, Path(path))
            save()
            show_world()
            status.set("Registered a real saved world. Click Build full world.")
        except Exception as exc:
            messagebox.showerror("Minecraft world", str(exc))

    def browse():
        folder = filedialog.askdirectory(
            title="Select Java Minecraft save (the folder containing level.dat)",
            initialdir=str(Path.home()))
        if folder:
            register(folder)

    def discover():
        try:
            from app import scan_worlds
            candidates = scan_worlds()
            if not candidates:
                messagebox.showinfo("World discovery", "No launcher saves found. Use Browse.")
                return
            menu = tk.Toplevel(root)
            menu.title("Detected Minecraft saves")
            menu.geometry("720x400")
            frame = ttk.Frame(menu, padding=12)
            frame.pack(fill="both", expand=True)
            listing = tk.Listbox(frame, font=("Segoe UI", 10))
            listing.pack(fill="both", expand=True)
            for name, path in candidates:
                listing.insert("end", f"{name}  —  {path}")
            def choose():
                indexes = listing.curselection()
                if indexes:
                    register(str(candidates[indexes[0]][1]))
                    menu.destroy()
            ttk.Button(frame, text="Use selected world", command=choose).pack(anchor="e", pady=8)
        except Exception as exc:
            messagebox.showerror("Discovery", str(exc))

    def run_build():
        if busy[0]:
            return
        try:
            key, world, _ = current_world(registry, root_dir)
            world_path = Path(world["path"])
        except Exception as exc:
            messagebox.showerror("Full-world render", str(exc))
            return
        busy[0] = True
        build_button.configure(state="disabled")
        status.set("Preparing pinned native converter. This is a one-time download if missing…")
        def notify(message):
            root.after(0, lambda: status.set(message))
        def worker():
            error, result, url = None, None, None
            try:
                result = converter.render(world_path, key, allow_download=True,
                                          on_progress=notify)
                url = start_viewer(result.directory, int(registry.get("port", 8787)), root_dir)
            except Exception as exc:
                error = str(exc)
            def finish():
                busy[0] = False
                build_button.configure(state="normal")
                if error:
                    status.set("Build failed; previous successful render remains intact.")
                    messagebox.showerror("Full-world build", error)
                else:
                    info.set(f"{world['name']} · {result.tiles:,} genuine saved-world tiles in {result.dimensions} dimension(s)")
                    status.set("Full-world renderer is running at " + url +
                               " — copy its URL into Lively as a Web wallpaper.")
            root.after(0, finish)
        threading.Thread(target=worker, daemon=True).start()

    def ensure_started() -> str:
        view = persist_view()
        key, world, folder = current_world(registry, root_dir)
        if folder is None:
            raise ConversionError("Build this world first. It has no converted geometry.")
        address = start_viewer(folder, int(registry.get("port", 8787)), root_dir)
        return camera_url(address, view)

    def open_view():
        try:
            webbrowser.open(ensure_started())
            status.set("Opened the real saved-world renderer in your browser.")
        except Exception as exc:
            messagebox.showerror("Open full world", str(exc))

    def copy_link():
        try:
            url = ensure_started()
            root.clipboard_clear()
            root.clipboard_append(url)
            root.update()
            status.set("Copied camera URL. In Lively: Add Wallpaper → Web Page → paste URL.")
            messagebox.showinfo("Lively Wallpaper",
                "Web URL copied:\n" + url +
                "\n\nIn Lively, add a Web Page wallpaper using this address. "
                "This small local viewer must be running while the wallpaper is displayed.")
        except Exception as exc:
            messagebox.showerror("Lively URL", str(exc))

    def stop():
        if stop_viewer(root_dir):
            status.set("Stopped the owned native viewer. Restart it to use Lively.")
        else:
            status.set("No owned viewer process to stop.")

    def add_view():
        try:
            _, world, _ = current_world(registry, root_dir)
            name = simpledialog.askstring("Camera name", "Name this camera location:", parent=root)
            if not name:
                return
            if any(v["name"] == name for v in world["views"]):
                raise ValueError("A camera with this name already exists")
            base = dict(world["views"][0])
            for field, var in fields.items():
                base[field] = float(var.get())
            base["name"] = name
            world["views"].append(base)
            save()
            refresh_views()
            selected_view.set(name)
            load_view()
        except Exception as exc:
            messagebox.showerror("Camera", str(exc))

    def delete_view():
        try:
            _, world, _ = current_world(registry, root_dir)
            if len(world["views"]) == 1:
                raise ValueError("Keep one camera view per world")
            name = selected_view.get()
            world["views"] = [v for v in world["views"] if v["name"] != name]
            save()
            refresh_views()
        except Exception as exc:
            messagebox.showerror("Camera", str(exc))

    def save_view():
        try:
            persist_view()
            status.set("Saved camera locally. Use Open or Copy Lively URL for this view.")
        except Exception as exc:
            messagebox.showerror("Camera", str(exc))

    def toggle_startup():
        try:
            set_login_startup(bool(startup.get()), Path(__file__).resolve().parents[1] / "full_world.py")
            registry["startup"] = bool(startup.get())
            save()
            status.set("Login startup " + ("enabled" if startup.get() else "disabled") +
                       "; only the small native viewer stays running.")
        except Exception as exc:
            startup.set(not startup.get())
            messagebox.showerror("Windows startup", str(exc))

    body = ttk.Frame(root, padding=22)
    body.pack(fill="both", expand=True)
    ttk.Label(body, text="MINECRAFT LIVING WORLD",
              font=("Segoe UI Semibold", 19)).pack(anchor="w")
    ttk.Label(body, text="Full saved-world pipeline · Native Vantage geometry · Three.js GPU rendering · Lively",
              font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 15))

    ttk.Label(body, text="1   SAVED WORLD", font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=5)
    row = ttk.Frame(body)
    row.pack(fill="x")
    world_combo = ttk.Combobox(row, textvariable=selected_world, state="readonly")
    world_combo.pack(side="left", fill="x", expand=True)
    world_combo.bind("<<ComboboxSelected>>", select_world)
    ttk.Button(row, text="Browse…", command=browse).pack(side="left", padx=(6, 0))
    ttk.Button(row, text="Discover", command=discover).pack(side="left", padx=(6, 0))
    ttk.Label(body, textvariable=info, wraplength=865).pack(anchor="w", pady=(7, 13))

    ttk.Label(body, text="2   COMPLETE WORLD CONVERSION", font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=5)
    ttk.Label(body, text="Uses the pinned Vantage native executable. All saved generated chunks; no crop radius or 8-block sampling.",
              wraplength=860).pack(anchor="w", pady=3)
    build_button = ttk.Button(body, text="Build full saved world", command=run_build)
    build_button.pack(anchor="w", pady=(7, 16))

    ttk.Label(body, text="3   CAMERA LOCATIONS", font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=5)
    row = ttk.Frame(body)
    row.pack(fill="x", pady=5)
    ttk.Label(row, text="Saved camera", width=18).pack(side="left")
    view_combo = ttk.Combobox(row, textvariable=selected_view, state="readonly", width=32)
    view_combo.pack(side="left", fill="x", expand=True)
    view_combo.bind("<<ComboboxSelected>>", load_view)
    ttk.Button(row, text="New camera", command=add_view).pack(side="left", padx=5)
    ttk.Button(row, text="Delete", command=delete_view).pack(side="left")
    grid = ttk.Frame(body)
    grid.pack(fill="x", pady=6)
    for n, key in enumerate(fields):
        cell = ttk.Frame(grid)
        cell.grid(row=n//3, column=n%3, padx=8, pady=6, sticky="ew")
        ttk.Label(cell, text=key.capitalize(), width=11).pack(side="left")
        ttk.Entry(cell, textvariable=fields[key], width=15).pack(side="left", fill="x", expand=True)
    for i in range(3):
        grid.columnconfigure(i, weight=1)
    ttk.Button(body, text="Save camera", command=save_view).pack(anchor="w", pady=(5, 14))

    ttk.Label(body, text="4   VIEW IN BROWSER OR LIVELY", font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=5)
    row = ttk.Frame(body)
    row.pack(fill="x", pady=8)
    ttk.Button(row, text="Open full-world viewer", command=open_view).pack(side="left")
    ttk.Button(row, text="Copy Lively Web URL", command=copy_link).pack(side="left", padx=8)
    ttk.Button(row, text="Stop viewer", command=stop).pack(side="left")
    ttk.Checkbutton(body, text="Start the native viewer at Windows login (optional)",
                    variable=startup, command=toggle_startup).pack(anchor="w", pady=8)
    ttk.Separator(body).pack(fill="x", pady=12)
    ttk.Label(body, textvariable=status, wraplength=860).pack(anchor="w", pady=6)
    ttk.Label(body, text="The original world stays read-only. Your old cropped wallpaper and settings remain untouched.",
              wraplength=860).pack(anchor="w", pady=6)
    show_world()
    root.mainloop()
