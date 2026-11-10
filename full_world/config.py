"""Machine-local world registry, camera bookmarks and settings.

A world's display title is not an identifier. All paths/coordinates stay in
the user's private data folder; public source contains no personal world data.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .backend import active_render, write_json_atomic

DEFAULT_PORT = 8787


def state_dir() -> Path:
    override = os.environ.get("MWW_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        return Path.home() / "COMPUTER STUFF" / "Minecraft Living World Wallpaper"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "minecraft-living-wallpaper"


def world_key(path: Path) -> str:
    path = Path(path).expanduser().resolve()
    value = os.path.normcase(str(path))
    # normcase on Unix does not alter case. Windows paths are case-insensitive.
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def default_state():
    return {"schema": 1, "active": "", "port": DEFAULT_PORT,
            "startup": False, "worlds": {}}


def load_state(root: Path | None = None) -> dict:
    root = root or state_dir()
    path = root / "full-world.json"
    if not path.exists():
        return default_state()
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != 1 or not isinstance(data.get("worlds"), dict):
        raise ValueError("Unsupported full-world registry. The original file was not changed.")
    return data


def save_state(state: dict, root: Path | None = None) -> None:
    if state.get("schema") != 1:
        raise ValueError("Registry schema mismatch")
    root = root or state_dir()
    write_json_atomic(root / "full-world.json", state)


def register_world(state: dict, path: Path) -> tuple[str, dict]:
    from mww.nbt import level_info  # Reuse the existing metadata reader only.
    path = Path(path).expanduser().resolve()
    if not (path / "level.dat").is_file():
        raise ValueError("Selected folder has no Minecraft Java level.dat")
    key = world_key(path)
    current = state.setdefault("worlds", {}).get(key)
    if current is None:
        info = level_info(path)
        point = info.get("player") or info.get("spawn") or [0, 90, 0]
        current = {
            "path": str(path), "name": info.get("name") or path.name,
            "views": [{
                "name": "Home", "dimension": "overworld",
                "x": round(float(point[0]), 1),
                "y": round(float(point[1]), 1),
                "z": round(float(point[2]), 1),
                "distance": 120, "rotation": 0.7, "tilt": 0.5,
            }],
        }
        state["worlds"][key] = current
    elif Path(current["path"]).resolve() != path:
        raise ValueError("World location identity conflict")
    state["active"] = key
    return key, current


def current_world(state: dict, root: Path | None = None):
    key = state.get("active")
    world = state.get("worlds", {}).get(key)
    if not world:
        raise ValueError("Choose and register a Minecraft save first")
    folder = (root or state_dir()) / "full-world" / key
    return key, world, active_render(folder)


def camera_hash(view: dict) -> str:
    """Vantage share-link camera hash: x,y,z,dist,rot,tilt."""
    vals = [float(view[k]) for k in ("x", "y", "z", "distance", "rotation", "tilt")]
    import math
    if not all(math.isfinite(v) for v in vals) or vals[3] <= 0:
        raise ValueError("Camera values must be finite; distance must be positive")
    dimension = str(view.get("dimension", "overworld"))
    if dimension not in ("overworld", "the_nether", "the_end"):
        raise ValueError("Unknown camera dimension")
    prefix = "" if dimension == "overworld" else dimension
    return "#" + prefix + "@" + ",".join(format(v, ".6g") for v in vals)


def camera_url(base: str, view: dict) -> str:
    return base.rstrip("/") + "/" + camera_hash(view)
