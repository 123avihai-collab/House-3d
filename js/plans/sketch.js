// Explanatory sketches for the element card (inline SVG strings).
// Every size comes from the element record (data/plans/k400.json); the only constants here are
// drawing constants (canvas size, exaggeration) taken from the `D` display object passed in.

const f2 = (v) => (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(2);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// rebar row → role (colour + plain name)
export function role(desc) {
  if (/לוליני/.test(desc)) return 'tie';
  if (/חישוק/.test(desc)) return 'tie';
  if (/טבע/.test(desc)) return 'ring';
  if (/קוצ/.test(desc)) return 'start';
  if (/ב\.ע|עליון/.test(desc)) return 'top';
  if (/אמצע/.test(desc)) return 'ring';
  return 'long';
}
export const ROLE_VAR = { long: '--steel-long', top: '--steel-top', tie: '--steel-tie', ring: '--steel-ring', start: '--steel-start' };
export const col = (r) => `var(${ROLE_VAR[r]})`;

/* ---------- pile: side view (elevation) ---------- */
export function pileElevation(p, det, beam, H0) {
  const W = 200, Hh = 330, top = 46, bot = 34;
  const L = p.length_m, D = p.diameter_m;
  const ky = (Hh - top - bot) / L;                 // px per metre (vertical)
  const kx = Math.min(70 / D, ky * 6);             // horizontal exaggeration (stated in the caption)
  const cx = 92, w = D * kx, x0 = cx - w / 2;
  const y0 = top, y1 = top + L * ky;
  const cov = det.cover_m.value * kx;
  const parts = [];
  // soil hatch
  parts.push(`<rect x="${x0 - 22}" y="${y0}" width="${w + 44}" height="${y1 - y0 + 8}" fill="var(--soil)" opacity=".35"/>`);
  // beam on top
  if (beam) {
    const bh = Math.min(beam.depth_m * ky * 2.2, 40);
    parts.push(`<rect x="${x0 - 34}" y="${y0 - bh}" width="${w + 68}" height="${bh}" fill="var(--concrete)" stroke="var(--concrete-edge)"/>`,
      `<text x="${cx}" y="${y0 - bh / 2 + 4}" text-anchor="middle" font-size="10">קורה ${esc(beam.id)}</text>`);
  }
  // concrete shaft
  parts.push(`<rect x="${x0}" y="${y0}" width="${w}" height="${y1 - y0}" fill="var(--concrete)" stroke="var(--concrete-edge)"/>`);
  // spiral: dense zone + rest (zig-zag, one stroke every pitch × visual factor)
  const dz = Math.min(det.denseZone_m.value, L);
  const zig = (ya, yb, pitch) => {
    const step = Math.max(pitch * ky, 3.2);
    let d = `M${x0 + cov},${ya}`; let s = 0;
    for (let y = ya; y < yb; y += step / 2) { s ^= 1; d += ` L${s ? x0 + w - cov : x0 + cov},${Math.min(y + step / 2, yb)}`; }
    return `<path d="${d}" fill="none" stroke="${col('tie')}" stroke-width="1"/>`;
  };
  parts.push(zig(y0 + 2, y0 + dz * ky, det.spiral.pitchDense_m), zig(y0 + dz * ky, y1 - 2, det.spiral.pitch_m));
  // longitudinal bars (two visible lines)
  for (const x of [x0 + cov, x0 + w - cov]) parts.push(`<line x1="${x}" y1="${y0 - (beam ? 10 : 0)}" x2="${x}" y2="${y1 - 3}" stroke="${col('long')}" stroke-width="2.4"/>`);
  // rings
  for (let z = 0; z <= L + 1e-6; z += det.ring.spacing_m) {
    const y = y0 + z * ky;
    parts.push(`<line x1="${x0 + cov - 2}" y1="${y}" x2="${x0 + w - cov + 2}" y2="${y}" stroke="${col('ring')}" stroke-width="3"/>`);
  }
  // starters (when the pile joins a beam / wall)
  if (p.rebar.some((r) => role(r.desc) === 'start')) {
    for (const x of [cx - w * 0.15, cx + w * 0.15]) parts.push(`<line x1="${x}" y1="${y0 + 20}" x2="${x}" y2="${y0 - 34}" stroke="${col('start')}" stroke-width="2"/>`);
  }
  // dimensions (right side in RTL reading = drawn at the left of the shaft for clarity)
  const dx = x0 + w + 30;
  parts.push(`<line x1="${dx}" y1="${y0}" x2="${dx}" y2="${y1}" stroke="var(--ink)" stroke-width="1"/>`,
    `<line x1="${dx - 4}" y1="${y0}" x2="${dx + 4}" y2="${y0}" stroke="var(--ink)"/><line x1="${dx - 4}" y1="${y1}" x2="${dx + 4}" y2="${y1}" stroke="var(--ink)"/>`,
    `<text x="${dx + 6}" y="${(y0 + y1) / 2}" font-size="12" class="n" transform="rotate(-90 ${dx + 6} ${(y0 + y1) / 2})" text-anchor="middle" dy="10">L = ${L.toFixed(2)} מ'</text>`,
    `<text x="${dx + 8}" y="${y0 + 4}" font-size="12" class="n">ראש ${f2(p.headRel)}</text>`,
    `<text x="${dx + 8}" y="${y0 + 17}" font-size="11" class="n" fill="var(--muted)" style="fill:var(--muted)">${(H0 + p.headRel).toFixed(2)}</text>`,
    `<text x="${dx + 8}" y="${y1 + 4}" font-size="12" class="n">תחתית ${f2(p.tipRel)}</text>`,
    `<text x="${dx + 8}" y="${y1 + 17}" font-size="11" class="n" style="fill:var(--muted)">${(H0 + p.tipRel).toFixed(2)}</text>`,
    `<text x="${cx}" y="${y1 + 22}" text-anchor="middle" font-size="11" class="n">ø${Math.round(D * 100)}</text>`);
  // dense-zone bracket
  parts.push(`<line x1="${x0 - 12}" y1="${y0}" x2="${x0 - 12}" y2="${y0 + dz * ky}" stroke="${col('tie')}" stroke-width="1.5"/>`,
    `<text x="${x0 - 16}" y="${y0 + dz * ky / 2}" font-size="11" text-anchor="end" style="fill:${col('tie')}">צפוף</text>`);
  return `<svg viewBox="0 0 ${W} ${Hh}" role="img" aria-label="מבט צד של כלונס ${esc(p.id)}">${parts.join('')}</svg>`;
}

/* ---------- pile: cross section ---------- */
export function pileSection(p, det) {
  const S = 200, c = S / 2, R = 78;
  const k = R / (p.diameter_m / 2);
  const n = det.longBars[String(p.diameter_m)] || 0;
  const rc = R - det.cover_m.value * k;
  const parts = [`<circle cx="${c}" cy="${c}" r="${R}" fill="var(--concrete)" stroke="var(--concrete-edge)" stroke-width="1.5"/>`,
    `<circle cx="${c}" cy="${c}" r="${rc}" fill="none" stroke="${col('tie')}" stroke-width="2"/>`];
  const rb = rc - 5;
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2 - Math.PI / 2;
    parts.push(`<circle cx="${c + rb * Math.cos(a)}" cy="${c + rb * Math.sin(a)}" r="5" fill="${col('long')}"/>`);
  }
  parts.push(`<line x1="${c - R}" y1="${S - 10}" x2="${c + R}" y2="${S - 10}" stroke="var(--ink)"/>`,
    `<text x="${c}" y="${S - 14}" text-anchor="middle" font-size="12" class="n">ø${Math.round(p.diameter_m * 100)} ס"מ</text>`,
    `<text x="${c}" y="${c + 4}" text-anchor="middle" font-size="12">${n} מוטות</text>`,
    `<text x="${c}" y="${c + 18}" text-anchor="middle" font-size="10" style="fill:var(--muted)">כיסוי ${Math.round(det.cover_m.value * 1000) / 10} ס"מ</text>`);
  return `<svg viewBox="0 0 ${S} ${S}" role="img" aria-label="חתך רוחב של כלונס ${esc(p.id)}">${parts.join('')}</svg>`;
}

/* ---------- beam: cross section ---------- */
export function beamSection(b, cover) {
  const S = 210, pad = 30;
  const k = Math.min((S - 2 * pad) / b.width_m, (S - 2 * pad) / b.depth_m);
  const w = b.width_m * k, h = b.depth_m * k, x0 = (S - w) / 2, y0 = (S - h) / 2;
  const cv = Math.max(cover * k, 5);
  const count = (pos) => Math.max(0, ...b.bars.filter((x) => x.position === pos).map((x) => x.count));
  const nb = count('bottom'), nt = count('top');
  const parts = [`<rect x="${x0}" y="${y0}" width="${w}" height="${h}" fill="var(--concrete)" stroke="var(--concrete-edge)" stroke-width="1.5"/>`];
  const hasTie = b.rebar.some((r) => role(r.desc) === 'tie');
  if (hasTie) parts.push(`<rect x="${x0 + cv}" y="${y0 + cv}" width="${w - 2 * cv}" height="${h - 2 * cv}" rx="3" fill="none" stroke="${col('tie')}" stroke-width="2"/>`);
  const row = (n, y, c) => {
    for (let i = 0; i < n; i++) {
      const x = n === 1 ? x0 + w / 2 : x0 + cv + 6 + (i * (w - 2 * cv - 12)) / (n - 1);
      parts.push(`<circle cx="${x}" cy="${y}" r="5" fill="${c}"/>`);
    }
  };
  row(nt, y0 + cv + 6, col('top'));
  row(nb, y0 + h - cv - 6, col('long'));
  parts.push(`<line x1="${x0}" y1="${S - 10}" x2="${x0 + w}" y2="${S - 10}" stroke="var(--ink)"/>`,
    `<text x="${S / 2}" y="${S - 14}" text-anchor="middle" font-size="11" class="n">${Math.round(b.width_m * 100)}</text>`,
    `<line x1="${x0 - 12}" y1="${y0}" x2="${x0 - 12}" y2="${y0 + h}" stroke="var(--ink)"/>`,
    `<text x="${x0 - 16}" y="${y0 + h / 2}" font-size="11" class="n" text-anchor="middle" transform="rotate(-90 ${x0 - 16} ${y0 + h / 2})">${Math.round(b.depth_m * 100)}</text>`,
    `<text x="${S / 2}" y="${y0 - 6}" text-anchor="middle" font-size="10" class="n">O.K ${f2(b.topRel)}</text>`);
  if (!nb && !nt) parts.push(`<text x="${S / 2}" y="${S / 2}" text-anchor="middle" font-size="11">אין פריסת ברזל</text>`);
  return `<svg viewBox="0 0 ${S} ${S}" role="img" aria-label="חתך רוחב של קורה ${esc(b.id)}">${parts.join('')}</svg>`;
}

/* ---------- beam: side view with the piles under it ---------- */
export function beamElevation(b, pilesById, tieSpacing_m) {
  const W = 320, Hh = 150, pad = 22;
  const L = b.length_m;
  const kx = (W - 2 * pad) / L;
  const h = 34, y0 = 34, x0 = pad;
  const parts = [`<rect x="${x0}" y="${y0}" width="${L * kx}" height="${h}" fill="var(--concrete)" stroke="var(--concrete-edge)"/>`];
  if (tieSpacing_m) {
    const step = Math.max(tieSpacing_m * kx, 7);   // schematic: at most one stroke every 7 px
    for (let x = x0 + 3; x < x0 + L * kx - 2; x += step) parts.push(`<line x1="${x}" y1="${y0 + 3}" x2="${x}" y2="${y0 + h - 3}" stroke="${col('tie')}" stroke-width=".9"/>`);
  }
  if (b.bars.some((x) => x.position === 'top')) parts.push(`<line x1="${x0 + 2}" y1="${y0 + 5}" x2="${x0 + L * kx - 2}" y2="${y0 + 5}" stroke="${col('top')}" stroke-width="2.4"/>`);
  if (b.bars.some((x) => x.position === 'bottom')) parts.push(`<line x1="${x0 + 2}" y1="${y0 + h - 5}" x2="${x0 + L * kx - 2}" y2="${y0 + h - 5}" stroke="${col('long')}" stroke-width="2.4"/>`);
  for (const q of b.piles) {
    const p = pilesById[q.id]; if (!p) continue;
    const x = x0 + q.along_m * kx, pw = Math.max(p.diameter_m * kx, 8);
    parts.push(`<rect x="${x - pw / 2}" y="${y0 + h}" width="${pw}" height="${Hh - y0 - h - 22}" fill="var(--concrete)" stroke="var(--concrete-edge)" stroke-dasharray="3 2"/>`,
      `<text x="${x}" y="${Hh - 8}" text-anchor="middle" font-size="12" class="n">${esc(q.id)}</text>`);
  }
  parts.push(`<line x1="${x0}" y1="16" x2="${x0 + L * kx}" y2="16" stroke="var(--ink)"/>`,
    `<line x1="${x0}" y1="12" x2="${x0}" y2="20" stroke="var(--ink)"/><line x1="${x0 + L * kx}" y1="12" x2="${x0 + L * kx}" y2="20" stroke="var(--ink)"/>`,
    `<text x="${x0 + L * kx / 2}" y="12" text-anchor="middle" font-size="11" class="n">${L.toFixed(2)} מ'</text>`);
  return `<svg viewBox="0 0 ${W} ${Hh}" role="img" aria-label="מבט צד של קורה ${esc(b.id)}">${parts.join('')}</svg>`;
}
