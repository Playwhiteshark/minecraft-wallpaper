"""Read-only saved-mob snapshot for the independent native Vantage viewer.

Only selected nearby, named/tamed, model-supported saved creatures are sent
to a localhost-only scene overlay. Terrain meshing/visibility is not involved.
Actual textures come from an installed vanilla client JAR; exact entity-model
descriptions use the project's pre-existing, locally cached model adapter.
No UUIDs or owner IDs enter the browser scene.
"""
from __future__ import annotations

import json
import math
import os
import re
import zipfile
from pathlib import Path

from .backend import write_json_atomic
from mww.entities import MODEL_TYPES, scan_world_mobs
from mww.mob_assets import build_entity_assets

MOB_RADIUS = 160
MOB_LIMIT = 24
SCENE_NAME = "mww-mobs.json"
EXPORT_FIELDS = ("type", "pos", "yaw", "baby", "name", "tame",
                 "variant", "collar", "texture", "passes")


def installed_client_jar(world: Path, selected: Path | None = None) -> Path | None:
    """Find a vanilla entity-texture JAR, without spawning Minecraft/downloads."""
    if selected:
        return Path(selected).expanduser().resolve() if Path(selected).is_file() else None
    world = Path(world).resolve()
    roots = []
    if world.parent.name.casefold() == "saves":
        roots.append(world.parent.parent)
    appdata = os.environ.get("APPDATA")
    if appdata:
        roots.append(Path(appdata) / ".minecraft")
    roots.append(Path.home() / ".minecraft")
    seen = set()
    for base in roots:
        if base in seen:
            continue
        seen.add(base)
        versions = base / "versions"
        if not versions.is_dir():
            continue
        candidates = sorted(versions.glob("*/*.jar"), key=lambda p: p.stat().st_mtime_ns, reverse=True)[:40]
        for jar in candidates:
            try:
                if jar.stat().st_size > 90_000_000:
                    continue
                with zipfile.ZipFile(jar) as archive:
                    # Newer Minecraft variants need not include the old wolf
                    # filename; accept any real vanilla entity PNG in this JAR.
                    if any(info.filename.startswith("assets/minecraft/textures/entity/")
                           and info.filename.endswith(".png")
                           for info in archive.infolist()):
                        return jar
            except (OSError, zipfile.BadZipFile):
                continue
    return None


def rank_mobs(records: list, centre: tuple[float, float, float], limit: int = MOB_LIMIT) -> list:
    """Stable selection, independent of the surface/cave or shadow algorithm."""
    x, y, z = centre
    if not all(math.isfinite(float(v)) for v in centre):
        raise ValueError("Mob focus must contain finite coordinates")
    eligible = [r for r in records if r.get("renderable")
                and isinstance(r.get("pos"), (list, tuple))
                and len(r["pos"]) == 3]
    def order(mob):
        px, py, pz = (float(v) for v in mob["pos"])
        distance_sq = (px-x)**2 + (py-y)**2 + (pz-z)**2
        return (0 if mob.get("tame") == "tamed" else 1,
                0 if mob.get("name") else 1, distance_sq,
                mob.get("type", ""), mob.get("key", ""))
    eligible.sort(key=order)
    return eligible[:limit]


def build_mob_overlay(world: Path, dimension: str, cache: Path,
                      centre: tuple[float, float, float],
                      jar: Path | None = None, *,
                      fetch_missing_models: bool = True) -> dict:
    """Build a genuine local model/skin overlay; never fake unavailable mobs.

    Keeps the entities and the packed models in a separate JSON asset whose
    contract doesn't mention terrain tile formats, cave flags, or surface-depth.
    """
    world, cache = Path(world).resolve(), Path(cache).resolve()
    dimension_legacy = {"overworld": "overworld", "the_nether": "nether",
                        "the_end": "end"}[dimension]
    records = scan_world_mobs(world, dimension_legacy, centre, MOB_RADIUS)
    selected = rank_mobs(records, centre)
    jar = installed_client_jar(world, jar)
    pack, errors = build_entity_assets(
        selected, cache.parent.parent.parent / "mww-models", jar,
        fetch_missing=fetch_missing_models and jar is not None)
    visible = [{k: e[k] for k in EXPORT_FIELDS if k in e}
               for e in selected if e.get("texture") and e["type"] in pack["models"]]
    payload = {
        "schema": 1, "dimension": dimension,
        "entities": visible, "pack": pack,
        "counts": {"nearby": len(records), "important": len(selected),
                   "textured": len(visible)},
        "warnings": errors[:30],
    }
    cache.mkdir(parents=True, exist_ok=True)
    write_json_atomic(cache / SCENE_NAME, payload)
    return {"nearby": len(records), "important": len(selected),
            "textured": len(visible), "warnings": errors[:30]}


def empty_mob_overlay(cache: Path, dimension: str, warning: str) -> None:
    """Degrade explicitly if entity data/models are unavailable, never cubes."""
    cache.mkdir(parents=True, exist_ok=True)
    write_json_atomic(cache / SCENE_NAME, {
        "schema": 1, "dimension": dimension,
        "entities": [], "pack": {"version": 1, "models": {}, "textures": {}},
        "counts": {"nearby": 0, "important": 0, "textured": 0},
        "warnings": [warning[:200]],
    })
