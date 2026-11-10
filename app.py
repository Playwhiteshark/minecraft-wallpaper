#!/usr/bin/env python3
"""On-demand Minecraft Living World Wallpaper control panel and refresh CLI.

Runtime dependencies: Python 3.10+ standard library, a Java Minecraft save,
optionally its local version jar, an existing browser and Lively Wallpaper.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import traceback
import webbrowser
from pathlib import Path

from mww.nbt import WorldFormatError, level_info
from mww.scene import build_scene, publish_scene, scene_fingerprint, verify_scene_script
from mww.entities import scan_world_mobs, find_named_mobs, MODEL_TYPES

PROJECT = Path(__file__).resolve().parent
WEB = PROJECT / 'web'
TASK_NAME = 'MinecraftLivingWallpaper.Refresh'
OWNED_MARKER = 'MWW-OWNED-WALLPAPER-V1'


def data_root() -> Path:
    override = os.environ.get('MWW_DATA_DIR')
    if override:
        return Path(override).expanduser().resolve()
    if os.name == 'nt':
        return Path.home() / 'COMPUTER STUFF' / 'Minecraft Living World Wallpaper'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share')) / 'minecraft-living-wallpaper'


def config_path() -> Path:
    return data_root() / 'config.json'


def default_config():
    return {
        'schema': 1, 'world': '', 'jar': '', 'lively_project': '',
        'selected': 0, 'shots': [
            {'name': 'Home base', 'dimension': 'overworld', 'x': 0, 'y': 80, 'z': 0,
             'radius': 24, 'landscape_radius': 128, 'below': 14, 'above': 28, 'light': 'golden',
             'yaw': 42, 'pitch': 22, 'distance': 52, 'pets': True,
             'mob_radius': 96}
        ],
        'last_fingerprint': '', 'last_stats': {},
    }


def load_config():
    path = config_path()
    if not path.exists():
        return default_config()
    obj = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(obj, dict) or obj.get('schema') != 1:
        raise ValueError(f'Unsupported configuration format at {path}')
    if not isinstance(obj.get('shots'), list) or not obj['shots']:
        raise ValueError('Configuration must have at least one saved shot')
    return obj


def save_config(config):
    root = data_root()
    root.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(config, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    with tempfile.NamedTemporaryFile(dir=root, prefix='.mww-config-', delete=False) as f:
        f.write(raw)
        temp = Path(f.name)
    try:
        os.replace(temp, config_path())
    finally:
        if temp.exists():
            temp.unlink()


def scan_worlds():
    if os.name == 'nt':
        home = Path(os.environ.get('APPDATA', str(Path.home() / 'AppData' / 'Roaming'))) / '.minecraft' / 'saves'
    else:
        home = Path.home() / '.minecraft' / 'saves'
    result = []
    if home.is_dir():
        for entry in home.iterdir():
            if entry.is_dir() and (entry / 'level.dat').is_file():
                try:
                    name = level_info(entry)['name']
                except Exception:
                    name = entry.name
                result.append((name, str(entry.resolve())))
    return sorted(result, key=lambda item: item[0].casefold())


def world_selection_key(world):
    """Stable local path identity for per-world mob choices (never a world name).

    Different saves can both be called 'New World'. Their selected UUIDs must
    not be conflated. A moved checkout is treated as a newly selected location;
    its old choices remain retained under the original key for recovery.
    """
    value = str(world or '').strip()
    if not value:
        return ''
    canonical = os.path.normcase(str(Path(value).expanduser().resolve()))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def output_folder():
    return data_root() / 'wallpaper'


def find_livelycu():
    executable = shutil.which('livelycu.exe') or shutil.which('livelycu')
    if executable:
        return Path(executable)
    if os.name != 'nt':
        return None
    root = Path(os.environ.get('LOCALAPPDATA', ''))
    candidates = (
        root / 'Programs' / 'Lively Wallpaper' / 'Livelycu.exe',
        root / 'Lively Wallpaper' / 'Livelycu.exe',
        root / 'Programs' / 'Lively Wallpaper' / 'Lively' / 'Livelycu.exe',
    )
    return next((p for p in candidates if p.is_file()), None)


def verify_owned_lively_project(path: Path):
    if not path.is_dir():
        raise ValueError(f'No such Lively project directory: {path}')
    html = path / 'index.html'
    if not html.is_file() or OWNED_MARKER not in html.read_text(encoding='utf-8', errors='replace'):
        raise ValueError('Selected folder is not an imported Minecraft Living World Wallpaper project.\\n'
                         'Only a folder with our unique index.html marker is eligible for updating.')
    for filename in ('scene-data.js', 'viewer.js'):
        target = path / filename
        if target.is_symlink() or not target.is_file():
            raise ValueError(f'Imported Lively project has no safe {filename} file')
    if 'Minecraft Living World Wallpaper' not in (path / 'viewer.js').read_text(
            encoding='utf-8', errors='replace')[:300]:
        raise ValueError('Lively viewer file is not recognised as our wallpaper renderer')


def sync_lively_project(config):
    target = config.get('lively_project', '').strip()
    if not target:
        return False
    path = Path(target).expanduser().resolve()
    verify_owned_lively_project(path)
    source = output_folder()
    if path == source.resolve():
        return True
    # The original v0.1 synced only scene-data.js. A new rendering feature
    # also needs its viewer.js to reach Lively's independently imported copy.
    # Both destination files are verified as ours; foreign projects are refused.
    for filename in ('index.html', 'viewer.js', 'entity-models.js', 'scene-data.js'):
        data = (source / filename).read_bytes()
        if filename == 'scene-data.js':
            verify_scene_script(data)
        destination = path / filename
        if destination.is_symlink():
            raise ValueError(f'Refusing symlinked Lively asset: {filename}')
        if destination.is_file() and destination.read_bytes() == data:
            continue
        with tempfile.NamedTemporaryFile(dir=path, prefix='.mww-sync-', delete=False) as f:
            f.write(data)
            temp = Path(f.name)
        try:
            os.replace(temp, destination)
        finally:
            if temp.exists():
                temp.unlink()
    return True


def reload_lively():
    exe = find_livelycu()
    if not exe:
        return 'Lively command utility not found; use Lively to reload the imported wallpaper.'
    result = subprocess.run([str(exe), 'seekwp', '--value', '0'],
                            capture_output=True, text=True, timeout=15, check=False)
    if result.returncode:
        return 'Lively reload was not confirmed: ' + (result.stderr.strip() or str(result.returncode))
    return 'Lively web wallpaper reload requested.'


def refresh(config, *, force=False, fetch_models=False):
    world = Path(str(config.get('world', ''))).expanduser().resolve()
    if not (world / 'level.dat').is_file():
        raise ValueError('Select a Minecraft Java world folder containing level.dat.')
    index = int(config.get('selected', 0))
    if not (0 <= index < len(config['shots'])):
        raise ValueError('Selected shot index is invalid')
    shot = dict(config['shots'][index])
    per_world = shot.pop('mobs_by_world', None)
    if isinstance(per_world, dict):
        shot['mob_ids'] = per_world.get(world_selection_key(world))
    elif shot.get('mob_world_key') and shot.get('mob_world_key') != world_selection_key(world):
        shot['mob_ids'] = None
    shot.pop('mob_world_key', None)
    shot['jar'] = config.get('jar', '')
    shot['model_cache'] = str(data_root() / 'mob-models')
    shot['fetch_models'] = fetch_models
    fingerprint = scene_fingerprint(world, shot)
    generated = output_folder() / 'scene-data.js'
    if not force and fingerprint == config.get('last_fingerprint') and generated.is_file():
        # A later manual Lively binding can still need syncing even if the save did not change.
        verify_scene_script(generated.read_bytes())
        synced = sync_lively_project(config)
        return {'status': 'unchanged', 'stats': config.get('last_stats', {}), 'synced': synced}
    scene = build_scene(world, shot)
    # Include the selected shot name, without emitting local paths or entity UUIDs.
    scene['shotName'] = shot.get('name', 'Base')
    publish_scene(scene, output_folder(), WEB)
    config['last_fingerprint'] = fingerprint
    config['last_stats'] = scene['stats']
    save_config(config)
    try:
        synced = sync_lively_project(config)
    except Exception as e:
        # Main generated scene remains valid; report failed external Lively synchronization.
        return {'status': 'rendered', 'stats': scene['stats'], 'synced': False, 'warning': str(e)}
    return {'status': 'rendered', 'stats': scene['stats'], 'synced': synced}


def open_preview():
    path = output_folder() / 'index.html'
    if not path.exists():
        raise ValueError('No wallpaper generated yet. Select a world and click Refresh.')
    webbrowser.open(path.resolve().as_uri() + '?preview=1')


def python_for_scheduled_job():
    exe = Path(sys.executable)
    if os.name == 'nt' and exe.name.lower() == 'python.exe':
        pw = exe.with_name('pythonw.exe')
        if pw.is_file():
            return pw
    return exe


def schedule_weekly(enabled: bool):
    if os.name != 'nt':
        raise OSError('Windows Task Scheduler is available on Windows only.')
    if enabled:
        python = python_for_scheduled_job()
        action = f'"{python}" "{PROJECT / "app.py"}" --refresh --quiet'
        command = ['schtasks', '/Create', '/SC', 'WEEKLY', '/D', 'SUN', '/ST', '15:00',
                   '/TN', TASK_NAME, '/TR', action, '/F']
    else:
        command = ['schtasks', '/Delete', '/TN', TASK_NAME, '/F']
    result = subprocess.run(command, capture_output=True, text=True, timeout=25, check=False)
    if result.returncode:
        raise OSError(result.stderr.strip() or result.stdout.strip() or f'schtasks exit {result.returncode}')
    return result.stdout.strip() or 'Scheduled Task updated.'


def gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk

    bg = '#111b29'; surface = '#1b293b'; surface2 = '#25364b'; fg = '#f1f5f9'; muted = '#aebbc9'
    teal = '#40c6b8'
    root = tk.Tk()
    root.title('Minecraft Living World Wallpaper')
    root.configure(bg=bg)
    root.minsize(920, 730)
    root.geometry('1060x790')
    style = ttk.Style(root); style.theme_use('clam')
    style.configure('TFrame', background=bg)
    style.configure('Surface.TFrame', background=surface)
    style.configure('TLabel', background=bg, foreground=fg, font=('Segoe UI', 10))
    style.configure('Surface.TLabel', background=surface, foreground=fg, font=('Segoe UI', 10))
    style.configure('Small.TLabel', background=bg, foreground=muted, font=('Segoe UI', 9))
    style.configure('Header.TLabel', background=bg, foreground=fg, font=('Segoe UI Semibold', 21))
    style.configure('TEntry', fieldbackground=surface2, foreground=fg, bordercolor=surface2, insertcolor=fg)
    style.configure('TCombobox', fieldbackground=surface2, foreground=fg, background=surface2, arrowcolor=fg)
    style.configure('TButton', background=surface2, foreground=fg, padding=(12, 8), font=('Segoe UI', 10))
    style.map('TButton', background=[('active', '#36536c')])
    style.configure('Accent.TButton', background='#168e85', foreground='white', padding=(16, 9),font=('Segoe UI Semibold', 10))
    style.map('Accent.TButton', background=[('active','#23a99c')])
    style.configure('TCheckbutton', background=bg, foreground=fg)
    style.configure('TSeparator', background=surface2)

    try:
        config = load_config()
    except Exception as e:
        messagebox.showerror('Invalid configuration', str(e))
        root.destroy()
        return

    header = ttk.Frame(root, padding=(24, 18, 24, 14)); header.pack(fill='x')
    ttk.Label(header, text='Living World', style='Header.TLabel').pack(side='left')
    ttk.Label(header, text='Minecraft → 3D diorama → Lively', style='Small.TLabel').pack(side='right', pady=12)
    body = ttk.Frame(root, padding=(24, 0, 24, 20)); body.pack(fill='both', expand=True)
    left = ttk.Frame(body); left.pack(side='left', fill='both', expand=True)
    right = ttk.Frame(body); right.pack(side='right', fill='both', expand=True, padx=(22, 0))

    def line(parent, label, var, width=14):
        frame=ttk.Frame(parent);frame.pack(fill='x', pady=3)
        ttk.Label(frame, text=label, width=18).pack(side='left')
        ttk.Entry(frame, textvariable=var, width=width).pack(side='left', fill='x', expand=True)

    worlds=scan_worlds()
    world_var=tk.StringVar(value=config.get('world',''))
    jar_var=tk.StringVar(value=config.get('jar',''))
    selected=tk.IntVar(value=min(max(0,int(config.get('selected',0))),len(config['shots'])-1))
    strings={k:tk.StringVar() for k in ('name','dimension','x','y','z','radius','landscape_radius','mob_radius','below','above','light','yaw','pitch','distance')}
    pets_var=tk.BooleanVar(value=True)
    # Internal identity keys are retained per shot in config, never in scene data.
    mob_selection = [None]
    mob_scope = [world_selection_key(config.get('world',''))]
    status_var=tk.StringVar(value='Ready. Minecraft must be closed before refreshing.')
    stat_var=tk.StringVar(value='No render yet.')
    busy=[False]

    ttk.Label(left,text='1   SOURCE WORLD',font=('Segoe UI Semibold', 11)).pack(anchor='w',pady=(2,10))
    cb=ttk.Combobox(left,textvariable=world_var,values=[str(p) for _,p in worlds])
    cb.pack(fill='x')
    ttk.Label(left,text='Select a vanilla world or browse to a launcher / CurseForge save.',style='Small.TLabel').pack(anchor='w',pady=(5,7))
    row=ttk.Frame(left);row.pack(fill='x')
    def browse_world():
        path=filedialog.askdirectory(title='Select a Minecraft world folder (contains level.dat)',initialdir=str(Path.home()))
        if path:
            world_var.set(path)
            try:
                info=level_info(Path(path))
                location=info['player']
                for k,val in zip(('x','y','z'),location if location is not None else ('','','')):
                    strings[k].set(str(val))
                if location is not None:
                    status_var.set(f"Loaded {info['name']}. Saved player position read from {info['player_source']}.")
                else:
                    status_var.set('No unambiguous player position found. Click Use player position or enter base X/Y/Z manually.')
            except Exception as e:
                messagebox.showwarning('World selection',str(e))
    ttk.Button(row,text='Browse world…',command=browse_world).pack(side='left')
    def use_location(key):
        try:
            info=level_info(Path(world_var.get()))
            if key == 'spawn':
                position=info['spawn']
                if position is None:
                    raise ValueError('This world has no saved spawn location. Enter coordinates manually.')
                label='world spawn'
            else:
                position=info['player']
                if position is not None:
                    label=f"saved player location ({info['player_source']})"
                else:
                    candidates=info['player_candidates']
                    if not candidates:
                        raise ValueError('No saved player position found in level.dat or playerdata. Use F3 in Minecraft to find your base X/Y/Z, then enter them manually.')
                    options='\n'.join(f"{i}: X={record['pos'][0]}, Y={record['pos'][1]}, Z={record['pos'][2]}" for i,record in enumerate(candidates,1))
                    choice=simpledialog.askinteger('Choose saved player',
                        'Several player records exist. Which coordinates are yours?\n\n' + options,
                        parent=root, minvalue=1, maxvalue=len(candidates))
                    if choice is None:
                        return
                    position=candidates[choice-1]['pos']
                    label='selected playerdata location'
            for k,v in zip(('x','y','z'),position):
                strings[k].set(str(v))
            status_var.set(f"Using {label}: X={position[0]}, Y={position[1]}, Z={position[2]}. Change the centre if your base is elsewhere.")
        except Exception as e:
            if key == 'player':
                for k in ('x','y','z'):
                    strings[k].set('')
            messagebox.showerror('Location',str(e))
    ttk.Button(row,text='Use player position',command=lambda:use_location('player')).pack(side='left',padx=6)
    ttk.Button(row,text='Use world spawn',command=lambda:use_location('spawn')).pack(side='left')
    ttk.Separator(left).pack(fill='x',pady=18)

    ttk.Label(left,text='2   BASE / CAMERA',font=('Segoe UI Semibold', 11)).pack(anchor='w',pady=(0,10))
    line(left,'Shot name',strings['name'])
    row=ttk.Frame(left);row.pack(fill='x',pady=3)
    ttk.Label(row,text='Dimension',width=18).pack(side='left')
    dim=ttk.Combobox(row,textvariable=strings['dimension'],values=['overworld','nether','end'],state='readonly')
    dim.pack(fill='x',expand=True)
    coords=ttk.Frame(left);coords.pack(fill='x',pady=(6,5))
    ttk.Label(coords,text='Centre X / Y / Z',width=18).pack(side='left')
    for k in ('x','y','z'):
        ttk.Entry(coords,textvariable=strings[k],width=8).pack(side='left',padx=(0,7),fill='x',expand=True)
    line(left,'Radius (8–48)',strings['radius'])
    line(left,'Surroundings (0–192)',strings['landscape_radius'])
    ttk.Label(left,text='Actual saved terrain in the distance (0 = old diorama).',style='Small.TLabel').pack(anchor='w',pady=(0,3))
    def auto_frame():
        try:
            radius=int(strings['radius'].get())
            strings['distance'].set(str(round(radius*2.25,1)))
            strings['yaw'].set('42');strings['pitch'].set('26')
        except ValueError:messagebox.showwarning('Auto framing','Enter a valid radius first.')
    ttk.Button(left,text='Auto-frame distance / camera',command=auto_frame).pack(anchor='w',pady=(2,5))
    for k,lab in [('below','Below centre'),('above','Above centre')]:line(left,lab,strings[k])
    light_row=ttk.Frame(left);light_row.pack(fill='x',pady=3)
    ttk.Label(light_row,text='Lighting',width=18).pack(side='left')
    ttk.Combobox(light_row,textvariable=strings['light'],values=['golden','day','night'],state='readonly').pack(fill='x',expand=True)
    row=ttk.Frame(left);row.pack(fill='x',pady=3)
    ttk.Label(row,text='Yaw / pitch / zoom',width=18).pack(side='left')
    for k in ('yaw','pitch','distance'):
        ttk.Entry(row,textvariable=strings[k],width=8).pack(side='left',padx=(0,7),fill='x',expand=True)
    ttk.Checkbutton(left,text='Include saved animals',variable=pets_var).pack(anchor='w',pady=(8,2))
    row=ttk.Frame(left);row.pack(fill='x',pady=3)
    ttk.Label(row,text='Mob search radius',width=18).pack(side='left')
    ttk.Entry(row,textvariable=strings['mob_radius'],width=12).pack(side='left',fill='x',expand=True)
    ttk.Button(row,text='Choose saved mobs…',command=lambda:choose_mobs()).pack(side='left',padx=(6,0))
    ttk.Button(left,text='Find named creature anywhere in saved world…',
               command=lambda:find_named_creature()).pack(anchor='w',pady=(1,4))
    ttk.Label(left,text='Nearby mob choices are per shot; the named-creature search can create a new shot.',
              style='Small.TLabel',wraplength=445).pack(anchor='w',pady=(0,5))

    ttk.Label(right,text='SAVED SHOTS',font=('Segoe UI Semibold',11)).pack(anchor='w',pady=(2,9))
    shotlist=tk.Listbox(right,background=surface,foreground=fg,selectbackground='#187e7c',relief='flat',height=7,
                       highlightthickness=1,highlightbackground='#344a60',font=('Segoe UI',10))
    shotlist.pack(fill='x')
    shotlist.bind('<<ListboxSelect>>',lambda e:select_shot())

    def form_from_shot(index):
        if not (0<=index<len(config['shots'])):return
        s=config['shots'][index]
        for k,var in strings.items():var.set(str(s.get(k,128 if k=='landscape_radius' else 96 if k=='mob_radius' else '')))
        pets_var.set(bool(s.get('pets',True)))
        key = world_selection_key(world_var.get())
        choices = s.get('mobs_by_world')
        if isinstance(choices,dict):
            active = choices.get(key)
        elif not s.get('mob_world_key') or s.get('mob_world_key') == key:
            active = s.get('mob_ids')
        else:
            active = None
        mob_selection[0] = list(active) if isinstance(active,list) else None
        mob_scope[0] = key
        selected.set(index)

    def refresh_list():
        shotlist.delete(0,'end')
        for i,s in enumerate(config['shots']):shotlist.insert('end',f"{i+1:02d}    {s.get('name','Scene')}  ·  {s.get('dimension','overworld')}")
        idx=selected.get();shotlist.selection_set(idx);shotlist.activate(idx)

    def select_shot():
        selection=shotlist.curselection()
        if selection:form_from_shot(selection[0])

    def read_shot():
        s={k:v.get().strip() for k,v in strings.items()}
        current_key = world_selection_key(world_var.get())
        existing = config['shots'][selected.get()]
        all_choices = dict(existing.get('mobs_by_world') or {})
        if mob_scope[0] == current_key:
            all_choices[current_key] = None if mob_selection[0] is None else list(mob_selection[0])
        s['mobs_by_world'] = all_choices
        s['mob_ids'] = all_choices.get(current_key)
        s['mob_world_key'] = current_key
        if not s['name']:raise ValueError('Shot needs a name')
        for k in ('x','y','z','radius','landscape_radius','mob_radius','below','above'):
            s[k]=int(s[k])
        for k in ('yaw','pitch','distance'):
            s[k]=float(s[k])
        s['pets']=bool(pets_var.get())
        if not 8<=s['radius']<=48:raise ValueError('Radius must be between 8 and 48')
        if not 8<=s['mob_radius']<=192:raise ValueError('Mob search radius must be 8–192')
        if not (s['landscape_radius']==0 or s['radius']+8<=s['landscape_radius']<=192):
            raise ValueError('Surroundings must be 0 or at least 8 blocks wider than the detailed radius (max 192)')
        if not 4<=s['below']<=40 or not 8<=s['above']<=60:raise ValueError('Vertical range is invalid')
        return s

    def persist():
        config['world']=world_var.get().strip();config['jar']=jar_var.get().strip()
        config['shots'][selected.get()]=read_shot();config['selected']=selected.get()
        save_config(config)

    def find_named_creature():
        """On-demand search of indexed saved entity chunks, never world terrain."""
        if busy[0]:
            return
        query = simpledialog.askstring(
            'Find named creature',
            'Search for a saved mob name (for example, Jeremy Bentham):',
            parent=root)
        if query is None or not query.strip():
            return
        try:
            shot = read_shot()
            world = Path(world_var.get()).expanduser().resolve()
            if not (world / 'level.dat').is_file():
                raise ValueError('Choose a Minecraft world first.')
        except Exception as exc:
            messagebox.showerror('Named creature search', str(exc))
            return
        busy[0] = True
        status_var.set('Searching saved mob records for '+query.strip()+'…')
        world_key = world_selection_key(world)
        def worker():
            try:
                found = find_named_mobs(world, shot['dimension'], query.strip())
                error = None
            except Exception as exc:
                found, error = None, str(exc)
            def finished():
                busy[0] = False
                if error:
                    status_var.set('Search failed; no settings were changed.')
                    messagebox.showerror('Named creature search', error)
                    return
                if world_key != world_selection_key(world_var.get()):
                    messagebox.showwarning('World changed','Select the world again and repeat the search.')
                    return
                if not found:
                    status_var.set('No matching name found in saved '+shot['dimension']+' entities.')
                    messagebox.showinfo('Named creature search',
                        'No matching creature name was found in saved entity regions for this dimension. '
                        'It may be in another dimension, a different world, or not currently saved.')
                    return
                status_var.set(f'Found {len(found)} matching saved creatures.')
                dialog = tk.Toplevel(root)
                dialog.title('Named creatures in saved world')
                dialog.configure(bg=bg)
                dialog.geometry('650x370')
                dialog.transient(root)
                dialog.grab_set()
                ttk.Label(dialog,text=f'{len(found)} matches for "{query.strip()}" in {shot["dimension"]}',
                          style='Small.TLabel').pack(anchor='w',padx=16,pady=(16,8))
                lst=tk.Listbox(dialog,background=surface,foreground=fg,
                    selectbackground='#187e7c',font=('Consolas',10),
                    exportselection=False,relief='flat')
                lst.pack(fill='both',expand=True,padx=16,pady=(0,12))
                for mob in found:
                    x,y,z=mob['pos']
                    lst.insert('end',
                        f'{mob["name"]} ({mob["type"]})  X={x:.0f} Y={y:.0f} Z={z:.0f}')
                lst.selection_set(0)
                buttons=ttk.Frame(dialog);buttons.pack(fill='x',padx=16,pady=(0,16))
                def create_shot_here():
                    index=lst.curselection()
                    if not index:
                        return
                    chosen=found[index[0]]
                    new=dict(shot)
                    new['name']=chosen['name'] or ('Near '+chosen['type'])
                    for k,v in zip(('x','y','z'),chosen['pos']):
                        new[k]=round(v)
                    # The new camera can show this mob without making a
                    # gigantic one-shot scene bridging it to the old base.
                    new['mobs_by_world']={world_key:[chosen['key']]}
                    new['mob_ids']=[chosen['key']]
                    new['mob_world_key']=world_key
                    new['pets']=True
                    config['shots'].append(new)
                    config['selected']=len(config['shots'])-1
                    config['world']=str(world)
                    save_config(config)
                    selected.set(config['selected'])
                    refresh_list()
                    form_from_shot(selected.get())
                    dialog.destroy()
                    status_var.set('Created a new shot near '+new['name']+
                                   '. Click Refresh scene when ready.')
                ttk.Button(buttons,text='Create shot at selected mob',
                           style='Accent.TButton',command=create_shot_here).pack(side='left')
                ttk.Button(buttons,text='Close',command=dialog.destroy).pack(side='right')
            root.after(0,finished)
        threading.Thread(target=worker,daemon=True).start()

    def choose_mobs():
        if busy[0]:
            return
        try:
            shot = read_shot()
            world = Path(world_var.get()).expanduser().resolve()
            if not (world / 'level.dat').is_file():
                raise ValueError('Choose a Minecraft world before scanning mobs')
        except Exception as exc:
            return messagebox.showerror('Mob selection', str(exc))
        busy[0] = True
        status_var.set('Scanning saved creatures in the selected region…')

        def worker():
            try:
                mobs = scan_world_mobs(world, shot['dimension'],
                                       (shot['x'], shot['y'], shot['z']),
                                       shot['mob_radius'])
                error = None
            except Exception as exc:
                mobs, error = None, str(exc)

            def finished():
                busy[0] = False
                if error:
                    status_var.set('Mob scan failed; no selections were changed.')
                    messagebox.showerror('Mob scan', error)
                    return
                status_var.set(f'Found {len(mobs)} saved creatures. Select which to render.')
                dialog = tk.Toplevel(root)
                dialog.title('Choose saved Minecraft mobs')
                dialog.configure(bg=bg)
                dialog.geometry('680x560')
                dialog.transient(root)
                dialog.grab_set()
                ttk.Label(dialog,text=f'{len(mobs)} creatures in {shot["dimension"]}, within {shot["mob_radius"]} blocks (all heights).',
                          font=('Segoe UI Semibold',11)).pack(anchor='w',padx=16,pady=(14,4))
                ttk.Label(dialog,text='Named and tamed mobs first. Unknown tamed status is labelled. Ctrl is not required: click to toggle.',
                          style='Small.TLabel',wraplength=650).pack(anchor='w',padx=16,pady=(0,6))
                row=ttk.Frame(dialog);row.pack(fill='both',expand=True,padx=16,pady=8)
                lst=tk.Listbox(row,selectmode=tk.MULTIPLE,exportselection=False,
                               background=surface,foreground=fg,selectbackground='#187e7c',
                               height=16,font=('Consolas',10),relief='flat')
                scrollbar=ttk.Scrollbar(row,orient='vertical',command=lst.yview)
                lst.configure(yscrollcommand=scrollbar.set)
                lst.pack(side='left',fill='both',expand=True)
                scrollbar.pack(side='right',fill='y')
                old_keys=set(shot.get('mob_ids') or [])
                missing_keys=old_keys-{mob['key'] for mob in mobs}
                for mob in mobs:
                    label=mob['name'] or ('Unnamed '+mob['type'].replace('_',' '))
                    tame='tamed' if mob['tame']=='tamed' else ('wild' if mob['tame']=='wild' else 'tame unknown')
                    supported='' if mob['renderable'] else ' · model unverified'
                    unstable='' if mob['stable'] else ' · no UUID'
                    lst.insert('end',f'{label}  [{mob["type"]}, {tame}]{supported}{unstable}')
                selected_ids=shot.get('mob_ids')
                if isinstance(selected_ids,list):
                    for i,mob in enumerate(mobs):
                        if mob['key'] in old_keys:lst.selection_set(i)
                else:
                    for i,mob in enumerate(mobs):
                        x,y,z=mob['pos']
                        if (mob['resource'] in MODEL_TYPES and
                            abs(x-shot['x'])<=shot['radius'] and
                            abs(z-shot['z'])<=shot['radius'] and
                            shot['y']-shot['below']-6<=y<=shot['y']+shot['above']+6):
                            lst.selection_set(i)
                keep_missing=[True]
                note=(f'{len(missing_keys)} previously selected mobs not found: selections preserved unless cleared.'
                      if missing_keys else 'Selection is saved locally by mob UUID; no private IDs go into the wallpaper.')
                ttk.Label(dialog,text=note,style='Small.TLabel',
                          wraplength=650).pack(anchor='w',padx=16,pady=(0,6))
                buttons=ttk.Frame(dialog);buttons.pack(fill='x',padx=16,pady=(4,14))
                def save_selected():
                    chosen=[mobs[i]['key'] for i in lst.curselection()]
                    if keep_missing[0]:
                        chosen.extend(sorted(missing_keys))
                    mob_selection[0]=list(dict.fromkeys(chosen))
                    mob_scope[0]=world_selection_key(world_var.get())
                    pets_var.set(True)
                    config['shots'][selected.get()]=read_shot()
                    config['world']=world_var.get().strip()
                    save_config(config)
                    status_var.set(f'Selected {len(chosen)} creatures for this shot. Click Refresh scene to render.')
                    dialog.destroy()
                def use_automatic():
                    mob_selection[0]=None
                    mob_scope[0]=world_selection_key(world_var.get())
                    config['shots'][selected.get()]=read_shot()
                    config['world']=world_var.get().strip()
                    save_config(config)
                    status_var.set('Using automatic nearby-mob selection for this shot.')
                    dialog.destroy()
                def clear_all():
                    lst.selection_clear(0,'end')
                    keep_missing[0]=False
                ttk.Button(buttons,text='Save selection',style='Accent.TButton',command=save_selected).pack(side='left')
                ttk.Button(buttons,text='Clear',command=clear_all).pack(side='left',padx=6)
                ttk.Button(buttons,text='Automatic',command=use_automatic).pack(side='left')
                ttk.Button(buttons,text='Cancel',command=dialog.destroy).pack(side='right')
            root.after(0, finished)
        threading.Thread(target=worker,daemon=True).start()

    def do_save():
        try:persist();refresh_list();status_var.set('Shot and settings saved locally.')
        except Exception as e:messagebox.showerror('Settings',str(e))

    def add_shot():
        try:
            new=read_shot();new['name']=new['name']+' copy'
            config['shots'].append(new);selected.set(len(config['shots'])-1)
            save_config(config);refresh_list();form_from_shot(selected.get())
        except Exception as e:messagebox.showerror('Add shot',str(e))

    def delete_shot():
        if len(config['shots'])<=1:return messagebox.showwarning('Shots','Keep at least one shot.')
        idx=selected.get()
        if messagebox.askyesno('Remove shot',f"Remove '{config['shots'][idx]['name']}' from saved shots? (World files are untouched.)"):
            config['shots'].pop(idx);selected.set(min(idx,len(config['shots'])-1));save_config(config);refresh_list();form_from_shot(selected.get())

    row=ttk.Frame(right);row.pack(fill='x',pady=(9,15))
    ttk.Button(row,text='Save shot',command=do_save).pack(side='left')
    ttk.Button(row,text='Duplicate',command=add_shot).pack(side='left',padx=6)
    ttk.Button(row,text='Remove',command=delete_shot).pack(side='left')
    ttk.Separator(right).pack(fill='x',pady=(0,17))

    ttk.Label(right,text='3   GENERATE + PREVIEW',font=('Segoe UI Semibold',11)).pack(anchor='w',pady=(0,10))
    ttk.Label(right,text='The converter runs only for refresh; the wallpaper is static HTML + WebGL2.',style='Small.TLabel',wraplength=400).pack(anchor='w',pady=(0,7))
    action=ttk.Frame(right);action.pack(fill='x')
    def do_refresh():
        if busy[0]:return
        try:persist()
        except Exception as e:return messagebox.showerror('Invalid settings',str(e))
        busy[0]=True;status_var.set('Reading saved chunks and building a bounded scene…')
        def worker():
            try:result=refresh(config,force=True,fetch_models=True);error=None
            except Exception as e:result=None;error=str(e)
            def finish():
                busy[0]=False
                if error:
                    status_var.set('Refresh failed. Previous wallpaper remains intact.')
                    messagebox.showerror('Refresh failed',error)
                    return
                stats=result.get('stats',{})
                stat_var.set(f"{stats.get('blocks',0):,} blocks · {stats.get('faces',0):,} faces · {stats.get('mobTextured',0)}/{stats.get('animals',0)} textured mobs · {stats.get('landscapeSamples',0)} landscape points")
                status='Scene refreshed. '+('Connected Lively project updated.' if result.get('synced') else 'Open preview or import to Lively.')
                if stats.get('mobWarnings'):
                    status+=' Mob texture/model issue: '+stats['mobWarnings'][0]
                if stats.get('mobMissing'):
                    status+=f" {stats['mobMissing']} selected creatures were not found."
                status_var.set(status)
                if result.get('warning'):messagebox.showwarning('Lively update',result['warning'])
                elif result.get('synced'):status_var.set(status_var.get()+' '+reload_lively())
            root.after(0,finish)
        threading.Thread(target=worker,daemon=True).start()
    ttk.Button(action,text='Refresh scene',style='Accent.TButton',command=do_refresh).pack(side='left')
    def preview():
        try:open_preview()
        except Exception as e:messagebox.showerror('Preview',str(e))
    ttk.Button(action,text='Open 3D preview',command=preview).pack(side='left',padx=7)
    ttk.Label(right,textvariable=stat_var,style='Small.TLabel',wraplength=400).pack(anchor='w',pady=(10,0))
    ttk.Separator(right).pack(fill='x',pady=17)
    ttk.Label(right,text='4   LIVELY / UPDATE',font=('Segoe UI Semibold',11)).pack(anchor='w',pady=(0,10))
    ttk.Label(right,text='Import wallpaper/index.html into Lively once. After import, connect the folder Lively created for this wallpaper; later refreshes update only our own scene-data.js there.',style='Small.TLabel',wraplength=408).pack(anchor='w',pady=(0,9))
    row=ttk.Frame(right);row.pack(fill='x')
    def open_folder():
        p=output_folder();p.mkdir(parents=True,exist_ok=True)
        if os.name=='nt':os.startfile(str(p))
        else:webbrowser.open(p.resolve().as_uri())
    ttk.Button(row,text='Open wallpaper folder',command=open_folder).pack(side='left')
    def connect_project():
        directory=filedialog.askdirectory(title='Select the Lively-imported Minecraft Living World Wallpaper folder')
        if not directory:return
        try:
            p=Path(directory).resolve();verify_owned_lively_project(p)
            config['lively_project']=str(p);save_config(config)
            status_var.set('Connected Lively project at '+str(p))
        except Exception as e:messagebox.showerror('Connect Lively',str(e))
    ttk.Button(row,text='Connect Lively copy',command=connect_project).pack(side='left',padx=7)
    row=ttk.Frame(right);row.pack(fill='x',pady=(8,0))
    ttk.Button(row,text='Reload Lively',command=lambda:messagebox.showinfo('Lively',reload_lively())).pack(side='left')
    def schedule(on):
        word='Enable' if on else 'Remove'
        if not messagebox.askyesno('Windows weekly refresh',f"{word} a 15:00 Sunday Windows Scheduled Task for this application?\n\nThis only runs the converter once; it will not run Minecraft or start a background watcher.\n\nThe task will depend on keeping this project checkout at its current location."):
            return
        try:messagebox.showinfo('Scheduled Task',schedule_weekly(on))
        except Exception as e:messagebox.showerror('Scheduled Task',str(e))
    ttk.Button(row,text='Weekly refresh',command=lambda:schedule(True)).pack(side='left',padx=7)
    ttk.Button(row,text='Remove weekly task',command=lambda:schedule(False)).pack(side='left')
    ttk.Separator(right).pack(fill='x',pady=17)
    ttk.Label(right,text='OPTIONAL GAME TEXTURES',font=('Segoe UI Semibold',11)).pack(anchor='w',pady=(0,9))
    ttk.Entry(right,textvariable=jar_var).pack(fill='x')
    def pick_jar():
        path=filedialog.askopenfilename(title='Choose an existing Minecraft version .jar',filetypes=[('Minecraft Java archive','*.jar')])
        if path:jar_var.set(path)
    ttk.Button(right,text='Choose installed Minecraft .jar…',command=pick_jar).pack(anchor='w',pady=(7,0))
    ttk.Label(right,text='No new downloads. If no jar is found, a simple colour palette is used.',style='Small.TLabel',wraplength=390).pack(anchor='w',pady=(6,0))

    foot=ttk.Frame(root,padding=(24,8,24,18));foot.pack(fill='x')
    ttk.Separator(foot).pack(fill='x',pady=(0,11))
    ttk.Label(foot,textvariable=status_var,style='Small.TLabel',wraplength=1000).pack(anchor='w')
    refresh_list();form_from_shot(selected.get())
    st=config.get('last_stats') or {}
    if st:stat_var.set(f"Last scene: {st.get('blocks',0):,} blocks · {st.get('faces',0):,} faces · {st.get('animals',0)} animals")
    root.mainloop()


def main(argv=None):
    parser=argparse.ArgumentParser(description='Minecraft Living World Wallpaper desktop app')
    parser.add_argument('--refresh',action='store_true',help='Refresh the saved world + shot with no GUI')
    parser.add_argument('--force',action='store_true',help='Rebuild even if source metadata did not change')
    parser.add_argument('--quiet',action='store_true',help='Suppress success output (errors still on stderr)')
    parser.add_argument('--preview',action='store_true',help='Open the last generated offline wallpaper in browser')
    args=parser.parse_args(argv)
    if args.preview:
        open_preview();return 0
    if not args.refresh:
        gui();return 0
    try:
        config=load_config()
        result=refresh(config,force=args.force)
        if result.get('synced'):
            result['lively']=reload_lively()
        if not args.quiet:
            print(json.dumps(result,indent=2))
        if result.get('warning'):
            print('WARNING:',result['warning'],file=sys.stderr)
        return 0
    except Exception as e:
        print('Refresh failed:',str(e),file=sys.stderr)
        return 1


if __name__=='__main__':
    sys.exit(main())
