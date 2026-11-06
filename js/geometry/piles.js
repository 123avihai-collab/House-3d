import * as THREE from 'three';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

// Piles from data/structure/piles.json: cylinders from head level down to head − L.
export function buildPiles(ctx) {
  const { data, coords, registry, scene, materials, display } = ctx;
  const P = display.piles;
  const mat = materials.get('concrete');
  const over = materials.get('concrete').clone(); over.color.set(P.overloadTint);
  // "x-ray" copy drawn on top of the soil, so piles hidden under the ground stay visible
  const ghost = new THREE.MeshBasicMaterial({ color: P.ghostColor, transparent: true, opacity: P.ghostOpacity, depthTest: false, depthWrite: false });
  const stats = { count: 0, drill_m: 0, concrete_m3: 0, byType: {} };
  for (const p of data.piles.piles) {
    const headAbs = coords.H0 + p.headRel, tipAbs = coords.H0 + p.tipRel;
    const len = headAbs - tipAbs, r = p.diameter_m / 2;
    const geo = new THREE.CylinderGeometry(r, r, len, P.radialSegments, 1);
    // world-metre UVs: u around circumference, v along length
    const uv = geo.attributes.uv; for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i) * 2 * Math.PI * r, uv.getY(i) * len);
    const m = new THREE.Mesh(geo, p.overAllowed ? over : mat);
    m.position.copy(coords.toLocal(p.E, p.N, (headAbs + tipAbs) / 2));
    m.castShadow = true; m.receiveShadow = true;
    const g = new THREE.Group(); g.add(m);
    // x-ray copy only while looking at the piles stage (later stages show beams / slabs in front of the piles)
    const gm = new THREE.Mesh(geo, ghost); gm.position.copy(m.position); gm.renderOrder = 5; gm.raycast = () => {};
    const gg = new THREE.Group(); gg.add(gm); scene.add(gg);
    registry.add(gg, { floor: p.zone === 'basement' ? 'unit' : 'ground', system: 'structure', stage: 'piles', stageTo: 'piles', layer: 'piles' }, { name: `כלונס ${p.id} (שיקוף)`, kind: 'ghost', pickable: false });
    const div = document.createElement('div');
    div.className = 'lbl pile' + (p.overAllowed ? ' over' : '');
    div.textContent = p.id;
    const l = new CSS2DObject(div); l.position.copy(coords.toLocal(p.E, p.N, headAbs + P.labelLift_m)); g.add(l);
    const x = p.xlsxCheck;
    const util = x ? (p.designLoad_t / x.allowed * 100) : null;
    registry.add(g, { floor: p.zone === 'basement' ? 'unit' : 'ground', system: 'structure', stage: 'piles', layer: 'piles' }, {
      name: `כלונס ${p.id} · ø${Math.round(p.diameter_m * 100)} · L=${p.length_m} מ'`, kind: 'pile', id: p.id,
      rows: [
        ['קוטר', `${Math.round(p.diameter_m * 100)} ס"מ`],
        ['אורך L', `${p.length_m} מ'`],
        ['מפלס ראש', coords.fmtH(headAbs)],
        ['מפלס תחתית (ראש − L)', coords.fmtH(tipAbs)],
        ['מיקום (ITM)', coords.fmtEN(p.E, p.N)],
        ['עומס תכנוני', `${p.designLoad_t} טון`],
        ['עומס מותר (דוח קרקע 6.4)', x ? `${x.allowed} טון · ניצול ${util.toFixed(0)}%` : '—'],
        ['הצלבה מול טבלת הכלונסאות', x ? (x.match ? '✔ תואם' : '✘ לא תואם') : 'לא בטבלה'],
      ],
      note: p.overAllowed ? `מבוצע כמו בתוכנית K-400 (N=${p.designLoad_t} ט'). עומס תכנוני מעל המותר בדוח הקרקע (${x?.allowed} ט') – לבדיקה מול הקונסטרוקטור (open-issues #17)` : p.tipNote,
      source: p.source,
    });
    scene.add(g);
    stats.count++; stats.drill_m += p.length_m; stats.concrete_m3 += Math.PI * r * r * p.length_m;
    const key = `ø${Math.round(p.diameter_m * 100)} L=${p.length_m}`;
    stats.byType[key] = (stats.byType[key] || 0) + 1;
  }
  return stats;
}
