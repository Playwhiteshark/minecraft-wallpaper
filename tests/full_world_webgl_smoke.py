"""End-to-end WebGL smoke on an actual native-converted two-chunk world.

The test serves Vantage output, opens its real Three.js viewer, and confirms
both a chunk-tile network response and GPU draw calls. It is not a fake
HTML renderer, synthetic geometry fallback or screenshot-only assertion.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_pipeline import make_world
from full_world_convert_smoke import minimal_assets, second_chunk
from full_world.backend import require_engine, validate_render


def smoke():
    with tempfile.TemporaryDirectory(prefix="mww-full-world-webgl-") as tmp:
        folder=Path(tmp)
        fixtures=folder/"fixture"
        fixtures.mkdir()
        world,_=make_world(fixtures)
        second_chunk(world/"region"/"r.0.0.mca")
        assets=minimal_assets(folder)
        engine=require_engine(folder,allow_download=True)
        output=folder/"rendered"
        run=subprocess.run([str(engine),"render",str(world),"--out",str(output),
                            "--assets",str(assets),"--caves","full",
                            "--memory","512","--threads","1"],
                           capture_output=True,text=True,timeout=180)
        assert run.returncode==0,(run.stdout+run.stderr)[-6000:]
        assert validate_render(output)[1]>0
        with socket.socket() as s:
            s.bind(("127.0.0.1",0))
            port=s.getsockname()[1]
        serve=subprocess.Popen([str(engine),"serve",str(output),
                                "--host","127.0.0.1","--port",str(port)],
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            base=f"http://127.0.0.1:{port}/"
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True,args=[
                    "--use-gl=angle","--use-angle=swiftshader",
                    "--enable-webgl","--disable-gpu-sandbox"])
                try:
                    page=browser.new_page(viewport={"width":1280,"height":720})
                    # Install instrumentation before any upstream JS creates GL.
                    page.add_init_script("""(() => {
                      window.__mwwDraws=0;
                      const proto=WebGL2RenderingContext.prototype;
                      for(const key of ['drawElements','drawElementsInstanced','drawArrays','drawArraysInstanced']){
                        const old=proto[key];if(!old)continue;
                        proto[key]=function(...args){window.__mwwDraws++;return old.apply(this,args);};
                      }
                    })();""")
                    seen_tiles=[]
                    errors=[]
                    page.on("response",lambda res:
                        seen_tiles.append((res.url,res.status)) if ".vtile" in res.url else None)
                    page.on("pageerror",lambda err:errors.append(str(err)))
                    page.goto(base,wait_until="domcontentloaded",timeout=30000)
                    page.wait_for_function(
                        "() => document.querySelector('canvas') && window.__mwwDraws > 0",
                        timeout=45000)
                    for i in range(30):
                        if any(status==200 for _,status in seen_tiles):break
                        page.wait_for_timeout(200)
                    assert any(status==200 for _,status in seen_tiles),seen_tiles
                    assert not errors,errors
                    draws=page.evaluate("window.__mwwDraws")
                    print(f"PASS: native two-chunk mesh streamed to embedded Three.js; {draws} WebGL draws, tile HTTP 200")
                finally:
                    browser.close()
        finally:
            serve.terminate()
            try:
                serve.wait(timeout=8)
            except subprocess.TimeoutExpired:
                serve.kill()
                serve.wait(timeout=5)


if __name__=="__main__":
    smoke()
