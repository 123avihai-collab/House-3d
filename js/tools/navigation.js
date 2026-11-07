import * as THREE from 'three';

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

// Minimap: top-down drawing of parcels, plot and the camera, click to jump.
export class Minimap {
  constructor(app, canvas) {
    this.app = app; this.canvas = canvas; this.ctx = canvas.getContext('2d');
    const d = app.display.minimap;
    this.size = d.size_px; this.extent = d.extent_m;
    canvas.width = canvas.height = this.size * devicePixelRatio;
    canvas.style.width = canvas.style.height = this.size + 'px';
    canvas.addEventListener('click', (e) => {
      const r = canvas.getBoundingClientRect();
      const [x, z] = this.toWorld(e.clientX - r.left, e.clientY - r.top);
      const v = app.viewer, off = v.camera.position.clone().sub(v.controls.target);
      const t = new THREE.Vector3(x, v.controls.target.y, z);
      app.nav.stopWalk(); v.flyTo(t, t.clone().add(off));
    });
    this.last = 0;
  }
  toPx(x, z) { const c = this.app.plotCenter, k = this.size / this.extent; return [this.size / 2 + (x - c.x) * k, this.size / 2 + (z - c.z) * k]; }
  toWorld(px, py) { const c = this.app.plotCenter, k = this.size / this.extent; return [c.x + (px - this.size / 2) / k, c.z + (py - this.size / 2) / k]; }
  draw() {
    if (this.app.store?.get().quality.minimap === false) return;   // hidden by the user
    const now = performance.now(); if (now - this.last < 60) return; this.last = now;
    const { ctx, app } = this; const dpr = devicePixelRatio;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, this.size, this.size);
    ctx.fillStyle = 'rgba(30,34,40,0.78)'; ctx.fillRect(0, 0, this.size, this.size);
    const ring = (r, stroke, fill, w = 1) => {
      ctx.beginPath();
      r.forEach(([E, N], i) => { const [x, z] = app.coords.xz(E, N); const [px, py] = this.toPx(x, z); i ? ctx.lineTo(px, py) : ctx.moveTo(px, py); });
      ctx.closePath(); if (fill) { ctx.fillStyle = fill; ctx.fill(); } ctx.strokeStyle = stroke; ctx.lineWidth = w; ctx.stroke();
    };
    for (const p of app.data.parcels.parcels) ring(p.ring, 'rgba(255,183,77,0.55)', p.use === 'public' ? 'rgba(120,130,140,0.35)' : null);
    ring(app.data.plot.ring, '#ff3d00', 'rgba(255,61,0,0.25)', 2);
    // camera
    const cam = app.viewer.camera; const [px, py] = this.toPx(cam.position.x, cam.position.z);
    const dir = new THREE.Vector3(); cam.getWorldDirection(dir);
    const a = Math.atan2(dir.x, dir.z);
    ctx.save(); ctx.translate(px, py); ctx.rotate(-a);
    ctx.fillStyle = '#00e5ff'; ctx.beginPath(); ctx.moveTo(0, 9); ctx.lineTo(5, -5); ctx.lineTo(-5, -5); ctx.closePath(); ctx.fill();
    ctx.restore();
    ctx.fillStyle = '#fff'; ctx.font = '10px sans-serif'; ctx.fillText('צ ↑', 6, 12);
  }
}
