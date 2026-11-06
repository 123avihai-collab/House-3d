import * as THREE from 'three';

// ITM <-> scene coordinates. Scene: x = E-E0, y = H-H0, z = -(N-N0). All metres.
export class Coords {
  constructor(origin) {
    this.E0 = origin.E0;
    this.N0 = origin.N0;
    this.H0 = origin.H0;
    this.trueNorthGridAz = origin.trueNorthGridAzimuth_deg; // grid azimuth of true north
    this.lat = origin.lotCentroid.lat;
    this.lon = origin.lotCentroid.lon;
  }
  toLocal(E, N, H = this.H0) { return new THREE.Vector3(E - this.E0, H - this.H0, -(N - this.N0)); }
  xz(E, N) { return [E - this.E0, -(N - this.N0)]; }
  fromLocal(v) { return { E: v.x + this.E0, N: -v.z + this.N0, H: v.y + this.H0 }; }
  rel(H) { return H - this.H0; }
  fmtH(H) {
    const r = H - this.H0;
    return `${H.toFixed(2)} (${r >= 0 ? '+' : '−'}${Math.abs(r).toFixed(2)})`;
  }
  fmtRel(r) { return `${r >= 0 ? '+' : '−'}${Math.abs(r).toFixed(2)}`; }
  fmtEN(E, N) { return `E ${E.toFixed(3)}  N ${N.toFixed(3)}`; }
}
