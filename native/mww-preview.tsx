// Wallpaper visual preview and independent saved-mob layer for Vantage.
// Terrain/surface chunks, caves, LOD and tile protocol are intentionally absent.
import { useEffect, useState } from 'react';
import * as THREE from 'three';
import { Panel } from '../src/react/Panel.js';
import { useVantage } from '../src/react/context.js';
import { createMwwEntityGeometry } from './mww-models.js';

type Appearance = {
  sunStrength: number; sunWarmth: number; sunAzimuth: number;
  hazeStart: number; hazeCurve: number; fog: number;
};
type Preset = 'vanilla' | 'cinematic' | 'misty';

const PRESETS: Record<Preset, Appearance> = {
  vanilla: { sunStrength: 0, sunWarmth: 0, sunAzimuth: 36,
             hazeStart: 0.12, hazeCurve: 1, fog: 1 },
  cinematic: { sunStrength: 0.58, sunWarmth: 0.40, sunAzimuth: 36,
               hazeStart: 0.07, hazeCurve: 0.72, fog: 1 },
  misty: { sunStrength: 0.35, sunWarmth: 0.23, sunAzimuth: 25,
           hazeStart: 0, hazeCurve: 0.52, fog: 1 },
};

export function MwwPreviewPanel({ wallpaper = false }: { wallpaper?: boolean }) {
  const { viewer } = useVantage();
  const [preset, setPreset] = useState<Preset | 'custom'>('cinematic');
  const [appearance, setAppearance] = useState<Appearance>(PRESETS.cinematic);

  useEffect(() => {
    if (!viewer) return;
    viewer.setDisplay(PRESETS.cinematic);
  }, [viewer]);

  const set = (next: Partial<Appearance>) => {
    if (!viewer) return;
    const merged = { ...appearance, ...next };
    setAppearance(merged);
    setPreset('custom');
    viewer.setDisplay(merged);
  };
  if (!viewer || wallpaper) return null;

  const sliders: { key: keyof Appearance; label: string; min: number; max: number; step: number }[] = [
    { key: 'sunStrength', label: 'sun relief', min: 0, max: 1, step: 0.05 },
    { key: 'sunWarmth', label: 'sun warmth', min: 0, max: 1, step: 0.05 },
    { key: 'sunAzimuth', label: 'sun direction', min: 0, max: 360, step: 5 },
    { key: 'hazeStart', label: 'haze start', min: 0, max: 0.8, step: 0.05 },
    { key: 'hazeCurve', label: 'haze softness', min: 0.3, max: 2, step: 0.05 },
    { key: 'fog', label: 'haze amount', min: 0, max: 1, step: 0.05 },
  ];

  return <Panel icon="☀" title="wallpaper look" defaultCollapsed={true}
    style={{ top: 16, left: 16, right: 'auto', bottom: 'auto', width: 220 }}>
    <div className="vtg-sliders">
      <div className="vtg-seg vtg-seg-full">
        {(['vanilla', 'cinematic', 'misty'] as const).map(name =>
          <button key={name} className={preset === name ? 'vtg-seg-on' : undefined}
            onClick={() => {
              const next = PRESETS[name];
              setPreset(name);
              setAppearance(next);
              viewer.setDisplay(next);
            }}>{name}</button>
        )}
      </div>
      {sliders.map(s => <label className="vtg-slider" key={s.key}>
        <span className="vtg-slider-row">
          <span>{s.label}</span><b>{appearance[s.key].toFixed(s.key === 'sunAzimuth' ? 0 : 2)}</b>
        </span>
        <input type="range" min={s.min} max={s.max} step={s.step}
          value={appearance[s.key]} onChange={e => set({ [s.key]: Number(e.target.value) })}/>
      </label>)}
      <small style={{ color: '#93a9cc' }}>
        Uses native Vantage terrain shaders and baked AO. Directional relief is
        a material preview, not a cast-shadow simulation.
      </small>
    </div>
  </Panel>;
}

type MobPack = {
  schema: number; dimension: string;
  entities: Array<{ type: string; pos: number[]; yaw: number; texture?: string }>;
  pack: { version: number; models: Record<string, unknown>; textures: Record<string, string> };
  counts?: { nearby: number; important: number; textured: number };
  warnings?: string[];
};

function makeMobs(data: MobPack, viewer: import('../src/three/viewer.js').VantageViewer): {
  group: THREE.Group; dispose: () => void;
} {
  const group = new THREE.Group();
  group.name = 'mww-saved-mobs';
  const owned: THREE.BufferGeometry[] = [];
  const materials = new Map<string, THREE.MeshLambertMaterial>();
  const textures = new Map<string, THREE.Texture>();
  const overlays = createMwwEntityGeometry(data.entities, data.pack, [0, 0, 0]);
  const trigger = () => viewer.setDisplay({}); // request next on-demand frame

  for (const overlay of overlays) {
    if (!overlay.vertices || overlay.vertices.length === 0 || overlay.vertices.length % 12) continue;
    const png = data.pack.textures[overlay.texture];
    if (!png) continue;
    let mat = materials.get(overlay.texture);
    if (!mat) {
      const image = new THREE.TextureLoader().load('data:image/png;base64,' + png, trigger);
      image.flipY = false; // matches Minecraft's unflipped legacy model UV net
      image.colorSpace = THREE.SRGBColorSpace;
      image.magFilter = THREE.NearestFilter;
      image.minFilter = THREE.NearestMipmapNearestFilter;
      textures.set(overlay.texture, image);
      mat = new THREE.MeshLambertMaterial({
        map: image, vertexColors: true, alphaTest: 0.1, side: THREE.DoubleSide,
      });
      materials.set(overlay.texture, mat);
    }

    // The existing model adapter produces WORLD-SPACE triangles and normal,
    // UV and tint attributes. No terrain heightmap or surface-floor lookup.
    const src: Float32Array = overlay.vertices;
    const count = src.length / 12;
    const pos = new Float32Array(count * 3);
    const nrm = new Float32Array(count * 3);
    const uv = new Float32Array(count * 2);
    const tint = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const at = i * 12;
      pos.set(src.subarray(at, at + 3), i * 3);
      nrm.set(src.subarray(at + 3, at + 6), i * 3);
      uv.set(src.subarray(at + 6, at + 8), i * 2);
      tint.set(src.subarray(at + 8, at + 11), i * 3);
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geometry.setAttribute('normal', new THREE.BufferAttribute(nrm, 3));
    geometry.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
    geometry.setAttribute('color', new THREE.BufferAttribute(tint, 3));
    geometry.computeBoundingSphere();
    owned.push(geometry);
    const mesh = new THREE.Mesh(geometry, mat);
    mesh.frustumCulled = true;
    group.add(mesh);
  }
  viewer.scene.add(group);

  // Vantage terrain uses its own saved-light shader. These two scene lights
  // exclusively light the separate standard-material mob models.
  const ambient = new THREE.HemisphereLight(0xb5d8ff, 0x463728, 2.4);
  const sun = new THREE.DirectionalLight(0xfff1d4, 2.3);
  sun.position.set(80, 150, 65);
  group.add(ambient, sun);
  trigger();

  return {
    group,
    dispose: () => {
      viewer.scene.remove(group);
      owned.forEach(g => g.dispose());
      materials.forEach(m => m.dispose());
      textures.forEach(t => t.dispose());
      trigger();
    },
  };
}

export function MwwMobLayer() {
  const { viewer } = useVantage();
  const [status, setStatus] = useState<string>('');

  useEffect(() => {
    if (!viewer) return;
    let cancelled = false;
    let active: ReturnType<typeof makeMobs> | null = null;

    const load = async () => {
      try {
        const response = await fetch('/mww-mobs.json', { cache: 'no-store' });
        if (!response.ok) throw new Error('Saved-mob snapshot unavailable');
        const json = await response.json() as MobPack;
        if (cancelled) return;
        if (json.schema !== 1 || json.pack?.version !== 1 ||
            !Array.isArray(json.entities) || json.entities.length > 24) {
          throw new Error('Invalid local mob scene version or count');
        }
        active = makeMobs(json, viewer);
        setStatus(json.counts?.textured
          ? 'saved mobs: ' + json.counts.textured
          : 'saved mobs: no textured models' +
            (json.warnings?.length ? ' (check model/JAR assets)' : ''));
      } catch (error) {
        if (!cancelled) {
          setStatus(error instanceof Error ? error.message : 'Saved-mob overlay unavailable');
        }
      }
    };
    void load();
    return () => {
      cancelled = true;
      active?.dispose();
    };
  }, [viewer]);

  if (!status || new URLSearchParams(location.search).has('wallpaper')) return null;
  return <div className="vtg-glass" style={{
    position: 'absolute', right: 255, top: 16, padding: '6px 10px',
    pointerEvents: 'none', color: '#bfd0e8', fontSize: 11,
  }}>{status}</div>;
}
