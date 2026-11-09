"""Synthetic modern Java world tests: no copyrighted assets or private saves."""
from __future__ import annotations

import gzip
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
from mww.nbt import RegionReader, WorldFormatError, level_info, parse_nbt, unpack_palette
from mww.scene import build_scene, publish_scene, verify_scene_script, dimension_directory


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
    chunk=root([('xPos',3,0),('zPos',3,0),('sections',9,(10,[section]))])
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
    html=app.output_folder()/'index.html'
    assert 'MWW-OWNED-WALLPAPER-V1' in html.read_text()
    data=verify_scene_script((app.output_folder()/'scene-data.js').read_bytes())
    assert len(data['entities'])==5
    assert any(x['type']=='happy_ghast' for x in data['entities'])
    assert any(t.get('png') for t in data['tiles'])
    assert data['opaque'] and data['alpha']
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
