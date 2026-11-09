// In-page confirm / text dialogs. The claude.ai artifact frame blocks window.confirm / window.prompt (they return
// false / null at once, without showing anything), so every "delete" / "rename" button uses these instead.
// askConfirm(text, {ok, danger}) -> Promise<boolean>; askText(label, value) -> Promise<string|null>.

const CSS = `.dlg-back{position:fixed;inset:0;background:rgba(0,0,0,.35);display:grid;place-items:center;z-index:1000;direction:rtl}
.dlg{background:#fff;color:#1d2329;border-radius:10px;padding:16px 18px;min-width:min(320px,88vw);max-width:92vw;box-shadow:0 8px 30px rgba(0,0,0,.3);font:14px/1.4 system-ui,sans-serif}
.dlg p{margin:0 0 12px;white-space:pre-wrap}.dlg input{width:100%;box-sizing:border-box;font:inherit;padding:7px 8px;border:1px solid #c9c4ba;border-radius:6px;margin-bottom:12px}
.dlg .b{display:flex;gap:8px;justify-content:flex-start}.dlg button{font:inherit;padding:7px 14px;border-radius:6px;border:1px solid #c9c4ba;background:#f1eee8;color:#1d2329;cursor:pointer;min-height:34px}
.dlg button.ok{background:#1d2329;color:#fff;border-color:#1d2329}.dlg button.ok.danger{background:#b3261e;border-color:#b3261e}`;

function open(build) {
  if (!document.getElementById('dlg-css')) { const s = document.createElement('style'); s.id = 'dlg-css'; s.textContent = CSS; document.head.append(s); }
  return new Promise((resolve) => {
    const back = document.createElement('div'); back.className = 'dlg-back';
    const box = document.createElement('div'); box.className = 'dlg'; box.setAttribute('role', 'dialog'); back.append(box);
    const done = (v) => { back.remove(); document.removeEventListener('keydown', key, true); resolve(v); };
    const key = (e) => { if (e.key === 'Escape') { e.stopPropagation(); done(build.cancel); } if (e.key === 'Enter') { e.stopPropagation(); e.preventDefault(); done(build.value()); } };
    build.render(box, done);
    back.addEventListener('pointerdown', (e) => { if (e.target === back) done(build.cancel); });
    document.addEventListener('keydown', key, true);
    document.body.append(back);
    (box.querySelector('input') || box.querySelector('button.ok'))?.focus();
  });
}

const btn = (text, cls, fn) => { const b = document.createElement('button'); b.textContent = text; if (cls) b.className = cls; b.onclick = fn; return b; };

export function askConfirm(text, { ok = 'אישור', cancel = 'ביטול', danger = false } = {}) {
  return open({ cancel: false, value: () => true, render(box, done) {
    const p = document.createElement('p'); p.textContent = text; const row = document.createElement('div'); row.className = 'b';
    row.append(btn(ok, 'ok' + (danger ? ' danger' : ''), () => done(true)), btn(cancel, '', () => done(false))); box.append(p, row);
  } });
}

export function askText(label, value = '', { ok = 'אישור', cancel = 'ביטול' } = {}) {
  let input;
  return open({ cancel: null, value: () => input.value, render(box, done) {
    const p = document.createElement('p'); p.textContent = label; input = document.createElement('input'); input.value = value ?? '';
    const row = document.createElement('div'); row.className = 'b'; row.append(btn(ok, 'ok', () => done(input.value)), btn(cancel, '', () => done(null)));
    box.append(p, input, row); setTimeout(() => input.select(), 0);
  } });
}
