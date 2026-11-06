import * as THREE from 'three';
import { MaterialLibrary } from '../../js/core/materials.js';
import { buildLots } from './lots.js';
import { buildStreets } from './streets.js';
import { buildEnvelopes } from './envelopes.js';
import { buildSheet04 } from './sheet04.js';
import { buildControls } from './controls.js';

// Environment: neighbouring lots, streets and maximum neighbour envelopes (data/environment/*).
// Replaces the stage-1 neighbour/street surfaces (built from data/site/terrain-regions.json) with the
// data of this module, so that the same layers show one consistent set of components.
const SUPERSEDED_ROLES = ['neighbor', 'sidewalk', 'road'];
const SUPERSEDED_LAYERS = ['street', 'neighborLots', 'neighborEnvelopes'];

export function buildEnvironment(ctx) {
  const link = document.createElement('link');
  link.rel = 'stylesheet'; link.href = new URL('./environment.css', import.meta.url).href;
  document.head.append(link);

  supersedeStage1(ctx);
  const mats = new MaterialLibrary(ctx.data.envMaterials, ctx.viewer.renderer, './');
  const streets = buildStreets(ctx, mats);
  const lots = buildLots(ctx, mats);
  const envelopes = buildEnvelopes(ctx, mats, lots);
  const sheet04 = buildSheet04(ctx, mats, lots);
  return {
    lots, envelopes, sheet04, streets,
    volumes: [...envelopes, ...sheet04], // transparency slider applies to all neighbour volumes
    // called from main.js once the app/store exist; returns the DOM for the "סביבה" group of the layers panel
    attach(app) { this.controls = buildControls(app, this); },
    panel() { return this.controls?.panel(); },
  };
}

function supersedeStage1(ctx) {
  const { registry, scene, ground } = ctx;
  const drop = registry.items.filter(it => SUPERSEDED_LAYERS.includes(it.tags.layer) &&
    (it.meta.kind !== 'terrain' || SUPERSEDED_ROLES.includes(it.meta.role)));
  for (const it of drop) {
    scene.remove(it.object);
    it.object.traverse(o => { o.geometry?.dispose?.(); if (o.isCSS2DObject) o.element.remove(); });
  }
  registry.items = registry.items.filter(it => !drop.includes(it));
  // context-parcel labels (stage 1, drawn on the reference plane) of the parcels modelled here
  const mine = new Set([...ctx.data.envLots.lots.map(l => l.parcel), ...ctx.data.envStreets.parcels, ...ctx.data.envLots.splits.map(s => s.merged)]);
  for (const it of registry.items.filter(i => i.tags.layer === 'contextParcels')) {
    for (const o of [...it.object.children]) {
      if (o.isCSS2DObject && mine.has(o.element.textContent)) { it.object.remove(o); o.element.remove(); }
    }
  }
  ground.regions = ground.regions.filter(r => !(r.kind === 'env' && /^(lot-(?!257)|sidewalk-|road-)/.test(r.id)));
}

export function overviewView(app) {
  const D = app.data.envDisplay;
  const [x0, y0, x1, y1] = app.data.envStreets.window;
  const cE = (x0 + x1) / 2, cN = (y0 + y1) / 2;
  const t = app.coords.toLocal(cE, cN, app.coords.H0);
  return { target: t, cam: t.clone().add(new THREE.Vector3(...D.overviewOffset_m)) };
}
