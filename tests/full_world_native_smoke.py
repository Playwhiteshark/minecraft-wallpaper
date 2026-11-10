"""Native upstream release smoke, run on CI Windows/Linux only.

Tests the exact pinned Vantage executable the desktop user will install and
checks that its embedded viewer actually exists. No Minecraft save is sent.
"""
from __future__ import annotations

import re
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from full_world.backend import VERSION, require_engine


def smoke():
    with tempfile.TemporaryDirectory(prefix="mww-vantage-smoke-") as tmp:
        root = Path(tmp)
        binary = require_engine(root, allow_download=True)
        help_run = subprocess.run([str(binary), "--help"], capture_output=True,
                                  text=True, timeout=20)
        output = help_run.stdout + help_run.stderr
        assert "render" in output and "serve" in output, output[-2500:]
        folder = root / "empty-render"
        folder.mkdir()
        (folder / "manifest.json").write_text('{"format":2,"tiles":[]}', encoding="utf-8")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        process = subprocess.Popen(
            [str(binary), "serve", str(folder), "--host", "127.0.0.1",
             "--port", str(port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            html = ""
            for _ in range(50):
                if process.poll() is not None:
                    raise AssertionError("Native Vantage process exited before serving")
                try:
                    with urllib.request.urlopen(
                            f"http://127.0.0.1:{port}/", timeout=0.5) as resp:
                        html = resp.read(30000).decode("utf-8", errors="replace")
                    break
                except OSError:
                    time.sleep(.1)
            assert "vantage" in html.casefold(), html[:1000]
            # If this is the fallback text-only server, the native binary was
            # built without the actual Three.js frontend and is NOT sufficient.
            assert re.search(r'<script\b', html, flags=re.I), (
                "Native release lacks embedded browser renderer: " + html[:1500])
            print(f"PASS: Vantage {VERSION} native embedded Three.js viewer on port {port}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    smoke()
