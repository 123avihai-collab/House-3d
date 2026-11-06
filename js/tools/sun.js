import * as THREE from 'three';

// Solar position (NOAA / Meeus simplified, accuracy ~0.01°) for the lot's real coordinates,
// local civil time in Asia/Jerusalem (DST handled by Intl). Azimuth from true north, clockwise.
export function solarPosition(dateUTC, latDeg, lonDeg) {
  const rad = Math.PI / 180;
  const jd = dateUTC.getTime() / 86400000 + 2440587.5;
  const T = (jd - 2451545.0) / 36525;
  const L0 = (280.46646 + T * (36000.76983 + T * 0.0003032)) % 360;
  const M = 357.52911 + T * (35999.05029 - 0.0001537 * T);
  const e = 0.016708634 - T * (0.000042037 + 0.0000001267 * T);
  const C = Math.sin(M * rad) * (1.914602 - T * (0.004817 + 0.000014 * T)) + Math.sin(2 * M * rad) * (0.019993 - 0.000101 * T) + Math.sin(3 * M * rad) * 0.000289;
  const trueLong = L0 + C;
  const omega = 125.04 - 1934.136 * T;
  const lambda = trueLong - 0.00569 - 0.00478 * Math.sin(omega * rad);
  const eps0 = 23 + (26 + (21.448 - T * (46.815 + T * (0.00059 - T * 0.001813))) / 60) / 60;
  const eps = eps0 + 0.00256 * Math.cos(omega * rad);
  const decl = Math.asin(Math.sin(eps * rad) * Math.sin(lambda * rad));
  const y = Math.tan(eps * rad / 2) ** 2;
  const eqTime = 4 / rad * (y * Math.sin(2 * L0 * rad) - 2 * e * Math.sin(M * rad) + 4 * e * y * Math.sin(M * rad) * Math.cos(2 * L0 * rad)
    - 0.5 * y * y * Math.sin(4 * L0 * rad) - 1.25 * e * e * Math.sin(2 * M * rad)); // minutes
  const utcMin = dateUTC.getUTCHours() * 60 + dateUTC.getUTCMinutes() + dateUTC.getUTCSeconds() / 60;
  const tst = (utcMin + eqTime + 4 * lonDeg + 1440) % 1440;
  const ha = (tst / 4 < 0 ? tst / 4 + 180 : tst / 4 - 180) * rad;
  const lat = latDeg * rad;
  const cosZen = Math.sin(lat) * Math.sin(decl) + Math.cos(lat) * Math.cos(decl) * Math.cos(ha);
  const zen = Math.acos(Math.max(-1, Math.min(1, cosZen)));
  let az = Math.atan2(Math.sin(ha), Math.cos(ha) * Math.sin(lat) - Math.tan(decl) * Math.cos(lat)) / rad + 180;
  az = (az + 360) % 360;
  let elev = 90 - zen / rad;
  // atmospheric refraction (approx.)
  if (elev > -0.575) {
    const te = Math.tan(elev * rad);
    const r = elev > 5 ? 58.1 / te - 0.07 / te ** 3 + 0.000086 / te ** 5 : elev > -0.575 ? 1735 + elev * (-518.2 + elev * (103.4 + elev * (-12.79 + elev * 0.711))) : -20.774 / te;
    elev += r / 3600;
  }
  return { azimuth: az, elevation: elev };
}

// Local wall-clock time in a time zone -> UTC Date
export function zonedToUtc(year, month, day, minutes, tz) {
  const guess = Date.UTC(year, month - 1, day, Math.floor(minutes / 60), minutes % 60);
  const off = tzOffsetMin(new Date(guess), tz);
  let utc = guess - off * 60000;
  const off2 = tzOffsetMin(new Date(utc), tz);
  if (off2 !== off) utc = guess - off2 * 60000;
  return new Date(utc);
}
function tzOffsetMin(date, tz) {
  const f = new Intl.DateTimeFormat('en-US', { timeZone: tz, hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const p = Object.fromEntries(f.formatToParts(date).map(x => [x.type, x.value]));
  const asUtc = Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute, +p.second);
  return Math.round((asUtc - date.getTime()) / 60000);
}

export class SunController {
  constructor(viewer, coords, display, tz) {
    this.viewer = viewer; this.coords = coords; this.tz = tz; this.display = display;
    this.center = new THREE.Vector3();
  }
  // date: 'YYYY-MM-DD', minutes since local midnight
  update(dateStr, minutes) {
    const [Y, Mo, D] = dateStr.split('-').map(Number);
    const utc = zonedToUtc(Y, Mo, D, minutes, this.tz);
    const pos = solarPosition(utc, this.coords.lat, this.coords.lon);
    const gridAz = (pos.azimuth + this.coords.trueNorthGridAz) * Math.PI / 180; // true -> ITM grid
    const el = Math.max(pos.elevation, -2) * Math.PI / 180;
    const dir = new THREE.Vector3(Math.sin(gridAz) * Math.cos(el), Math.sin(el), -Math.cos(gridAz) * Math.cos(el));
    const sun = this.viewer.sun;
    sun.position.copy(this.center).addScaledVector(dir, 200);
    sun.target.position.copy(this.center);
    sun.target.updateMatrixWorld();
    const up = Math.max(0, Math.sin(el));
    sun.intensity = this.display.sun.intensity * Math.min(1, up * 3);
    sun.color.setHSL(0.1, 0.6 * (1 - Math.min(1, up * 2.2)), 0.5 + 0.5 * Math.min(1, up * 2.2));
    this.viewer.scene.environmentIntensity = this.display.sun.ambientEnvIntensity * (0.25 + 0.75 * Math.min(1, up * 4));
    this.viewer.invalidate();
    this.last = { ...pos, utc };
    return this.last;
  }
  // sunrise/sunset by scanning the day (1-minute resolution)
  riseSet(dateStr) {
    const [Y, Mo, D] = dateStr.split('-').map(Number);
    let rise = null, set = null, prev = null;
    for (let m = 0; m <= 1440; m += 1) {
      const e = solarPosition(zonedToUtc(Y, Mo, D, m, this.tz), this.coords.lat, this.coords.lon).elevation;
      if (prev !== null) {
        if (prev < -0.833 && e >= -0.833) rise = m;
        if (prev >= -0.833 && e < -0.833) set = m;
      }
      prev = e;
    }
    return { rise, set };
  }
}

export const fmtMin = (m) => m == null ? '—' : `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
