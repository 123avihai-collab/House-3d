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
import { buildStairs } from './geometry/stairs.js';
import { buildPerimeter } from './geometry/perimeter.js';
import { buildMamadFrames } from './geometry/openings.js';
import { buildMamad } from './geometry/mamad.js';
import { buildStarters } from './geometry/starters.js';
import { buildWallProposals } from './geometry/proposals.js';
import { buildProps } from './geometry/props.js';
import { buildBlocks } from './geometry/blocks.js';
import { buildOwnerElements } from './geometry/ownerElements.js';
import { buildPlumbing } from '../src/plumbing/index.js';
import { buildElectrical } from '../src/electrical/index.js';
import { buildFinishes } from '../src/finishes/index.js';
import { SunController } from './tools/sun.js';
import { MeasureTool } from './tools/measure.js';
import { InspectTool } from './tools/inspect.js';
import { SectionTool } from './tools/section.js';
import { NotesTool } from './tools/notes.js';
import { FixTool } from './tools/fixes.js';
import { RebarTool } from './tools/rebar.js';
import { Prefs } from './tools/prefs.js';
import { compactRegistry } from './core/compact.js';
import { SearchTool } from './tools/search.js';
import { LabelManager } from './core/labels.js';
import { Proposals } from './tools/proposals.js';
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

  // build timings (window.__buildMs) – to see what the model spends its loading time on
  const T = (window.__buildMs = {}); const tm = (k, f) => { const t0 = performance.now(); const r = f(); T[k] = Math.round(performance.now() - t0); return r; };
  ctx.ground = tm('terrain', () => buildTerrain(ctx));
  tm('site', () => buildSite(ctx));
  const environment = tm('environment', () => buildEnvironment(ctx));
  const quantities = { excavation: tm('excavation', () => buildExcavation(ctx)), piles: tm('piles', () => buildPiles(ctx)), foundations: tm('foundations', () => buildFoundations(ctx)),
    plumbing: tm('plumbingFoundations', () => buildPlumbingFoundations(ctx)), pool: tm('pool', () => buildPool(ctx)), groundFloor: tm('groundFloor', () => buildFloorSkeleton(ctx, data.floorGround)),
    firstFloor: tm('firstFloor', () => buildFloorSkeleton(ctx, data.floorFirst)), roof: tm('roof', () => buildFloorSkeleton(ctx, data.floorRoof)), stairs: tm('stairs', () => buildStairs(ctx)),
    perimeter: tm('perimeter', () => buildPerimeter(ctx)), mamadFrames: tm('mamadFrames', () => buildMamadFrames(ctx)), mamad: tm('mamad', () => buildMamad(ctx)), starters: tm('starters', () => buildStarters(ctx)),
    proposals: tm('proposals', () => buildWallProposals(ctx)), props: tm('props', () => buildProps(ctx)), blocks: tm('blocks', () => buildBlocks(ctx)) };   // windows / doors: on hold (Avihai 07.11 – skeleton first) – only the mamad frames, cast with the walls (ק15); data in data/architecture/openings.json, module js/geometry/openings.js
  buildOwnerChangeZones(ctx);
  buildOwnerElements(ctx);   // OC-12 / OC-13 – elements from the architectural plans, red, for Avihai's check
  const plumbing = tm('plumbing', () => buildPlumbing(ctx));   // plumbing layer (separate module, src/plumbing)
  const electrical = tm('electrical', () => buildElectrical(ctx));
  const finishes = tm('finishes', () => buildFinishes(ctx));   // plaster / waterproofing / tiling prep / room names (src/finishes) – layers off on open, built when first shown   // electrical layer (separate module, src/electrical) – stage ח1: main supply

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
    floors: Object.fromEntries(data.tags.floors.map(f => [f.id, { visible: true, opacity: 1, ceiling: true, slab: true }])),
    stageIndex: data.tags.sequence.length - 1, systemFilter: null,
    sun: { date: today, minutes: 600 },
    section: { hOn: false, hLevel: 3, vOn: false, vAxis: 'E', vPos: 0, vFlip: false },
    notes: [], bookmarks: [], labelsOff: {},
    // proposals layer (js/tools/proposals.js): false = plan mode (as the plans, no red); proposalShow[id] = false hides one change in proposals mode
    proposals: false, proposalShow: {},
    quality: { ao: !mobile, shadows: true, labels: true, exposure: 1.0, minimap: true },
  };
  const store = new StateStore(defaults);
  // a step index from a saved state / link / import that does not exist (the sequence changed) must not break the app
  const nSteps = data.tags.sequence.length;
  const clampStage = (v) => (Number.isInteger(+v) && +v >= 0 && +v < nSteps ? +v : nSteps - 1);
  const rawSet = store.set.bind(store);
  store.set = (patch, o) => rawSet(patch && 'stageIndex' in patch ? { ...patch, stageIndex: clampStage(patch.stageIndex) } : patch, o);
  if (clampStage(store.get().stageIndex) !== store.get().stageIndex) store.set({ stageIndex: nSteps - 1 }, { record: false });

  const app = {
    data, coords, viewer, registry, store, display, defaults, plotCenter, ground: ctx.ground, tools: {}, activeTool: 'inspect', quantities, lineMats,
    sun: new SunController(viewer, coords, display, data.origin.timezone),
  };
  app.sun.center.copy(plotCenter);
  app.environment = environment;
  environment.attach(app);
  app.modules = { plumbing, electrical, finishes }; plumbing?.attach(app); finishes?.attach(app);
  app.compacted = tm('compact', () => compactRegistry(registry, viewer.scene));   // same picture, far fewer objects / draw calls (Avihai 08.11 – after every module built its parts)
  MaterialLibrary.onTexture = () => viewer.invalidate();
  registry.compactor = (fresh) => { compactRegistry(registry, viewer.scene, fresh); viewer.invalidate(); };   // layers built later (registry.defer) – compacted the same way
  app.tools.section = new SectionTool(app);   // before the UI: the stage bar's "גובה קיר" row reads its floors / fill colours
  app.ui = new UI(app);
  app.nav = new Navigation(app);
  app.tools.inspect = new InspectTool(app);
  app.tools.measure = new MeasureTool(app);
  app.tools.notes = new NotesTool(app);
  app.tools.fixes = new FixTool(app);
  app.tools.rebar = new RebarTool(app);
  app.tools.search = new SearchTool(app);
  app.labels = new LabelManager(app);
  app.proposals = new Proposals(app);
  const minimap = app.minimap = new Minimap(app, document.getElementById('minimap'));
  viewer.afterRender = () => { minimap.draw(); updateCompass(); };

  app.setTool = (id) => {
    const map = { inspect: 'inspect', measure: 'measure', note: 'notes', fix: 'fixes' };
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
    const oc = s.proposals ? '1' : '';
    return `${location.origin}${location.pathname}#v=${[...v.cam, ...v.target].join(',')}&stage=${data.tags.sequence[s.stageIndex]?.id || ''}&date=${s.sun.date}&t=${s.sun.minutes}${oc ? '&prop=1' : ''}`;
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
  // "צנרת מוסתרת": the concrete (one shared material) turns half see-through so the pipes in / under it show
  const concreteMats = ['concrete', 'concreteProvisional', 'leanConcrete'].map(k => { try { return materials.get(k); } catch { return null; } }).filter(Boolean);
  const applyState = (s) => {
    for (const m of concreteMats) { const on = !!s.showHidden; if (m.transparent !== on) { m.transparent = on; m.opacity = on ? display.xray.concreteOpacity : 1; m.depthWrite = !on; m.needsUpdate = true; } }
    registry.apply(s);
    app.sun.update(s.sun.date, s.sun.minutes);
    viewer.setAO(s.quality.ao);
    if (viewer.renderer.shadowMap.enabled !== s.quality.shadows) viewer.setShadows(s.quality.shadows);
    viewer.renderer.toneMappingExposure = s.quality.exposure;
    document.body.classList.toggle('no-labels', !s.quality.labels);
    document.body.classList.toggle('no-minimap', s.quality.minimap === false);
    document.querySelector('#toolbar [data-k="minimap"]')?.classList.toggle('on', s.quality.minimap !== false);
    viewer.invalidate();
  };
  store.on(applyState);
  // edit mode = skeleton correction notes for Claude
  let lastMode = store.get().mode;
  store.on((s) => {
    if (s.mode === lastMode) return; const prevMode = lastMode; lastMode = s.mode;
    if (s.mode === 'edit') { app.setTool('fix'); app.ui.openTab('fixes', !app.ui.isMobile()); } else if (app.activeTool === 'fix') app.setTool('inspect');
    // tiling mode = the tiling workshop (src/tiling): tile layer on, the zone list in "נתונים ← סדנת ריצוף"
    if (s.mode === 'tiling') finishes?.tiling?.enter(); else if (prevMode === 'tiling') finishes?.tiling?.leave();
  });
  applyState(store.get());
  app.prefs = new Prefs(app);   // last layers / saved views – restored on open (Avihai 08.11)
  app.ui.refreshPanel();
  app.setTool(store.get().mode === 'edit' ? 'fix' : 'inspect');
  if (store.get().mode === 'tiling') finishes?.tiling?.enter();

  // deep link
  const hp = new URLSearchParams(location.hash.slice(1));
  if (hp.get('v')) { const a = hp.get('v').split(',').map(Number); if (a.length === 6) { viewer.camera.position.set(a[0], a[1], a[2]); viewer.controls.target.set(a[3], a[4], a[5]); } }
  // proposals mode from a link (&prop=1; older links: &oc=OC-n:1 – any change on = proposals mode)
  if (hp.get('prop') || hp.get('oc')) store.set({ proposals: hp.get('prop') === '1' || /:1/.test(hp.get('oc') || '') }, { record: false });
  if (hp.get('stage') || hp.get('date')) {
    const sp = hp.get('stage'); const byId = data.tags.sequence.findIndex(x => x.id === sp);
    store.set({ stageIndex: sp == null ? store.get().stageIndex : byId >= 0 ? byId : clampStage(sp), sun: { date: hp.get('date') || store.get().sun.date, minutes: +(hp.get('t') ?? store.get().sun.minutes) } }, { record: false });
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
    const vis = hits.filter(h => planes.every(p => p.distanceToPoint(h.point) >= 0));
    app.lastHits = vis;   // the measuring snap also looks at the parts just behind the first one (corners shared by two parts)
    return vis[0] || null;
  };
  let down = null;
  el.addEventListener('pointerdown', (e) => { down = { x: e.clientX, y: e.clientY, lx: e.clientX, ly: e.clientY }; });
  el.addEventListener('pointermove', (e) => {
    if (app.nav.walking && down) { app.nav.look(e.clientX - down.lx, e.clientY - down.ly); down.lx = e.clientX; down.ly = e.clientY; return; }
    if (e.pointerType === 'mouse') hover(e);
  });
  el.addEventListener('pointerleave', () => { if (app.activeTool === 'measure') app.tools.measure.hideMarker(); });
  el.addEventListener('pointerup', (e) => {
    if (!down) return;
    const moved = Math.hypot(e.clientX - down.x, e.clientY - down.y) > 6;
    down = null;
    if (moved) return;   // a drag = orbit / look around; a click works in walk mode too (inspect, note, measure, fix)
    const hit = pick(e);
    const map = { inspect: 'inspect', measure: 'measure', note: 'notes', fix: 'fixes' };
    if (app.activeTool === 'measure') app.tools.measure.handleClick(hit, e); else app.tools[map[app.activeTool]]?.handleClick(hit);
    if (hit && app.activeTool === 'inspect' && hit.object.userData.component?.meta.onClick) { hit.object.userData.component.meta.onClick(hit); app.viewer.invalidate(); }   // mamad window / sliding door: open / close
    if (hit) showReadout(hit);
  });
  let hoverT = 0;
  const hover = (e) => { const now = performance.now(); if (now - hoverT < 50) return; hoverT = now; const hit = pick(e); if (hit) showReadout(hit);
    if (app.activeTool === 'measure' && !down) app.tools.measure.handleHover(hit, e); };   // snap marker + live line (not while orbiting)
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
  const el = document.getElementById('loading');
  if (err.webgl || /WebGL/i.test(err.message || '')) glHelp(el, 'הדפדפן לא הצליח לפתוח את הגרפיקה התלת-ממדית (WebGL).');
  else el.textContent = 'שגיאה בטעינה: ' + err.message;
});
// WebGL refused / lost (busy GPU on a tablet or phone): explain and offer a reload
function glHelp(el, why) {
  el.replaceChildren();
  const b = document.createElement('button'); b.textContent = '↻ נסה שוב'; b.onclick = () => location.reload();
  b.style.cssText = 'margin-top:12px;padding:8px 18px;font-size:16px;border-radius:8px;border:0;background:#ff7a45;color:#fff';
  const p = document.createElement('div'); p.style.cssText = 'direction:rtl;text-align:center;line-height:1.6;max-width:520px';
  p.innerHTML = `<b>${why}</b><br>אחרי קריסה של כרטיס הגרפיקה Chrome חוסם את הגרפיקה לאתר עד שהדפדפן נסגר לגמרי – רענון לא מספיק.<br>` +
    '<b>באנדרואיד:</b> הגדרות ← אפליקציות ← Chrome ← <b>עצירה בכפייה</b> (או החלקת Chrome מרשימת האפליקציות הפתוחות), ואז לפתוח מחדש. ' +
    'אם עדיין לא – להפעיל מחדש את הטאבלט.<br><small>בדיקה: לפתוח chrome://gpu ולוודא ש-WebGL מופיע כ-Hardware accelerated.</small>';
  p.append(document.createElement('br'), b); el.append(p); document.body.classList.add('loading');
}
window.addEventListener('house3d-glLost', () => {
  const el = document.getElementById('loading'); if (el) glHelp(el, 'הגרפיקה התלת-ממדית נעצרה (הדפדפן שחרר את זיכרון הגרפיקה).');
});
