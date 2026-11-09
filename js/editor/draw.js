// Canvas rendering of one floor: grid, architect background, structure, pipes (proposal + consultant), nodes, snap marker.

function path(ctx, v, P, close) {
  ctx.moveTo(v.sx(P[0][0]), v.sy(P[0][1]));
  for (let i = 1; i < P.length; i++) ctx.lineTo(v.sx(P[i][0]), v.sy(P[i][1]));
  if (close) ctx.closePath();
}

export function drawGrid(ctx, v, cfg) {
  const g = cfg.grid, [x0, y1] = v.toLocal(0, 0), [x1, y0] = v.toLocal(v.w, v.h);
  for (const [step, col] of [[g.minor_m, g.minor], [g.major_m, g.majorColor]]) {
    if (step * v.k < g.minPx) continue;
    ctx.beginPath(); ctx.strokeStyle = col; ctx.lineWidth = 1;
    for (let x = Math.ceil(x0 / step) * step; x <= x1; x += step) { const s = Math.round(v.sx(x)) + 0.5; ctx.moveTo(s, 0); ctx.lineTo(s, v.h); }
    for (let y = Math.ceil(y0 / step) * step; y <= y1; y += step) { const s = Math.round(v.sy(y)) + 0.5; ctx.moveTo(0, s); ctx.lineTo(v.w, s); }
    ctx.stroke();
  }
}

export function drawBackground(ctx, v, cfg, B, on) {
  for (const [g, st] of Object.entries(cfg.background)) {
    if (!on('bg.' + g) || g === 'texts' || !B[g]) continue;
    ctx.beginPath(); ctx.strokeStyle = st.color; ctx.lineWidth = st.width_px;
    for (const P of B[g]) path(ctx, v, P, false);
    ctx.stroke();
  }
  if (on('bg.texts') && v.k > 25) {
    const st = cfg.background.texts; ctx.fillStyle = st.color; ctx.font = `${st.font_px}px system-ui, sans-serif`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    for (const t of B.texts) for (const [i, line] of t.t.split('\n').entries()) ctx.fillText(line, v.sx(t.xy[0]), v.sy(t.xy[1]) + i * (st.font_px + 1));
  }
}

export function drawStructure(ctx, v, cfg, S, on) {
  for (const [k, st] of Object.entries(cfg.structure)) {
    if (!on('st.' + k) || !S[k]) continue;
    ctx.save(); if (st.dash) ctx.setLineDash(st.dash);
    for (const e of S[k]) {
      ctx.beginPath(); path(ctx, v, e.poly, !e.line); for (const h of e.holes || []) path(ctx, v, h, true);
      if (st.fill && !e.line) { ctx.fillStyle = st.fill; ctx.fill('evenodd'); }
      ctx.strokeStyle = e.status === 'provisional' ? '#d08a00' : st.stroke; ctx.lineWidth = st.width_px; ctx.stroke();
    }
    ctx.restore();
  }
}

export function drawPipes(ctx, v, cfg, items, sys, sel, hover, errIds, focus) {
  const sc = cfg.systems;
  // consultant first (under), then proposal
  for (const pass of ['cons', 'prop']) for (const it of items) {
    const p = it.p; if (p.layer !== pass) continue;
    const col = (sys[p.system] || { color: '#888' }).color, chosen = sel === p, hov = hover === p;
    ctx.save();
    ctx.globalAlpha = p.layer === 'cons' ? (p.superseded ? sc.supersededAlpha : sc.consultantAlpha) : 1;
    const inFocus = focus && p.layer === 'prop' && focus.has(p.id); if (focus && !inFocus) ctx.globalAlpha *= cfg.manifold.dimAlpha;
    ctx.strokeStyle = col; ctx.fillStyle = col; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.lineWidth = chosen ? sc.selectedWidth_px : inFocus ? cfg.manifold.focusWidth_px : (p.layer === 'cons' ? sc.consultantWidth_px : sc.width_px) + (hov ? 1.5 : 0);
    if (it.mode === 'plan' && p.pts.length > 1) {
      if (p.layer === 'cons' && p.superseded) ctx.setLineDash([4, 4]);
      ctx.beginPath(); path(ctx, v, p.pts, false); ctx.stroke(); ctx.setLineDash([]);
      if (errIds && p.layer === 'prop' && errIds.has(p.id)) { ctx.save(); ctx.globalAlpha = 0.9 * (focus && !inFocus ? cfg.manifold.dimAlpha : 1); ctx.strokeStyle = cfg.checks.colors.error; ctx.lineWidth = ctx.lineWidth + 2.5; ctx.setLineDash([]); ctx.beginPath(); path(ctx, v, p.pts, false); ctx.stroke(); ctx.restore(); }
      if (p.manual) { ctx.save(); ctx.globalAlpha = 0.25; ctx.lineWidth = ctx.lineWidth + 5; ctx.strokeStyle = '#8e24aa'; ctx.beginPath(); path(ctx, v, p.pts, false); ctx.stroke(); ctx.restore(); }
      if (p.layer === 'prop' && (cfg.edit.gravitySystems || []).includes(p.system)) drawArrows(ctx, v, cfg, p.pts);
      if (chosen) for (const q of p.pts) { ctx.beginPath(); ctx.arc(v.sx(q[0]), v.sy(q[1]), 3.2, 0, 7); ctx.fillStyle = '#fff'; ctx.fill(); ctx.lineWidth = 1.5; ctx.stroke(); }
    }
    // vertical pieces: ring = passes through this floor, filled = starts / ends here
    const R = sc.verticalMarker_px + (chosen ? 1.5 : 0);
    const verts = it.mode === 'plan' ? p.verticals : p.verticals.filter(q => q.lo < it.band[1] && q.hi > it.band[0]);
    for (const q of verts) { ctx.beginPath(); ctx.arc(v.sx(q.xy[0]), v.sy(q.xy[1]), R, 0, 7); ctx.globalAlpha *= 1; ctx.fillStyle = '#fff'; ctx.fill(); ctx.lineWidth = 2; ctx.stroke(); ctx.beginPath(); ctx.arc(v.sx(q.xy[0]), v.sy(q.xy[1]), R * 0.45, 0, 7); ctx.fillStyle = col; ctx.fill(); }
    if (it.mode === 'pass' && !p.verticals.length && p.pts.length) { const q = p.pts[0]; ctx.beginPath(); ctx.arc(v.sx(q[0]), v.sy(q[1]), R, 0, 7); ctx.lineWidth = 2; ctx.stroke(); }
    ctx.restore();
  }
}

export function drawNodes(ctx, v, cfg, nodes, sel, hover) {
  const c = cfg.nodes; ctx.save(); ctx.font = `${c.font_px}px system-ui, sans-serif`; ctx.textAlign = 'center'; ctx.textBaseline = 'top';
  for (const n of nodes) {
    const x = v.sx(n.xy[0]), y = v.sy(n.xy[1]), on = sel === n || hover === n;
    if (n.kind === 'manifold' && n.outletsXY) { drawManifold(ctx, v, cfg, n, on); continue; }
    ctx.beginPath();
    if (n.kind === 'manifold') { const s = c.manifoldSize_px; ctx.rect(x - s / 2, y - s / 2, s, s); }
    else ctx.arc(x, y, c.radius_px + (on ? 1.5 : 0), 0, 7);
    ctx.fillStyle = n.kind === 'manifold' ? '#1d2329' : '#fff'; ctx.fill(); ctx.strokeStyle = c.color; ctx.lineWidth = on ? 2.2 : 1.3; ctx.stroke();
    if (v.k > 45) { ctx.fillStyle = c.color; ctx.fillText(n.id.split('@')[0], x, y + c.radius_px + 2); }
  }
  ctx.restore();
}

export function drawSnap(ctx, v, s) {
  if (!s) return; const x = v.sx(s.x), y = v.sy(s.y); ctx.save(); ctx.strokeStyle = s.kind === 'grid' ? '#888' : '#e0661b'; ctx.lineWidth = 1.6;
  ctx.beginPath();
  if (s.kind === 'vertex' || s.kind === 'node') ctx.rect(x - 5, y - 5, 10, 10);
  else if (s.kind === 'edge') { ctx.moveTo(x - 6, y + 6); ctx.lineTo(x + 6, y - 6); ctx.moveTo(x - 6, y - 6); ctx.lineTo(x + 6, y + 6); }
  else { ctx.moveTo(x - 5, y); ctx.lineTo(x + 5, y); ctx.moveTo(x, y - 5); ctx.lineTo(x, y + 5); }
  ctx.stroke(); ctx.restore();
}

// flow direction (vertex order = downstream) on gravity lines
function drawArrows(ctx, v, cfg, P) {
  const a = cfg.edit.arrow_px;
  for (let i = 0; i + 1 < P.length; i++) {
    const x1 = v.sx(P[i][0]), y1 = v.sy(P[i][1]), x2 = v.sx(P[i + 1][0]), y2 = v.sy(P[i + 1][1]), L = Math.hypot(x2 - x1, y2 - y1);
    if (L < cfg.edit.arrowMinSeg_px) continue;
    const ux = (x2 - x1) / L, uy = (y2 - y1) / L, mx = (x1 + x2) / 2 + ux * a / 2, my = (y1 + y2) / 2 + uy * a / 2;
    ctx.beginPath(); ctx.moveTo(mx, my); ctx.lineTo(mx - ux * a - uy * a * 0.55, my - uy * a + ux * a * 0.55); ctx.lineTo(mx - ux * a + uy * a * 0.55, my - uy * a - ux * a * 0.55); ctx.closePath(); ctx.fill();
  }
}

// editing handles of the selected run: stations (square; filled = riser), selected station / segment highlighted
export function drawHandles(ctx, v, cfg, S, selV, selSeg, color) {
  const h = cfg.edit.handle_px; ctx.save();
  if (selSeg != null && S[selSeg + 1]) { ctx.strokeStyle = '#ff6f00'; ctx.lineWidth = 6; ctx.globalAlpha = 0.5; ctx.beginPath(); ctx.moveTo(v.sx(S[selSeg].x), v.sy(S[selSeg].y)); ctx.lineTo(v.sx(S[selSeg + 1].x), v.sy(S[selSeg + 1].y)); ctx.stroke(); ctx.globalAlpha = 1; }
  S.forEach((q, i) => {
    const x = v.sx(q.x), y = v.sy(q.y), on = i === selV, end = i === 0 || i === S.length - 1;
    ctx.beginPath(); ctx.rect(x - h - (on ? 1.5 : 0), y - h - (on ? 1.5 : 0), 2 * h + (on ? 3 : 0), 2 * h + (on ? 3 : 0));
    ctx.fillStyle = on ? '#ff6f00' : q.H.length > 1 ? color : '#fff'; ctx.fill(); ctx.lineWidth = end ? 2.2 : 1.4; ctx.strokeStyle = '#1d2329'; ctx.stroke();
  });
  ctx.restore();
}

export function drawDraft(ctx, v, pts, cursor, color) {
  if (!pts.length) return; ctx.save(); ctx.strokeStyle = color; ctx.lineWidth = 2.6; ctx.setLineDash([7, 4]);
  ctx.beginPath(); ctx.moveTo(v.sx(pts[0][0]), v.sy(pts[0][1])); for (const q of pts.slice(1)) ctx.lineTo(v.sx(q[0]), v.sy(q[1])); if (cursor) ctx.lineTo(v.sx(cursor[0]), v.sy(cursor[1])); ctx.stroke();
  ctx.setLineDash([]); ctx.fillStyle = color; for (const q of pts) { ctx.beginPath(); ctx.arc(v.sx(q[0]), v.sy(q[1]), 3.5, 0, 7); ctx.fill(); }
  if (cursor && pts.length) { const a = pts[pts.length - 1], L = Math.hypot(cursor[0] - a[0], cursor[1] - a[1]); ctx.font = '11px system-ui'; ctx.fillStyle = '#1d2329'; ctx.fillText(`${L.toFixed(2)} מ'`, v.sx(cursor[0]) + 10, v.sy(cursor[1]) - 8); }
  ctx.restore();
}

// check markers: ⛔ error / ⚠ warning / ℹ info at the place of the finding
export function drawIssues(ctx, v, cfg, list, flash) {
  const C = cfg.checks, r = C.marker_px; ctx.save();
  for (const i of list) {
    const x = v.sx(i.at[0]), y = v.sy(i.at[1]); ctx.fillStyle = C.colors[i.sev]; ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5;
    ctx.beginPath();
    if (i.sev === 'error') { ctx.arc(x, y, r, 0, 7); } else { ctx.moveTo(x, y - r - 1); ctx.lineTo(x + r, y + r - 1); ctx.lineTo(x - r, y + r - 1); ctx.closePath(); }
    ctx.fill(); ctx.stroke(); ctx.fillStyle = '#fff'; ctx.font = `bold ${r + 3}px system-ui`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(i.sev === 'error' ? '!' : i.sev === 'warn' ? '!' : 'i', x, y + (i.sev === 'error' ? 0.5 : 1));
  }
  if (flash) { const x = v.sx(flash.at[0]), y = v.sy(flash.at[1]); ctx.strokeStyle = '#ff6f00'; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(x, y, 18, 0, 7); ctx.stroke(); }
  ctx.restore();
}

// Manifold body: in plan the cold and hot outlets are at the same place (one above the other), so on screen the cold row
// is drawn on one side of the axis and the hot row on the other; a frame around both, a valve per outlet, name + counts.
// Returns the screen position of every outlet (for the numbers), keyed "cold:i" / "hot:i".
export function manifoldScreen(v, cfg, n) {
  const g = cfg.manifold.barGap_px, all = [...(n.outletsXY.cold || []), ...(n.outletsXY.hot || [])].map(o => [v.sx(o.xy[0]), v.sy(o.xy[1])]);
  let ax = [1, 0];
  if (all.length > 1) { const a = all[0], b = all[all.length - 1]; const L = Math.hypot(b[0] - a[0], b[1] - a[1]); if (L > 1e-6) ax = [(b[0] - a[0]) / L, (b[1] - a[1]) / L]; }
  const nm = [-ax[1], ax[0]], pos = {};
  for (const [k, sgn] of [['cold', -1], ['hot', 1]]) (n.outletsXY[k] || []).forEach((o, i) => { pos[`${k}:${i}`] = [v.sx(o.xy[0]) + nm[0] * g * sgn, v.sy(o.xy[1]) + nm[1] * g * sgn]; });
  return { pos, ax, nm };
}
function drawManifold(ctx, v, cfg, n, on) {
  const C = cfg.manifold, { pos, ax, nm } = manifoldScreen(v, cfg, n), pts = Object.values(pos); if (!pts.length) return;
  // frame: along the axis over all outlets, across over both rows
  const cx = pts.reduce((s, p) => s + p[0], 0) / pts.length, cy = pts.reduce((s, p) => s + p[1], 0) / pts.length;
  const along = pts.map(p => (p[0] - cx) * ax[0] + (p[1] - cy) * ax[1]), across = pts.map(p => (p[0] - cx) * nm[0] + (p[1] - cy) * nm[1]);
  const a0 = Math.min(...along) - C.bodyPad_px, a1 = Math.max(...along) + C.bodyPad_px, c0 = Math.min(...across) - C.bodyPad_px, c1 = Math.max(...across) + C.bodyPad_px;
  const P = (a, c) => [cx + ax[0] * a + nm[0] * c, cy + ax[1] * a + nm[1] * c];
  ctx.save();
  ctx.beginPath(); [P(a0, c0), P(a1, c0), P(a1, c1), P(a0, c1)].forEach((q, i) => i ? ctx.lineTo(...q) : ctx.moveTo(...q)); ctx.closePath();
  ctx.fillStyle = on ? 'rgba(255,193,7,0.35)' : 'rgba(255,255,255,0.85)'; ctx.fill(); ctx.strokeStyle = '#1d2329'; ctx.lineWidth = on ? 2.4 : 1.4; ctx.stroke();
  for (const [k, col] of [['cold', '#1f6fd1'], ['hot', '#cf3a2c']]) {
    const row = (n.outletsXY[k] || []).map((_, i) => pos[`${k}:${i}`]); if (!row.length) continue;
    ctx.strokeStyle = col; ctx.lineWidth = 2.6; ctx.beginPath(); ctx.moveTo(...row[0]); ctx.lineTo(...row[row.length - 1]); ctx.stroke();
    ctx.fillStyle = '#fff'; for (const q of row) { ctx.beginPath(); ctx.arc(q[0], q[1], C.valve_px, 0, 7); ctx.fill(); ctx.lineWidth = 1.2; ctx.stroke(); }
  }
  const nc = (n.outlets.cold || []).length, nh = (n.outlets.hot || []).length, e0 = P(a0, 0), e1 = P(a1, 0), up = e0[1] < e1[1] ? e0 : e1, top = [up[0], up[1] - 6];   // beyond the upper end, clear of the outlet numbers
  ctx.font = `600 ${C.labelFont_px}px system-ui, sans-serif`; ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
  const t = `${n.id.split('@')[0]} · ${nc} קרים · ${nh} חמים`, w = ctx.measureText(t).width;
  ctx.fillStyle = 'rgba(255,255,255,0.9)'; ctx.fillRect(top[0] - w / 2 - 3, top[1] - C.labelFont_px - 3, w + 6, C.labelFont_px + 4);
  ctx.fillStyle = '#1d2329'; ctx.fillText(t, top[0], top[1]);
  ctx.restore();
}

// numbered badges (manifold focus): {xy (screen), text, color}
export function drawBadges(ctx, cfg, list) {
  const r = cfg.manifold.badge_px; ctx.save(); ctx.font = `bold ${r + 1}px system-ui, sans-serif`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  for (const b of list) { ctx.beginPath(); ctx.arc(b.xy[0], b.xy[1], r, 0, 7); ctx.fillStyle = b.color; ctx.fill(); ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5; ctx.stroke(); ctx.fillStyle = '#fff'; ctx.fillText(b.text, b.xy[0], b.xy[1] + 0.5); }
  ctx.restore();
}

// consultant points (and site points of the proposal): a symbol per group, name = id + Hebrew kind; infrastructure
// groups (utility, pumping, rain, pool) are labelled from a far zoom, the rest when zoomed in
export function drawPoints(ctx, v, cfg, list, sel, hover, showLabels) {
  const P = cfg.points, r = P.radius_px; ctx.save(); ctx.font = `${P.labelFont_px}px system-ui, sans-serif`; ctx.textAlign = 'center'; ctx.textBaseline = 'top';
  for (const n of list) {
    const [g, kname] = P.kinds[n.kind] || ['water', n.kind], G = P.groups[g] || { color: '#555' }, x = v.sx(n.xy[0]), y = v.sy(n.xy[1]), on = sel === n || hover === n;
    const R = r + (on ? 2 : 0) + (g === 'utility' ? 1.5 : 0);
    ctx.beginPath();
    if (g === 'utility' || g === 'pump') ctx.rect(x - R, y - R, 2 * R, 2 * R);
    else if (g === 'rain' || g === 'pool') { ctx.moveTo(x, y - R - 1); ctx.lineTo(x + R + 1, y); ctx.lineTo(x, y + R + 1); ctx.lineTo(x - R - 1, y); ctx.closePath(); }
    else ctx.arc(x, y, R, 0, 7);
    ctx.fillStyle = g === 'sewage' || g === 'utility' ? G.color : '#fff'; ctx.fill(); ctx.strokeStyle = G.color; ctx.lineWidth = on ? 2.4 : 1.5; ctx.stroke();
    if (n.kind === 'sewerChamber' || n.kind === 'municipalManhole') { ctx.beginPath(); ctx.arc(x, y, R * 0.45, 0, 7); ctx.fillStyle = '#fff'; ctx.fill(); }
    const always = P.alwaysLabel.includes(g) || n.floor === 'site';
    if (showLabels && (on || v.k >= (always ? P.siteLabelMinK : P.labelMinK))) {
      const t1 = n.id.split('@')[0], t2 = kname, w = Math.max(ctx.measureText(t1).width, ctx.measureText(t2).width) + 6;
      ctx.fillStyle = 'rgba(255,255,255,0.88)'; ctx.fillRect(x - w / 2, y + R + 2, w, P.labelFont_px * 2 + 4);
      ctx.fillStyle = G.color; ctx.font = `600 ${P.labelFont_px}px system-ui, sans-serif`; ctx.fillText(t1, x, y + R + 3);
      ctx.font = `${P.labelFont_px}px system-ui, sans-serif`; ctx.fillStyle = '#333'; ctx.fillText(t2, x, y + R + 4 + P.labelFont_px);
    }
  }
  ctx.restore();
}
