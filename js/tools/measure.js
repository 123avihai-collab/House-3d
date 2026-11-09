import * as THREE from 'three';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { Line2 } from 'three/addons/lines/Line2.js';
import { LineGeometry } from 'three/addons/lines/LineGeometry.js';
import { LineMaterial } from 'three/addons/lines/LineMaterial.js';
import { Snapper, SNAP_KIND, houseAxes, axesFromDeg } from './snap.js';

// Measuring (one way, like AutoCAD): two points with object snap (corner > midpoint > edge > surface).
// Result: the direct (diagonal) line = the main dimension, plus its split along the house axes:
//   X / Y = the two wall directions of the house (derived from the walls, see snap.js houseAxes), Z = height,
// drawn as dashed legs A -> X -> Y -> Z -> B. Ortho (F8) locks the second point to the nearest axis from the first.
// Axes can be switched to the ITM grid (E / N). Settings are kept in the browser.
// Constants: data/config/display.json "measure".
export class MeasureTool {
  constructor(app) {
    this.app = app;
    this.C = app.display.measure || {};
    this.col = { direct: '#00e5ff', x: '#ff5252', y: '#69f0ae', z: '#448aff', preview: '#ffd740', ...(this.C.colors || {}) };
    this.group = new THREE.Group(); this.group.renderOrder = 10;
    app.viewer.scene.add(this.group);
    this.snapper = new Snapper(app);
    this.snapper.pickables = () => app.registry.pickables();
    this.house = houseAxes(app.data, this.C.axisHistogramBinDeg ?? 0.5);
    this.first = null; this.items = []; this.cur = null;
    let saved = {}; try { saved = JSON.parse(localStorage.getItem('measureOpts') || '{}'); } catch {}
    this.opts = { snap: saved.snap !== false, ortho: !!saved.ortho, axes: saved.axes === 'itm' ? 'itm' : 'house' };
    const r = this.C.dotRadius_m ?? 0.06;
    this.dotGeo = new THREE.SphereGeometry(r, 12, 8);
    this.mats = {};
    this.lineMats = app.lineMats || [];   // shared with main.js: viewer.onResize updates their resolution
    // snap marker + live preview (one of each, reused)
    const mk = document.createElement('div'); mk.className = 'snapmark hidden';
    this.marker = new CSS2DObject(mk); this.markerEl = mk; this.group.add(this.marker);
    this.preview = null;
  }

  axes() { return this.opts.axes === 'itm' ? axesFromDeg(0) : this.house; }
  setOpt(k, v) {
    this.opts[k] = v;
    try { localStorage.setItem('measureOpts', JSON.stringify(this.opts)); } catch {}
    this.app.ui.syncMeasureBar?.(); this.app.ui.refreshPanel('tools');
  }
  axisNames() { return this.opts.axes === 'itm' ? { x: 'E', y: 'N', z: 'Z' } : { x: 'X', y: 'Y', z: 'Z' }; }

  activate() { this.first = null; this.app.ui.hint('מדידה: לחץ על נקודה ראשונה – נצמד לפינה ■, לאמצע ▲ או לקצה ◆'); this.app.ui.syncMeasureBar?.(); }
  deactivate() { this.clearPending(); this.hideMarker(); this.app.ui.syncMeasureBar?.(); }
  clearPending() {
    if (this.first?.dot) this.group.remove(this.first.dot);
    this.first = null; this.clearPreview(); this.app.viewer.invalidate();
  }
  undoPoint() {
    if (this.first) { this.clearPending(); this.app.ui.hint('מדידה: הנקודה בוטלה – לחץ על נקודה ראשונה'); return true; }
    return false;
  }

  // ---- drawing helpers ----
  mat(color) { return this.mats[color] ||= new THREE.MeshBasicMaterial({ color, depthTest: false, transparent: true }); }
  line(points, color, { dashed = false, width = 2.5 } = {}) {
    const g = new LineGeometry(); g.setPositions(points.flatMap(p => [p.x, p.y, p.z]));
    const m = new LineMaterial({ color, linewidth: width, dashed, dashSize: 0.15, gapSize: 0.1, depthTest: false, transparent: true });
    m.resolution.copy(this.app.viewer.resolution); this.lineMats.push(m);
    const l = new Line2(g, m); l.computeLineDistances(); l.renderOrder = 11; return l;
  }
  label(html, cls, at) { const d = document.createElement('div'); d.className = 'lbl measure ' + (cls || ''); d.innerHTML = html; const o = new CSS2DObject(d); o.position.copy(at); return o; }
  dot(p, color = this.col.direct) { const m = new THREE.Mesh(this.dotGeo, this.mat(color)); m.position.copy(p); m.renderOrder = 12; return m; }
  disposeObj(o) { o.geometry?.dispose?.(); if (o.material && this.lineMats.includes(o.material)) { o.material.dispose(); this.lineMats.splice(this.lineMats.indexOf(o.material), 1); } o.element?.remove?.(); }

  // components of b - a along the current axes
  split(a, b) {
    const A = this.axes(); const d = b.clone().sub(a);
    const dx = d.dot(A.u1), dy = d.dot(A.u2), dz = d.y;
    return { dx, dy, dz, d3: d.length(), dh: Math.hypot(dx, dy), A };
  }
  // ortho: keep only the largest component (from the first point)
  ortho(a, p) {
    const { dx, dy, dz, A } = this.split(a, p);
    const ax = [[Math.abs(dx), A.u1, dx], [Math.abs(dy), A.u2, dy], [Math.abs(dz), A.up, dz]].sort((x, y) => y[0] - x[0])[0];
    return a.clone().addScaledVector(ax[1], ax[2]);
  }
  fmt(v) { return v.toFixed(3); }
  sgn(v) { return (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(3); }
  iso(t) { return '\u2066' + t.replace(/ /g, '\u00a0') + '\u2069'; }   // keep "X 1.234" left-to-right inside the Hebrew hint

  // ---- pointer ----
  pickPoint(hit, e) {
    if (!hit) return null;
    const r = this.app.viewer.renderer.domElement.getBoundingClientRect();
    const px = { x: e.clientX - r.left, y: e.clientY - r.top };
    const s = this.snapper.snap(hit, px, { touch: e.pointerType === 'touch' || e.pointerType === 'pen', enabled: this.opts.snap, hits: this.app.lastHits });
    if (s && this.first && this.opts.ortho) { s.point = this.ortho(this.first.p, s.point); s.kind = s.kind + '+ortho'; }
    return s;
  }
  showMarker(s) {
    if (!s) { this.hideMarker(); return; }
    const kind = s.kind.split('+')[0];
    this.marker.position.copy(s.point);
    this.markerEl.className = 'snapmark k-' + kind;
    this.markerEl.textContent = { vertex: '■', mid: '▲', edge: '◆', face: '●' }[kind] + ' ' + SNAP_KIND[kind] + (s.kind.includes('ortho') ? ' · אורתו' : '');
    this.marker.visible = true; this.app.viewer.invalidate();
  }
  hideMarker() { this.marker.visible = false; this.markerEl.className = 'snapmark hidden'; this.app.viewer.invalidate(); }
  clearPreview() { if (this.preview) { this.preview.forEach(o => { this.group.remove(o); this.disposeObj(o); }); this.preview = null; } }

  handleHover(hit, e) {
    const s = this.pickPoint(hit, e); this.cur = s;
    this.showMarker(s);
    this.clearPreview();
    if (this.first && s) {
      const a = this.first.p, b = s.point; const sp = this.split(a, b); const n = this.axisNames();
      this.preview = [this.line([a, b], this.col.preview, { width: 2 }), this.label(`${this.fmt(sp.d3)} מ'`, 'live', a.clone().lerp(b, 0.5))];
      this.preview.forEach(o => this.group.add(o));
      const I = (t) => this.iso(t);
      this.app.ui.hint(`ישיר ${I(this.fmt(sp.d3))} · ${I(`${n.x} ${this.sgn(sp.dx)}`)} · ${I(`${n.y} ${this.sgn(sp.dy)}`)} · ${I(`${n.z} ${this.sgn(sp.dz)}`)} – ${SNAP_KIND[s.kind.split('+')[0]]}`);
    }
    this.app.viewer.invalidate();
  }

  handleClick(hit, e) {
    const s = e ? this.pickPoint(hit, e) : (hit ? { point: hit.point.clone(), kind: 'face' } : null);
    if (!s) return;
    const p = s.point.clone();
    if (!this.first) {
      const dot = this.dot(p); this.group.add(dot);
      this.first = { p, dot, kind: s.kind };
      this.app.ui.hint(`נקודה ראשונה: ${SNAP_KIND[s.kind.split('+')[0]]}. לחץ על נקודה שנייה (F8 = אורתו, Esc = ביטול)`);
      this.app.viewer.invalidate(); return;
    }
    this.clearPreview();
    const a = this.first.p, b = p;
    const it = this.build(a, b, this.first.kind, s.kind, [this.first.dot]);
    this.items.push(it);
    this.first = null;
    const n = this.axisNames();
    const I = (t) => this.iso(t);
    this.app.ui.hint(`ישיר ${I(this.fmt(it.d3))} מ' · ${I(`${n.x} ${this.fmt(Math.abs(it.dx))}`)} · ${I(`${n.y} ${this.fmt(Math.abs(it.dy))}`)} · ${I(`${n.z} ${this.sgn(it.dz)}`)}. לחץ להמשך מדידה.`);
    this.app.ui.refreshPanel('tools');
    this.app.viewer.invalidate();
  }

  // the drawing of one measurement: direct line + dashed split along the axes, with labels
  build(a, b, ka, kb, extra = []) {
    const sp = this.split(a, b); const n = this.axisNames(); const Z = this.C.zeroComponent_m ?? 0.005;
    const objs = [...extra, this.dot(b), this.line([a, b], this.col.direct, { width: 3 })];
    objs.push(this.label(`<b>${this.fmt(sp.d3)} מ'</b>` + (Math.abs(sp.dz) > Z && sp.dh > Z ? `<br><small>אופקי ${this.fmt(sp.dh)}</small>` : ''), 'main', a.clone().lerp(b, 0.5)));
    // legs A -> X -> Y -> Z -> B (corners of the split)
    const p1 = a.clone().addScaledVector(sp.A.u1, sp.dx), p2 = p1.clone().addScaledVector(sp.A.u2, sp.dy);
    // legs drawn only when they matter (> zero and > 2% of the line) – the exact values are always in the table
    const legs = [[a, p1, sp.dx, 'x'], [p1, p2, sp.dy, 'y'], [p2, b, sp.dz, 'z']].filter(l => Math.abs(l[2]) > Z && Math.abs(l[2]) > (this.C.minLegShare ?? 0.02) * sp.d3);
    // a single leg = the direct line itself (no split needed)
    if (legs.length > 1) for (const [p, q, v, k] of legs) {
      objs.push(this.line([p, q], this.col[k], { dashed: true, width: 2 }));
      objs.push(this.label(`${n[k]} ${this.fmt(Math.abs(v))}`, 'ax ax-' + k, p.clone().lerp(q, 0.5)));
    }
    objs.forEach(o => { if (!o.parent) this.group.add(o); });
    return { ...sp, a: a.clone(), b: b.clone(), A: this.app.coords.fromLocal(a), B: this.app.coords.fromLocal(b), ka, kb, axes: this.opts.axes, axesDeg: sp.A.deg, objs };
  }

  remove(i) {
    const it = this.items[i]; if (!it) return;
    it.objs.forEach(o => { this.group.remove(o); this.disposeObj(o); });
    this.items.splice(i, 1);
    this.app.viewer.invalidate(); this.app.ui.refreshPanel('tools');
  }
  // re-draw all measurements in the current axes (after switching house / ITM)
  redraw() {
    this.items = this.items.map(it => { it.objs.forEach(o => { this.group.remove(o); this.disposeObj(o); }); return this.build(it.a, it.b, it.ka, it.kb, [this.dot(it.a)]); });
    this.app.viewer.invalidate(); this.app.ui.refreshPanel('tools');
  }
  focus(i) {
    const it = this.items[i]; if (!it) return;
    const c = it.a.clone().lerp(it.b, 0.5); const r = Math.max(3, it.d3 * 1.2);
    this.app.viewer.flyTo(c, c.clone().add(new THREE.Vector3(r * 0.6, r * 0.7, r * 0.6)));
  }
  clearAll() {
    this.clearPending();
    for (const it of this.items) it.objs.forEach(o => { this.group.remove(o); this.disposeObj(o); });
    this.items = [];
    this.app.viewer.invalidate();
    this.app.ui.refreshPanel('tools');
  }
  axesText() {
    return this.opts.axes === 'itm' ? 'צירי רשת ITM: E = מזרח, N = צפון'
      : `צירי הבית: X = כיוון הקירות ${this.house.deg >= 0 ? '' : '−'}${Math.abs(this.house.deg).toFixed(2)}° ממזרח הרשת, Y = ניצב לו, Z = גובה (נגזר מקירות קומת הקרקע)`;
  }
  toText() {
    const n = this.axisNames(); const C = this.app.coords;
    return [this.axesText(), ...this.items.map((it, i) =>
      `#${i + 1}: ישיר ${this.fmt(it.d3)} מ' · אופקי ${this.fmt(it.dh)} · ${n.x} ${this.sgn(it.dx)} · ${n.y} ${this.sgn(it.dy)} · ${n.z} ${this.sgn(it.dz)}\n` +
      `    מ-${C.fmtEN(it.A.E, it.A.N)} H ${C.fmtH(it.A.H)} (${SNAP_KIND[it.ka.split('+')[0]]}) עד ${C.fmtEN(it.B.E, it.B.N)} H ${C.fmtH(it.B.H)} (${SNAP_KIND[it.kb.split('+')[0]]})`)].join('\n');
  }
}
