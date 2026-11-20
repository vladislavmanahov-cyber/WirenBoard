'use strict';
// Состояние: id устройства -> {id, title, controls: [...]}
const devices = new Map();
const $ = (id) => document.getElementById(id);

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

async function send(dev, ctrl, value) {
  const r = await fetch(`/api/devices/${encodeURIComponent(dev)}/controls/${encodeURIComponent(ctrl)}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ value: String(value) }),
  });
  if (!r.ok) {
    const e = await r.json().catch(() => ({}));
    alert(e.detail || `Ошибка ${r.status}`);
  }
}

function controlHtml(dev, c) {
  const name = esc(c.title || c.id);
  const units = c.units ? ' ' + esc(c.units) : '';
  const data = `data-dev="${esc(dev)}" data-ctrl="${esc(c.id)}"`;
  let widget;
  if (c.writable && c.type === 'switch') {
    widget = `<label class="switch"><input type="checkbox" ${data} data-kind="switch" ${c.value === '1' ? 'checked' : ''}><span></span></label>`;
  } else if (c.writable && c.type === 'pushbutton') {
    widget = `<button ${data} data-kind="push">Нажать</button>`;
  } else if (c.writable && c.type === 'range') {
    widget = `<input type="range" ${data} data-kind="range" min="${c.min ?? 0}" max="${c.max ?? 100}" value="${esc(c.value ?? 0)}"><span class="val">${esc(c.value)}${units}</span>`;
  } else if (c.writable && (c.type === 'text' || c.type === 'value')) {
    widget = `<input type="text" ${data} data-kind="text" value="${esc(c.value)}">`;
  } else if (c.type === 'switch' || c.type === 'alarm') {
    widget = `<span class="val">${c.value === '1' ? 'вкл' : 'выкл'}</span>`;
  } else {
    widget = `<span class="val">${esc(c.value ?? '—')}${units}</span>`;
  }
  return `<div class="row${c.error ? ' err' : ''}" title="${esc(c.error || '')}"><span class="name">${name}</span>${widget}</div>`;
}

function render() {
  const q = $('filter').value.trim().toLowerCase();
  const list = [...devices.values()].sort((a, b) => a.title.localeCompare(b.title, 'ru'));
  const html = [];
  for (const d of list) {
    const ctrls = q && !(`${d.title} ${d.id}`.toLowerCase().includes(q))
      ? d.controls.filter((c) => `${c.title || ''} ${c.id}`.toLowerCase().includes(q))
      : d.controls;
    if (!ctrls.length) continue;
    const sub = d.title !== d.id ? `<small>${esc(d.id)}</small>` : '';
    html.push(`<section class="card"><h2>${esc(d.title)}${sub}</h2>${ctrls.map((c) => controlHtml(d.id, c)).join('')}</section>`);
  }
  // не перерисовываем поле, в которое сейчас вводят текст
  const active = document.activeElement;
  if (active && active.dataset && active.dataset.kind === 'text') return;
  $('devices').innerHTML = html.join('');
  $('empty').hidden = devices.size > 0;
}

function upsertControl(devId, ctrl) {
  const d = devices.get(devId) || { id: devId, title: devId, controls: [] };
  const i = d.controls.findIndex((c) => c.id === ctrl.id);
  if (i >= 0) d.controls[i] = ctrl; else d.controls.push(ctrl);
  d.controls.sort((a, b) => ((a.order ?? 1e9) - (b.order ?? 1e9)) || a.id.localeCompare(b.id));
  devices.set(devId, d);
}

let timer = null;
function scheduleRender() {
  if (!timer) timer = requestAnimationFrame(() => { timer = null; render(); });
}

function connect() {
  const es = new EventSource('/api/events');
  es.addEventListener('snapshot', (e) => {
    devices.clear();
    for (const d of JSON.parse(e.data)) devices.set(d.id, d);
    scheduleRender();
  });
  es.addEventListener('device', (e) => { const d = JSON.parse(e.data).device; devices.set(d.id, d); scheduleRender(); });
  es.addEventListener('control', (e) => { const ev = JSON.parse(e.data); upsertControl(ev.device, ev.control); scheduleRender(); });
  es.onopen = refreshStatus;
  es.onerror = () => { $('status').textContent = 'Нет связи с сервисом'; $('status').className = 'status bad'; };
}

async function refreshStatus() {
  try {
    const s = await (await fetch('/api/status')).json();
    const el = $('status');
    if (!s.mqtt_configured) { el.textContent = 'MQTT не настроен'; el.className = 'status bad'; }
    else if (s.connected) { el.textContent = 'Контроллер на связи'; el.className = 'status ok'; }
    else { el.textContent = 'Нет связи с контроллером'; el.className = 'status bad'; }
  } catch { /* покажет onerror */ }
}

document.addEventListener('change', (e) => {
  const t = e.target, k = t.dataset && t.dataset.kind;
  if (k === 'switch') send(t.dataset.dev, t.dataset.ctrl, t.checked ? '1' : '0');
  else if (k === 'range' || k === 'text') send(t.dataset.dev, t.dataset.ctrl, t.value);
});
document.addEventListener('click', (e) => {
  const t = e.target;
  if (t.dataset && t.dataset.kind === 'push') send(t.dataset.dev, t.dataset.ctrl, '1');
});
$('filter').addEventListener('input', render);

connect();
setInterval(refreshStatus, 10000);
