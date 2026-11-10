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
from .service import (set_login_startup, start_live_viewer, stop_viewer,
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
        world["jar"] = legacy.get("jar") or ""
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
    root.title("Minecraft Living World — Live Viewer")
    root.geometry("970x810")
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
    jar_var = tk.StringVar()
    dimension_var = tk.StringVar(value="overworld")
    fields = {k: tk.StringVar() for k in
              ("x", "y", "z", "distance", "rotation", "tilt")}
    startup = tk.BooleanVar(value=bool(registry.get("startup", False)))
    status = tk.StringVar(value="Ready. Open the camera-driven viewer; full-world export is optional.")
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
            info.set(f'World: {world["name"]} · {"Offline export ready" if current else "Live viewing available"} · {world["path"]}')
            jar_var.set(world.get("jar", ""))
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
                dimension_var.set(str(view.get("dimension", "overworld")))
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
        view["dimension"] = dimension_var.get()
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
            status.set("Registered the saved world. Select a camera and click Open viewer.")
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
            world["jar"] = jar_var.get().strip()
            save()
        except Exception as exc:
            messagebox.showerror("Full-world render", str(exc))
            return
        busy[0] = True
        build_button.configure(state="disabled")
        status.set("Preparing optional offline export. The live viewer does not require this step…")
        def notify(message):
            root.after(0, lambda: status.set(message))
        def worker():
            error, result, url = None, None, None
            try:
                result = converter.render(world_path, key, allow_download=True,
                                          client_jar=Path(world["jar"]) if world.get("jar") else None,
                                          on_progress=notify)
                url = None  # Keep the live viewer untouched; offline export is only a cacheable option.
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
                    status.set("Optional full-world export completed. Open viewer still uses on-demand streaming.")
            root.after(0, finish)
        threading.Thread(target=worker, daemon=True).start()

    def start_camera(action: str):
        if busy[0]:
            return
        try:
            view = persist_view()
            key, world, _ = current_world(registry, root_dir)
            world_path = Path(world["path"])
            jar_text = jar_var.get().strip()
            if world.get("jar", "") != jar_text:
                world["jar"] = jar_text
                save()
        except Exception as exc:
            messagebox.showerror("Camera", str(exc))
            return
        busy[0] = True
        build_button.configure(state="disabled")
        status.set("Opening Vantage live: reading saved chunks and preparing the first visible tile…")

        def worker():
            error, url = None, None
            try:
                address = start_live_viewer(
                    world_path, key, view.get("dimension", "overworld"),
                    int(registry.get("port", 8787)), root_dir,
                    client_jar=Path(jar_text) if jar_text else None,
                    allow_download=True)
                url = camera_url(address, view)
            except Exception as exc:
                error = str(exc)

            def finish():
                busy[0] = False
                build_button.configure(state="normal")
                if error:
                    status.set("Live viewer failed. No fabricated terrain was substituted.")
                    messagebox.showerror("Vantage live viewer", error)
                    return
                if action == "open":
                    webbrowser.open(url)
                    status.set("Opened the native on-demand 3D renderer in the browser.")
                else:
                    root.clipboard_clear()
                    root.clipboard_append(url)
                    root.update()
                    status.set("Copied the live camera URL for Lively's Web Page wallpaper.")
                    messagebox.showinfo(
                        "Lively Wallpaper",
                        "Web URL copied:\n" + url +
                        "\n\nLively → Add Wallpaper → Web Page. "
                        "Leave this native viewer running while the wallpaper is displayed.")
            root.after(0, finish)
        threading.Thread(target=worker, daemon=True).start()

    def open_view():
        start_camera("open")

    def copy_link():
        start_camera("copy")

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
            base["dimension"] = dimension_var.get()
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
    ttk.Label(body, text="Camera-driven Vantage streaming · Native Minecraft geometry · Three.js GPU rendering · Lively",
              font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 15))

    ttk.Label(body, text="1   SAVED WORLD", font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=5)
    row = ttk.Frame(body)
    row.pack(fill="x")
    world_combo = ttk.Combobox(row, textvariable=selected_world, state="readonly")
    world_combo.pack(side="left", fill="x", expand=True)
    world_combo.bind("<<ComboboxSelected>>", select_world)
    ttk.Button(row, text="Browse…", command=browse).pack(side="left", padx=(6, 0))
    ttk.Button(row, text="Discover", command=discover).pack(side="left", padx=(6, 0))
    ttk.Label(body, textvariable=info, wraplength=865).pack(anchor="w", pady=(7, 8))
    row = ttk.Frame(body)
    row.pack(fill="x", pady=(0, 9))
    ttk.Label(row, text="Minecraft client JAR", width=20).pack(side="left")
    ttk.Entry(row, textvariable=jar_var).pack(side="left", fill="x", expand=True)
    def choose_jar():
        jar = filedialog.askopenfilename(
            title="Optional: choose installed Minecraft client version JAR",
            filetypes=[("Minecraft client JAR", "*.jar")])
        if jar:
            jar_var.set(jar)
    ttk.Button(row, text="Browse…", command=choose_jar).pack(side="left", padx=(5, 0))
    ttk.Label(body, text="Optional. Leave empty to let Vantage discover your installed vanilla assets.",
              wraplength=865).pack(anchor="w", pady=(0, 8))

    ttk.Label(body, text="2   OPTIONAL OFFLINE EXPORT", font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=5)
    ttk.Label(body, text="Optional complete-world export. Live viewing streams camera-visible tiles and meshes the real Overworld surface (16-block depth; no deep underground columns).",
              wraplength=860).pack(anchor="w", pady=3)
    build_button = ttk.Button(body, text="Export full world (optional)", command=run_build)
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
    row = ttk.Frame(body)
    row.pack(fill="x", pady=5)
    ttk.Label(row, text="Dimension", width=18).pack(side="left")
    ttk.Combobox(row, textvariable=dimension_var,
                 values=("overworld", "the_nether", "the_end"),
                 state="readonly", width=30).pack(side="left")
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

    ttk.Label(body, text="4   OPEN LIVE VIEW IN BROWSER OR LIVELY", font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=5)
    row = ttk.Frame(body)
    row.pack(fill="x", pady=8)
    ttk.Button(row, text="Open live viewer", command=open_view).pack(side="left")
    ttk.Button(row, text="Copy Lively Web URL", command=copy_link).pack(side="left", padx=8)
    ttk.Button(row, text="Stop viewer", command=stop).pack(side="left")
    ttk.Checkbutton(body, text="Start the native viewer at Windows login (optional)",
                    variable=startup, command=toggle_startup).pack(anchor="w", pady=8)
    ttk.Separator(body).pack(fill="x", pady=12)
    ttk.Label(body, textvariable=status, wraplength=860).pack(anchor="w", pady=6)
    ttk.Label(body, text="No full-world build is needed. Vantage only bakes requested tiles and retains a private cache; the source world remains read-only.",
              wraplength=860).pack(anchor="w", pady=6)
    def on_close():
        if busy[0]:
            messagebox.showwarning("Conversion is active",
                                   "The saved-world conversion is active. Close after it completes to protect the output.")
            return
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_close)
    show_world()
    root.mainloop()
