// Loads the data the plan editor needs and turns it into per-floor drawable layers in the house frame.
// Nothing here holds a dimension: every coordinate comes from data/ (structure, blocks, plumbing JSON).
import { Frame } from './view.js';

const NEED = ['origin', 'plot', 'tags', 'framing', 'floorGround', 'floorFirst', 'floorRoof', 'perimeter', 'blocks',
  'plumbing', 'plumbingDisplay', 'plumbingCatalog'];

async function getJson(url) {
  const r = await fetch(url, { cache: 'no-cache' });
  if (!r.ok) throw new Error(`טעינת ${url} נכשלה (${r.status})`);
  return r.json();
}

export async function loadEditorData(base = './') {
  const man = await getJson(base + 'data/manifest.json');
  const paths = { ...Object.fromEntries(NEED.map(k => [k, man.files[k]])), ...Object.fromEntries(Object.entries(man.editorFiles).filter(([k]) => k !== '_doc')) };
  const out = { manifest: man };
  await Promise.all(Object.entries(paths).map(async ([k, p]) => { out[k] = await getJson(base + p); out[k].__path = p; }));
  return out;
}

// beam footprint from its axis and width (same construction as tools/plumbing/proposal_common.py beam_poly)
function beamPoly(b) {
  const [[e1, n1], [e2, n2]] = b.axisITM; const L = Math.hypot(e2 - e1, n2 - n1); if (!L) return null;
  const ux = (e2 - e1) / L, uy = (n2 - n1) / L, hw = b.width_m / 2;
  return [[e1 - uy * hw, n1 + ux * hw], [e2 - uy * hw, n2 + ux * hw], [e2 + uy * hw, n2 - ux * hw], [e1 + uy * hw, n1 - ux * hw]];
}
function blockPoly(w) {
  const [[e1, n1], [e2, n2]] = w.axisITM; const L = Math.hypot(e2 - e1, n2 - n1); if (!L) return null;
  const ux = (e2 - e1) / L, uy = (n2 - n1) / L, hw = w.thickness_m / 2;
  return [[e1 - uy * hw, n1 + ux * hw], [e2 - uy * hw, n2 + ux * hw], [e2 + uy * hw, n2 - ux * hw], [e1 + uy * hw, n1 - ux * hw]];
}

export function buildModel(D) {
  const fr = new Frame(D.routes.frame), H0 = D.origin.H0, cfg = D.planEditor;
  const L = (P) => P.map(([E, N]) => fr.toLocal(E, N));
  const levels = D.tags.floors.filter(f => f.level != null).map(f => ({ id: f.id, level: f.level })).sort((a, b) => a.level - b.level);
  const band = (fid) => { const i = levels.findIndex(l => l.id === fid); return [levels[i].level, i + 1 < levels.length ? levels[i + 1].level : Infinity]; };
  const floorStruct = { ground: D.floorGround, first: D.floorFirst, roof: D.floorRoof };
  const below = { unit: null, ground: D.floorGround, first: D.floorGround, roof: D.floorFirst };   // whose ceiling beams sit under this floor's slab
  const el = (kind, r, poly, extra = {}) => poly && poly.length > 2 ? { kind, id: r.id, poly: L(poly), holes: (r.holesITM || []).map(L), bottomRel: r.bottomRel, topRel: r.topRel, status: r.status, source: r.source, ...extra } : null;

  const floors = {};
  for (const f of cfg.floors) {
    const S = { concreteWalls: [], columns: [], blocks: [], beamsAbove: [], beamsBelow: [], plot: [], perimeter: [] };
    if (f.structure === 'unit') {
      for (const w of D.framing.basementWalls) S.concreteWalls.push(el('קיר מרתף', w, w.footprintITM));
      for (const b of D.framing.groundBeams) if (b.axisITM) S.beamsAbove.push(el('קורת יסוד (תקרת המרתף)', b, beamPoly(b), { width_m: b.width_m, depth_m: b.depth_m }));
    } else {
      const F = floorStruct[f.structure];
      for (const w of F.walls) S.concreteWalls.push(el('קיר בטון', w, w.footprintITM));
      for (const c of F.columns) S.columns.push(el('עמוד', c, c.footprintITM));
      for (const b of F.ceiling.beams || []) if (b.axisITM) S.beamsAbove.push(el('קורת תקרה', b, beamPoly(b), { width_m: b.width_m, depth_m: b.depth_m }));
      const under = f.structure === 'ground' ? D.framing.groundBeams : (below[f.structure]?.ceiling.beams || []);
      for (const b of under) if (b.axisITM) S.beamsBelow.push(el(f.structure === 'ground' ? 'קורת יסוד' : 'קורה מתחת לרצפה', b, beamPoly(b), { width_m: b.width_m, depth_m: b.depth_m }));
    }
    for (const w of D.blocks.walls) if (w.floor === f.structure) S.blocks.push(el('קיר בלוקים', w, blockPoly(w), { thickness_m: w.thickness_m }));
    if (f.id === 'ground') {
      S.plot.push({ kind: 'גבול מגרש', id: 'מגרש ' + D.plot.lot, poly: L(D.plot.ring), source: D.plot.source, line: true });
      for (const w of D.perimeter.walls) if (w.ringITM) S.perimeter.push(el('חומה היקפית', w, w.ringITM));
    }
    for (const k in S) S[k] = S[k].filter(Boolean);
    const bg = D.planBackground.floors[f.background];
    const B = {}; for (const g in bg.groups) B[g] = bg.groups[g].map(L);
    B.texts = bg.texts.map(t => ({ ...t, xy: fr.toLocal(t.E, t.N) }));
    floors[f.id] = { cfg: f, band: band(f.id), structure: S, background: B };
  }

  // ---- pipes: proposal (routes.json, editable from stage 2) + consultant (network.json, read only)
  const sup = new Set(D.routes.superseded.runs);
  const verticals = (V) => {   // vertical pieces (plan move < 2 cm, height change > 5 cm) -> plan point + rel range
    const out = [];
    for (let i = 0; i + 1 < V.length; i++) {
      const a = V[i], b = V[i + 1]; if (a[2] == null || b[2] == null) continue;
      if (Math.hypot(b[0] - a[0], b[1] - a[1]) < 0.02 && Math.abs(b[2] - a[2]) > 0.05) out.push({ xy: fr.toLocal(a[0], a[1]), lo: Math.min(a[2], b[2]) - H0, hi: Math.max(a[2], b[2]) - H0 });
    }
    return out;
  };
  const propPipe = (r) => ({ layer: 'prop', ref: r, id: r.id, system: r.system, floor: r.floor, kind: r.kind, pts: r.vertices.map(v => fr.toLocal(v[0], v[1])),
    H: r.vertices.map(v => v[2]), verticals: verticals(r.vertices), readOnly: false, manual: r.status === 'manual' });
  const pipes = D.routes.runs.map(propPipe);
  for (const r of D.plumbing.runs) {
    pipes.push({ layer: 'cons', ref: r, id: r.id, system: r.system, floor: r.drawnOn === 'ground' && r.floor === 'site' ? 'site' : r.floor, kind: 'run',
      pts: r.pts.map(p => fr.toLocal(p[0], p[1])), H: null, verticals: [], superseded: sup.has(r.id), readOnly: true });
  }
  for (const l of D.plumbing.lines3d) {
    pipes.push({ layer: 'cons', ref: l, id: l.id, system: l.system, floor: l.floors ? 'multi' : null, floors: l.floors, kind: l.kind || 'line3d',
      pts: l.pts3d.map(p => fr.toLocal(p[0], p[1])), H: l.pts3d.map(p => p[2]), verticals: verticals(l.pts3d), superseded: sup.has(l.id), readOnly: true });
  }
  // which floor shows which pipe: own floor (site on the ground view); vertical pieces also on every floor band they cross
  const showsOn = (p, fid) => {
    const f = floors[fid];
    if (p.floor === fid || (f.cfg.alsoRuns || []).includes(p.floor)) return 'plan';
    if (p.floors && p.floors.includes(fid)) return 'pass';
    const [lo, hi] = f.band; if (p.verticals.some(v => v.lo < hi && v.hi > lo)) return 'pass';
    return null;
  };
  const nodes = D.routes.nodes.map(n => ({ ...n, xy: fr.toLocal(n.E, n.N) }));
  const M = { frame: fr, H0, floors, pipes, nodes, showsOn, levels };
  // the proposal part is rebuilt from the store after every edit; the consultant part never changes
  M.setNodes = (list) => { M.nodes = list.map(n => ({ ...n, xy: fr.toLocal(n.E, n.N) })); };
  M.setRuns = (runs) => { M.pipes = [...runs.map(propPipe), ...pipes.filter(p => p.layer === 'cons')]; };
  return M;
}

export function systemsOf(D) {
  const cfg = D.planEditor.systems, disp = D.plumbingDisplay.systems, out = {};
  for (const s of cfg.order) {
    const base = disp[s] || cfg.extra[s] || { label: s, color: '#888' };
    out[s] = { id: s, label: base.label, color: (cfg.override || {})[s] || base.color };
  }
  return out;
}
