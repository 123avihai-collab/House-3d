import * as THREE from 'three';
import { makeInterpolator, pointInRing, densifyRing, ringArea, distToRing, Delaunator } from './tin.js';

// Builds terrain meshes from data/site/terrain-regions.json + control points.
// No dimensions here: rings, heights and sampling come from data files.
export function buildTerrain(ctx) {
  const { data, coords, registry, materials, scene, display } = ctx;
  const T = display.terrain;
  const lotH = data.heights.lotCorners;
  const streetCtrl = streetControlPoints(data);
  const ground = new GroundService();
  const built = [];

  for (const region of data.regions.regions) {
    let ctrl;
    if (region.control.lotCorners) ctrl = region.control.lotCorners.map(i => ({ x: lotH[i].at[0], y: lotH[i].at[1], z: lotH[i].z }));
    else ctrl = streetCtrl;
    const interp = makeInterpolator(ctrl);
    if (!interp) { console.warn('region without control points', region.id); continue; }
    const mesh = regionMesh(region.ring, interp, coords, materials.get(region.material), materials.get('soilCut'), T, ctrl);
    const role = region.role;
    const tags = role === 'plot'
      ? { floor: 'site', system: 'site', stage: 'finishes', layer: 'topoPlanned' }
      : { floor: 'site', system: 'environment', stage: 'existing', layer: region.layer };
    const name = role === 'plot' ? 'מגרש 5187 – פני קרקע מתוכננים (סופי)'
      : role === 'neighbor' ? `מגרש שכן – חלקה ${region.parcel}`
      : role === 'sidewalk' ? 'מדרכה (פיתוח מתוכנן)' : 'כביש (פיתוח מתוכנן)';
    // lot 5187: the planned surface is drawn by the excavation module (development step), cut around the structure
    if (role !== 'plot') {
      registry.add(mesh, tags, {
        name, kind: 'terrain', role, parcel: region.parcel, ring: region.ring,
        area: Math.abs(ringArea(region.ring)), hMin: mesh.userData.hMin, hMax: mesh.userData.hMax,
        interp: interp.kind, controlCount: interp.count, note: region.note, source: region.source,
      });
      scene.add(mesh);
    }
    ground.add(region.ring, interp, role === 'plot' ? 'final' : 'env', region.id);
    built.push({ region, interp, mesh });
  }

  // existing ground of lot 5187 (survey 2025) – shown until the development (finishes) stage
  const s25 = data.survey.survey2025;
  if (s25) {
    const pts = s25.points.map(p => ({ x: p.E, y: p.N, z: p.z }));
    const interp25 = makeInterpolator(pts);
    const lot = data.plot.ring;
    const m = regionMesh(lot, interp25, coords, materials.get('soilPlot'), materials.get('soilCut'), T, []);
    registry.add(m, { floor: 'site', system: 'site', stage: 'existing', stepTo: 'existing', layer: 'topoExisting2025' }, {
      name: 'מגרש 5187 – קרקע קיימת (מדידה 25.09.2025)', kind: 'terrain', role: 'plotExisting', ring: lot,
      area: Math.abs(ringArea(lot)), hMin: m.userData.hMin, hMax: m.userData.hMax, interp: interp25.kind, controlCount: interp25.count,
      source: s25.source, note: `נקודות הגובה הועתקו מסריקה; דיוק מיקום ±${s25.positionAccuracy_m} מ'`,
    });
    scene.add(m);
    ground.add(lot, interp25, 'existing', 'lot-257-existing');
    // translucent comparison overlay over the survey extent
    const hull = convexHull(pts.map(p => [p.x, p.y]));
    const ov = regionMesh(hull, interp25, coords, materials.get('existing'), null, T, []);
    ov.castShadow = false; ov.receiveShadow = false;
    ov.renderOrder = 2;
    registry.add(ov, { floor: 'site', system: 'site', stage: 'existing', layer: 'existingOverlay' }, {
      name: 'שכבת השוואה – קרקע קיימת 2025', kind: 'overlay', area: Math.abs(ringArea(hull)), hMin: ov.userData.hMin, hMax: ov.userData.hMax, source: s25.source,
    });
    scene.add(ov);
  }

  // neutral context ground (no height data) below the modelled surfaces, with a hole at lot 5187
  // (the lot is always fully modelled; the hole keeps the plane out of the excavation pit)
  const allZ = built.flatMap(b => [b.mesh.userData.hMin]);
  const zMin = Math.min(...allZ) - T.contextGroundBelowMin_m;
  const half = T.contextGroundMargin_m;
  const c0 = coords.xz(data.plot.ring[0][0], data.plot.ring[0][1]);
  const outer = new THREE.Shape([[-half, -half], [half, -half], [half, half], [-half, half]].map(([a, b]) => new THREE.Vector2(c0[0] + a, -c0[1] + b)));
  const holeRing = data.plot.ring.map(([E, N]) => { const [x, z] = coords.xz(E, N); return new THREE.Vector2(x, -z); });
  outer.holes.push(new THREE.Path(holeRing));
  const g = new THREE.ShapeGeometry(outer);
  g.rotateX(-Math.PI / 2); // shape (x, -z) -> scene (x, z)
  const uv = g.attributes.uv, ps = g.attributes.position;
  for (let i = 0; i < uv.count; i++) uv.setXY(i, ps.getX(i), -ps.getZ(i));
  const plane = new THREE.Mesh(g, materials.get('context'));
  plane.position.y = zMin - coords.H0;
  plane.receiveShadow = true;
  registry.add(plane, { floor: 'site', system: 'environment', stage: 'existing', layer: 'contextParcels' }, {
    name: 'משטח ייחוס (ללא נתוני גובה)', kind: 'context', pickable: true,
    note: `גובה תצוגה בלבד: הנמוך שבגבהי המקור (${zMin.toFixed(2)}). אין במקורות גבהים לאזור זה.`,
  });
  scene.add(plane);
  ground.contextZ = zMin;
  return ground;
}

function streetControlPoints(data) {
  const pts = [];
  for (const c of data.street.contours) for (const [x, y] of c.points) pts.push({ x, y, z: c.z });
  for (const s of data.heights.streetSpots) pts.push({ x: s.at[0], y: s.at[1], z: s.z });
  return pts;
}

// Triangulated surface of one region + vertical skirt down to (min - skirtDepth).
export function regionMesh(ring, interp, coords, topMat, sideMat, T, ctrl) {
  const sp = T.sampleSpacing_m;
  const boundary = densifyRing(ring, T.boundaryDensify_m);
  const xs = ring.map(p => p[0]), ys = ring.map(p => p[1]);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const pts = boundary.slice();
  for (let x = Math.ceil(x0 / sp) * sp; x < x1; x += sp) {
    for (let y = Math.ceil(y0 / sp) * sp; y < y1; y += sp) {
      if (pointInRing(x, y, ring) && distToRing(x, y, ring) > sp * 0.35) pts.push([x, y]);
    }
  }
  for (const c of ctrl) if (pointInRing(c.x, c.y, ring) && distToRing(c.x, c.y, ring) > 0.05) pts.push([c.x, c.y]);
  const d = Delaunator.from(pts);
  const H = pts.map(([x, y]) => interp(x, y));
  const pos = [], uvs = [], idx = [];
  pts.forEach(([x, y], i) => {
    const [lx, lz] = coords.xz(x, y);
    pos.push(lx, H[i] - coords.H0, lz);
    uvs.push(x - coords.E0, y - coords.N0);
  });
  for (let i = 0; i < d.triangles.length; i += 3) {
    const a = d.triangles[i], b = d.triangles[i + 1], c = d.triangles[i + 2];
    const cx = (pts[a][0] + pts[b][0] + pts[c][0]) / 3, cy = (pts[a][1] + pts[b][1] + pts[c][1]) / 3;
    if (pointInRing(cx, cy, ring)) idx.push(a, c, b); // flip: ITM ccw -> scene (z = -N) needs reversed winding for +Y normals
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
  geo.setIndex(idx);
  geo.computeVertexNormals();
  fixUpwardNormals(geo);
  const group = new THREE.Group();
  const top = new THREE.Mesh(geo, topMat);
  top.receiveShadow = true; top.castShadow = true;
  group.add(top);
  const hMin = Math.min(...H), hMax = Math.max(...H);
  if (sideMat) {
    // outward-facing skirt (FrontSide), pulled a few mm inside the ring so that the walls of two
    // adjacent regions never coincide: from either side only the wall of the far region is seen.
    const base = hMin - T.skirtDepthBelowMin_m - coords.H0;
    const inset = 0.004;
    const ccw = ringArea(ring) > 0;
    const sp2 = [], su = [], si = [];
    let along = 0, vi = 0;
    for (let i = 0; i < boundary.length; i++) {
      const [x1, y1] = boundary[i], [x2, y2] = boundary[(i + 1) % boundary.length];
      const L = Math.hypot(x2 - x1, y2 - y1); if (L < 1e-6) continue;
      // inward normal in ITM
      let nx = -(y2 - y1) / L, ny = (x2 - x1) / L; if (!ccw) { nx = -nx; ny = -ny; }
      const a = coords.xz(x1 + nx * inset, y1 + ny * inset), b = coords.xz(x2 + nx * inset, y2 + ny * inset);
      const ha = interp(x1, y1) - coords.H0, hb = interp(x2, y2) - coords.H0;
      sp2.push(a[0], ha, a[1], a[0], base, a[1], b[0], hb, b[1], b[0], base, b[1]);
      su.push(along, ha, along, base, along + L, hb, along + L, base);
      along += L;
      // winding: outward normal in scene = -(inward); choose order so that face normal points outward
      const out = new THREE.Vector3(-nx, 0, ny); // scene z = -N
      const e1 = new THREE.Vector3(b[0] - a[0], hb - ha, b[1] - a[1]);
      const e2 = new THREE.Vector3(0, base - ha, 0);
      const fn = new THREE.Vector3().crossVectors(e1, e2);
      if (fn.dot(out) >= 0) si.push(vi, vi + 2, vi + 1, vi + 1, vi + 2, vi + 3);
      else si.push(vi, vi + 1, vi + 2, vi + 1, vi + 3, vi + 2);
      vi += 4;
    }
    const sg = new THREE.BufferGeometry();
    sg.setAttribute('position', new THREE.Float32BufferAttribute(sp2, 3));
    sg.setAttribute('uv', new THREE.Float32BufferAttribute(su, 2));
    sg.setIndex(si);
    sg.computeVertexNormals();
    const side = new THREE.Mesh(sg, sideMat);
    side.castShadow = true; side.receiveShadow = true;
    group.add(side);
  }
  group.userData.hMin = hMin; group.userData.hMax = hMax;
  return group;
}

function fixUpwardNormals(geo) {
  // if the majority of normals point down, flip winding
  const n = geo.attributes.normal; let s = 0;
  for (let i = 0; i < n.count; i++) s += n.getY(i);
  if (s < 0) {
    const ix = geo.index.array;
    for (let i = 0; i < ix.length; i += 3) { const t = ix[i + 1]; ix[i + 1] = ix[i + 2]; ix[i + 2] = t; }
    geo.index.needsUpdate = true; geo.computeVertexNormals();
  }
}

export function convexHull(points) {
  const p = points.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lo = [], up = [];
  for (const q of p) { while (lo.length >= 2 && cross(lo[lo.length - 2], lo[lo.length - 1], q) <= 0) lo.pop(); lo.push(q); }
  for (const q of p.reverse()) { while (up.length >= 2 && cross(up[up.length - 2], up[up.length - 1], q) <= 0) up.pop(); up.push(q); }
  return lo.slice(0, -1).concat(up.slice(0, -1));
}

// Height lookup by ITM position, used to drape lines/labels on the terrain.
export class GroundService {
  constructor() { this.regions = []; this.contextZ = null; }
  add(ring, interp, kind, id) { this.regions.push({ ring, interp, kind, id }); }
  // height from a specific region's surface (used for lines lying exactly on a shared boundary)
  heightIn(id, E, N) { const r = this.regions.find(x => x.id === id); return r ? r.interp(E, N) : this.heightAt(E, N); }
  heightAt(E, N, prefer = 'final') {
    const hits = this.regions.filter(r => pointInRing(E, N, r.ring));
    const pick = hits.find(r => r.kind === prefer) || hits.find(r => r.kind !== 'existing') || hits[0];
    if (pick) return pick.interp(E, N);
    return this.contextZ;
  }
}
