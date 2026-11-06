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
    this.ray = new THREE.Raycaster();
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
  startWalk() {
    const v = this.app.viewer;
    this.walking = true;
    v.controls.enabled = false;
    const dir = new THREE.Vector3(); v.camera.getWorldDirection(dir);
    this.yaw = Math.atan2(-dir.x, -dir.z); this.pitch = 0;
    const c = this.app.plotCenter;
    v.camera.position.set(c.x, v.camera.position.y, c.z + 14);
    this.snapToGround();
    this.app.ui.setWalkUI(true);
    this.app.ui.hint('הליכה: חיצים / WASD לתנועה, גרירה להסתכלות. Esc ליציאה');
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
  groundAt(x, z, fromY) {
    this.ray.set(new THREE.Vector3(x, fromY, z), new THREE.Vector3(0, -1, 0));
    const hits = this.ray.intersectObjects(this.app.registry.pickables().filter(m => m.userData.component?.meta.kind === 'terrain' || m.userData.component?.meta.walkable), false);
    return hits.length ? hits[0].point.y : null;
  }
  snapToGround() {
    const cam = this.app.viewer.camera;
    const g = this.groundAt(cam.position.x, cam.position.z, cam.position.y + 30);
    if (g !== null) cam.position.y = g + this.app.display.camera.eyeHeight_m;
  }
  step(dt) {
    if (!this.walking) return false;
    const cam = this.app.viewer.camera;
    const sp = this.app.display.camera.walkSpeed_mps * (this.keys.has('ShiftLeft') ? 2.5 : 1);
    let f = 0, s = 0;
    if (this.keys.has('KeyW') || this.keys.has('ArrowUp')) f += 1;
    if (this.keys.has('KeyS') || this.keys.has('ArrowDown')) f -= 1;
    if (this.keys.has('KeyA') || this.keys.has('ArrowLeft')) s -= 1;
    if (this.keys.has('KeyD') || this.keys.has('ArrowRight')) s += 1;
    f += -this.joy.y; s += this.joy.x;
    if (f || s) {
      // forward = (-sin yaw, -cos yaw), right = (cos yaw, -sin yaw) in scene x/z
      cam.position.x += (-Math.sin(this.yaw) * f + Math.cos(this.yaw) * s) * sp * dt;
      cam.position.z += (-Math.cos(this.yaw) * f - Math.sin(this.yaw) * s) * sp * dt;
      const g = this.groundAt(cam.position.x, cam.position.z, cam.position.y + 1.2); // step-up tolerance (stairs)
      if (g !== null) cam.position.y = g + this.app.display.camera.eyeHeight_m;
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
