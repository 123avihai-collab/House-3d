import * as THREE from 'three';
import { houseAxes } from './snap.js';

// Navigation: viewpoints (from data), saved views, eye-level walk mode (keyboard / touch joystick,
// follows any surface below incl. future stairs), and a minimap.
export class Navigation {
  constructor(app) {
    this.app = app;
    this.walking = false;
    this.keys = new Set();
    this.yaw = 0; this.pitch = 0;
    this.joy = { x: 0, y: 0 };
    this.ray = new THREE.Raycaster(); this.ray.camera = app.viewer.camera;
    app.viewer.updaters.push((dt) => this.step(dt));
    window.addEventListener('keydown', e => { if (this.walking && !isTyping(e)) { this.keys.add(e.code); e.preventDefault(); } });
    window.addEventListener('keyup', e => this.keys.delete(e.code));
  }
  viewpoints() {
    const { data, coords, ground } = this.app;
    const c = this.app.plotCenter;
    const vps = [
      { id: 'overview', label: 'מבט כללי על המגרש', target: c, offset: new THREE.Vector3(-30, 28, 34) },
      { id: 'top', label: 'מבט על (צפון למעלה)', target: c, offset: new THREE.Vector3(0, 70, 0.01) },
      { id: 'street', label: 'מהרחוב (דרום-מערב)', target: c, offset: new THREE.Vector3(-14, 4, 26) },
      { id: 'foundations', label: 'יסודות ומרתף', target: c.clone().add(new THREE.Vector3(2, -2, -1)), offset: new THREE.Vector3(0, 15, 23), stage: 'walls' },
      { id: 'sewer', label: 'ביוב: שוחות וצנרת', target: c.clone().add(new THREE.Vector3(-4, -1.5, 8)), offset: new THREE.Vector3(1, 8.5, 11), stage: 'walls' },
      { id: 'groundSkeleton', label: 'שלד קומת הקרקע', target: c.clone().add(new THREE.Vector3(1, 1, -1)), offset: new THREE.Vector3(-14, 14, 20), step: 'groundCeiling' },
      { id: 'pit', label: 'חפירה וכלונסאות', target: c.clone().add(new THREE.Vector3(0, -3, 0)), offset: new THREE.Vector3(-16, 13, 18), stage: 'piles' },
    ];
    for (const [name, p] of Object.entries(data.plot.points)) {
      const t = coords.toLocal(p.E, p.N, ground.heightAt(p.E, p.N));
      vps.push({ id: 'pt' + name, label: `נקודת גבול ${name}`, target: t, offset: new THREE.Vector3(6, 6, 6) });
    }
    return vps;
  }
  goTo(vp) {
    this.stopWalk();
    if (vp.stage || vp.step) { const i = vp.step ? this.app.registry.stepById(vp.step) : this.app.registry.stepIndex(vp.stage, 'unit'); if (i >= 0) this.app.store.set({ stageIndex: i }, { label: 'stage' }); }
    this.app.viewer.flyTo(vp.target.clone(), vp.target.clone().add(vp.offset));
  }
  // ----- walk -----
  // Walkable surfaces = every visible component (slabs, landings, stair treads, beams, terrain…) whose face under the walker
  // points up; the walker climbs up to stepUp_m (stairs, slab level steps), descends off an edge at fallSpeed_mps, and is
  // stopped by walls (vertical faces) at wallClearance_m. Constants: data/config/display.json "camera".
  walkMeshes() {
    if (!this._walk) {
      const skip = new Set(['ghost', 'overlay', 'lines', 'labels', 'points', 'symbol', 'grid', 'marks']);
      // solid meshes only (fat lines / marks are meshes too)
      this._walk = this.app.registry.pickables().filter(m => !m.isLineSegments2 && !m.isLine2 && !skip.has(m.userData.component?.meta.kind));
      if (!this._hooked) { this._hooked = true; this.app.registry.onChange(() => { this._walk = null; }); }
    }
    return this._walk;
  }
  speed() { const C = this.app.display.camera; const i = this.app.store.get().quality.walkSpeed ?? 1; return (C.walkSpeeds_mps || [C.walkSpeed_mps])[i] ?? C.walkSpeed_mps; }
  setSpeed(i) {
    const q = this.app.store.get().quality; const C = this.app.display.camera;
    this.app.store.set({ quality: { ...q, walkSpeed: i } }, { record: false });
    this.app.ui.toast(`מהירות הליכה: ${C.walkSpeedLabels?.[i] || ''} (${C.walkSpeeds_mps[i]} מ'/ש')`);
  }
  startWalk() {
    const v = this.app.viewer; const C = this.app.display.camera;
    this.walking = true;
    v.controls.enabled = false;
    const dir = new THREE.Vector3(); v.camera.getWorldDirection(dir);
    this.yaw = Math.atan2(-dir.x, -dir.z); this.pitch = 0;
    // start where the screen centre points (a slab / the ground); otherwise at the street side of the lot, on the ground
    this.ray.set(v.camera.position, dir); this.ray.far = 500;
    const hit = this.ray.intersectObjects(this.walkMeshes(), false)[0];
    this.ray.far = Infinity;
    let feet = null;
    if (hit) {
      // under the point: the floor at the ground-floor level (±0.00 + step) if there is one there, else the surface hit
      const p = hit.point; const g0 = 0;   // scene y of ±0.00 (y = H − H0)
      // step back along the view (up to 6 m) until there is room ahead (not standing in / facing a wall)
      const back = new THREE.Vector3(-dir.x, 0, -dir.z).normalize();
      for (let k = 0; k <= 12 && feet === null; k++) {
        const x = p.x + back.x * 0.5 * k, z = p.z + back.z * 0.5 * k;
        let f = this.groundAt(x, z, Math.min(p.y, g0 + C.stepUp_m) + 0.05);
        if (f === null) f = this.groundAt(x, z, p.y + 0.05);
        const P = this.app.coords.fromLocal(new THREE.Vector3(x, f ?? 0, z));
        const inWall = f !== null && (this.app.tools.inspect?.wallsNear(P.E, P.N, f + 1)[0]?.dist ?? 1) < C.wallClearance_m;
        if (f === null || (k < 12 && (inWall || this.blocked(x, z, -back.x * 1.5, -back.z * 1.5, f)))) continue;
        feet = f; v.camera.position.set(x, f + C.eyeHeight_m, z);
      }
    }
    if (feet === null) {
      const c = this.app.plotCenter;
      v.camera.position.set(c.x, v.camera.position.y, c.z + 14);
      this.snapToGround();
    }
    this.vy = 0;
    this.app.ui.setWalkUI(true);
    this.app.ui.hint((matchMedia('(pointer: coarse)').matches ? 'הליכה: ג׳ויסטיק לתנועה, גרירה להסתכלות. 🚶 שוב ליציאה' : 'הליכה: חיצים / WASD לתנועה, גרירה להסתכלות, 1/2/3 מהירות, Shift האצה. Esc ליציאה')
      + ` · ${C.walkSpeedLabels?.[this.app.store.get().quality.walkSpeed ?? 1] || ''}`);
  }
  // start walking at a point of the plan (minimap), on the floor at that level: true if there is a visible floor there
  walkAt(x, z, levelRel) {
    const v = this.app.viewer; const C = this.app.display.camera;
    const y0 = levelRel + 1.0;   // search down from 1 m above the floor level (scene y = H − H0 = level relative to ±0.00)
    const f = this.groundAt(x, z, y0);
    if (f === null || f < levelRel - 1.0) return false;
    const dir = new THREE.Vector3(); v.camera.getWorldDirection(dir);
    if (!this.walking) { this.walking = true; v.controls.enabled = false; this.vy = 0; this.pitch = 0; this.app.ui.setWalkUI(true); }
    this.yaw = Math.atan2(-dir.x, -dir.z);
    v.camera.position.set(x, f + C.eyeHeight_m, z);
    v.invalidate();
    this.app.ui.hint('הליכה מהנקודה שנבחרה במפה · לחיצה על רכיב = מידות / הערה לפי הכלי · Esc ליציאה');
    return true;
  }
  stopWalk() {
    if (!this.walking) return;
    const v = this.app.viewer;
    this.walking = false;
    const dir = new THREE.Vector3(); v.camera.getWorldDirection(dir);
    v.controls.target.copy(v.camera.position).addScaledVector(dir, 10);
    v.controls.enabled = true;
    this.app.ui.setWalkUI(false);
  }
  look(dx, dy) {
    this.yaw -= dx * 0.004; this.pitch = Math.max(-1.2, Math.min(1.2, this.pitch - dy * 0.004));
    this.app.viewer.invalidate();
  }
  // height of the first upward-facing surface below fromY (a slab, landing, tread, beam top or the ground), or null
  groundAt(x, z, fromY, terrainOnly = false) {
    this.ray.set(new THREE.Vector3(x, fromY, z), new THREE.Vector3(0, -1, 0));
    const list = terrainOnly ? this.walkMeshes().filter(m => m.userData.component?.meta.kind === 'terrain') : this.walkMeshes();
    for (const h of this.ray.intersectObjects(list, false)) {
      if (!h.face) continue;
      const n = h.face.normal.clone().transformDirection(h.object.matrixWorld);
      if (n.y > 0.6) return h.point.y;                // a face looking up (top of a slab / tread / beam / ground)
    }
    return null;
  }
  snapToGround() {
    const cam = this.app.viewer.camera;
    const g = this.groundAt(cam.position.x, cam.position.z, cam.position.y + 30, true);
    if (g !== null) cam.position.y = g + this.app.display.camera.eyeHeight_m;
  }
  // a wall (vertical face) between the feet+step level and chest height within reach of the move
  blocked(x, z, dx, dz, feet) {
    const C = this.app.display.camera; const L = Math.hypot(dx, dz); if (!L) return false;
    const dir = new THREE.Vector3(dx / L, 0, dz / L);
    for (const hgt of [C.stepUp_m + 0.05, 1.2]) {
      this.ray.set(new THREE.Vector3(x, feet + hgt, z), dir); this.ray.far = L + C.wallClearance_m;
      const hit = this.ray.intersectObjects(this.walkMeshes(), false).find(h => h.face && Math.abs(h.face.normal.clone().transformDirection(h.object.matrixWorld).y) < 0.5);
      this.ray.far = Infinity;
      if (hit) return true;
    }
    return false;
  }
  step(dt) {
    if (!this.walking) return false;
    const cam = this.app.viewer.camera; const C = this.app.display.camera;
    const sp = this.speed() * (this.keys.has('ShiftLeft') || this.keys.has('ShiftRight') ? 2.5 : 1);
    for (const [k, i] of [['Digit1', 0], ['Digit2', 1], ['Digit3', 2]]) if (this.keys.has(k)) { this.keys.delete(k); this.setSpeed(i); }
    let f = 0, s = 0;
    if (this.keys.has('KeyW') || this.keys.has('ArrowUp')) f += 1;
    if (this.keys.has('KeyS') || this.keys.has('ArrowDown')) f -= 1;
    if (this.keys.has('KeyA') || this.keys.has('ArrowLeft')) s -= 1;
    if (this.keys.has('KeyD') || this.keys.has('ArrowRight')) s += 1;
    f += -this.joy.y; s += this.joy.x;
    let feet = cam.position.y - C.eyeHeight_m;
    let moved = false;
    if (f || s) {
      // forward = (-sin yaw, -cos yaw), right = (cos yaw, -sin yaw) in scene x/z
      const dx = (-Math.sin(this.yaw) * f + Math.cos(this.yaw) * s) * sp * dt;
      const dz = (-Math.cos(this.yaw) * f - Math.sin(this.yaw) * s) * sp * dt;
      const { x, z } = cam.position;
      // move, or slide along the wall (one axis), or stop
      for (const [mx, mz] of [[dx, dz], [dx, 0], [0, dz]]) {
        if (!mx && !mz) continue;
        if (!this.blocked(x, z, mx, mz, feet)) { cam.position.x = x + mx; cam.position.z = z + mz; moved = true; break; }
      }
    }
    // stand on the surface under the walker: climb up to stepUp, descend off an edge gradually
    const g = this.groundAt(cam.position.x, cam.position.z, feet + C.stepUp_m);
    if (g !== null) {
      if (g >= feet - 0.02) { feet = g; this.vy = 0; }
      else { this.vy = Math.min(C.fallSpeed_mps, (this.vy || 0) + 9.8 * dt); feet = Math.max(g, feet - this.vy * dt); moved = true; }
      cam.position.y = feet + C.eyeHeight_m;
    }
    cam.rotation.set(this.pitch, this.yaw, 0, 'YXZ');
    return true;
  }
}

function isTyping(e) { const t = e.target; return t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA'); }

// Minimap. Two modes:
//  - house (default): floor plan of one floor – slab outline, concrete walls and columns (floor-*.json, framing.json),
//    block walls with their door gaps (architecture/blocks.json). Click a spot (a room) -> walk mode starts there, on
//    that floor. The floor follows the walker (auto) or is picked in the bar above the map.
//  - site: parcels + plot, click = fly there (as before).
// Constants: data/config/display.json "minimap".
export class Minimap {
  constructor(app, canvas) {
    this.app = app; this.canvas = canvas; this.ctx = canvas.getContext('2d');
    this.D = app.display.minimap || {};
    let saved = {}; try { saved = JSON.parse(localStorage.getItem('minimapOpts') || '{}'); } catch {}
    this.mode = saved.mode === 'site' ? 'site' : 'house';
    this.floor = saved.floor || 'auto';
    this.big = !!saved.big;
    this.plans = this.buildPlans();
    // the house plan is turned so the walls are horizontal / vertical, as in the drawings (house axes from the walls, snap.js)
    this.rot = THREE.MathUtils.degToRad(houseAxes(app.data, app.display.measure?.axisHistogramBinDeg ?? 0.5).deg);
    this.houseBox = this.box();
    this.buildBar();
    this.resize();
    window.addEventListener('resize', () => this.resize());
    canvas.addEventListener('click', (e) => this.onClick(e));
    canvas.addEventListener('mousemove', (e) => { const r = canvas.getBoundingClientRect(); this.hover = [e.clientX - r.left, e.clientY - r.top]; this.last = 0; app.viewer.invalidate(); });
    canvas.addEventListener('mouseleave', () => { this.hover = null; this.last = 0; app.viewer.invalidate(); });
    this.last = 0;
  }
  save() { try { localStorage.setItem('minimapOpts', JSON.stringify({ mode: this.mode, floor: this.floor, big: this.big })); } catch {} }

  // ---- data: one plan per floor (ITM rings; nothing measured here) ----
  buildPlans() {
    const d = this.app.data; const T = Object.fromEntries(d.tags.floors.map(f => [f.id, f]));
    const fp = (arr) => (arr || []).map(w => ({ ring: w.footprintITM || w.outlineITM || w.ringITM, holes: w.holesITM || [] })).filter(w => w.ring?.length > 2);
    const blocks = (fl) => (d.blocks?.walls || []).filter(w => w.floor === fl);
    const P = (id, slabs, walls, cols) => ({ id, label: T[id]?.label || id, level: T[id]?.level ?? 0, slabs: fp(slabs), walls: fp(walls), cols: fp(cols), blocks: blocks(id) });
    return [
      P('unit', d.framing?.slabs, d.framing?.basementWalls, []),
      P('ground', d.floorGround?.slab, d.floorGround?.walls, d.floorGround?.columns),
      P('first', d.floorGround?.ceiling?.slab, d.floorFirst?.walls, d.floorFirst?.columns),
      P('roof', d.floorFirst?.ceiling?.slab, d.floorRoof?.walls, d.floorRoof?.columns),
    ].filter(p => p.slabs.length || p.walls.length);
  }
  box() {
    let x0 = Infinity, z0 = Infinity, x1 = -Infinity, z1 = -Infinity;
    const c = Math.cos(this.rot), s = Math.sin(this.rot);
    const add = (r) => r.forEach(([E, N]) => { const [x, z] = this.app.coords.xz(E, N); const u = c * x - s * z, v = s * x + c * z; x0 = Math.min(x0, u); x1 = Math.max(x1, u); z0 = Math.min(z0, v); z1 = Math.max(z1, v); });
    add(this.app.data.plot.ring);
    for (const p of this.plans) [...p.slabs, ...p.walls].forEach(w => add(w.ring));
    const m = this.D.houseMargin_m ?? 2; const um = (x0 + x1) / 2, vm = (z0 + z1) / 2;
    // centre back to scene x / z (inverse rotation)
    return { cx: c * um + s * vm, cz: -s * um + c * vm, ext: Math.max(x1 - x0, z1 - z0) + 2 * m, rot: this.rot };
  }
  // the floor shown: picked, or (auto) the one the walker / camera is on
  curFloor() {
    if (this.floor !== 'auto') return this.plans.find(p => p.id === this.floor) || this.plans[0];
    const y = this.app.viewer.camera.position.y - (this.app.nav?.walking ? this.app.display.camera.eyeHeight_m : 0);
    let best = this.plans[0];
    for (const p of this.plans) if (y >= p.level - 0.5) best = p;
    // camera high above the house (overview): the ground floor
    if (!this.app.nav?.walking && y > (this.plans.at(-1)?.level ?? 0) + 6) best = this.plans.find(p => p.id === 'ground') || best;
    return best;
  }

  // ---- UI: bar above the map ----
  buildBar() {
    const bar = document.createElement('div'); bar.id = 'mapbar'; this.bar = bar;
    const btn = (txt, title, fn, data) => { const b = document.createElement('button'); b.textContent = txt; b.title = title; b.onclick = fn; if (data) b.dataset.k = data; return b; };
    bar.append(
      btn('🏠', 'מפת הבית (תוכנית קומה) / מפת המגרשים', () => { this.mode = this.mode === 'house' ? 'site' : 'house'; this.save(); this.sync(); }, 'mode'),
      btn('אוטו', 'הקומה שבה אתה נמצא', () => this.setFloor('auto'), 'f-auto'),
      ...this.plans.map(p => btn({ unit: 'מרתף', ground: 'קרקע', first: "א'", roof: 'גג' }[p.id] || p.label, `תוכנית ${p.label}`, () => this.setFloor(p.id), 'f-' + p.id)),
      btn('⤢', 'הגדלה / הקטנה של המפה', () => { this.big = !this.big; this.save(); this.resize(); }, 'big'));
    this.canvas.parentElement.append(bar);
    this.sync();
  }
  setFloor(id) { this.floor = id; this.save(); this.sync(); }
  sync() {
    this.bar.querySelectorAll('button').forEach(b => {
      const k = b.dataset.k;
      if (k === 'mode') { b.textContent = this.mode === 'house' ? '🏠 בית' : '🗺 מגרש'; b.classList.toggle('on', this.mode === 'house'); }
      else if (k?.startsWith('f-')) { b.style.display = this.mode === 'house' ? '' : 'none'; b.classList.toggle('on', k === 'f-' + this.floor); }
      else if (k === 'big') b.classList.toggle('on', this.big);
    });
    this.canvas.title = this.mode === 'house' ? 'תוכנית הבית – לחיצה על חדר = הליכה משם' : 'מפת המגרשים – לחיצה לקפיצה';
    this.last = 0; this.app.viewer.invalidate();
  }
  resize() {
    const mobile = innerWidth <= 760;
    const small = mobile ? (this.D.size_px_mobile ?? 120) : (this.D.size_px ?? 180);
    const big = Math.min(this.D.bigSize_px ?? 340, innerWidth - 80, innerHeight - 260);
    this.size = Math.max(small, this.big ? big : small);
    const dpr = devicePixelRatio || 1;
    this.canvas.width = this.canvas.height = Math.round(this.size * dpr);
    this.canvas.style.width = this.canvas.style.height = this.size + 'px';
    this.canvas.parentElement.style.setProperty('--mm-size', this.size + 'px');
    this.last = 0; this.app.viewer.invalidate();
  }

  // ---- geometry ----
  view() {
    if (this.mode === 'house') return this.houseBox;
    const c = this.app.plotCenter; return { cx: c.x, cz: c.z, ext: this.D.extent_m ?? 90, rot: 0 };
  }
  toPx(x, z) {
    const v = this.view(), k = this.size / v.ext, c = Math.cos(v.rot), s = Math.sin(v.rot); const dx = x - v.cx, dz = z - v.cz;
    return [this.size / 2 + (c * dx - s * dz) * k, this.size / 2 + (s * dx + c * dz) * k];
  }
  toWorld(px, py) {
    const v = this.view(), k = this.size / v.ext, c = Math.cos(v.rot), s = Math.sin(v.rot); const u = (px - this.size / 2) / k, w = (py - this.size / 2) / k;
    return [v.cx + c * u + s * w, v.cz - s * u + c * w];
  }

  onClick(e) {
    const { app } = this; const r = this.canvas.getBoundingClientRect();
    const [x, z] = this.toWorld(e.clientX - r.left, e.clientY - r.top);
    if (this.mode === 'house') {
      const f = this.curFloor();
      if (!app.nav.walkAt(x, z, f.level)) app.ui.toast(`אין כאן רצפה מוצגת ב${f.label} (בשלב הבנייה הנוכחי)`);
      return;
    }
    const v = app.viewer, off = v.camera.position.clone().sub(v.controls.target);
    const t = new THREE.Vector3(x, v.controls.target.y, z);
    app.nav.stopWalk(); v.flyTo(t, t.clone().add(off));
  }

  draw() {
    if (this.app.store?.get().quality.minimap === false) return;   // hidden by the user
    const now = performance.now(); if (now - this.last < 60) return; this.last = now;
    const { ctx, app } = this; const dpr = devicePixelRatio || 1;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, this.size, this.size);
    ctx.fillStyle = 'rgba(30,34,40,0.82)'; ctx.fillRect(0, 0, this.size, this.size);
    const path = (r) => r.forEach(([E, N], i) => { const [x, z] = app.coords.xz(E, N); const [px, py] = this.toPx(x, z); i ? ctx.lineTo(px, py) : ctx.moveTo(px, py); });
    const ring = (r, stroke, fill, w = 1, holes = []) => {
      ctx.beginPath(); path(r); ctx.closePath(); for (const h of holes) { path(h); ctx.closePath(); }
      if (fill) { ctx.fillStyle = fill; ctx.fill('evenodd'); } if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = w; ctx.stroke(); }
    };
    if (this.mode === 'site') {
      for (const p of app.data.parcels.parcels) ring(p.ring, 'rgba(255,183,77,0.55)', p.use === 'public' ? 'rgba(120,130,140,0.35)' : null);
      ring(app.data.plot.ring, '#ff3d00', 'rgba(255,61,0,0.25)', 2);
    } else {
      const f = this.curFloor(); const k = this.size / this.view().ext;
      ring(app.data.plot.ring, 'rgba(255,61,0,0.8)', null, 1.5);
      for (const s of f.slabs) ring(s.ring, 'rgba(180,190,200,0.35)', 'rgba(200,205,210,0.16)', 1, s.holes);
      // block walls: a band along the axis, minus the door gaps (openings that reach the floor)
      ctx.lineCap = 'butt';
      for (const b of f.blocks) {
        const [A, B] = b.axisITM; const L = Math.hypot(B[0] - A[0], B[1] - A[1]); if (!L) continue;
        const doors = (b.openings || []).filter(o => o.z0 <= b.bottomRel + 0.15).map(o => [o.s0, o.s1]).sort((p, q) => p[0] - q[0]);
        const runs = []; let s0 = 0; for (const [a, c] of doors) { if (a > s0) runs.push([s0, a]); s0 = Math.max(s0, c); } if (s0 < L) runs.push([s0, L]);
        ctx.strokeStyle = '#d7ccc8'; ctx.lineWidth = Math.max(1.5, b.thickness_m * k);
        for (const [a, c] of runs) {
          const P = (t) => this.toPx(...app.coords.xz(A[0] + (B[0] - A[0]) * t / L, A[1] + (B[1] - A[1]) * t / L));
          const [x0, y0] = P(a), [x1, y1] = P(c); ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
        }
      }
      for (const w of f.walls) ring(w.ring, null, '#eceff1', 1, w.holes);
      for (const c of f.cols) ring(c.ring, null, '#ffffff', 1);
      ctx.fillStyle = '#ffd740'; ctx.font = 'bold 11px sans-serif'; ctx.textAlign = 'right';
      ctx.fillText(f.label + (this.floor === 'auto' ? ' · אוטו' : ''), this.size - 6, this.size - 6); ctx.textAlign = 'left';
      if (this.hover) { const [hx, hy] = this.hover; ctx.strokeStyle = '#00e5ff'; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(hx, hy, 6, 0, Math.PI * 2); ctx.stroke(); }
    }
    // camera / walker
    const cam = app.viewer.camera; const [px, py] = this.toPx(cam.position.x, cam.position.z);
    const dir = new THREE.Vector3(); cam.getWorldDirection(dir);
    const a = Math.atan2(dir.x, dir.z) - this.view().rot;
    if (px > -10 && py > -10 && px < this.size + 10 && py < this.size + 10) {
      ctx.save(); ctx.translate(px, py); ctx.rotate(-a);
      ctx.fillStyle = app.nav?.walking ? '#76ff03' : '#00e5ff'; ctx.beginPath(); ctx.moveTo(0, 9); ctx.lineTo(5, -5); ctx.lineTo(-5, -5); ctx.closePath(); ctx.fill();
      ctx.restore();
    }
    // north arrow (turned with the plan)
    const r = this.view().rot; ctx.save(); ctx.translate(14, 16); ctx.rotate(r);
    ctx.fillStyle = '#ef5350'; ctx.beginPath(); ctx.moveTo(0, -9); ctx.lineTo(4, 3); ctx.lineTo(-4, 3); ctx.closePath(); ctx.fill();
    ctx.fillStyle = '#fff'; ctx.font = 'bold 9px sans-serif'; ctx.textAlign = 'center'; ctx.fillText('צ', 0, 12); ctx.restore(); ctx.textAlign = 'left';
  }
}
