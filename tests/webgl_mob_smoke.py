"""One headless WebGL2 smoke: real-model shader + selected mobs on a saved world.

Run only in CI (temporary Playwright/Chromium installation). No extra runtime
dependencies are installed by the application and no Mojang assets are bundled.
"""
from __future__ import annotations
import json
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / 'tests'))

from playwright.sync_api import sync_playwright
from test_pipeline import make_world, make_config, fake_png
from mww.entities import scan_world_mobs
from mww.mob_assets import MODEL_VERSION
import app


def run():
    with tempfile.TemporaryDirectory(prefix='mww-webgl-smoke-') as root:
        root = Path(root)
        os.environ['MWW_DATA_DIR'] = str(root / 'state')
        world, jar = make_world(root)
        selected = scan_world_mobs(world, 'overworld', (7,82,7), 32)
        selected = [e for e in selected if e['type'] in ('happy_ghast','cat')]
        config = make_config(world,jar)
        config['shots'][0]['mob_radius']=32
        config['shots'][0]['mob_ids']=[e['key'] for e in selected]
        with zipfile.ZipFile(jar,'a') as z:
            for path in ('ghast/happy_ghast.png','cat/cat_black.png'):
                z.writestr('assets/minecraft/textures/entity/' + path, fake_png())
        cache=app.data_root()/'mob-models'/MODEL_VERSION
        cache.mkdir(parents=True)
        for kind in ('cat','happy_ghast'):
            model={'id':'minecraft:'+kind,'layers':{'main':{
                'texture':[64,32],
                'textureLocation':'minecraft:textures/entity/'+
                   ('cat/cat_black.png' if kind=='cat' else 'ghast/happy_ghast.png'),
                'root':{'pose':{'offset':[0,0,0],'rotation':[0,0,0]},
                    'cubes':[{'origin':[-4,0,-4],'size':[8,8,8],'uv':[0,0]}],
                    'children':{}}}},'transform':[]}
            (cache/(kind+'.json')).write_text(json.dumps(model),encoding='utf-8')
        result=app.refresh(config,force=True,fetch_models=False)
        assert result['stats']['mobTextured']==len(selected)
        output=app.output_folder()
        html=(output/'index.html').read_text(encoding='utf-8')
        css=(output/'viewer.css').read_text(encoding='utf-8')
        html=html.replace('<link rel="stylesheet" href="viewer.css">',
                          '<style>'+css+'</style>')
        html=re.sub(r'<script defer src="[^"]+"></script>', '', html)
        scripts=''.join('<script>'+ (output/file).read_text(encoding='utf-8') + '</script>'
                        for file in ('scene-data.js','entity-models.js','viewer.js'))
        html=html.replace('</body>', scripts+'</body>')
        errors=[]
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,args=[
                '--use-gl=angle','--use-angle=swiftshader',
                '--enable-webgl','--disable-gpu-sandbox'])
            try:
                page=browser.new_page(viewport={'width':1280,'height':720})
                page.on('pageerror',lambda error: errors.append(str(error)))
                page.set_content(html,wait_until='load')
                page.wait_for_timeout(700)
                assert not errors, errors
                issue=page.locator('#error')
                assert issue.get_attribute('hidden') is not None, issue.inner_text()
                assert 'textured mobs' in page.locator('#location-title').inner_text()
                draws=page.evaluate("""() => {
                    window.__modelDraws=0;
                    const gl=document.getElementById('world').getContext('webgl2');
                    const draw=gl.drawArrays.bind(gl);
                    gl.drawArrays=(...args)=>{window.__modelDraws++;return draw(...args);};
                    document.getElementById('reset').click();
                    return true;
                }""")
                page.wait_for_timeout(700)
                draws=page.evaluate('window.__modelDraws')
                assert draws >= 2, f'Expected selected entity meshes to be drawn, got {draws}'
                assert not errors, errors
                print(f'WebGL real-texture model shader: {draws} draws; {len(selected)} selected entities')
            finally:
                browser.close()


if __name__ == '__main__':
    run()
