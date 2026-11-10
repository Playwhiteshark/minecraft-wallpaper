"""Real Minecraft entity-model and entity-texture loader, used only on refresh.

The wallpaper is fully offline. A user-triggered refresh may cache a public
versioned model description, then reads PNG skins ONLY from the local Minecraft
client JAR. Neither models nor Mojang textures are committed to this source
repository. The view receives the selected material/geometry data as a local
scene asset. No Node/JVM/long-lived runtime is required.
"""
from __future__ import annotations

import base64
import json
import re
import urllib.request
import zipfile
from pathlib import Path

MODEL_VERSION = '26.1.2'
MODEL_SOURCE = 'InventivetalentDev/minecraft-entity-models'
MODEL_URL = ('https://raw.githubusercontent.com/' + MODEL_SOURCE +
             '/' + MODEL_VERSION + '/minecraft/{}.json')
SAFE_ID = re.compile(r'^[a-z0-9_]{1,80}$')
MAX_MODEL_BYTES = 160_000
MAX_TEXTURE_BYTES = 2_000_000

# Names are a compatibility map of the game data, not scanner restrictions.
CAT_VARIANTS = ('tabby', 'black', 'red', 'siamese', 'british_shorthair',
                'calico', 'persian', 'ragdoll', 'white', 'jellie', 'all_black')
HORSE_COATS = ('white', 'creamy', 'chestnut', 'brown', 'black', 'gray', 'darkbrown')


def _validate_model(raw: bytes, kind: str) -> dict:
    if len(raw) > MAX_MODEL_BYTES:
        raise ValueError('Minecraft model description exceeds the size cap')
    model = json.loads(raw)
    if not isinstance(model, dict) or model.get('id') != 'minecraft:' + kind:
        raise ValueError('Minecraft model ID did not match the requested entity')
    layers = model.get('layers', {})
    if not isinstance(layers, dict) or not isinstance(layers.get('main'), dict):
        raise ValueError('Minecraft model does not have a main geometry layer')
    # Reject resource-abuse before handing the tree to the JavaScript viewer.
    if len(layers) > 8 or len(raw) > MAX_MODEL_BYTES:
        raise ValueError('Minecraft model exceeds supported complexity')
    return model


def load_model(kind: str, cache_root: Path, *, fetch_missing: bool = True):
    """Load an extracted model locally, fetching it once on explicit refresh."""
    if not SAFE_ID.fullmatch(kind):
        return None, 'Unsupported entity resource name'
    cache_root.mkdir(parents=True, exist_ok=True)
    cached = cache_root / MODEL_VERSION / (kind + '.json')
    if cached.is_file():
        try:
            return _validate_model(cached.read_bytes(), kind), None
        except (ValueError, OSError, UnicodeError):
            # A corrupt downloaded record is never silently trusted.
            cached.unlink(missing_ok=True)
    if not fetch_missing:
        return None, 'Model definition not cached'
    url = MODEL_URL.format(kind)
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={'User-Agent': 'MinecraftLivingWorldWallpaper/0.3'}),
                timeout=5) as response:
            raw = response.read(MAX_MODEL_BYTES + 1)
        model = _validate_model(raw, kind)
        cached.parent.mkdir(parents=True, exist_ok=True)
        from tempfile import NamedTemporaryFile
        import os
        with NamedTemporaryFile(dir=cached.parent, prefix='.mww-model-',
                                delete=False) as tmp:
            tmp.write(raw)
            temporary = Path(tmp.name)
        try:
            os.replace(temporary, cached)
        finally:
            temporary.unlink(missing_ok=True)
        return model, None
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f'Model unavailable ({type(exc).__name__})'


def _variant(record, kind: str):
    value = record.get('variant')
    if kind == 'cat':
        if isinstance(value, int):
            return CAT_VARIANTS[value] if 0 <= value < len(CAT_VARIANTS) else 'black'
        if isinstance(value, str):
            name = value.rsplit(':', 1)[-1].replace('cat_', '').lower()
            return name if name in CAT_VARIANTS else 'black'
        return 'black'
    if kind == 'horse':
        if isinstance(value, int):
            return HORSE_COATS[value & 255] if value & 255 < len(HORSE_COATS) else 'brown'
        if isinstance(value, str):
            name = value.rsplit(':', 1)[-1]
            return name if name in HORSE_COATS else 'brown'
        return 'brown'
    return None


def _main_texture_candidates(record, model):
    kind = record['type']
    layer = model['layers']['main']
    original = layer.get('textureLocation', '')
    options = []
    variant = _variant(record, kind)
    baby = '_baby' if record.get('baby') else ''
    if kind == 'cat':
        options.extend([
            f'minecraft:textures/entity/cat/cat_{variant}{baby}.png',
            f'minecraft:textures/entity/cat/cat_{variant}.png',
        ])
    elif kind == 'horse':
        options.extend([
            f'minecraft:textures/entity/horse/horse_{variant}{baby}.png',
            f'minecraft:textures/entity/horse/horse_{variant}.png',
        ])
    elif kind == 'wolf' and record.get('tame') == 'tamed':
        options.append('minecraft:textures/entity/wolf/wolf_tame' + baby + '.png')
    if original:
        options.append(original)
    return list(dict.fromkeys(options))


def _jar_png(jar: zipfile.ZipFile, texture_location: str):
    if not isinstance(texture_location, str):
        return None
    namespace, _, tail = texture_location.partition(':')
    if namespace != 'minecraft' or not tail.startswith('textures/entity/'):
        return None
    if '..' in tail or not tail.endswith('.png') or not re.fullmatch(r'[a-z0-9_/.-]+', tail):
        return None
    try:
        with jar.open('assets/minecraft/' + tail) as stream:
            data = stream.read(MAX_TEXTURE_BYTES + 1)
        if len(data) > MAX_TEXTURE_BYTES or not data.startswith(b'\x89PNG\r\n\x1a\n'):
            return None
        return base64.b64encode(data).decode('ascii')
    except KeyError:
        return None


def build_entity_assets(entities, cache_root: Path, jar_path: Path | None,
                        *, fetch_missing=True):
    """Attach only texture/model paths required by the selected saved mobs."""
    pack = {'version': 1, 'modelVersion': MODEL_VERSION,
            'models': {}, 'textures': {}}
    errors = []
    if not entities:
        return pack, errors
    if not jar_path or not Path(jar_path).is_file():
        return pack, ['Select an installed Minecraft client JAR to load real mob textures']
    selected_kinds = sorted({e['type'] for e in entities})
    with zipfile.ZipFile(jar_path) as jar:
        for kind in selected_kinds:
            model, err = load_model(kind, cache_root, fetch_missing=fetch_missing)
            if model is None:
                errors.append(f'{kind}: {err}')
                continue
            available = False
            for entity in (e for e in entities if e['type'] == kind):
                paths = _main_texture_candidates(entity, model)
                for path in paths:
                    if path not in pack['textures']:
                        encoded = _jar_png(jar, path)
                        if encoded:
                            pack['textures'][path] = encoded
                    if path in pack['textures']:
                        entity['texture'] = path
                        available = True
                        break
                if 'texture' not in entity:
                    errors.append(f'{kind}: no matching PNG in selected Minecraft JAR')
                # Additional vanilla layers: collars or similar only when their
                # corresponding model layer and texture are present.
                if 'texture' in entity:
                    layers = []
                    for layer in model.get('passes', []):
                        if not isinstance(layer, dict):
                            continue
                        condition = layer.get('when')
                        if condition == 'tamed' and entity.get('tame') != 'tamed':
                            continue
                        if condition not in (None, 'tamed'):
                            continue
                        layer_name = layer.get('layer', 'main')
                        layer_def = model.get('layers', {}).get(layer_name, {})
                        p = layer.get('textureLocation') or layer_def.get('textureLocation')
                        if not p:
                            continue
                        if entity.get('baby') and p.endswith('.png'):
                            baby_p = p[:-4] + '_baby.png'
                            if baby_p not in pack['textures']:
                                img = _jar_png(jar, baby_p)
                                if img:pack['textures'][baby_p] = img
                            if baby_p in pack['textures']:p = baby_p
                        if p not in pack['textures']:
                            img = _jar_png(jar, p)
                            if img:pack['textures'][p] = img
                        if p in pack['textures']:
                            layers.append({'layer': layer_name, 'texture': p,
                                           'tint': layer.get('tint')})
                    entity['passes'] = layers
            if available:
                pack['models'][kind] = model
    return pack, errors
