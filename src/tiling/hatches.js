import * as THREE from 'three';

// Tiled access hatches over the pool machine room (Avihai 13.11.2026): a recessed tile-insert cover – stainless frame in the
// slab opening, a tray holding the same tiles as the paving around (the tiles are laid by the tiling workshop in the shared
// joint grid – zones ext:H1 / ext:H2 – and attached here to the lid), hinged on one side, opening to 95° on two struts.
// Click a hatch to open / close it. Also the machine-room roof slab with the two openings (structure, provisional).
// Data: data/finishes/exterior/hatches.json (tools/finishes/derive_hatches.py); look: data/config/display.json → hatches.
// No dimension is written here.

export class Hatches {
  constructor(F) {
    this.F = F; this.H = F.ctx.data.hatches; this.D = F.ctx.data.display.hatches || {};
    this.P = this.H.product; this.lids = {}; this.items = [];
    this.open = {};   // id -> 0 (closed) … 1 (open)
    const host = (h) => (F.EX?.rooms || []).find(r => r.room === 'ext:' + h.id);
    for (const h of this.H.hatches) {
      const r = host(h); if (!r) continue;
      this.lids[h.id] = { h, r, objs: new Set(), t: 0 };
    }
  }
  V(E, N, z) { return new THREE.Vector3(...this.F.V(E, N, z)); }
  zTop(id, E, N) { return this.lids[id].r.zAt(E, N); }

  build() {
    const F = this.F, P = this.P, mat = new THREE.MeshStandardMaterial({ color: this.D.steelColor || '#c9cdd1', metalness: this.D.steelMetalness ?? 0.85, roughness: this.D.steelRoughness ?? 0.32 });
    const fill = new THREE.MeshStandardMaterial({ color: this.D.mortarColor || '#9e9a92', roughness: 0.9 });
    const mk = (pts, m) => { const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pts.flat(), 3)); g.computeVertexNormals(); const o = new THREE.Mesh(g, m); o.castShadow = o.receiveShadow = true; o.userData.keep = true; return o; };
    const box = (ring, holes, zf0, zf1) => {   // a prism over a ring (+ holes): top / bottom / sides – z from (E, N)
      const out = [...F.ringTris(ring, holes, zf1), ...F.ringTris(ring, holes, zf0)];
      for (const rr of [ring, ...(holes || [])]) for (let i = 0; i < rr.length; i++) { const a = rr[i], b = rr[(i + 1) % rr.length];
        out.push(...F.quadTris([[a[0], a[1], zf0(...a)], [b[0], b[1], zf0(...b)], [b[0], b[1], zf1(...b)], [a[0], a[1], zf1(...a)]])); }
      return out;
    };
    const inset = (ring, d) => {   // a convex quad moved inward by d (the lid / tray inside the frame)
      const c = ring.reduce((a, p) => [a[0] + p[0] / ring.length, a[1] + p[1] / ring.length], [0, 0]);
      return ring.map((p, i) => { const pr = ring[(i + ring.length - 1) % ring.length], nx = ring[(i + 1) % ring.length];
        const e1 = [p[0] - pr[0], p[1] - pr[1]], e2 = [nx[0] - p[0], nx[1] - p[1]], l1 = Math.hypot(...e1), l2 = Math.hypot(...e2);
        const n1 = [e1[1] / l1, -e1[0] / l1], n2 = [e2[1] / l2, -e2[0] / l2];
        const s = Math.sign((c[0] - p[0]) * (n1[0] + n2[0]) + (c[1] - p[1]) * (n1[1] + n2[1])) || 1;
        const bis = [n1[0] + n2[0], n1[1] + n2[1]], bl = Math.hypot(...bis), k = d / Math.max(0.2, (bis[0] / bl) * n1[0] + (bis[1] / bl) * n1[1]);
        return [p[0] + s * bis[0] / bl * k, p[1] + s * bis[1] / bl * k]; });
    };
    // the machine-room roof slab with the openings
    const R = this.H.roof, rel = (z) => z - F.ctx.coords.H0;
    const roof = mk(box(R.ringITM, this.H.hatches.map(h => h.openingITM), () => rel(R.bottom), () => rel(R.top)), F.ctx.materials?.get?.('concrete') || fill);
    const rg = new THREE.Group(); rg.add(roof);
    this.items.push(F.ctx.registry.add(rg, { floor: 'ground', system: 'structure', stage: 'walls', layer: 'pool' }, { name: 'תקרת חדר המכונות – עם 2 פתחים למכסים (זמני)', status: 'provisional',
      rows: [['תחתית / ראש', `${R.bottom.toFixed(2)} / ${R.top.toFixed(2)} (${Math.round(R.thickness_m * 100)} ס"מ)`], ['פתחים', this.H.hatches.map(h => `${h.label} ${Math.round(h.clear_m[0] * 100)}×${Math.round(h.clear_m[1] * 100)}`).join(' · ')]],
      source: R.source, note: 'עובי התקרה לפי "גובה פנים 180" בחתך א – זמני (open-issues #214)' }));
    F.ctx.scene.add(rg);
    for (const [id, L] of Object.entries(this.lids)) {
      const h = L.h, ring = h.openingITM, lid = inset(ring, P.frameTop_m);
      const top = (E, N) => this.zTop(id, E, N), depth = (E, N) => top(E, N) - P.frameDepth_m;
      // frame (fixed): the stainless ring in the opening, frameTop wide, frameDepth deep
      const fg = new THREE.Group(); fg.add(mk(box(ring, [lid], depth, top), mat));
      // lid (hinged): tray sides + bottom plate (steel) + the mortar bed under the tiles; the tiles – the workshop's zone ext:<id>
      const tile = L.r.layers.find(l => l.id === 'extTile');
      const bed = (E, N) => top(E, N) + tile.dz0 - this.F.EX.buildUp.layers.find(l => l.id === 'extAdhesive').thickness_m;
      const tray = inset(lid, P.trayPlate_m);
      const lg = new THREE.Group();
      lg.add(mk(box(lid, [tray], depth, (E, N) => top(E, N) - 0.0005), mat));                            // tray walls
      lg.add(mk(box(tray, [], depth, (E, N) => depth(E, N) + P.trayPlate_m), mat));                     // bottom plate
      lg.add(mk(box(tray, [], (E, N) => depth(E, N) + P.trayPlate_m, bed), fill));                      // mortar / adhesive bed
      L.placeholder = mk(F.ringTris(tray, [], (E, N) => top(E, N) - 0.001), new THREE.MeshStandardMaterial({ color: this.D.placeholderColor || '#b7b3ab', roughness: 0.85 }));
      lg.add(L.placeholder);
      // hinge: the edge of the opening on the pool side (ring[0] → ring[1] – derive_hatches.py), at the top of the frame
      const [a, b] = h.hinge === 'pool' ? [lid[0], lid[1]] : [lid[2], lid[3]];
      L.o = this.V(a[0], a[1], top(...a)); L.axis = this.V(b[0], b[1], top(...b)).sub(L.o).normalize();
      const far = h.hinge === 'pool' ? lid[3] : lid[1], fp = this.V(far[0], far[1], top(...far)).sub(L.o);
      L.sign = fp.clone().applyAxisAngle(L.axis, 0.3).y > fp.y ? 1 : -1;   // the far edge goes up
      // struts: one on each side, between the frame side and the tray underside (attach points along the sides)
      const sides = h.hinge === 'pool' ? [[lid[0], lid[3], lid[1]], [lid[1], lid[2], lid[0]]] : [[lid[3], lid[0], lid[2]], [lid[2], lid[1], lid[3]]];
      L.struts = sides.map(([h0, h1, other]) => {
        const along = [h1[0] - h0[0], h1[1] - h0[1]], al = Math.hypot(...along), inw = [(other[0] - h0[0]) / Math.hypot(other[0] - h0[0], other[1] - h0[1]), (other[1] - h0[1]) / Math.hypot(other[0] - h0[0], other[1] - h0[1])];
        const at = (d, z) => { const E = h0[0] + along[0] / al * d + inw[0] * P.strutInset_m, N = h0[1] + along[1] / al * d + inw[1] * P.strutInset_m; return this.V(E, N, z(E, N)); };
        const base = at(P.strutBaseFromHinge_m, (E, N) => top(E, N) - P.strutBaseDepth_m), tip = at(P.strutLidFromHinge_m, depth);
        const barrel = new THREE.Mesh(new THREE.CylinderGeometry(P.strutBarrelR_m, P.strutBarrelR_m, 1, 12), mat), rod = new THREE.Mesh(new THREE.CylinderGeometry(P.strutRodR_m, P.strutRodR_m, 1, 10), mat);
        barrel.userData.keep = rod.userData.keep = true; fg.add(barrel, rod);
        return { base, tip, barrel, rod, len0: base.distanceTo(tip) };
      });
      L.lid = lg; L.objs.add(lg);
      const grp = new THREE.Group(); grp.add(fg, lg);
      const it = F.ctx.registry.add(grp, { floor: 'ground', system: 'finishes', stage: 'finishes', step: 'tiling', layer: 'poolHatches' }, {
        name: `${h.label} – מכסה מרוצף נפתח (זמני)`, kind: 'hatch', id: 'hatch-' + id, pickable: true, status: 'provisional',
        rows: [['מוצר', P.label], ['פתח נקי', `${Math.round(h.clear_m[0] * 100)} × ${Math.round(h.clear_m[1] * 100)} ס"מ (נמדד בתוכנית האדריכל, 1:100)`],
          ['מסגרת / מגש', `${P.frameMaterial} · עומק ${Math.round(P.frameDepth_m * 1000)} מ"מ · פס נראה ${Math.round(P.frameTop_m * 1000)} מ"מ`],
          ['פתיחה', `ציר בצד ${h.hinge === 'pool' ? 'הבריכה' : 'הנגדי'} · ${P.openAngle_deg}° · ${P.struts} בוכנות`], ['ריצוף', 'באותה רשת פוגות של הריצוף מסביב (סדנת ריצוף, אזור ' + L.r.roomName + ')'],
          ['עומס', P.load], ['לחיצה', 'פתיחה / סגירה']],
        source: h.source, note: 'סוג מוצר, מידות מסגרת ובוכנות – זמניים (open-issues #214)', onClick: () => this.toggle(id) });
      F.ctx.scene.add(grp); this.items.push(it);
      this.pose(id);
    }
  }
  // the tiles of a lid (built by the workshop – src/tiling/workshop.js): rotate with it
  attach(id, obj) { const L = this.lids[id]; if (!L) return; L.objs.add(obj); this.pose(id); if (L.placeholder) L.placeholder.visible = false; }
  detachAll() { for (const L of Object.values(this.lids)) { for (const o of [...L.objs]) if (o !== L.lid) L.objs.delete(o); if (L.placeholder) L.placeholder.visible = true; } }
  pose(id) {
    const L = this.lids[id]; if (!L?.o) return;
    const ang = L.sign * L.t * this.P.openAngle_deg * Math.PI / 180, q = new THREE.Quaternion().setFromAxisAngle(L.axis, ang);
    for (const o of L.objs) { o.quaternion.copy(q); o.position.copy(L.o).sub(L.o.clone().applyQuaternion(q)); o.updateMatrixWorld(true); }
    for (const s of L.struts) {   // barrel fixed at the base, rod to the moving tip
      const tip = s.tip.clone().sub(L.o).applyQuaternion(q).add(L.o), d = tip.clone().sub(s.base), len = d.length(), dir = d.clone().normalize();
      const bl = Math.min(len, s.len0 * (this.D.barrelFrac ?? 0.6)), up = new THREE.Vector3(0, 1, 0);
      s.barrel.scale.set(1, bl, 1); s.barrel.quaternion.setFromUnitVectors(up, dir); s.barrel.position.copy(s.base).addScaledVector(dir, bl / 2);
      s.rod.scale.set(1, len - bl * 0.9, 1); s.rod.quaternion.setFromUnitVectors(up, dir); s.rod.position.copy(s.base).addScaledVector(dir, bl * 0.9 + (len - bl * 0.9) / 2);
    }
  }
  toggle(id) {
    const L = this.lids[id]; if (!L) return;
    const to = L.t > 0.5 ? 0 : 1, from = L.t, t0 = performance.now(), ms = this.D.openMs ?? 1400;
    const step = (now) => { const k = Math.min(1, (now - t0) / ms), e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
      L.t = from + (to - from) * e; this.pose(id); this.F.app?.viewer.invalidate(); if (k < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  }
}
