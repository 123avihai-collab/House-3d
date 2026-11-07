import * as THREE from 'three';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

// Starter bars + outlines (Avihai's note 5): at every slab / ceiling pour (groundSlab, groundCeiling, firstCeiling) the
// footprint of each concrete wall / column that rises from it is marked on the concrete with its id, and the starter bars
// stick out of the pour. Count / diameter: the vertical-bar callouts of the rebar sheets (rebar.json plan "columnBars",
// K-22 / K-32 / K-42). Projection: K-23 / K-33 / K-43 typical details (walls d+80, columns 45ø – rebar.json starters).
// An element with no callout gets schematic bars (display.starters, "המחשה"). An element flagged noRebar (e.g. RW21 –
// no rebar detail from the engineer) gets the outline only. Hidden from the step the element itself is cast.
export function buildStarters(ctx) {
  const { data, coords, registry, scene, display } = ctx;
  const S = data.rebar?.starters; const D = display.starters; if (!S || !D) return null;
  const SHEET = { ground: 'K-22', first: 'K-32', roof: 'K-42' };
  const calls = {};
  for (const e of data.rebar.plan || []) if (e.kind === 'columnBars' && e.element) (calls[`${e.sheet}|${e.element}`] ||= []).push(e);
  const prevStep = (id) => registry.steps[registry.steps.findIndex(s => s.id === id) - 1].id;
  const roofLevel = data.tags.floors.find(f => f.id === 'roof')?.level ?? 99;
  const barMat = new THREE.MeshStandardMaterial({ color: D.barColor, roughness: 0.5, metalness: 0.6 });
  const fillMat = new THREE.MeshBasicMaterial({ color: D.outlineColor, transparent: true, opacity: D.fillOpacity, depthWrite: false, side: THREE.DoubleSide });
  const lineMat = new THREE.LineBasicMaterial({ color: D.outlineColor });
  const schemMat = new THREE.MeshStandardMaterial({ color: D.schematicBarColor, roughness: 0.6, metalness: 0.3 });
  const toV = ([E, N]) => { const [x, z] = coords.xz(E, N); return new THREE.Vector2(x, -z); };
  const area2 = (r) => r.reduce((a, p, i) => { const q = r[(i + 1) % r.length]; return a + p[0] * q[1] - q[0] * p[1]; }, 0);
  // points every `step` along the ring, pulled inside by `cover` (normal of the edge they sit on)
  const along = (ring, n, spacing, cover) => {
    const L = ring.map((p, i) => { const q = ring[(i + 1) % ring.length]; return Math.hypot(q[0] - p[0], q[1] - p[1]); });
    const tot = L.reduce((a, b) => a + b, 0); const k = n || Math.max(4, Math.round(tot / spacing)); const sgn = area2(ring) > 0 ? 1 : -1;
    const out = [];
    for (let j = 0; j < k; j++) {
      let s = (j + 0.5) * tot / k, i = 0; while (s > L[i] && i < L.length - 1) { s -= L[i]; i++; }
      const p = ring[i], q = ring[(i + 1) % ring.length], t = s / L[i], ux = (q[0] - p[0]) / L[i], uy = (q[1] - p[1]) / L[i];
      out.push([p[0] + (q[0] - p[0]) * t - sgn * uy * cover, p[1] + (q[1] - p[1]) * t + sgn * ux * cover]);
    }
    return out;
  };
  const sets = [
    { floor: 'ground', F: data.floorGround, slab: 'groundSlab', step: (w) => (w.mamad ? 'groundCeiling' : 'groundWalls') },
    { floor: 'first', F: data.floorFirst, slab: 'groundCeiling', step: () => 'firstWalls' },
    { floor: 'roof', F: data.floorRoof, slab: (w) => (w.bottomRel < roofLevel - 0.5 ? 'groundCeiling' : 'firstCeiling'), step: (w) => (w.bottomRel < roofLevel - 0.5 ? 'firstWalls' : 'roofWalls') },
  ];
  let n = 0, nBars = 0;
  for (const st of sets) {
    if (!st.F) continue;
    for (const [kind, list] of [['wall', st.F.walls || []], ['column', st.F.columns || []]]) {
      for (const w of list) {
        const ring = w.footprintITM; if (!ring?.length) continue;
        const slabStep = typeof st.slab === 'function' ? st.slab(w) : st.slab, elStep = st.step(w);
        const cs = calls[`${SHEET[st.floor]}|${w.id}`] || [];
        const counts = [...new Set(cs.map(c => `${c.count}Ø${c.dia_mm}`))];
        const best = cs.reduce((a, c) => (!a || c.count > a.count ? c : a), null);
        const dia = (best?.dia_mm ?? D.schematicDia_mm) / 1000;
        const proj = kind === 'column' ? S.columnLap_d * dia : S.wallProjection_m;
        const zTop = coords.H0 + w.bottomRel;
        const g = new THREE.Group();
        // outline + light fill on the pour
        const sh = new THREE.Shape(ring.map(toV)); const fg = new THREE.ShapeGeometry(sh); fg.rotateX(-Math.PI / 2); fg.translate(0, w.bottomRel + D.lift_m, 0);
        const fill = new THREE.Mesh(fg, fillMat); fill.renderOrder = 4; g.add(fill);
        const pts = ring.map(([E, N]) => coords.toLocal(E, N, zTop + D.lift_m)); g.add(new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(pts), lineMat));
        // bars
        let barsTxt;
        if (w.noRebar) barsTxt = 'אין פרט זיון – לא מוצג';
        else {
          const P = along(ring, best?.count, D.schematicSpacing_m, S.cover_m + dia / 2);
          const geo = new THREE.CylinderGeometry(dia / 2 * D.barScale, dia / 2 * D.barScale, proj, 6); geo.translate(0, proj / 2, 0);
          const im = new THREE.InstancedMesh(geo, best ? barMat : schemMat, P.length); const M = new THREE.Matrix4();
          P.forEach(([E, N], i) => { const v = coords.toLocal(E, N, zTop); M.makeTranslation(v.x, v.y, v.z); im.setMatrixAt(i, M); });
          im.castShadow = true; g.add(im); nBars += P.length;
          barsTxt = best ? `${counts.join(' / ')} – ${SHEET[st.floor]}` : `סכמטי Ø${D.schematicDia_mm}@${Math.round(D.schematicSpacing_m * 100)} – המחשה (אין תיוג בגיליון)`;
        }
        const c = ring.reduce((a, p) => [a[0] + p[0] / ring.length, a[1] + p[1] / ring.length], [0, 0]);
        const div = document.createElement('div'); div.className = `lbl starter${best ? '' : ' schematic'}`; div.textContent = `${w.planName || w.id}${best ? ' · ' + counts.join('/') : ''}`;
        const lo = new CSS2DObject(div); lo.position.copy(coords.toLocal(c[0], c[1], zTop + proj + D.labelLift_m)); g.add(lo);
        const status = w.noRebar ? 'provisional' : best ? (counts.length > 1 ? 'approx' : 'source') : 'provisional';
        registry.add(g, { floor: st.floor, system: 'structure', stage: 'slab', layer: 'starters', step: slabStep, stepTo: prevStep(elStep) }, {
          id: `starters-${w.id}`, name: `קוצים + סימון ${kind === 'column' ? 'עמוד' : 'קיר'} ${w.planName || w.id}`, status,
          rows: [['קוצים', barsTxt], ['בליטה מעל הבטון', w.noRebar ? '—' : `${Math.round(proj * 100)} ס"מ (${kind === 'column' ? `${S.columnLap_d}ø` : 'd+80'})`],
            ['פני הבטון', coords.fmtH(zTop)], ['נוצק בשלב', registry.steps.find(s => s.id === elStep)?.label || elStep], ['כיסוי', `${Math.round(S.cover_m * 1000) / 10} ס"מ`]],
          note: [kind === 'column' ? S.columnSource : S.wallSource, counts.length > 1 ? `שני תיוגים קרובים בגיליון (${counts.join(', ')}) – מוצג הגדול; לבדוק מול הגיליון.` : '',
            best ? '' : 'אין תיוג ברזל אנכי לאלמנט בגיליון – קוצים סכמטיים להמחשה בלבד.', w.noRebar ? w.noRebarNote || '' : ''].filter(Boolean).join(' '),
          source: best ? `sources/structure/${SHEET[st.floor]} (${best.text}); ${S.wallSource.split(':')[0]}` : S.wallSource.split(':')[0],
        });
        scene.add(g); n++;
      }
    }
  }
  return { elements: n, bars: nBars };
}
