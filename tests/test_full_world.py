"""Full-world orchestration tests; no downloaded executables or private worlds."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path

import pytest

from full_world import backend, config, service
from test_pipeline import make_world


def write_native_tile_scene(folder):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "tiles").mkdir(exist_ok=True)
    (folder / "tiles" / "t.0.0.vtile").write_bytes(b"VTL9\x01\x00")
    (folder / "manifest.json").write_text(
        json.dumps({"format": 2, "tiles": [{"x": 0, "z": 0}]}),
        encoding="utf-8")


def test_saved_world_identity_is_path_based_not_display_name(tmp_path):
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first, _ = make_world(first_dir)
    second, _ = make_world(second_dir)
    state = config.default_state()
    key1, w1 = config.register_world(state, first)
    key2, w2 = config.register_world(state, second)
    assert key1 != key2
    assert w1["name"] == w2["name"]
    assert len(state["worlds"]) == 2
    config.save_state(state, tmp_path)
    loaded = config.load_state(tmp_path)
    assert loaded["active"] == key2
    assert loaded["worlds"][key1]["path"] == str(first)


def test_camera_is_a_stable_bookmark_not_a_hardcoded_base():
    view = {"x": 1024, "y": 79, "z": -300, "distance": 150,
            "rotation": 1.1, "tilt": 0.45, "dimension": "overworld"}
    assert config.camera_url("http://127.0.0.1:8787/", view) == (
        "http://127.0.0.1:8787/#@1024,79,-300,150,1.1,0.45")
    assert "127.0.0.1" in service.viewer_url(8787)
    with pytest.raises(ValueError):
        service.viewer_url(1)
    with pytest.raises(ValueError):
        config.camera_hash({**view, "distance": 0})


def test_full_native_render_has_no_radius_or_sampling_and_is_atomic(monkeypatch, tmp_path):
    world_dir = tmp_path / "save"
    world_dir.mkdir()
    world = world_dir / "Real Saved World"
    world.mkdir()
    (world / "level.dat").write_bytes(b"fake for command shape test")
    engine = tmp_path / "vantage.exe"
    engine.write_bytes(b"fake exe; subprocess is mocked")
    monkeypatch.setattr(backend, "require_engine", lambda *a, **kw: engine)
    recorded = []

    def fake_render(command, **kw):
        recorded.append(command)
        assert command[1] == "render"
        assert Path(command[2]) == world.resolve()
        assert "--radius" not in command
        assert "--caves" in command and "full" in command
        out = Path(command[command.index("--out") + 1])
        write_native_tile_scene(out)
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(backend.subprocess, "run", fake_render)
    key = "0123456789abcdef01234567"
    engine_obj = backend.VantageConverter(tmp_path)
    first = engine_obj.render(world, key)
    assert first.tiles == 1 and first.dimensions == 1
    assert first.previous is None
    assert (first.directory / "tiles" / "t.0.0.vtile").is_file()
    second = engine_obj.render(world, key)
    assert second.previous == first.directory
    assert backend.active_render(tmp_path / "full-world" / key) == second.directory
    assert len(recorded) == 2
    assert (world / "level.dat").read_bytes() == b"fake for command shape test"

    def failed_render(command, **kw):
        return type("Result", (), {"returncode": 2})()
    monkeypatch.setattr(backend.subprocess, "run", failed_render)
    with pytest.raises(backend.ConversionError, match="conversion failed"):
        engine_obj.render(world, key)
    assert backend.active_render(tmp_path / "full-world" / key) == second.directory


def test_empty_or_incorrect_native_output_is_not_accepted(tmp_path):
    path = tmp_path / "bad"
    path.mkdir()
    with pytest.raises(backend.ConversionError):
        backend.validate_render(path)
    (path / "manifest.json").write_text('{"format":2,"tiles":[]}', encoding="utf-8")
    with pytest.raises(backend.ConversionError, match="zero real"):
        backend.validate_render(path)
    write_native_tile_scene(path)
    assert backend.validate_render(path) == (1, 1)


def test_download_refuses_unpinned_or_modified_archive(monkeypatch, tmp_path):
    import zipfile
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as f:
        f.writestr("vantage.exe", b"untrusted")
    raw = stream.getvalue()
    class FakeOpen:
        def __enter__(self): return io.BytesIO(raw)
        def __exit__(self, *args): return False
    monkeypatch.setattr(backend.platform, "system", lambda: "Windows")
    monkeypatch.setattr(backend.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(backend.urllib.request, "urlopen", lambda *a, **kw: FakeOpen())
    with pytest.raises(backend.ConversionError, match="SHA-256"):
        backend.require_engine(tmp_path, allow_download=True)
    assert not backend.backend_path(tmp_path).exists()


def test_never_terminate_unrecognised_pid(tmp_path, monkeypatch):
    backend.write_json_atomic(tmp_path / service.SERVICE_FILE, {
        "schema": 1, "pid": 424242, "binary": "/foreign/app",
        "render_dir": "/elsewhere", "port": 8787})
    monkeypatch.setattr(service, "_pid_matches", lambda record: False)
    assert service.stop_viewer(tmp_path)
    assert not (tmp_path / service.SERVICE_FILE).exists()


def test_no_saved_renderer_is_not_imagined(tmp_path):
    root = tmp_path / "full-world" / "0123456789abcdef01234567"
    root.mkdir(parents=True)
    assert backend.active_render(root) is None
    (root / "current.json").write_text('{"schema":1,"version":"../secrets"}')
    assert backend.active_render(root) is None
