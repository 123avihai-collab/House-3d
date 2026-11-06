import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { HDRLoader } from 'three/addons/loaders/HDRLoader.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { GTAOPass } from 'three/addons/postprocessing/GTAOPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { CSS2DRenderer } from 'three/addons/renderers/CSS2DRenderer.js';

// Renderer, scene, camera, controls, HDRI environment, sun light with soft shadows, GTAO ambient occlusion.
export class Viewer {
  constructor(container, display, { hdri, mobile }) {
    this.container = container;
    this.display = display;
    this.mobile = mobile;
    this.updaters = [];
    this.needsRender = true;

    const r = this.renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
    r.setPixelRatio(Math.min(window.devicePixelRatio, mobile ? 1.5 : 2));
    r.outputColorSpace = THREE.SRGBColorSpace;
    r.toneMapping = THREE.ACESFilmicToneMapping;
    r.toneMappingExposure = 1.0;
    r.shadowMap.enabled = true;
    r.shadowMap.type = THREE.PCFShadowMap;
    r.localClippingEnabled = true;
    container.appendChild(r.domElement);

    this.labels = new CSS2DRenderer();
    this.labels.domElement.className = 'label-layer';
    container.appendChild(this.labels.domElement);

    this.scene = new THREE.Scene();
    const c = display.camera;
    this.camera = new THREE.PerspectiveCamera(c.fov, 1, c.near, c.far);
    this.camera.position.set(-35, 32, 38);

    this.controls = new OrbitControls(this.camera, r.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.maxPolarAngle = Math.PI * 0.495;
    this.controls.target.set(0, 0, 0);
    this.controls.addEventListener('change', () => this.invalidate());

    // sun
    const s = display.sun;
    this.sun = new THREE.DirectionalLight(0xffffff, s.intensity);
    this.sun.castShadow = true;
    const sz = mobile ? Math.min(2048, s.shadowMapSize) : s.shadowMapSize;
    this.sun.shadow.mapSize.set(sz, sz);
    const ext = s.shadowExtent_m;
    Object.assign(this.sun.shadow.camera, { left: -ext, right: ext, top: ext, bottom: -ext, near: 1, far: 600 });
    this.sun.shadow.radius = s.shadowRadius;
    this.sun.shadow.bias = -0.0004;
    this.sun.shadow.normalBias = 0.03;
    this.scene.add(this.sun, this.sun.target);

    // environment (HDRI)
    this.hdriReady = resolveHdri(hdri).then((url) => new Promise((resolve) => {
      new HDRLoader().load(url, (tex) => {
        tex.mapping = THREE.EquirectangularReflectionMapping;
        const pmrem = new THREE.PMREMGenerator(r);
        this.scene.environment = pmrem.fromEquirectangular(tex).texture;
        this.scene.environmentIntensity = s.ambientEnvIntensity;
        this.scene.background = tex;
        this.scene.backgroundIntensity = 0.9;
        pmrem.dispose();
        this.invalidate();
        resolve();
      }, undefined, (e) => { console.error('HDRI', e); resolve(); });
    }));

    // post-processing
    this.composer = new EffectComposer(r);
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    const ao = display.ao;
    this.gtao = new GTAOPass(this.scene, this.camera, 512, 512);
    this.gtao.updateGtaoMaterial({ radius: ao.radius, distanceFallOff: ao.distanceFallOff, thickness: ao.thickness });
    this.gtao.blendIntensity = ao.blendIntensity;
    this.gtao.enabled = ao.enabled && !mobile;
    this.composer.addPass(this.gtao);
    this.composer.addPass(new OutputPass());

    this.timer = new THREE.Timer();
    window.addEventListener('resize', () => this.resize());
    this.resize();
    const loop = () => {
      requestAnimationFrame(loop);
      this.timer.update(); const dt = Math.min(this.timer.getDelta(), 0.1);
      let active = false;
      for (const u of this.updaters) active = u(dt) || active;
      if (this.controls.enabled && this.controls.update()) active = true;
      if (this.needsRender || active) {
        this.needsRender = false;
        this.composer.render();
        this.labels.render(this.scene, this.camera);
        this.afterRender?.();
      }
    };
    loop();
  }
  invalidate() { this.needsRender = true; }
  resize() {
    const w = this.container.clientWidth, h = this.container.clientHeight;
    this.camera.aspect = w / Math.max(h, 1);
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h);
    this.composer.setSize(w, h);
    this.labels.setSize(w, h);
    this.resolution = new THREE.Vector2(w, h);
    this.onResize?.(w, h);
    this.invalidate();
  }
  setAO(on) { this.gtao.enabled = on; this.invalidate(); }
  setShadows(on) {
    this.renderer.shadowMap.enabled = on;
    this.scene.traverse(o => { if (o.material) (Array.isArray(o.material) ? o.material : [o.material]).forEach(m => { m.needsUpdate = true; }); });
    this.invalidate();
  }
  fitShadowTo(center, radius) {
    const sc = this.sun.shadow.camera;
    sc.left = -radius; sc.right = radius; sc.top = radius; sc.bottom = -radius;
    sc.updateProjectionMatrix();
    this.shadowCenter = center.clone();
  }
  flyTo(target, position, ms = 700) {
    const t0 = performance.now();
    const p0 = this.camera.position.clone(), q0 = this.controls.target.clone();
    const step = () => {
      const k = Math.min(1, (performance.now() - t0) / ms);
      const e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
      this.camera.position.lerpVectors(p0, position, e);
      this.controls.target.lerpVectors(q0, target, e);
      this.invalidate();
      if (k < 1) requestAnimationFrame(step);
    };
    step();
  }
  screenshot() { this.composer.render(); return this.renderer.domElement.toDataURL('image/png'); }
}

// The claude.ai artifact host does not serve .hdr files, so the publish step
// (tools/build_artifact.py) adds a base64 copy next to it: <name>.hdr.b64.txt.
// Use the binary file when it is served, otherwise decode the base64 copy.
async function resolveHdri(url) {
  try {
    const bin0 = await fetch(url);
    if (bin0.ok) return URL.createObjectURL(await bin0.blob());
    await bin0.text(); // drain the 404 body so the request completes cleanly
    const res = await fetch(url + '.b64.txt');
    if (!res.ok) return url;
    const b64 = (await res.text()).replace(/\s+/g, '');
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return URL.createObjectURL(new Blob([bytes], { type: 'application/octet-stream' }));
  } catch {
    return url;
  }
}
