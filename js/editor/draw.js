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

export function drawPipes(ctx, v, cfg, items, sys, sel, hover) {
  const sc = cfg.systems;
  // consultant first (under), then proposal
  for (const pass of ['cons', 'prop']) for (const it of items) {
    const p = it.p; if (p.layer !== pass) continue;
    const col = (sys[p.system] || { color: '#888' }).color, chosen = sel === p, hov = hover === p;
    ctx.save();
    ctx.globalAlpha = p.layer === 'cons' ? (p.superseded ? sc.supersededAlpha : sc.consultantAlpha) : 1;
    ctx.strokeStyle = col; ctx.fillStyle = col; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.lineWidth = chosen ? sc.selectedWidth_px : (p.layer === 'cons' ? sc.consultantWidth_px : sc.width_px) + (hov ? 1.5 : 0);
    if (it.mode === 'plan' && p.pts.length > 1) {
      if (p.layer === 'cons' && p.superseded) ctx.setLineDash([4, 4]);
      ctx.beginPath(); path(ctx, v, p.pts, false); ctx.stroke(); ctx.setLineDash([]);
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
