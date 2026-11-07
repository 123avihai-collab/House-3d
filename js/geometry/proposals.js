import * as THREE from 'three';
import { CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

// Owner-change proposals that cancel a wall (data/changes/owner-changes.json "cancelsWall"; the wall is flagged cancelledBy
// in floor-*.json by tools/extract_floor.py). The wall itself stays in floors.js as the "original" variant (as in the
// plans, red edges); this module builds the "changed" variant: the wall as a red ghost, the cantilever beam proposed in its
// place (footprint = the cancelled wall, depth = the beam it catches – placeholder until the engineer sizes it) and a
// question mark on every roof beam that rested on the wall (OC-2, Avihai's note 2.2: B-30 / B-4 at the pergola corner).
export function buildWallProposals(ctx) {
  const { data, coords, registry, scene, materials, display } = ctx;
  const D = display.framing; const H = (rel) => coords.H0 + rel;
  const OC = data.ownerChanges?.changes || [];
  const toV = ([E, N]) => { const [x, z] = coords.xz(E, N); return new THREE.Vector2(x, -z); };
  const prism = (ring, zb, zt, mat) => {
    const g = new THREE.ExtrudeGeometry(new THREE.Shape(ring.map(toV)), { depth: zt - zb, bevelEnabled: false });
    g.rotateX(-Math.PI / 2); g.translate(0, zb, 0); return new THREE.Mesh(g, mat);
  };
  const label = (text, E, N, Habs, cls) => {
    const d = document.createElement('div'); d.className = cls; d.textContent = text;
    const o = new CSS2DObject(d); o.position.copy(coords.toLocal(E, N, Habs)); return o;
  };
  const centroid = (r) => r.reduce((a, p) => [a[0] + p[0] / r.length, a[1] + p[1] / r.length], [0, 0]);
  const ghostM = new THREE.MeshBasicMaterial({ color: D.ownerChangeRemovedColor, transparent: true, opacity: D.ownerChangeRemovedOpacity, depthWrite: false });
  let n = 0;
  for (const [floor, F] of [['ground', data.floorGround], ['first', data.floorFirst], ['roof', data.floorRoof]]) {
    for (const w of F?.walls || []) {
      const c = OC.find(o => o.id === w.cancelledBy); if (!c) continue;
      const [cE, cN] = centroid(w.footprintITM);
      // 1) the cancelled wall – red ghost
      const g = new THREE.Group(); g.add(prism(w.footprintITM, w.bottomRel, w.topRel, ghostM));
      g.add(label(`${c.id} · ${c.removedLabel}`, cE, cN, H(w.topRel) + D.labelLift_m, 'lbl removed'));
      registry.add(g, { floor, system: 'structure', stage: 'walls', layer: 'ownerChanges', ...(w.bottomRel < 6 ? { step: 'firstWalls' } : {}) }, {
        id: `${c.id}-wall`, name: `מבוטל (${c.id}): ${w.displayName || w.id}`, status: 'provisional', variant: { change: c.id, show: 'changed' },
        rows: [['תחתית / ראש (לפי התוכניות)', `${coords.fmtH(H(w.bottomRel))} / ${coords.fmtH(H(w.topRel))}`], ['סטטוס', 'ממתין לאישור קונסטרוקטור']],
        note: c.description, source: c.source,
      });
      scene.add(g); n++;
      // 2) the cantilever beam proposed in its place: catches the beam(s) that framed into the wall
      for (const fb of (w.framedBy || []).slice(0, 1)) {
        const m = prism(w.footprintITM, fb.bottomRel, fb.topRel, materials.get('concrete')); m.castShadow = m.receiveShadow = true;
        const bg = new THREE.Group(); bg.add(m);
        bg.add(new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry, 30), new THREE.LineBasicMaterial({ color: D.ownerChangeColor })));
        bg.add(label(`${c.id} · קורת זיז מוצעת – תופסת את ${fb.id} (חתך לקביעה)`, cE, cN, H(fb.topRel) + D.labelLift_m, 'lbl change'));
        registry.add(bg, { floor: 'ground', system: 'structure', stage: 'ceiling', layer: 'groundCeilingBeams' }, {
          id: `${c.id}-cantilever`, name: `קורת זיז מוצעת (${c.id}) – תופסת את ${fb.id}`, status: 'provisional', variant: { change: c.id, show: 'changed' },
          rows: [['תוואי', 'לאורך הקיר המבוטל, מפינת הבית'], ['עליון / תחתון (זמני)', `${coords.fmtH(H(fb.topRel))} / ${coords.fmtH(H(fb.bottomRel))} – כמו ${fb.id}`],
            ['רוחב (זמני)', `${Math.round(w.thickness_m * 100)} ס"מ – כמו הקיר המבוטל`], ['סטטוס', 'הצעה – שאלה לקונסטרוקטור (חתך, ברזל, עיגון)']],
          note: `${c.title}. ${c.approvals?.[0]?.what || ''}`, source: c.source,
        });
        scene.add(bg); n++;
      }
      // 3) roof beams that rested on the wall: their end loses its support – question
      for (const rb of w.carriesRoof || []) {
        const [E, N] = rb.endITM; const qg = new THREE.Group();
        const s = new THREE.Mesh(new THREE.SphereGeometry(display.proposals.questionMarker_m, 16, 12), new THREE.MeshBasicMaterial({ color: D.ownerChangeRemovedColor }));
        s.position.copy(coords.toLocal(E, N, H(rb.bottomRel))); qg.add(s);
        qg.add(label(`? ${rb.id}: הקצה נשען על הקיר המבוטל – מה התמיכה? (שאלה לקונסטרוקטור)`, E, N, H(rb.topRel) + D.labelLift_m, 'lbl removed-q'));
        registry.add(qg, { floor: 'roof', system: 'structure', stage: 'ceiling', layer: 'ownerChanges', step: 'roofWalls' }, {
          id: `${c.id}-${rb.id}`, name: `שאלה (${c.id}): תמיכת הקצה של ${rb.id}`, status: 'provisional', variant: { change: c.id, show: 'changed' },
          rows: [['קורה', `${rb.id} (O.K ${coords.fmtH(H(rb.topRel))})`], ['נשענה על', `${w.displayName || w.id} – מבוטל בהצעה`]],
          note: `בהצעה ${c.id} הקיר מבוטל ו-${rb.id} נשארת בלי תמיכה בקצה הזה. נדרשת החלטת קונסטרוקטור (זיז נוסף בגג / עמוד / שינוי הקורה).`, source: c.source,
        });
        scene.add(qg); n++;
      }
    }
  }
  return { count: n };
}
