import * as THREE from 'three';

// Props under the roof slab and the roof perimeter beams (Avihai's note 2.6): K-43 note 12 – "פירוק טפסות בכל שלב יהיה אך
// ורק באישור בכתב ממתכנן הקונסטרוקציה". The roof slab props stay from the slab pour (firstCeiling) until after the
// perimeter ring is cast (roofWalls); the ring's own props go up with it. Illustration only – the layout / spacing is the
// contractor's (display.props); each prop stands on the first concrete surface under it (ground ceiling, else ground slab).
export function buildProps(ctx) {
  const { data, coords, registry, scene, display } = ctx;
  const P = display.props; const FF = data.floorFirst, FG = data.floorGround, FR = data.floorRoof;
  if (!P || !FF?.ceiling?.slab?.length) return null;
  const inRing = (r, [x, y]) => { let c = false; for (let i = 0, j = r.length - 1; i < r.length; j = i++) { const [xi, yi] = r[i], [xj, yj] = r[j]; if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) c = !c; } return c; };
  const inPoly = (s, p) => inRing(s.footprintITM, p) && !(s.holesITM || []).some(h => inRing(h, p));
  const solids = [...(FF.walls || []), ...(FF.columns || []), ...(FG.walls || []), ...(FG.columns || [])];
  const base = (p) => {   // highest concrete surface under the point
    const c = (FG.ceiling?.slab || []).filter(s => inPoly(s, p)).map(s => s.topRel);
    if (c.length) return Math.max(...c);
    const g = (FG.slab || []).filter(s => inPoly(s, p)).map(s => s.topRel);
    return g.length ? Math.max(...g) : null;
  };
  const mat = new THREE.MeshStandardMaterial({ color: P.color, roughness: 0.6, metalness: 0.4 });
  const geo = new THREE.CylinderGeometry(P.dia_m / 2, P.dia_m / 2, 1, 6); geo.translate(0, 0.5, 0);
  const head = new THREE.BoxGeometry(P.headPlate_m, 0.02, P.headPlate_m);
  const make = (pts, topRel) => {
    const im = new THREE.InstancedMesh(geo, mat, pts.length), ih = new THREE.InstancedMesh(head, mat, pts.length), M = new THREE.Matrix4();
    pts.forEach(([E, N, b], i) => {
      const v = coords.toLocal(E, N, coords.H0 + b);
      M.compose(v, new THREE.Quaternion(), new THREE.Vector3(1, topRel - b, 1)); im.setMatrixAt(i, M);
      M.makeTranslation(v.x, topRel - 0.01, v.z); ih.setMatrixAt(i, M);
    });
    im.castShadow = true; const g = new THREE.Group(); g.add(im); g.add(ih); return g;
  };
  const note = 'המחשה בלבד – פריסת התמיכות וצפיפותן לפי תכנון הקבלן. K-43 הערה 12: "פירוק טפסות בכל שלב יהיה אך ורק באישור בכתב ממתכנן הקונסטרוקציה" – התמיכות נשארות עד אחרי יציקת חומת הגג (הערת אביחי 2.6).';
  let n = 0;
  // 1) under the roof slab: a grid in the slab's own axes (the house walls' direction)
  for (const s of FF.ceiling.slab) {
    const r = s.footprintITM; let best = [1, 0], L = 0;
    r.forEach((p, i) => { const q = r[(i + 1) % r.length], d = Math.hypot(q[0] - p[0], q[1] - p[1]); if (d > L) { L = d; best = [(q[0] - p[0]) / d, (q[1] - p[1]) / d]; } });
    const [ux, uy] = best, vx = -uy, vy = ux, U = r.map(p => p[0] * ux + p[1] * uy), V = r.map(p => p[0] * vx + p[1] * vy);
    const pts = [];
    for (let a = Math.min(...U) + P.inset_m; a <= Math.max(...U) - P.inset_m; a += P.spacing_m)
      for (let b = Math.min(...V) + P.inset_m; b <= Math.max(...V) - P.inset_m; b += P.spacing_m) {
        const p = [a * ux + b * vx, a * uy + b * vy];
        if (!inPoly(s, p) || solids.some(e => inRing(e.footprintITM, p))) continue;
        const b0 = base(p); if (b0 != null && b0 < s.bottomRel - 0.3) pts.push([p[0], p[1], b0]);
      }
    if (!pts.length) continue;
    const gs = make(pts, s.bottomRel); scene.add(gs);
    registry.add(gs, { floor: 'first', system: 'structure', stage: 'ceiling', layer: 'props', step: 'firstCeiling', stepTo: 'roofWalls' }, {
      id: `props-${s.id}`, name: `תמיכות תקרת הגג ${s.id} (המחשה)`, status: 'provisional',
      rows: [['מספר (המחשה)', `${pts.length} במרווח ${P.spacing_m} מ'`], ['מותקנות', 'שלב תקרת הגג'], ['פירוק', 'אחרי יציקת חומת הגג – באישור בכתב של הקונסטרוקטור']],
      note, source: 'sources/structure/K-43-קומה גג - פריסת ברזל.pdf הערה 12',
    });
    n++;
  }
  // 2) under the roof perimeter beams that are outside the slab (their formwork goes up with the ring)
  for (const b of FR?.ceiling?.beams || []) {
    if (!b.axisITM || !b.castWith) continue;
    const [[E1, N1], [E2, N2]] = b.axisITM, L = Math.hypot(E2 - E1, N2 - N1), pts = [];
    for (let t = P.inset_m; t <= L - P.inset_m + 1e-6; t += P.spacing_m) {
      const p = [E1 + (E2 - E1) * t / L, N1 + (N2 - N1) * t / L];
      if (FF.ceiling.slab.some(s => inPoly(s, p)) || solids.some(e => inRing(e.footprintITM, p))) continue;
      const b0 = base(p); if (b0 != null && b0 < b.bottomRel - 0.3) pts.push([p[0], p[1], b0]);
    }
    if (!pts.length) continue;
    const gb = make(pts, b.bottomRel); scene.add(gb);
    registry.add(gb, { floor: 'roof', system: 'structure', stage: 'ceiling', layer: 'props', step: 'roofWalls', stepTo: 'roofWalls' }, {
      id: `props-${b.id}`, name: `תמיכות קורת ההיקף ${b.id} (המחשה)`, status: 'provisional',
      rows: [['מספר (המחשה)', `${pts.length}`], ['פירוק', 'אחרי יציקת חומת הגג – באישור בכתב של הקונסטרוקטור']], note,
      source: 'sources/structure/K-43-קומה גג - פריסת ברזל.pdf הערה 12',
    });
    n++;
  }
  return { groups: n };
}
