// Live checks of the proposal routes (stage 3): clash with columns / beams / concrete (by plan footprint AND level),
// wall crossing not square to the wall, drainage slope (against the run's design slope / a set minimum, reverse fall),
// open ends and consumption points without a water connection. Obstacles come from the structure JSON only
// (data/structure/*, data/architecture/blocks.json) – never from the architect background.

const inPoly = (x, y, P) => { let c = false; for (let i = 0, j = P.length - 1; i < P.length; j = i++) { const [xi, yi] = P[i], [xj, yj] = P[j]; if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) c = !c; } return c; };
const segDist = (x, y, a, b) => { const dx = b[0] - a[0], dy = b[1] - a[1], L2 = dx * dx + dy * dy; const t = L2 ? Math.max(0, Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / L2)) : 0; return Math.hypot(a[0] + t * dx - x, a[1] + t * dy - y); };
const edgeDist = (x, y, P) => { let d = Infinity; for (let i = 0; i < P.length; i++) d = Math.min(d, segDist(x, y, P[i], P[(i + 1) % P.length])); return d; };
const bbox = (P) => P.reduce((b, [x, y]) => [Math.min(b[0], x), Math.min(b[1], y), Math.max(b[2], x), Math.max(b[3], y)], [Infinity, Infinity, -Infinity, -Infinity]);
function segX(a, b, c, d) {   // intersection parameter t on a→b with c→d, or null
  const r = [b[0] - a[0], b[1] - a[1]], s = [d[0] - c[0], d[1] - c[1]], den = r[0] * s[1] - r[1] * s[0]; if (Math.abs(den) < 1e-12) return null;
  const t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den, u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den;
  return t >= 0 && t <= 1 && u >= 0 && u <= 1 ? { t, edge: [c, d] } : null;
}

export function buildObstacles(D, fr) {
  const L = (P) => P.map(([E, N]) => fr.toLocal(E, N)), out = [];
  const beamPoly = (b, w) => { const [[e1, n1], [e2, n2]] = b.axisITM, l = Math.hypot(e2 - e1, n2 - n1); if (!l) return null; const ux = (e2 - e1) / l, uy = (n2 - n1) / l, h = w / 2; return [[e1 - uy * h, n1 + ux * h], [e2 - uy * h, n2 + ux * h], [e2 + uy * h, n2 - ux * h], [e1 + uy * h, n1 - ux * h]]; };
  const add = (cat, label, r, polyITM, src) => { if (!polyITM || polyITM.length < 3 || r.bottomRel == null || r.topRel == null) return; const poly = L(polyITM); out.push({ cat, label, id: r.id, poly, holes: (r.holesITM || []).map(L), bb: bbox(poly), lo: r.bottomRel, hi: r.topRel, status: r.status, source: src }); };
  for (const [F, name] of [[D.floorGround, 'floor-ground'], [D.floorFirst, 'floor-first'], [D.floorRoof, 'floor-roof']]) {
    for (const c of F.columns) add('column', 'עמוד', c, c.footprintITM, `data/structure/${name}.json`);
    for (const w of F.walls) add('wall', 'קיר בטון', w, w.footprintITM, `data/structure/${name}.json`);
    for (const b of F.ceiling.beams || []) if (b.axisITM) add('beam', 'קורה', b, beamPoly(b, b.width_m), `data/structure/${name}.json ceiling.beams`);
  }
  for (const w of D.framing.basementWalls) add('wall', 'קיר מרתף', w, w.footprintITM, 'data/structure/framing.json basementWalls');
  for (const b of D.framing.groundBeams) if (b.axisITM) add('beam', 'קורת יסוד', b, beamPoly(b, b.width_m), 'data/structure/framing.json groundBeams');
  for (const w of D.blocks.walls) if (w.axisITM) add('block', 'קיר בלוקים', w, beamPoly(w, w.thickness_m), 'data/architecture/blocks.json');
  // English courtyards: no pipe in plan at any level (Avihai 09.11 – not exposed, not under the concrete either)
  for (const z of D.floorGround.openZones || []) if (z.zone === 'courtyard') { const poly = L(z.footprintITM); out.push({ cat: 'courtyard', label: z.label || 'חצר אנגלית', id: 'חצר', poly, holes: [], bb: bbox(poly), lo: -Infinity, hi: Infinity, source: 'data/structure/floor-ground.json openZones (courtyard)' }); }
  return out;
}

// radius of the pipe from the catalog (outside diameter), else the nominal diameter
export const radiusOf = (r, cat) => { const od = cat[r.material]?.sizes?.[String(r.D_mm)]?.OD; return od ? od / 2 : r.D_mm ? r.D_mm / 2000 : 0; };

export function checkRun(run, ctx) {
  const { fr, H0, obstacles, cfg, cat } = ctx, C = cfg.checks, out = [];
  const R = radiusOf(run, cat), V = run.vertices.map(v => ({ xy: fr.toLocal(v[0], v[1]), h: v[2] }));
  const texts = new Set();
  const push = (sev, type, text, at, el) => !texts.has(type + text) && texts.add(type + text) && out.push({ sev, type, text, at, run: run.id, el: el ? `${el.label} ${el.id}` : null, elSource: el?.source });
  const seen = new Set();
  // 1. structure: sample every segment, compare plan (inside or within R of the footprint) and level (rel to ±0.00)
  for (let i = 0; i + 1 < V.length; i++) {
    const a = V[i], b = V[i + 1]; if (a.h == null || b.h == null) continue;
    const plan = Math.hypot(b.xy[0] - a.xy[0], b.xy[1] - a.xy[1]), vertical = plan < cfg.edit.stationTol_m;
    const n = Math.max(1, Math.ceil((vertical ? Math.abs(b.h - a.h) : plan) / C.sampleStep_m));
    const sb = [Math.min(a.xy[0], b.xy[0]) - R, Math.min(a.xy[1], b.xy[1]) - R, Math.max(a.xy[0], b.xy[0]) + R, Math.max(a.xy[1], b.xy[1]) + R];
    for (const o of obstacles) {
      if (o.bb[0] > sb[2] || o.bb[2] < sb[0] || o.bb[1] > sb[3] || o.bb[3] < sb[1]) continue;
      if (o.cat === 'courtyard') continue;                      // checked separately below
      if (o.cat === 'block' && !vertical) continue;            // horizontal through block walls: angle check below
      if (o.cat === 'block') continue;                          // risers chased in block walls – not a clash
      let hit = null;
      for (let k = 0; k <= n; k++) {
        const t = k / n, x = a.xy[0] + (b.xy[0] - a.xy[0]) * t, y = a.xy[1] + (b.xy[1] - a.xy[1]) * t, z = a.h + (b.h - a.h) * t - H0;
        if (z + R <= o.lo + C.levelTol_m || z - R >= o.hi - C.levelTol_m) continue;
        const inside = inPoly(x, y, o.poly) && !o.holes.some(h => inPoly(x, y, h));
        if (inside || (R > 0 && edgeDist(x, y, o.poly) < R - C.levelTol_m)) { hit = { x, y, z, inside }; break; }
      }
      if (!hit) continue;
      if (o.cat === 'wall' && !vertical) continue;               // horizontal through a concrete wall = a sleeve: angle check below
      const key = o.cat + o.id + o.lo + o.hi + (vertical ? 'v' : 'h'); if (seen.has(key)) continue; seen.add(key);   // a beam split in pieces: one finding
      push('error', o.cat === 'beam' ? 'clashBeam' : o.cat === 'column' ? 'clashColumn' : 'inConcrete',
        o.cat === 'beam' ? `חוצה קורה ${o.id} (${fmt(o.lo)}…${fmt(o.hi)}) במפלס ${fmt(hit.z)}` :
        o.cat === 'column' ? `חוצה עמוד ${o.id} במפלס ${fmt(hit.z)}` : `${vertical ? 'קטע אנכי' : 'קטע'} בתוך ${o.label} ${o.id}`, [hit.x, hit.y], o);
    }
  }
  // 1b. English courtyard: any piece of the run inside the courtyard footprint, whatever its level
  for (const o of obstacles) {
    if (o.cat !== 'courtyard' || C.courtyard?.value !== 'forbidden') continue;
    for (let i = 0; i + 1 < V.length; i++) {
      const a = V[i], b = V[i + 1], plan = Math.hypot(b.xy[0] - a.xy[0], b.xy[1] - a.xy[1]), n = Math.max(1, Math.ceil(plan / C.sampleStep_m));
      let hit = null; for (let k = 0; k <= n; k++) { const t = k / n, x = a.xy[0] + (b.xy[0] - a.xy[0]) * t, y = a.xy[1] + (b.xy[1] - a.xy[1]) * t; if (inPoly(x, y, o.poly)) { hit = [x, y]; break; } }
      if (hit) { push('error', 'courtyard', 'עובר בחצר האנגלית (אסור – גם מתחת לבטון)', hit, o); break; }
    }
  }
  // 2. walls (concrete + blocks): a horizontal segment that crosses a wall face must be square to it
  for (let i = 0; i + 1 < V.length; i++) {
    const a = V[i], b = V[i + 1], plan = Math.hypot(b.xy[0] - a.xy[0], b.xy[1] - a.xy[1]); if (plan < cfg.edit.stationTol_m) continue;
    for (const o of obstacles) {
      if (o.cat !== 'wall' && !(o.cat === 'block' && C.blockWallAngle)) continue;   // diagonal allowed (Avihai 09.11): blocks are crossed in the fill
      const P = o.poly;
      for (let e = 0; e < P.length; e++) {
        const c = P[e], d = P[(e + 1) % P.length], eL = Math.hypot(d[0] - c[0], d[1] - c[1]); if (eL < C.minFace_m) continue;   // only the long faces
        const X = segX(a.xy, b.xy, c, d); if (!X) continue;
        const z = a.h != null && b.h != null ? a.h + (b.h - a.h) * X.t - H0 : null;
        if (z != null && (z + R <= o.lo || z - R >= o.hi)) continue;
        const ang = Math.abs(Math.atan2((b.xy[0] - a.xy[0]) * (d[1] - c[1]) - (b.xy[1] - a.xy[1]) * (d[0] - c[0]), (b.xy[0] - a.xy[0]) * (d[0] - c[0]) + (b.xy[1] - a.xy[1]) * (d[1] - c[1]))) * 180 / Math.PI;
        const off = Math.abs(90 - Math.min(ang, 180 - ang));
        const key = 'ang' + o.id + i; if (off > C.wallPerpTol_deg && !seen.has(key)) { seen.add(key); push('warn', 'wallAngle', `חוצה ${o.label} ${o.id} בזווית ${(90 - off).toFixed(1)}° (לא בניצב)`, [a.xy[0] + (b.xy[0] - a.xy[0]) * X.t, a.xy[1] + (b.xy[1] - a.xy[1]) * X.t], o); }
      }
    }
  }
  // 3. drainage: along the vertex order (= flow), every horizontal step falls ≥ min slope × plan length; no rise
  if ((cfg.edit.gravitySystems || []).includes(run.system) && !['stack', 'vent', 'connector', 'drop'].includes(run.kind)) {   // connectors / drops: fittings, no fall of their own
    const minS = C.minSlope?.[run.system]?.value ?? run.slope ?? null;
    if (minS == null) push('info', 'noSlope', 'אין שיפוע תכנון לקו – לא נבדק', V[0].xy);
    for (let i = 0; i + 1 < V.length; i++) {
      const a = V[i], b = V[i + 1]; if (a.h == null || b.h == null) continue;
      const plan = Math.hypot(b.xy[0] - a.xy[0], b.xy[1] - a.xy[1]), drop = a.h - b.h, m = [(a.xy[0] + b.xy[0]) / 2, (a.xy[1] + b.xy[1]) / 2];
      if (plan < cfg.edit.stationTol_m) { if (drop < -C.levelTol_m) push('error', 'rise', `קטע אנכי עולה בכיוון הזרימה (${(-drop).toFixed(2)} מ')`, a.xy); continue; }
      if (drop < -C.levelTol_m) push('error', 'reverse', `שיפוע נגדי ${(drop / plan * 100).toFixed(1)}%`, m);
      else if (minS != null && drop < minS * plan - C.levelTol_m) push('warn', 'lowSlope', `שיפוע ${(drop / plan * 100).toFixed(2)}% – מתחת ל-${(minS * 100).toFixed(1)}%`, m);
    }
  }
  return out;
}
const fmt = (r) => `${r >= 0 ? '+' : '−'}${Math.abs(r).toFixed(2)}`;

// connections: run ends that touch nothing; consumption points whose water is not connected
// A run end counts as connected when: it names a node / a run (proposal or consultant), or it lies within connectTol of a
// node, of a vertex of another proposal run or of any consultant line. The top end of a stack / vent is its vent cap.
export function checkConnections(runs, nodes, consNodes, ctx, consLines = []) {
  const { fr, cfg } = ctx, tol = cfg.checks.connectTol_m, out = [];
  const ends = [], verts = [];
  for (const r of runs) {
    const V = r.vertices.map(v => fr.toLocal(v[0], v[1])); V.forEach(p => verts.push({ p, r }));
    const top = ['stack', 'vent'].includes(r.kind) || r.system === 'vent' ? ((r.vertices[0][2] ?? 0) > (r.vertices[r.vertices.length - 1][2] ?? 0) ? 'from' : 'to') : null;
    if (top !== 'from') ends.push({ p: V[0], r, which: 'from' }); if (top !== 'to') ends.push({ p: V[V.length - 1], r, which: 'to' });
  }
  for (const l of consLines) for (const q of (l.pts || l.pts3d)) verts.push({ p: fr.toLocal(q[0], q[1]), r: null });
  const near = (p, q) => Math.hypot(p[0] - q[0], p[1] - q[1]) <= tol;
  const nodeXY = [...nodes.map(n => ({ id: n.id, xy: n.xy })), ...consNodes.map(n => ({ id: n.id, xy: fr.toLocal(n.E, n.N) }))];
  const ids = new Set([...nodes.map(n => n.id), ...consNodes.map(n => n.id), ...runs.map(r => r.id), ...consLines.map(l => l.id)]);
  for (const e of ends) {
    const named = e.r[e.which]; if (named && ids.has(named)) continue;
    if (nodeXY.some(n => near(n.xy, e.p))) continue;
    if (verts.some(v => v.r !== e.r && near(v.p, e.p))) continue;
    out.push({ sev: 'warn', type: 'openEnd', text: `קצה ${e.which === 'from' ? 'התחלה' : 'סוף'} לא מחובר`, at: e.p, run: e.r.id });
  }
  for (const n of nodes) {
    if (!['wc', 'basin', 'shower', 'sink', 'washer', 'balconyTap'].includes(n.kind)) continue;
    for (const [s, need] of [['cold', n.cold], ['hot', n.hot && !n.hotPending]]) {
      if (!need) continue;
      const ok = runs.some(r => r.system === s && (r.to === n.id || r.from === n.id || [r.vertices[0], r.vertices[r.vertices.length - 1]].some(v => near(fr.toLocal(v[0], v[1]), n.xy))));
      if (!ok) out.push({ sev: 'warn', type: 'unconnected', text: `${n.id}: אין קו ${s === 'cold' ? 'מים קרים' : 'מים חמים'}`, at: n.xy, node: n.id });
    }
  }
  return out;
}
