import * as THREE from 'three';
import { Line2 } from 'three/addons/lines/Line2.js';
import { LineGeometry } from 'three/addons/lines/LineGeometry.js';
import { LineMaterial } from 'three/addons/lines/LineMaterial.js';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

// Site linework, markers and labels. Positions/heights come only from data files.
export function buildSite(ctx) {
  const { data, coords, registry, scene, display, ground, lineMats } = ctx;
  const L = display.lines;
  const site = (layer, system = 'site') => ({ floor: 'site', system, stage: 'existing', layer });
  const fat = (pts, color, width, opts = {}) => {
    const g = new LineGeometry();
    g.setPositions(pts.flatMap(v => [v.x, v.y, v.z]));
    const m = new LineMaterial({ color, linewidth: width, dashed: !!opts.dashed, dashSize: 0.6, gapSize: 0.35, transparent: true, opacity: opts.opacity ?? 1, depthTest: opts.depthTest ?? true });
    m.resolution.copy(ctx.viewer.resolution);
    lineMats.push(m);
    const l = new Line2(g, m);
    l.computeLineDistances();
    l.renderOrder = 5;
    return l;
  };
  // prefer: 'final' | 'env' | 'existing' (lookup by position) or a region id such as 'lot-257' (exact surface)
  const hAt = (E, N, prefer) => prefer.startsWith('lot-') ? ground.heightIn(prefer, E, N) : ground.heightAt(E, N, prefer);
  const drape = (E, N, prefer = 'final', lift = L.lineLift_m) => coords.toLocal(E, N, hAt(E, N, prefer) + lift);
  const drapeLine = (pts, step = 0.5, prefer = 'final', lift = L.lineLift_m) => {
    const out = [];
    for (let i = 0; i < pts.length - 1; i++) {
      const [x1, y1] = pts[i], [x2, y2] = pts[i + 1];
      const n = Math.max(1, Math.ceil(Math.hypot(x2 - x1, y2 - y1) / step));
      for (let k = 0; k < n; k++) out.push(drape(x1 + (x2 - x1) * k / n, y1 + (y2 - y1) * k / n, prefer, lift));
    }
    const last = pts[pts.length - 1]; out.push(drape(last[0], last[1], prefer, lift));
    return out;
  };
  const label = (text, cls, pos, title) => {
    const div = document.createElement('div');
    div.className = `lbl ${cls}`; div.textContent = text; if (title) div.title = title;
    const o = new CSS2DObject(div); o.position.copy(pos); return o;
  };

  // ---------- plot boundary ----------
  const plot = data.plot;
  const ring = plot.ring.concat([plot.ring[0]]);
  const g1 = new THREE.Group();
  g1.add(fat(drapeLine(ring, 0.25, 'lot-257', L.plotBoundaryLift_m), L.plotBoundaryColor, L.plotBoundaryWidth_px));
  const pinMat = new THREE.MeshStandardMaterial({ color: L.plotBoundaryColor, roughness: 0.5 });
  for (const [name, p] of Object.entries(plot.points)) {
    const h = ground.heightIn('lot-257', p.E, p.N);
    const pin = new THREE.Mesh(new THREE.CylinderGeometry(display.labels.pointMarkerRadius_m * 0.4, display.labels.pointMarkerRadius_m * 0.4, 1, 12), pinMat);
    pin.position.copy(coords.toLocal(p.E, p.N, h + 0.5));
    pin.castShadow = true;
    g1.add(pin);
    g1.add(label(`${name}`, 'pt', coords.toLocal(p.E, p.N, h + 1.15), `נקודת גבול ${name}\nE ${p.E.toFixed(3)}\nN ${p.N.toFixed(3)}`));
  }
  // edge lengths (computed from the source coordinates; arc edge uses R)
  for (const e of plot.edges) {
    const a = plot.points[e.from], b = plot.points[e.to];
    const chord = Math.hypot(b.E - a.E, b.N - a.N);
    const len = e.type === 'arc' ? 2 * e.radius * Math.asin(chord / (2 * e.radius)) : chord;
    const mE = (a.E + b.E) / 2, mN = (a.N + b.N) / 2;
    g1.add(label(`${len.toFixed(2)}${e.type === 'arc' ? ` (R=${e.radius.toFixed(2)})` : ''}`, 'len', drape(mE, mN, 'lot-257', 0.3)));
  }
  registry.add(g1, site('plotBoundary'), {
    name: 'גבול מגרש 5187', kind: 'plotBoundary', ring: plot.ring, area: plot.area_m2_computed,
    source: plot.source, pickable: true,
  });
  scene.add(g1);

  // ---------- building lines (drawn in the buyer's map) ----------
  const g2 = new THREE.Group();
  for (const pl of data.buildingLines.lot5187Envelope) g2.add(fat(drapeLine(pl.points, 0.5, 'lot-257'), L.buildingLineColor, 2.5, { dashed: true }));
  for (const pl of data.buildingLines.buildLines) g2.add(fat(drapeLine(pl.points), L.buildingLineColor, 1.5, { dashed: true, opacity: 0.7 }));
  const env = data.buildingLines.lot5187Envelope[0]?.points;
  if (env) g2.add(label('קו בניין', 'bl', drape(env[1][0], env[1][1], 'final', 0.25)));
  registry.add(g2, site('buildingLines'), { name: 'קווי בניין (מפה למשתכן)', kind: 'lines', source: data.buildingLines.source });
  scene.add(g2);

  // ---------- planned contours ----------
  const g3 = new THREE.Group();
  for (const c of data.street.contours) {
    const pts = c.points.map(([x, y]) => coords.toLocal(x, y, c.z + L.lineLift_m));
    g3.add(fat(pts, L.contourColor, c.z % 1 === 0 ? 2.2 : 1.2, { opacity: 0.85 }));
    const mid = c.points[Math.floor(c.points.length / 2)];
    g3.add(label(c.z.toFixed(1), 'contour', coords.toLocal(mid[0], mid[1], c.z + 0.15)));
  }
  registry.add(g3, site('contours', 'environment'), { name: 'קווי גובה מתוכננים – רחוב', kind: 'lines', source: data.street.contours[0]?.source });
  scene.add(g3);

  // ---------- planned height labels ----------
  const g4 = new THREE.Group();
  const dot = new THREE.SphereGeometry(display.labels.pointMarkerRadius_m, 12, 8);
  const dotMat = new THREE.MeshStandardMaterial({ color: '#ffd54f', roughness: 0.4 });
  for (const h of data.heights.lotCorners) {
    const p = coords.toLocal(h.at[0], h.at[1], h.z);
    const s = new THREE.Mesh(dot, dotMat); s.position.copy(p); g4.add(s);
    g4.add(label(coords.fmtH(h.z), h.parcel === '257' ? 'h h-plot' : 'h', p.clone().add(new THREE.Vector3(0, 0.45, 0)),
      `גובה מתוכנן מגרש – חלקה ${h.parcel}\n${h.source}`));
  }
  for (const h of data.heights.streetSpots) {
    const p = coords.toLocal(h.at[0], h.at[1], h.z);
    const s = new THREE.Mesh(dot, dotMat); s.position.copy(p); g4.add(s);
    g4.add(label(coords.fmtH(h.z), 'h h-street', p.clone().add(new THREE.Vector3(0, 0.45, 0)), `גובה מתוכנן מדרכה\n${h.source}`));
  }
  const z0 = data.heights.houseZero;
  if (z0) {
    const p = coords.toLocal(z0.at[0], z0.at[1], z0.z);
    const ring0 = new THREE.Mesh(new THREE.TorusGeometry(0.35, 0.04, 8, 32), new THREE.MeshStandardMaterial({ color: '#7e57c2' }));
    ring0.rotation.x = Math.PI / 2; ring0.position.copy(p); g4.add(ring0);
    g4.add(label(`±0.00 = ${z0.z.toFixed(2)}`, 'h h-zero', p.clone().add(new THREE.Vector3(0, 0.55, 0)), z0.source));
  }
  registry.add(g4, site('plannedHeights'), { name: 'גבהים מתוכננים (מפה למשתכן)', kind: 'labels', source: 'data/site/planned-heights.json' });
  scene.add(g4);

  // ---------- street linework ----------
  const g5 = new THREE.Group();
  for (const c of data.street.curbs) g5.add(fat(drapeLine(c.points, 0.5, 'env', 0.03), L.curbColor, c.layer === 'HW-CURB-GUTR' ? 2.2 : 1.4));
  for (const c of data.street.islands) g5.add(fat(drapeLine(c.points, 0.3, 'env', 0.03), L.curbColor, 1.4));
  registry.add(g5, site('street', 'environment'), { name: 'אבני שפה ואיים (מפה למשתכן)', kind: 'lines', source: data.street.source });
  scene.add(g5);
  const g6 = new THREE.Group();
  for (const c of data.street.pavedEntries) g6.add(fat(drapeLine(c.points, 0.3, 'final', 0.04), '#90a4ae', 2));
  registry.add(g6, site('pavedEntries'), { name: 'משטחי כניסה/חניה מתוכננים', kind: 'lines', source: data.street.source });
  scene.add(g6);

  // ---------- parcels: modelled neighbours + context outlines ----------
  const modelled = new Set(data.regions.regions.filter(r => r.parcel).map(r => r.parcel));
  const g7 = new THREE.Group(), g8 = new THREE.Group();
  for (const p of data.parcels.parcels) {
    if (p.parcel === '257') continue;
    const r = p.ring.concat([p.ring[0]]);
    const c = centroid(p.ring);
    if (modelled.has(p.parcel)) {
      g7.add(fat(drapeLine(r, 0.4, `lot-${p.parcel}`, 0.04), L.parcelColor, 2));
      g7.add(label(`חלקה ${p.parcel}`, 'parcel', drape(c[0], c[1], `lot-${p.parcel}`, 0.6)));
    } else {
      const z = ground.contextZ + 0.02;
      g8.add(fat(r.map(([x, y]) => coords.toLocal(x, y, z)), L.contextParcelColor, 1.2, { opacity: 0.9 }));
      if (p.parcel) g8.add(label(p.parcel, 'parcel ctx', coords.toLocal(c[0], c[1], z + 0.3)));
    }
  }
  registry.add(g7, site('neighborLots', 'environment'), { name: 'גבולות מגרשי שכנים', kind: 'lines', source: data.parcels.parcels[0]?.source });
  registry.add(g8, site('contextParcels', 'environment'), { name: 'חלקות בסביבה', kind: 'lines', source: data.parcels.parcels[0]?.source });
  scene.add(g7, g8);

  // ---------- survey points ----------
  const sp = (pts, color, layer, nm, src) => {
    const g = new THREE.Group();
    const m = new THREE.MeshStandardMaterial({ color });
    for (const p of pts) {
      const v = coords.toLocal(p.E, p.N, p.z);
      const s = new THREE.Mesh(dot, m); s.scale.setScalar(0.7); s.position.copy(v); g.add(s);
      g.add(label(p.z.toFixed(2), 'sv', v.clone().add(new THREE.Vector3(0, 0.3, 0))));
    }
    registry.add(g, site(layer), { name: nm, kind: 'points', source: src });
    scene.add(g);
  };
  // off on open – built the first time the layer is switched on (registry.defer)
  if (data.survey.survey2025) registry.defer(['surveyPoints2025'], () => sp(data.survey.survey2025.points, '#29b6f6', 'surveyPoints2025', 'נקודות גובה קיימות – מדידה 2025', data.survey.survey2025.source));
  registry.defer(['surveyPoints2023'], () => sp(data.survey.survey2023, '#ab47bc', 'surveyPoints2023', 'נקודות גובה – מפה למשתכן 2023', data.survey.survey2023[0]?.source));

  // ---------- north arrow (true north) ----------
  const na = new THREE.Group();
  const ext = data.origin.mapFrameITM;
  const corner = ext.reduce((a, b) => (b[0] + b[1] < a[0] + a[1] ? b : a)); // south-west corner of the data frame
  const base = coords.toLocal(corner[0] - 5, corner[1] - 5, ground.contextZ + 0.05);
  const az = THREE.MathUtils.degToRad(coords.trueNorthGridAz);
  const shape = new THREE.Shape();
  shape.moveTo(0, 2.6); shape.lineTo(0.9, -1.2); shape.lineTo(0, -0.4); shape.lineTo(-0.9, -1.2); shape.closePath();
  const arrow = new THREE.Mesh(new THREE.ExtrudeGeometry(shape, { depth: 0.12, bevelEnabled: false }), new THREE.MeshStandardMaterial({ color: '#c62828', roughness: 0.5 }));
  arrow.rotation.x = -Math.PI / 2; arrow.rotation.z = -az; arrow.position.copy(base); arrow.castShadow = true;
  na.add(arrow);
  const tip = base.clone().add(new THREE.Vector3(Math.sin(az) * 3.4, 0.4, -Math.cos(az) * 3.4));
  na.add(label('צפון', 'north', tip, `צפון אמיתי (סטייה מצפון הרשת: ${coords.trueNorthGridAz.toFixed(3)}°)`));
  registry.add(na, site('northArrow', 'environment'), { name: 'חץ צפון אמיתי', kind: 'symbol', source: 'data/site/origin.json trueNorthGridAzimuth_deg' });
  scene.add(na);

  // ---------- ITM grid (5 m) ----------
  const gg = new THREE.Group();
  const [cE0, cN0, cE1, cN1] = data.origin.contextWindowITM;
  const zg = ground.contextZ + 0.03;
  const gm = new THREE.LineBasicMaterial({ color: '#455a64', transparent: true, opacity: 0.5 });
  const verts = [];
  for (let E = Math.ceil(cE0 / 5) * 5; E <= cE1; E += 5) verts.push(coords.toLocal(E, cN0, zg), coords.toLocal(E, cN1, zg));
  for (let N = Math.ceil(cN0 / 5) * 5; N <= cN1; N += 5) verts.push(coords.toLocal(cE0, N, zg), coords.toLocal(cE1, N, zg));
  gg.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(verts), gm));
  for (let E = Math.ceil(cE0 / 25) * 25; E <= cE1; E += 25) gg.add(label(`E ${E}`, 'grid', coords.toLocal(E, cN0, zg)));
  for (let N = Math.ceil(cN0 / 25) * 25; N <= cN1; N += 25) gg.add(label(`N ${N}`, 'grid', coords.toLocal(cE0, N, zg)));
  registry.add(gg, site('itmGrid', 'environment'), { name: 'רשת ITM', kind: 'grid', pickable: false });
  scene.add(gg);
}

export function centroid(ring) {
  let a = 0, cx = 0, cy = 0;
  for (let i = 0; i < ring.length; i++) {
    const [x1, y1] = ring[i], [x2, y2] = ring[(i + 1) % ring.length];
    const f = x1 * y2 - x2 * y1; a += f; cx += (x1 + x2) * f; cy += (y1 + y2) * f;
  }
  a /= 2; return [cx / (6 * a), cy / (6 * a)];
}
