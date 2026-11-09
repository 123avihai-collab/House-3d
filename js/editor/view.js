// Plan-view geometry: ITM (E, N) <-> house frame (x along ux, y along uy, metres from frame.origin) <-> screen pixels.
// The plan is drawn in the house axes (data/plumbing/routes.json frame), so walls are horizontal / vertical on screen.

export class Frame {
  constructor(f) { this.o = f.origin; this.ux = f.ux; this.uy = f.uy; }
  toLocal(E, N) { const dx = E - this.o[0], dy = N - this.o[1]; return [dx * this.ux[0] + dy * this.ux[1], dx * this.uy[0] + dy * this.uy[1]]; }
  toITM(x, y) { return [this.o[0] + x * this.ux[0] + y * this.uy[0], this.o[1] + x * this.ux[1] + y * this.uy[1]]; }
  // screen angle (radians, 0 = up, clockwise) of the grid-north direction in this frame
  gridNorthAngle() { const [x, y] = [this.ux[1], this.uy[1]]; return Math.atan2(x, y); }
}

export class View {
  constructor(canvas, cfg) {
    this.c = canvas; this.cfg = cfg; this.k = 40; this.cx = 0; this.cy = 0; this.dpr = 1; this.w = 1; this.h = 1;
  }
  resize() {
    const r = this.c.getBoundingClientRect(); this.dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.w = Math.max(1, r.width); this.h = Math.max(1, r.height);
    this.c.width = Math.round(this.w * this.dpr); this.c.height = Math.round(this.h * this.dpr);
  }
  // local metres -> CSS pixels
  sx(x) { return this.w / 2 + (x - this.cx) * this.k; }
  sy(y) { return this.h / 2 - (y - this.cy) * this.k; }
  toLocal(px, py) { return [this.cx + (px - this.w / 2) / this.k, this.cy - (py - this.h / 2) / this.k]; }
  fit(b) {
    if (!b) return; const pad = this.cfg.zoom.fitPadding_px;
    const kx = (this.w - 2 * pad) / Math.max(0.5, b[2] - b[0]), ky = (this.h - 2 * pad) / Math.max(0.5, b[3] - b[1]);
    this.k = this.clampK(Math.min(kx, ky)); this.cx = (b[0] + b[2]) / 2; this.cy = (b[1] + b[3]) / 2;
  }
  clampK(k) { return Math.min(this.cfg.zoom.max_pxPerM, Math.max(this.cfg.zoom.min_pxPerM, k)); }
  zoomAt(px, py, f) {
    const [x, y] = this.toLocal(px, py); this.k = this.clampK(this.k * f);
    this.cx = x - (px - this.w / 2) / this.k; this.cy = y + (py - this.h / 2) / this.k;
  }
  pan(dx, dy) { this.cx -= dx / this.k; this.cy += dy / this.k; }
}

export function bboxOf(polys) {
  let b = null;
  for (const P of polys) for (const [x, y] of P) {
    if (!b) b = [x, y, x, y]; else { if (x < b[0]) b[0] = x; if (y < b[1]) b[1] = y; if (x > b[2]) b[2] = x; if (y > b[3]) b[3] = y; }
  }
  return b;
}
