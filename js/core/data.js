// Loads every JSON data file listed in data/manifest.json into one object.
export async function loadData(base = './') {
  const manifest = await fetchJson(base + 'data/manifest.json');
  const out = { manifest };
  await Promise.all(Object.entries(manifest.files).map(async ([key, path]) => {
    out[key] = await fetchJson(base + path);
  }));
  return out;
}

async function fetchJson(url) {
  const r = await fetch(url, { cache: 'no-cache' });
  if (!r.ok) throw new Error(`טעינת ${url} נכשלה (${r.status})`);
  return r.json();
}
