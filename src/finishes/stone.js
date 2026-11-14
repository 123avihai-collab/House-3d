import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

// Stone cladding on the street side of the front wall (data/finishes/cladding/stone.json + the claddingStone surfaces of
// data/finishes/cladding/surfaces.json). Tiles laid in courses from the top of the wall down (running bond), the lowest
// course cut along the street surface at the wall face (ground 'env' – the front street); coping stones on the wall top.
// Every size comes from the data file; nothing is written here.
export function buildStoneCladding(F, items) {
  const { ctx } = F, { coords, data, ground, materials } = ctx, S = data.claddingStone, st = S.stone, tile = st.tile, cp = st.coping, J = st.joint_m;
  const H0 = coords.H0, X = (E) => E - coords.E0, Z = (N) => -(N - coords.N0);
  const pv = data.perimeter?.walls || [];
  const tex = materials.get('curb');   // concrete_floor_01 – sawn grey stone look (stone.json display)
  const mk = (tint) => { const m = tex.clone(); m.map = null; m.color.set(tint);   // relief (normal / roughness / AO) of the texture, colour from stone.json
    m.vertexColors = true; m.side = THREE.FrontSide; return m; };
  const tileMat = mk(S.display.tint), copMat = mk(S.display.copingTint);
  // deterministic per-stone shade
  const shade = (i) => { const x = Math.sin(i * 12.9898 + 78.233) * 43758.5453; return 1 + (x - Math.floor(x) - 0.5) * 2 * S.display.variation; };
  // prism from a quad in the wall plane (u along a->b, z up) pushed out by depth along the normal
  const quad = (a, ux, uy, nx, ny, u0, u1, zb0, zb1, zt, d0, d1, c) => {
    const P = (u, z, d) => [X(a[0] + ux * u + nx * d), z - H0, Z(a[1] + uy * u + ny * d)];
    const f = [P(u0, zb0, d1), P(u1, zb1, d1), P(u1, zt, d1), P(u0, zt, d1)], b = [P(u0, zb0, d0), P(u1, zb1, d0), P(u1, zt, d0), P(u0, zt, d0)];
    const faces = [[f[0], f[1], f[2], f[3]], [b[1], b[0], b[3], b[2]], [f[3], f[2], b[2], b[3]], [b[0], b[1], f[1], f[0]], [b[0], f[0], f[3], b[3]], [f[1], b[1], b[2], f[2]]];
    const pos = [], uv = [], col = [];
    for (const q of faces) {
      const e1 = new THREE.Vector3(...q[1]).sub(new THREE.Vector3(...q[0])), e2 = new THREE.Vector3(...q[3]).sub(new THREE.Vector3(...q[0]));
      const L1 = e1.length(), L2 = e2.length();
      const tri = [[q[0], 0, 0], [q[1], L1, 0], [q[2], L1, L2], [q[0], 0, 0], [q[2], L1, L2], [q[3], 0, L2]];
      for (const [p, s, t] of tri) { pos.push(...p); uv.push(s + u0, t + zb0); col.push(c, c, c); }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
    g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3)); g.computeVertexNormals(); return g;
  };
  const tiles = [], cops = [], rows = []; let area = 0, nTiles = 0, nCop = 0, k = 0;
  for (const it of items) {
    const w = pv.find(x => x.id === it.owner);
    const top = H0 + (w ? w.topRel : it.z1);
    const a = it.a, b = it.b, L = Math.hypot(b[0] - a[0], b[1] - a[1]), ux = (b[0] - a[0]) / L, uy = (b[1] - a[1]) / L, [nx, ny] = it.normal;
    const zc = top - cp.thickness_m;   // the stone courses end under the coping
    const gAt = (u) => ground.heightAt(a[0] + ux * u + nx * 0.05, a[1] + uy * u + ny * 0.05, 'env');
    let lo = Infinity; for (let u = 0; u <= L + 1e-6; u += 0.1) lo = Math.min(lo, gAt(Math.min(u, L)));
    let face = 0;
    for (let r = 0, zt = zc; zt > lo + 0.005; r++, zt -= tile.height_m + J) {
      const zb = zt - tile.height_m, off = st.bond === 'half' && r % 2 ? tile.length_m / 2 : 0;
      for (let u0 = -off; u0 < L - 1e-6; u0 += tile.length_m + J) {
        const s0 = Math.max(0, u0), s1 = Math.min(L, u0 + tile.length_m); if (s1 - s0 < 0.005) continue;
        const g0 = gAt(s0), g1 = gAt(s1), b0 = Math.max(zb, g0), b1 = Math.max(zb, g1);
        if (zt - b0 < 0.005 && zt - b1 < 0.005) continue;
        tiles.push(quad(a, ux, uy, nx, ny, s0, s1, Math.min(b0, zt), Math.min(b1, zt), zt, 0, tile.thickness_m, shade(k++)));
        face += (s1 - s0) * (zt - (b0 + b1) / 2); nTiles++;
      }
    }
    // coping on the wall top (along the wall, the street edge at the stone face)
    const depth = cp.width_m;
    for (let u0 = 0; u0 < L - 1e-6; u0 += cp.length_m + J) {
      const u1 = Math.min(L, u0 + cp.length_m);
      cops.push(quad(a, ux, uy, nx, ny, u0, u1, zc, zc, top, tile.thickness_m - depth, tile.thickness_m, shade(k++))); nCop++;
    }
    area += face;
    rows.push([it.owner, `${L.toFixed(2)} מ' · ראש ${coords.fmtH(top)} · תחתית (רחוב) ${coords.fmtH(lo)} · ${face.toFixed(2)} מ"ר`]);
  }
  const meta = (name, extra) => ({ name, kind: 'cladding', id: 'claddingStone', provisional: false, source: st.source,
    rows: [['אבן', `${st.name} (${S.choiceSource})`], ['אריח', `${tile.label} ס"מ · מק"ט ${tile.sku} · ${tile.maker}`], ['קופינג', `${cp.name} ${cp.label} · מק"ט ${cp.sku}`],
      ['פוגה', st.jointNote], ['הנחה', st.bondSource], ['גובה', S.height.decision], ['פרט השכונה', S.height.ruleSource], ...extra],
    note: `${S.approval}. ${S.backing.note}. קופינג: ${S.copingPlacement.rule} (זמני).` });
  const out = [];
  if (tiles.length) { const m = new THREE.Mesh(mergeGeometries(tiles), tileMat); m.castShadow = m.receiveShadow = true;
    out.push([m, meta('חיפוי אבן באר שבע אפור – חומה לרחוב', [['שטח חיפוי', `${area.toFixed(2)} מ"ר`], ['אריחים', `${nTiles} (כולל חתוכים)`], ...rows])]); }
  if (cops.length) { const m = new THREE.Mesh(mergeGeometries(cops), copMat); m.castShadow = m.receiveShadow = true;
    out.push([m, meta('קופינג באר שבע אפור 30/50/4.5 – ראש החומה לרחוב', [['אבני קופינג', `${nCop}`], ...rows])]); }
  return out;
}
