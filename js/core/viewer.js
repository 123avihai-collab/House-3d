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

    // WebGL may be refused on a busy tablet / phone (GPU memory taken by other tabs): fall back to lighter settings
    // before giving up (Avihai 08.11: "Error creating WebGL context")
    const tries = [{ antialias: true, preserveDrawingBuffer: true, powerPreference: 'high-performance' },
      { antialias: false, preserveDrawingBuffer: true, powerPreference: 'default' },
      { antialias: false, preserveDrawingBuffer: false, powerPreference: 'low-power', failIfMajorPerformanceCaveat: false }];
    let r = null, lastErr = null;
    for (const [i, o] of tries.entries()) {
      try { r = new THREE.WebGLRenderer(o); this.lite = i > 0; break; } catch (e) { lastErr = e; }
    }
    if (!r) throw Object.assign(new Error('webgl'), { webgl: true, cause: lastErr });
    this.renderer = r;
    r.setPixelRatio(Math.min(window.devicePixelRatio, this.lite ? 1 : mobile ? 1.25 : 2));
    r.domElement.addEventListener('webglcontextlost', (e) => { e.preventDefault(); window.dispatchEvent(new CustomEvent('house3d-glLost')); });
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
    const sz = mobile ? Math.min(1024, s.shadowMapSize) : s.shadowMapSize;   // tablets / phones: less GPU memory (WebGL was blocked after GPU crashes, 08.11)
    this.sun.shadow.mapSize.set(sz, sz);
    const ext = s.shadowExtent_m;
    Object.assign(this.sun.shadow.camera, { left: -ext, right: ext, top: ext, bottom: -ext, near: 1, far: 600 });
    this.sun.shadow.radius = s.shadowRadius;
    this.sun.shadow.bias = -0.0004;
    this.sun.shadow.normalBias = 0.03;
    this.scene.add(this.sun, this.sun.target);

    // environment (HDRI)
    const useEnv = (tex) => {
      tex.mapping = THREE.EquirectangularReflectionMapping;
      const pmrem = new THREE.PMREMGenerator(r);
      this.scene.environment = pmrem.fromEquirectangular(tex).texture;
      this.scene.environmentIntensity = s.ambientEnvIntensity;
      this.scene.background = tex;
      this.scene.backgroundIntensity = 0.9;
      pmrem.dispose();
      this.invalidate();
    };
    // hosts that do not serve .hdr files (e.g. the Claude artifact page) get the same bytes as base64 text: <hdri>.b64.txt
    const fromBase64 = async () => {
      const txt = await (await fetch(hdri + '.b64.txt')).text();
      const bin = atob(txt.trim()); const buf = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
      const td = new HDRLoader().parse(buf.buffer);
      const tex = new THREE.DataTexture(td.data, td.width, td.height, THREE.RGBAFormat, td.type);
      tex.colorSpace = THREE.LinearSRGBColorSpace; tex.minFilter = tex.magFilter = THREE.LinearFilter; tex.generateMipmaps = false; tex.flipY = true; tex.needsUpdate = true;
      return tex;
    };
    this.hdriReady = new Promise((resolve) => {
      new HDRLoader().load(hdri, (tex) => { useEnv(tex); resolve(); }, undefined,
        () => fromBase64().then(useEnv).catch((e) => console.error('HDRI', e)).finally(resolve));
    });

    // post-processing
    // a stencil buffer in the post-processing target: the section fill (js/tools/section.js) counts the cut solids in it
    { const sz = r.getSize(new THREE.Vector2()), pr = r.getPixelRatio();
      const rt = new THREE.WebGLRenderTarget(sz.x * pr, sz.y * pr, { type: THREE.HalfFloatType, stencilBuffer: true });
      rt.texture.name = 'EffectComposer.rt1';
      this.composer = new EffectComposer(r, rt); }
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    const ao = display.ao;
    this.gtao = new GTAOPass(this.scene, this.camera, 512, 512);
    this.gtao.updateGtaoMaterial({ radius: ao.radius, distanceFallOff: ao.distanceFallOff, thickness: ao.thickness });
    this.gtao.blendIntensity = ao.blendIntensity;
    // the AO depth / normal pass draws every mesh with one override material: front faces only by default, so a thin
    // double-sided sheet (plaster, waterproofing) seen from its back was skipped and the blocks / beam edges behind it
    // showed through as dark lines (12.11.2026). Both sides, as the meshes themselves are drawn.
    this.gtao.normalMaterial.side = THREE.DoubleSide;
    // the section-fill stencil helpers draw nothing themselves: kept out of the AO normal / depth pass
    { const g = this.gtao, ov = g._overrideVisibility.bind(g);
      g._overrideVisibility = () => { ov(); this.scene.traverse(o => { if (o.userData.sectionCap && o.visible) { o.visible = false; g._visibilityCache.push(o); } }); }; }
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
        this.beforeLabels?.();
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
