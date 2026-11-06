// Usage: node convert.mjs <input.dwg> <output.json>
// Reads a DWG with libredwg (WASM) and writes entities + blocks as JSON.
import { Dwg_File_Type, LibreDwg } from '@mlightcad/libredwg-web';
import fs from 'fs';
const [, , input, output] = process.argv;
if (!input || !output) { console.error('usage: node convert.mjs in.dwg out.json'); process.exit(1); }
const wasmDir = new URL('./node_modules/@mlightcad/libredwg-web/wasm/', import.meta.url).pathname;
const lib = await LibreDwg.create(wasmDir);
const dwg = lib.dwg_read_data(fs.readFileSync(input), Dwg_File_Type.DWG);
const db = lib.convert(dwg);
const out = {
  source: input,
  header: db.header,
  layers: db.tables?.LAYER?.entries?.map(l => l.name),
  entities: db.entities,
  blocks: db.tables?.BLOCK_RECORD?.entries?.map(b => ({ name: b.name, entities: b.entities })),
};
fs.writeFileSync(output, JSON.stringify(out, (k, v) => (typeof v === 'bigint' ? Number(v) : v)));
console.log(`${input}: ${db.entities.length} entities -> ${output}`);
