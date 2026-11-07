import * as THREE from 'three';
import { loadData } from './core/data.js';
import { Coords } from './core/coords.js';
import { Viewer } from './core/viewer.js';
import { Registry } from './core/registry.js';
import { StateStore } from './core/state.js';
import { MaterialLibrary } from './core/materials.js';
import { buildTerrain } from './geometry/terrain.js';
import { buildSite, centroid } from './geometry/site.js';
import { buildEnvironment } from '../src/environment/index.js';
import { buildExcavation } from './geometry/excavation.js';
import { buildPiles } from './geometry/piles.js';
import { buildFoundations, buildPlumbingFoundations, buildOwnerChangeZones, buildPool } from './geometry/foundations.js';
import { buildFloorSkeleton } from './geometry/floors.js';
import { buildPlumbing } from '../src/plumbing/index.js';
import { SunController } from './tools/sun.js';
import { MeasureTool } from './tools/measure.js';
import { InspectTool } from './tools/inspect.js';
import { SectionTool } from './tools/section.js';
import { NotesTool } from './tools/notes.js';
import { Navigation, Minimap } from './tools/navigation.js';
import { UI } from './ui/ui.js';

window.__errors = [];
window.addEventListener('error', e => window.__errors.push(String(e.message)));
window.addEventListener('unhandledrejection', e => window.__errors.push(String(e.reason?.message || e.reason)));

async function main() {
  const data = await loadData('./');
  const mobile = matchMedia('(pointer: coarse)').matches || innerWidth < 760;
  const coords = new Coords(data.origin);
  const display = data.display;
  const viewer = new Viewer(document.getElementById('viewport'), display, { hdri: 'assets/hdri/kloofendal_43d_clear_puresky_2k.hdr', mobile });
  const registry = new Registry(data.tags);
  const materials = new MaterialLibrary(data.materials, viewer.renderer, './');
  const lineMats = [];
  const ctx = { data, coords, viewer, registry, materials, scene: viewer.scene, display, lineMats };

  ctx.ground = buildTerrain(ctx);
  buildSite(ctx);
  const environment = buildEnvironment(ctx);
  const quantities = { excavation: buildExcavation(ctx), piles: buildPiles(ctx), foundations: buildFoundations(ctx), plumbing: buildPlumbingFoundations(ctx), pool: buildPool(ctx), groundFloor: buildFloorSkeleton(ctx, data.floorGround) };
  buildOwnerChangeZones(ctx);
  const plumbing = buildPlumbing(ctx);   // plumbing layer (separate module, src/plumbing)

  const pc = centroid(data.plot.ring);
  const plotCenter = coords.toLocal(pc[0], pc[1], ctx.ground.heightAt(pc[0], pc[1]));
  viewer.controls.target.copy(plotCenter);
  viewer.camera.position.copy(plotCenter).add(new THREE.Vector3(-30, 28, 34));
  viewer.fitShadowTo(plotCenter, display.sun.shadowExtent_m);
  viewer.onResize = (w, hgt) => lineMats.forEach(m => m.resolution.set(w, hgt));
  viewer.onResize(viewer.resolution.x, viewer.resolution.y);

  // ---------- default settings ----------
  const layers = {};
  for (const g of data.layers.groups) for (const l of g.layers) layers[l.id] = g.implemented && l.implemented !== false ? l.visible !== false : false;
  const today = new Date().toLocaleDateString('sv-SE', { timeZone: data.origin.timezone });
  const defaults = {
    version: 2, mode: 'view', layers,
    floors: Object.fromEntries(data.tags.floors.map(f => [f.id, { visible: true, opacity: 1 }])),
    stageIndex: data.tags.sequence.length - 1, systemFilter: null,
    sun: { date: today, minutes: 600 },
    section: { hOn: false, hLevel: 3, vOn: false, vAxis: 'E', vPos: 0, vFlip: false },
    notes: [], bookmarks: [], labelsOff: {},
    ownerChanges: Object.fromEntries((data.ownerChanges?.changes || []).map(c => [c.id, true])),
    quality: { ao: !mobile, shadows: true, labels: true, exposure: 1.0 },
  };
  const store = new StateStore(defaults);

  const app = {
    data, coords, viewer, registry, store, display, defaults, plotCenter, ground: ctx.ground, tools: {}, activeTool: 'inspect', quantities,
    sun: new SunController(viewer, coords, display, data.origin.timezone),
  };
  app.sun.center.copy(plotCenter);
  app.environment = environment;
  environment.attach(app);
  app.modules = { plumbing }; plumbing?.attach(app);
  app.ui = new UI(app);
  app.nav = new Navigation(app);
  app.tools.inspect = new InspectTool(app);
  app.tools.measure = new MeasureTool(app);
  app.tools.notes = new NotesTool(app);
  app.tools.section = new SectionTool(app);
  const minimap = new Minimap(app, document.getElementById('minimap'));
  viewer.afterRender = () => { minimap.draw(); updateCompass(); };

  app.setTool = (id) => {
    const map = { inspect: 'inspect', measure: 'measure', note: 'notes' };
    app.tools[map[app.activeTool]]?.deactivate?.();
    app.activeTool = id;
    app.tools[map[id]]?.activate?.();
    app.ui.setActiveTool(id);
    app.ui.refreshPanel();
  };
  app.currentView = () => ({ cam: viewer.camera.position.toArray().map(v => +v.toFixed(3)), target: viewer.controls.target.toArray().map(v => +v.toFixed(3)) });
  app.restoreView = (b) => { app.nav.stopWalk(); viewer.flyTo(new THREE.Vector3(...b.target), new THREE.Vector3(...b.cam)); };
  app.flyToPoint = (n) => { const t = coords.toLocal(n.E, n.N, n.H); viewer.flyTo(t, t.clone().add(new THREE.Vector3(6, 6, 6))); };
  app.viewLink = () => {
    const v = app.currentView(); const s = store.get();
    const oc = Object.entries(s.ownerChanges || {}).map(([k, v]) => `${k}:${v ? 1 : 0}`).join(',');
    return `${location.origin}${location.pathname}#v=${[...v.cam, ...v.target].join(',')}&stage=${s.stageIndex}&date=${s.sun.date}&t=${s.sun.minutes}${oc ? '&oc=' + oc : ''}`;
  };
  let playTimer = null;
  app.toggleSunPlay = () => {
    if (playTimer) { clearInterval(playTimer); playTimer = null; app.sunPlaying = false; app.ui.refreshPanel('sun'); return; }
    app.sunPlaying = true;
    playTimer = setInterval(() => {
      const s = store.get(); let m = s.sun.minutes + 5; if (m > 1260) m = 240;
      store.set({ sun: { ...s.sun, minutes: m } }, { record: false });
    }, 60);
    app.ui.refreshPanel('sun');
  };

  // ---------- apply state ----------
  const applyState = (s) => {
    registry.apply(s);
    app.sun.update(s.sun.date, s.sun.minutes);
    viewer.setAO(s.quality.ao);
    if (viewer.renderer.shadowMap.enabled !== s.quality.shadows) viewer.setShadows(s.quality.shadows);
    viewer.renderer.toneMappingExposure = s.quality.exposure;
    document.body.classList.toggle('no-labels', !s.quality.labels);
    viewer.invalidate();
  };
  store.on(applyState);
  applyState(store.get());
  app.ui.refreshPanel();
  app.setTool('inspect');

  // deep link
  const hp = new URLSearchParams(location.hash.slice(1));
  if (hp.get('v')) { const a = hp.get('v').split(',').map(Number); if (a.length === 6) { viewer.camera.position.set(a[0], a[1], a[2]); viewer.controls.target.set(a[3], a[4], a[5]); } }
  if (hp.get('oc')) {
    const cur = { ...(store.get().ownerChanges || {}) };
    for (const kv of hp.get('oc').split(',')) { const [k, v] = kv.split(':'); if (k in cur) cur[k] = v === '1'; }
    store.set({ ownerChanges: cur }, { record: false });
  }
  if (hp.get('stage') || hp.get('date')) {
    store.set({ stageIndex: +(hp.get('stage') ?? store.get().stageIndex), sun: { date: hp.get('date') || store.get().sun.date, minutes: +(hp.get('t') ?? store.get().sun.minutes) } }, { record: false });
  }

  // ---------- pointer: click tools, hover readout, walk look ----------
  const el = viewer.renderer.domElement;
  const ray = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  const pick = (e) => {
    const r = el.getBoundingClientRect();
    ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ndc, viewer.camera);
    const hits = ray.intersectObjects(registry.pickables(), false);
    const planes = viewer.renderer.clippingPlanes;
    return hits.find(h => planes.every(p => p.distanceToPoint(h.point) >= 0)) || null;
  };
  let down = null;
  el.addEventListener('pointerdown', (e) => { down = { x: e.clientX, y: e.clientY, lx: e.clientX, ly: e.clientY }; });
  el.addEventListener('pointermove', (e) => {
    if (app.nav.walking && down) { app.nav.look(e.clientX - down.lx, e.clientY - down.ly); down.lx = e.clientX; down.ly = e.clientY; return; }
    if (e.pointerType === 'mouse') hover(e);
  });
  el.addEventListener('pointerup', (e) => {
    if (!down) return;
    const moved = Math.hypot(e.clientX - down.x, e.clientY - down.y) > 6;
    down = null;
    if (moved || app.nav.walking) return;
    const hit = pick(e);
    const map = { inspect: 'inspect', measure: 'measure', note: 'notes' };
    app.tools[map[app.activeTool]]?.handleClick(hit);
    if (hit) showReadout(hit);
  });
  let hoverT = 0;
  const hover = (e) => { const now = performance.now(); if (now - hoverT < 50) return; hoverT = now; const hit = pick(e); if (hit) showReadout(hit); };
  const showReadout = (hit) => {
    const P = coords.fromLocal(hit.point);
    app.ui.status(`${coords.fmtEN(P.E, P.N)} · H ${coords.fmtH(P.H)} · ${hit.object.userData.component?.meta?.name || ''}`);
  };

  // touch joystick for walk mode
  const joy = document.getElementById('joy');
  const knob = joy.querySelector('i');
  let jid = null, jc = null;
  joy.addEventListener('pointerdown', (e) => { jid = e.pointerId; const r = joy.getBoundingClientRect(); jc = { x: r.left + r.width / 2, y: r.top + r.height / 2, R: r.width / 2 }; joy.setPointerCapture(jid); });
  joy.addEventListener('pointermove', (e) => {
    if (e.pointerId !== jid) return;
    let dx = (e.clientX - jc.x) / jc.R, dy = (e.clientY - jc.y) / jc.R; const L = Math.hypot(dx, dy); if (L > 1) { dx /= L; dy /= L; }
    app.nav.joy = { x: dx, y: dy }; knob.style.transform = `translate(${dx * 30}px, ${dy * 30}px)`;
  });
  const jend = () => { jid = null; app.nav.joy = { x: 0, y: 0 }; knob.style.transform = ''; };
  joy.addEventListener('pointerup', jend); joy.addEventListener('pointercancel', jend);

  // compass follows camera heading (grid north; true north offset is ~0.2°)
  const compass = document.getElementById('compass');
  function updateCompass() {
    const d = new THREE.Vector3(); viewer.camera.getWorldDirection(d);
    const ang = Math.atan2(d.x, -d.z) * 180 / Math.PI + coords.trueNorthGridAz;
    compass.style.transform = `rotate(${-ang}deg)`;
  }

  await viewer.hdriReady;
  document.body.classList.remove('loading');
  window.__app = app;
  window.__ready = true;
}

main().catch(err => {
  console.error(err);
  window.__errors.push(String(err.message || err));
  document.getElementById('loading').textContent = 'שגיאה בטעינה: ' + err.message;
});
