import * as THREE from 'three';

// Builds PBR materials from data/materials/materials.json. Texture tiles are mapped in world metres
// (geometry UVs are in metres; each material's texture repeat = 1/size_m).
export class MaterialLibrary {
  constructor(def, renderer, base = './') {
    this.def = def.materials;
    this.cache = new Map();
    this.loader = new THREE.TextureLoader();
    this.maxAniso = Math.min(renderer.capabilities.getMaxAnisotropy(), matchMedia('(pointer: coarse)').matches ? 4 : 16);   // less texture memory on tablets / phones
    this.base = base;
  }
  get(name) {
    if (this.cache.has(name)) return this.cache.get(name);
    const d = this.def[name];
    if (!d) throw new Error(`material ${name} not defined`);
    const m = new THREE.MeshStandardMaterial({
      color: new THREE.Color(d.tint || d.color || '#ffffff'),
      roughness: d.roughness ?? 1,
      metalness: 0,
      transparent: !!d.transparent,
      opacity: d.opacity ?? 1,
      envMapIntensity: d.envMapIntensity ?? 1,
      side: d.transparent ? THREE.DoubleSide : THREE.FrontSide,
    });
    if (d.texture) {
      const rep = 1 / d.size_m;
      const tex = (file, srgb) => {
        const t = this.loader.load(`${this.base}${d.texture}/${file}.jpg`);
        t.wrapS = t.wrapT = THREE.RepeatWrapping;
        t.repeat.set(rep, rep);
        t.anisotropy = this.maxAniso;
        if (srgb) t.colorSpace = THREE.SRGBColorSpace;
        return t;
      };
      m.map = tex('color', true);
      m.normalMap = tex('normal', false);
      m.roughnessMap = tex('roughness', false);
      m.aoMap = tex('ao', false);
      m.aoMapIntensity = 1;
    }
    m.name = name;
    this.cache.set(name, m);
    return m;
  }
}
