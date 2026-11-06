import * as THREE from 'three';

// Section planes: horizontal (keep below level) and vertical (east-west or north-south), movable.
export class SectionTool {
  constructor(app) {
    this.app = app;
    this.hPlane = new THREE.Plane(new THREE.Vector3(0, -1, 0), 0);
    this.vPlane = new THREE.Plane(new THREE.Vector3(-1, 0, 0), 0);
    app.store.on(s => this.apply(s.section));
    this.apply(app.store.get().section);
  }
  apply(sec) {
    const planes = [];
    if (sec.hOn) { this.hPlane.set(new THREE.Vector3(0, -1, 0), sec.hLevel); planes.push(this.hPlane); }
    if (sec.vOn) {
      // axis 'E': plane perpendicular to east axis at E = E0 + pos ; 'N': perpendicular to north axis
      const sgn = sec.vFlip ? -1 : 1;
      if (sec.vAxis === 'E') this.vPlane.set(new THREE.Vector3(-sgn, 0, 0), sgn * sec.vPos);
      else this.vPlane.set(new THREE.Vector3(0, 0, sgn), sgn * sec.vPos); // scene z = -(N-N0)
      planes.push(this.vPlane);
    }
    this.app.viewer.renderer.clippingPlanes = planes;
    this.app.viewer.invalidate();
  }
}
