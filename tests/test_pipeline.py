"""Synthetic modern Java world tests: no copyrighted assets or private saves."""
from __future__ import annotations

import gzip
import base64
import json
import math
import os
import struct
import uuid
import zipfile
import zlib
from pathlib import Path

import pytest

import app
from mww.nbt import RegionReader, WorldFormatError, block_name, block_properties, level_info, parse_nbt, unpack_palette
from mww.scene import build_scene, publish_scene, verify_scene_script, slab_shape, lights_near, dimension_directory


def u16(value):return struct.pack('>H',value)
def i32(value):return struct.pack('>i',value)
def lng(value):return struct.pack('>q',value)


def nbt_str(value):
    raw=value.encode('utf-8');return u16(len(raw))+raw


def payload(kind,value):
    if kind==1:return struct.pack('>b',value)
    if kind==2:return struct.pack('>h',value)
    if kind==3:return i32(value)
    if kind==4:return lng(value)
    if kind==5:return struct.pack('>f',value)
    if kind==6:return struct.pack('>d',value)
    if kind==8:return nbt_str(value)
    if kind==9:
        subtype,items=value
        return bytes([subtype])+i32(len(items))+b''.join(payload(subtype,x) for x in items)
    if kind==10:
        return b''.join(bytes([k])+nbt_str(name)+payload(k,v) for name,k,v in value)+b'\0'
    if kind==11:return i32(len(value))+struct.pack('>'+str(len(value))+'i',*value)
    if kind==12:return i32(len(value))+struct.pack('>'+str(len(value))+'q',*value)
    raise ValueError(kind)


def root(items):return b'\x0a'+u16(0)+payload(10,items)


def region(path,chunk):
    content=zlib.compress(chunk)
    data=i32(len(content)+1)+b'\x02'+content
    sectors=math.ceil(len(data)/4096)
    header=bytearray(8192)
    header[0:4]=((2<<8)|sectors).to_bytes(4,'big')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(bytes(header)+data.ljust(sectors*4096,b'\0'))


def fake_png():
    def chunk(kind,data):return i32(len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    raw=b''.join(b'\0'+b'\x85\x95\x72' * 16 for _ in range(16))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',16,16,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')


def make_world(tmp_path):
    world=tmp_path/'Synthetic Example World';world.mkdir()
    data=[('DataVersion',3,4000),('LevelName',8,'Synthetic Test World'),
          ('SpawnX',3,7),('SpawnY',3,83),('SpawnZ',3,7),
          ('Player',10,[('Pos',9,(6,[7.0,82.0,7.0]))])]
    (world/'level.dat').write_bytes(gzip.compress(root([('Data',10,data)])))
    names=['minecraft:air','minecraft:stone','minecraft:oak_planks','minecraft:glass','minecraft:lantern']
    values=[0]*4096
    def at(x,y,z,p):values[(y%16)*256+z*16+x]=p
    for x in range(16):
        for z in range(16):at(x,0,z,1)
    # Four inner-facing walls + roof; closed room with actual air inside.
    for x in range(3,11):
        for z in range(3,11):
            at(x,5,z,2)
            for y in range(1,5):
                if x in (3,10) or z in (3,10):at(x,y,z,2)
    at(7,2,3,3);at(8,3,7,4)
    packed=[]
    for i in range(0,4096,16):
        number=sum(v<<(j*4) for j,v in enumerate(values[i:i+16]))
        packed.append(number if number<(1<<63) else number-(1<<64))
    palette=[('Name',8,name) for name in names]
    section=[('Y',1,5),('block_states',10,[
        ('palette',9,(10,[[('Name',8,name)] for name in names])),
        ('data',12,packed)
    ])]
    # The generated chunk contains a real packed heightmap, just like vanilla
    # region files. The single fixture section begins at Y=80 (section 5).
    heights=[]
    for first in range(0,256,12):
        encoded=sum(1 << (i*5) for i in range(min(12,256-first)))
        heights.append(encoded if encoded<2**63 else encoded-2**64)
    chunk=root([('xPos',3,0),('zPos',3,0),('sections',9,(10,[section])),
                ('Heightmaps',10,[('WORLD_SURFACE',12,heights)])])
    region(world/'region'/'r.0.0.mca',chunk)
    entities=[]
    for i,kind in enumerate(['happy_ghast','happy_ghast','horse','wolf','cat']):
        entities.append([('id',8,'minecraft:'+kind),('Pos',9,(6,[4.0+i,83.0,6.0])),
                         ('Rotation',9,(5,[0.0,0.0])),('UUID',11,[i,0,0,0])])
    entity_chunk=root([('Entities',9,(10,entities)),('Position',11,[0,0])])
    region(world/'entities'/'r.0.0.mca',entity_chunk)
    jar=tmp_path/'synthetic-client.jar'
    with zipfile.ZipFile(jar,'w') as z:
        for tex in ['stone','oak_planks','glass','lantern']:
            z.writestr(f'assets/minecraft/textures/block/{tex}.png',fake_png())
    return world,jar


def make_config(world,jar):
    cfg=app.default_config()
    cfg['world']=str(world)
    cfg['jar']=str(jar)
    cfg['shots'][0].update({'x':7,'y':82,'z':7,'radius':8,'below':4,'above':8,'light':'golden'})
    return cfg


def test_palette_padded_and_root():
    assert unpack_palette([0]*256,5,4000)==[0]*4096
    assert parse_nbt(root([('thing',8,'hello')]))['thing']=='hello'
    with pytest.raises(WorldFormatError):parse_nbt(b'\x0a\x00\x00\x08\x00')


def test_full_refresh_and_unchanged(tmp_path,monkeypatch):
    world,jar=make_world(tmp_path)
    monkeypatch.setenv('MWW_DATA_DIR',str(tmp_path/'owned-output'))
    cfg=make_config(world,jar)
    import hashlib
    source_files=[world/'level.dat',world/'region'/'r.0.0.mca',world/'entities'/'r.0.0.mca']
    original=[hashlib.sha256(p.read_bytes()).digest() for p in source_files]
    first=app.refresh(cfg,force=True)
    assert first['status']=='rendered'
    assert first['stats']['animals']==5
    assert first['stats']['blocks']>100
    assert first['stats']['faces']>50
    assert first['stats']['landscapeSamples'] > 0
    html=app.output_folder()/'index.html'
    assert 'MWW-OWNED-WALLPAPER-V1' in html.read_text()
    data=verify_scene_script((app.output_folder()/'scene-data.js').read_bytes())
    assert len(data['entities'])==5
    assert any(x['type']=='happy_ghast' for x in data['entities'])
    assert any(t.get('png') for t in data['tiles'])
    assert data['opaque'] and data['alpha']
    assert data['landscape']['present'] > 0
    second=app.refresh(cfg)
    assert second['status']=='unchanged'
    assert original==[hashlib.sha256(p.read_bytes()).digest() for p in source_files]
    assert not list(app.output_folder().glob('.mww-*'))


def test_rollback_on_corrupted_source(tmp_path,monkeypatch):
    world,jar=make_world(tmp_path)
    monkeypatch.setenv('MWW_DATA_DIR',str(tmp_path/'owned-output'))
    cfg=make_config(world,jar)
    app.refresh(cfg,force=True)
    active=app.output_folder()/'scene-data.js'
    original=active.read_bytes()
    (world/'region'/'r.0.0.mca').write_bytes(b'garbage')
    with pytest.raises(WorldFormatError):app.refresh(cfg,force=True)
    assert active.read_bytes()==original


def test_refuse_foreign_lively_project(tmp_path):
    p=tmp_path/'a-folder';p.mkdir();(p/'index.html').write_text('<html>Other app</html>')
    with pytest.raises(ValueError,match='not an imported'):
        app.verify_owned_lively_project(p)



def test_owned_lively_copy_receives_new_viewer_and_scene(tmp_path, monkeypatch):
    world, jar = make_world(tmp_path)
    monkeypatch.setenv('MWW_DATA_DIR', str(tmp_path / 'owned-output'))
    config = make_config(world, jar)
    app.refresh(config, force=True)
    output = app.output_folder()
    imported = tmp_path / 'imported-lively'
    imported.mkdir()
    for name in ('index.html', 'viewer.js', 'scene-data.js'):
        (imported / name).write_bytes((output / name).read_bytes())
    (imported / 'viewer.js').write_text(
        (imported / 'viewer.js').read_text(encoding='utf-8') + '\\n// stale viewer', encoding='utf-8')
    (imported / 'scene-data.js').write_text('stale scene')
    config['lively_project'] = str(imported)
    assert app.sync_lively_project(config)
    for name in ('viewer.js', 'scene-data.js'):
        assert (imported / name).read_bytes() == (output / name).read_bytes()

def test_scene_rejects_bad_payload():
    with pytest.raises(ValueError):verify_scene_script(b'window.MWW_SCENE = {};')


def test_world_bounds(tmp_path):
    world,jar=make_world(tmp_path)
    cfg=make_config(world,jar)
    cfg['shots'][0]['radius']=100
    with pytest.raises(ValueError):build_scene(world,cfg['shots'][0])

def test_no_implicit_spawn_fallback_when_player_missing(tmp_path):
    world=tmp_path/'No Player';world.mkdir()
    data=[('DataVersion',3,4000),('SpawnX',3,0),('SpawnY',3,80),('SpawnZ',3,0)]
    (world/'level.dat').write_bytes(gzip.compress(root([('Data',10,data)])))
    info=level_info(world)
    assert info['spawn']==[0,80,0]
    assert info['player'] is None
    assert info['player_source'] is None
    assert info['player_candidates']==[]


def test_playerdata_location_used_if_unique(tmp_path):
    world=tmp_path/'One Player';world.mkdir()
    data=[('DataVersion',3,4000),('SpawnX',3,0),('SpawnY',3,80),('SpawnZ',3,0)]
    (world/'level.dat').write_bytes(gzip.compress(root([('Data',10,data)])))
    folder=world/'playerdata';folder.mkdir()
    (folder/'someone.dat').write_bytes(gzip.compress(root([('Pos',9,(6,[-12.25,69.9,238.1]))])))
    info=level_info(world)
    assert info['spawn']==[0,80,0]
    assert info['player']==[-13,69,238]
    assert info['player_source']=='playerdata'


def test_playerdata_multiple_ambiguous_does_not_pick_first(tmp_path):
    world=tmp_path/'Multiple Players';world.mkdir()
    data=[('DataVersion',3,4000),('SpawnX',3,0),('SpawnY',3,80),('SpawnZ',3,0)]
    (world/'level.dat').write_bytes(gzip.compress(root([('Data',10,data)])))
    folder=world/'playerdata';folder.mkdir()
    for name,coordinates in [('alpha',[8.,80.,9.]),('beta',[111.,50.,222.])]:
        (folder/(name+'.dat')).write_bytes(gzip.compress(root([('Pos',9,(6,coordinates))])))
    info=level_info(world)
    assert info['player'] is None
    assert len(info['player_candidates'])==2
    assert info['player_candidates'][0]['pos']==[8,80,9]


def test_level_dat_player_overrides_playerdata(tmp_path):
    world=tmp_path/'Integrated';world.mkdir()
    data=[('DataVersion',3,4000),('Player',10,[('Pos',9,(6,[5.7,69.,11.2]))]),
          ('SpawnX',3,0),('SpawnY',3,80),('SpawnZ',3,0)]
    (world/'level.dat').write_bytes(gzip.compress(root([('Data',10,data)])))
    assert level_info(world)['player']==[5,69,11]


def test_minecraft_26_1_saved_player_and_full_refresh(tmp_path, monkeypatch):
    """New storage: singleplayer_uuid -> players/data; chunk directories under dimensions."""
    world, jar = make_world(tmp_path)
    uid = uuid.UUID('12345678-1234-5678-abcd-1234567890ab')
    signed = list(struct.unpack('>iiii', uid.bytes))
    data = [('DataVersion', 3, 5000), ('LevelName', 8, 'New Format'),
            ('SpawnX', 3, 0), ('SpawnY', 3, 80), ('SpawnZ', 3, 0),
            ('singleplayer_uuid', 11, signed)]
    (world / 'level.dat').write_bytes(gzip.compress(root([('Data', 10, data)])))
    folder = world / 'players' / 'data'
    folder.mkdir(parents=True)
    (folder / (str(uid) + '.dat')).write_bytes(
        gzip.compress(root([('Pos', 9, (6, [-421.6, 86.2, 123.4]))])))
    dimension = world / 'dimensions' / 'minecraft' / 'overworld'
    dimension.mkdir(parents=True)
    (world / 'region').rename(dimension / 'region')
    (world / 'entities').rename(dimension / 'entities')
    info = level_info(world)
    assert info['spawn'] == [0, 80, 0]
    assert info['player'] == [-422, 86, 123]
    assert info['player_source'] == 'players/data (singleplayer_uuid)'
    assert dimension_directory(world, 'overworld') == dimension
    monkeypatch.setenv('MWW_DATA_DIR', str(tmp_path / 'result'))
    cfg = make_config(world, jar)
    output = app.refresh(cfg, force=True)
    assert output['status'] == 'rendered'
    assert output['stats']['blocks'] > 100
    assert output['stats']['animals'] == 5
    assert app.refresh(cfg)['status'] == 'unchanged'


def test_minecraft_26_1_uuid_selects_correct_player(tmp_path):
    world = tmp_path / 'Two Players'
    world.mkdir()
    uid = uuid.UUID('ffffffff-0000-0000-0000-000000000001')
    data = [('DataVersion', 3, 5000), ('singleplayer_uuid', 8, str(uid)),
            ('SpawnX', 3, 0), ('SpawnY', 3, 80), ('SpawnZ', 3, 0)]
    (world / 'level.dat').write_bytes(gzip.compress(root([('Data', 10, data)])))
    folder = world / 'players' / 'data'
    folder.mkdir(parents=True)
    for name, pos in [(str(uid), [91., 72., 203.]),
                      ('00000000-0000-0000-0000-000000000002', [2., 80., 3.])]:
        (folder / (name + '.dat')).write_bytes(
            gzip.compress(root([('Pos', 9, (6, pos))])))
    info = level_info(world)
    assert info['player'] == [91, 72, 203]
    assert info['player_source'] == 'players/data (singleplayer_uuid)'


def test_modern_nether_end_overworld_paths(tmp_path):
    world = tmp_path / 'New Worlds'
    for name in ('the_nether', 'the_end'):
        (world / 'dimensions' / 'minecraft' / name / 'region').mkdir(parents=True)
    assert dimension_directory(world, 'nether') == world / 'dimensions' / 'minecraft' / 'the_nether'
    assert dimension_directory(world, 'end') == world / 'dimensions' / 'minecraft' / 'the_end'
    assert dimension_directory(world, 'overworld') == world / 'dimensions' / 'minecraft' / 'overworld'


def test_new_layout_unmatched_uuid_does_not_use_wrong_player(tmp_path):
    world = tmp_path / 'Unmatched Player'
    world.mkdir()
    data = [('DataVersion', 3, 5000), ('singleplayer_uuid', 8, '12345678-1234-5678-abcd-1234567890ab')]
    (world / 'level.dat').write_bytes(gzip.compress(root([('Data', 10, data)])))
    folder = world / 'players' / 'data'
    folder.mkdir(parents=True)
    (folder / '00000000-0000-0000-0000-000000000001.dat').write_bytes(
        gzip.compress(root([('Pos', 9, (6, [2., 81., 4.]))])))
    info = level_info(world)
    assert info['player'] is None
    assert len(info['player_candidates']) == 1

def test_java_26_3_palette_entries_and_old_properties():
    assert block_name('minecraft:stone') == 'minecraft:stone'
    assert block_name({'': 'minecraft:stone'}) == 'minecraft:stone'
    assert block_name({'id': 'minecraft:oak_slab',
                       'properties': {'type': 'top'}}) == 'minecraft:oak_slab'
    assert block_name({'Name': 'minecraft:oak_slab',
                       'Properties': {'type': 'bottom'}}) == 'minecraft:oak_slab'
    assert block_properties({'properties': {'type': 'top'}}) == {'type': 'top'}
    assert slab_shape('minecraft:oak_slab',
                      {'id': 'minecraft:oak_slab', 'properties': {'type': 'top'}}) == 1
    assert slab_shape('minecraft:oak_slab',
                      {'Name': 'minecraft:oak_slab', 'Properties': {'type': 'bottom'}}) == 2
    assert lights_near({(1, 80, 1): {
        'id': 'minecraft:redstone_lamp', 'properties': {'lit': 'false'}
    }}, (0, 80, 0)) == []
    with pytest.raises(WorldFormatError):
        block_name({'unrecognized': 'minecraft:stone'})


def test_java_26_3_compound_palette_refresh(tmp_path, monkeypatch):
    world, jar = make_world(tmp_path)
    # Real 26.3 still uses at least FOUR bits per block-state index.
    packed = [0] * 256
    local_index = (2 * 256) + (7 * 16) + 7
    packed[local_index // 16] = 1 << ((local_index % 16) * 4)
    palette = [[('', 8, 'minecraft:air')],
               [('id', 8, 'minecraft:oak_slab'),
                ('properties', 10, [('type', 8, 'top')])]]
    section = [('Y', 1, 5), ('block_states', 10, [
        ('palette', 9, (10, palette)), ('data', 12, packed)
    ])]
    chunk = root([('DataVersion', 3, 5023), ('xPos', 3, 0), ('zPos', 3, 0),
                  ('sections', 9, (10, [section]))])
    region(world / 'region' / 'r.0.0.mca', chunk)
    monkeypatch.setenv('MWW_DATA_DIR', str(tmp_path / 'out'))
    cfg = make_config(world, jar)
    result = app.refresh(cfg, force=True)
    assert result['status'] == 'rendered'
    assert result['stats']['blocks'] == 1
    assert result['stats']['faces'] == 6


def test_java_26_3_plain_string_palette_refresh(tmp_path, monkeypatch):
    world, jar = make_world(tmp_path)
    packed = [0] * 256
    index = (2 * 256) + (7 * 16) + 7
    packed[index // 16] = 1 << ((index % 16) * 4)
    section = [('Y', 1, 5), ('block_states', 10, [
        ('palette', 9, (8, ['minecraft:air', 'minecraft:stone'])),
        ('data', 12, packed)
    ])]
    chunk = root([('DataVersion', 3, 5023), ('xPos', 3, 0), ('zPos', 3, 0),
                  ('sections', 9, (10, [section]))])
    region(world / 'region' / 'r.0.0.mca', chunk)
    monkeypatch.setenv('MWW_DATA_DIR', str(tmp_path / 'out'))
    result = app.refresh(make_config(world, jar), force=True)
    assert result['stats']['blocks'] == 1


def test_saved_mob_picker_uses_stable_uuid_selection(tmp_path, monkeypatch):
    from mww.entities import scan_world_mobs
    world, jar = make_world(tmp_path)
    monkeypatch.setenv('MWW_DATA_DIR', str(tmp_path / 'owned-output'))
    mobs = scan_world_mobs(world, 'overworld', (7,82,7), 32)
    assert len(mobs) == 5
    assert all(e['stable'] and e['key'].startswith('uuid:') for e in mobs)
    cat = next(e for e in mobs if e['type'] == 'cat')
    assert cat['name'] == '' and cat['tame'] == 'unknown'
    cfg = make_config(world, jar)
    missing = 'uuid:ffffffff-ffff-ffff-ffff-ffffffffffff'
    cfg['shots'][0]['mob_ids'] = [cat['key'], missing]
    cfg['shots'][0]['mob_radius'] = 32
    result = app.refresh(cfg, force=True)
    scene = verify_scene_script((app.output_folder() / 'scene-data.js').read_bytes())
    assert result['stats']['mobSelected'] == 1
    assert result['stats']['mobMissing'] == 1
    assert result['stats']['mobFound'] == 5
    assert [mob['type'] for mob in scene['entities']] == ['cat']
    assert 'uuid:' not in (app.output_folder() / 'scene-data.js').read_text(encoding='utf-8')
    assert cfg['shots'][0]['mob_ids'] == [cat['key'], missing]


def test_named_tamed_mobs_sort_first_with_unknown_status(monkeypatch, tmp_path):
    from mww import entities
    def mob(name, uid, label=None, owner=None, variant=None):
        data = {'id':'minecraft:'+name, 'UUID':[uid,0,0,0],
                'Pos':[3.0,81.0,3.0], 'Rotation':[0.0,0.0]}
        if label: data['CustomName']=json.dumps({'text':label})
        if owner: data['Owner']=[99,0,0,0]
        if variant: data['variant']=variant
        return data
    records = [
        mob('pig',1), mob('cat',2,'Whiskers',True,'minecraft:calico'),
        mob('wolf',3,owner=True), mob('sheep',4,'Daisy'),
        {'id':'minecraft:item','Pos':[3.,81.,3.]},
    ]
    class Reader:
        def __init__(self, path): pass
        def __enter__(self): return self
        def __exit__(self,*a): return None
        def chunk(self,cx,cz):return {'Entities':records} if cx==cz==0 else None
    monkeypatch.setattr(entities,'RegionReader',Reader)
    result=entities.scan_saved_entities(tmp_path,
        (0,15,None,None,0,15),all_heights=True)
    assert [x['type'] for x in result]==['cat','sheep','wolf','pig']
    assert result[0]['name']=='Whiskers'
    assert result[0]['variant']=='minecraft:calico'
    assert result[0]['tame']=='tamed'
    assert result[-1]['tame']=='unknown'


def test_genuine_mob_asset_package_from_local_jar_and_cached_model(tmp_path):
    from mww.mob_assets import build_entity_assets, MODEL_VERSION
    cache=tmp_path/'cache'
    target=cache/MODEL_VERSION/'cat.json'
    target.parent.mkdir(parents=True)
    model={'id':'minecraft:cat','layers':{'main':{
        'texture':[64,32],
        'textureLocation':'minecraft:textures/entity/cat/cat_black.png',
        'root':{'pose':{'offset':[0,0,0],'rotation':[0,0,0]},
                'cubes':[{'origin':[-3,0,-3],'size':[6,6,6],'uv':[0,0]}],
                'children':{}}}}, 'transform':[]}
    target.write_text(json.dumps(model),encoding='utf-8')
    jar=tmp_path/'local-client.jar'
    with zipfile.ZipFile(jar,'w') as z:
        z.writestr('assets/minecraft/textures/entity/cat/cat_calico.png',fake_png())
    entity={'type':'cat','pos':[4,82,4],'baby':False,'yaw':0,
            'tame':'unknown','variant':'minecraft:calico','collar':None}
    pack,errors=build_entity_assets([entity],cache,jar,fetch_missing=False)
    assert errors==[]
    assert entity['texture']=='minecraft:textures/entity/cat/cat_calico.png'
    assert pack['models']['cat']==model
    assert base64.b64decode(pack['textures'][entity['texture']]).startswith(b'\x89PNG')


def test_no_minecraft_model_is_redistributed_in_source(tmp_path):
    from mww.mob_assets import load_model
    model,error=load_model('../not_a_model',tmp_path,fetch_missing=False)
    assert model is None and error


def test_same_display_name_worlds_do_not_share_mob_choices(tmp_path, monkeypatch):
    import shutil
    from mww.entities import scan_world_mobs
    first_folder=tmp_path/'one'
    first_folder.mkdir()
    world,jar=make_world(first_folder)
    copy=tmp_path/'two'/'Synthetic Example World'
    copy.parent.mkdir()
    shutil.copytree(world,copy)
    assert level_info(world)['name']==level_info(copy)['name']
    key1=app.world_selection_key(world)
    key2=app.world_selection_key(copy)
    assert key1 != key2
    selected=next(m['key'] for m in scan_world_mobs(world,'overworld',(7,82,7),32)
                  if m['type']=='cat')
    cfg=make_config(world,jar)
    cfg['shots'][0]['mobs_by_world']={key1:[selected],key2:[]}
    cfg['shots'][0]['mob_ids']=[selected]
    monkeypatch.setenv('MWW_DATA_DIR',str(tmp_path/'output'))
    assert app.refresh(cfg,force=True)['stats']['mobSelected']==1
    cfg['world']=str(copy)
    second=app.refresh(cfg,force=True)
    assert second['stats']['mobSelected']==0
    data=verify_scene_script((app.output_folder()/'scene-data.js').read_bytes())
    assert data['entities']==[]
    assert cfg['shots'][0]['mobs_by_world'][key1]==[selected]

