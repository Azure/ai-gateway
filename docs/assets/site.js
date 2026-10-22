(() => {
'use strict';
/* 01-core.js */
// Core helpers, theme, storage, toast, copy, values (placeholders).
const D = window.AIGW || { rel: './', labs: [], paths: [] };
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const h = (html) => { const t = document.createElement('template'); t.innerHTML = html.trim(); return t.content.firstElementChild; };
const escHtml = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const isMac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

const SV = (d) => `<svg class="i" viewBox="0 0 20 20" aria-hidden="true">${d}</svg>`;
const IC = {
  search: SV('<circle cx="8.5" cy="8.5" r="5"/><path d="m12.5 12.5 4.5 4.5"/>'),
  close: SV('<path d="m5 5 10 10M15 5 5 15"/>'),
  check: SV('<path d="m5 10.5 3.2 3.2L15 6.8"/>'),
  x: SV('<circle cx="10" cy="10" r="7.5"/><path d="m7.5 7.5 5 5M12.5 7.5l-5 5"/>'),
  ok: SV('<circle cx="10" cy="10" r="7.5"/><path d="m6.8 10.2 2.2 2.2 4.3-4.6"/>'),
  minus: SV('<circle cx="10" cy="10" r="7.5"/><path d="M6.5 10h7"/>'),
  sliders: SV('<path d="M3 6h7M14 6h3M3 14h3M10 14h7"/><circle cx="12" cy="6" r="2"/><circle cx="8" cy="14" r="2"/>'),
  info: SV('<circle cx="10" cy="10" r="7.5"/><path d="M10 9v5M10 6.2v.1"/>'),
  play: SV('<path d="M6.5 4.5v11l9-5.5Z"/>'),
  expand: SV('<path d="M3.5 7.5v-4h4M12.5 3.5h4v4M16.5 12.5v4h-4M7.5 16.5h-4v-4"/>'),
  reset: SV('<path d="M3.5 10a6.5 6.5 0 1 0 2-4.7"/><path d="M3.5 3.5v3.5H7"/>'),
  user: SV('<circle cx="10" cy="7" r="3.2"/><path d="M3.8 17a6.2 6.2 0 0 1 12.4 0"/>'),
  key: SV('<circle cx="6.5" cy="13.5" r="3.5"/><path d="m9 11 7.5-7.5M14 6l2 2M12 8l1.5 1.5"/>'),
  shield: SV('<path d="M10 2.5 16 5v4.5c0 4-2.7 6.7-6 8-3.3-1.3-6-4-6-8V5Z"/>'),
  gauge: SV('<path d="M3.5 14a6.5 6.5 0 1 1 13 0"/><path d="m10 14 3.5-4.5"/><circle cx="10" cy="14" r="1"/>'),
  coins: SV('<ellipse cx="8" cy="6" rx="5" ry="2.5"/><path d="M3 6v3.5C3 10.9 5.2 12 8 12s5-1.1 5-2.5V6"/><path d="M7 12.4V14c0 1.4 2.2 2.5 5 2.5s5-1.1 5-2.5v-3.5c0-1.2-1.6-2.2-3.8-2.4"/>'),
  filter: SV('<path d="M3 4.5h14l-5.5 6.5v5l-3 1.5V11Z"/>'),
  route: SV('<circle cx="5" cy="5" r="2"/><circle cx="15" cy="15" r="2"/><path d="M7 5h5.5a2.5 2.5 0 0 1 0 5h-5a2.5 2.5 0 0 0 0 5H13"/>'),
  server: SV('<rect x="3" y="3" width="14" height="6" rx="1.5"/><rect x="3" y="11" width="14" height="6" rx="1.5"/><path d="M6 6h.01M6 14h.01"/>'),
  chart: SV('<path d="M3 3v14h14"/><path d="m6 13 3.5-4 3 2.5L17 6"/>'),
  app: SV('<rect x="3" y="3.5" width="14" height="13" rx="2"/><path d="M3 7.5h14M6 5.5h.01M8 5.5h.01"/>'),
  globe: SV('<circle cx="10" cy="10" r="7.5"/><path d="M2.5 10h15M10 2.5c2 2.2 3 4.7 3 7.5s-1 5.3-3 7.5c-2-2.2-3-4.7-3-7.5s1-5.3 3-7.5Z"/>'),
  eye: SV('<path d="M2 10s3-5.5 8-5.5S18 10 18 10s-3 5.5-8 5.5S2 10 2 10Z"/><circle cx="10" cy="10" r="2.5"/>'),
  layers: SV('<path d="M10 2.5 17.5 6.5 10 10.5 2.5 6.5Z"/><path d="m2.5 10 7.5 4 7.5-4M2.5 13.5l7.5 4 7.5-4"/>'),
  models: SV('<path d="M10 2.5 16.5 6v8L10 17.5 3.5 14V6Z"/><path d="M3.5 6 10 9.5 16.5 6M10 9.5v8"/>'),
  tools: SV('<path d="M12.5 3a4 4 0 0 0-3.8 5.3L3.5 13.5a1.5 1.5 0 0 0 0 2.1l.9.9a1.5 1.5 0 0 0 2.1 0l5.2-5.2A4 4 0 0 0 17 7.5l-2.3 2.3-2.3-.4-.4-2.3L14.3 4.8A4 4 0 0 0 12.5 3Z"/>'),
  sparkle: SV('<path d="M10 2.5 11.6 8.4 17.5 10l-5.9 1.6L10 17.5l-1.6-5.9L2.5 10l5.9-1.6Z"/>'),
  flag: SV('<path d="M5 17.5V3M5 3.5h9.5l-2 3.5 2 3.5H5"/>'),
  stream: SV('<path d="M2.5 6c2-1.5 3.5-1.5 5 0s3 1.5 5 0 3.5-1.5 5 0M2.5 10c2-1.5 3.5-1.5 5 0s3 1.5 5 0 3.5-1.5 5 0M2.5 14c2-1.5 3.5-1.5 5 0s3 1.5 5 0 3.5-1.5 5 0"/>'),
  arrowR: SV('<path d="M4 10h12M11.5 5.5 16 10l-4.5 4.5"/>'),
  arrowL: SV('<path d="M16 10H4M8.5 5.5 4 10l4.5 4.5"/>'),
  lock: SV('<rect x="4" y="9" width="12" height="8.5" rx="2"/><path d="M7 9V6.5a3 3 0 0 1 6 0V9"/>'),
};

// Storage (namespaced, JSON, fail-safe)
const store = {
  get(k, d) { try { const v = localStorage.getItem(`aigw-${k}`); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(`aigw-${k}`, JSON.stringify(v)); } catch { /* private mode */ } },
  del(k) { try { localStorage.removeItem(`aigw-${k}`); } catch { /* ignore */ } },
};
const progressAll = () => store.get('progress', {});
function labProgress(slug) {
  const p = progressAll()[slug] || {};
  return { steps: p.steps || {}, total: p.total || 0, done: !!p.done };
}
function saveLabProgress(slug, data) {
  const all = progressAll();
  all[slug] = { ...(all[slug] || {}), ...data };
  store.set('progress', all);
}
function labRatio(slug) {
  const p = labProgress(slug);
  if (p.done) return 1;
  const n = Object.values(p.steps).filter(Boolean).length;
  return p.total ? Math.min(1, n / p.total) : 0;
}

// Theme
function initTheme() {
  const root = document.documentElement;
  $$('[data-theme-toggle]').forEach((b) => b.addEventListener('click', () => {
    const t = root.dataset.theme === 'dark' ? 'light' : 'dark';
    root.dataset.theme = t;
    try { localStorage.setItem('aigw-theme', t); } catch { /* ignore */ }
    document.dispatchEvent(new CustomEvent('aigw:theme', { detail: t }));
  }));
  $$('[data-kbd]').forEach((k) => { k.textContent = isMac ? '⌘K' : 'Ctrl K'; });
}

// Toast
let toastEl, toastTimer;
function toast(msg, icon = IC.check) {
  if (!toastEl) { toastEl = h('<div class="toast" role="status" aria-live="polite"></div>'); document.body.append(toastEl); }
  toastEl.innerHTML = `${icon}<span>${escHtml(msg)}</span>`;
  toastEl.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastEl.classList.remove('show'), 2200);
}

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch {
    const ta = h('<textarea style="position:fixed;opacity:0"></textarea>');
    ta.value = text; document.body.append(ta); ta.select();
    const ok = document.execCommand('copy'); ta.remove(); return ok;
  }
}

// Values: personalise <placeholders> in code. Never stores secrets.
const VALUE_FIELDS = [
  ['subscription-id', 'Subscription ID', '00000000-0000-0000-0000-000000000000'],
  ['tenant-id', 'Tenant ID', '00000000-0000-0000-0000-000000000000'],
  ['resource-group', 'Resource group', 'rg-aigw-labs'],
  ['gateway', 'Gateway name', 'aigw-labs-001'],
  ['location', 'Region', 'eastus2'],
  ['provider-name', 'Model provider', 'foundry'],
  ['model-name', 'Model alias', 'chat'],
  ['foundry-account-name', 'Foundry account', 'ai-labs-foundry'],
];
const getValues = () => store.get('values', {});

function applyValues(root = document) {
  const v = getValues();
  $$('.ph[data-ph]', root).forEach((el) => {
    const k = el.dataset.ph; const val = (v[k] || '').trim();
    el.textContent = val || `<${k}>`;
    el.classList.toggle('filled', !!val);
    el.title = val ? `Your value for ${k}. Edit in “Your values”.` : `Replace with your ${k}. Set it once in “Your values”.`;
  });
}

let drawer;
function openValues() {
  if (!drawer) {
    const v = getValues();
    drawer = h(`<div class="drawer" role="dialog" aria-modal="true" aria-labelledby="values-title" hidden>
      <div class="drawer-scrim" data-close></div>
      <div class="drawer-card">
        <div class="drawer-head"><h2 id="values-title">${IC.sliders}Your values</h2><button class="icon-btn" type="button" data-close aria-label="Close">${IC.close}</button></div>
        <p class="drawer-note">Fill these in once and every command in the labs uses them. Values stay in this browser. <strong>Never enter keys or secrets here.</strong></p>
        <form class="values-form">${VALUE_FIELDS.map(([k, label, ex]) => `<label class="field"><span>${label}<code>&lt;${k}&gt;</code></span><input name="${k}" value="${escHtml(v[k] || '')}" placeholder="${ex}" autocomplete="off" spellcheck="false"></label>`).join('')}</form>
        <div class="drawer-foot"><button class="btn btn-ghost btn-sm" type="button" data-clear>${IC.reset}Clear all</button><button class="btn btn-primary btn-sm" type="button" data-close>Done</button></div>
      </div></div>`);
    document.body.append(drawer);
    const form = $('form', drawer);
    form.addEventListener('input', () => {
      const vals = Object.fromEntries(new FormData(form).entries());
      Object.keys(vals).forEach((k) => { vals[k] = vals[k].trim(); if (!vals[k]) delete vals[k]; });
      store.set('values', vals); applyValues();
    });
    form.addEventListener('submit', (e) => { e.preventDefault(); closeValues(); });
    $('[data-clear]', drawer).addEventListener('click', () => { $$('input', form).forEach((i) => { i.value = ''; }); store.del('values'); applyValues(); });
    $$('[data-close]', drawer).forEach((b) => b.addEventListener('click', closeValues));
    drawer.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeValues(); trapFocus(e, $('.drawer-card', drawer)); });
  }
  drawer.lastFocus = document.activeElement;
  drawer.hidden = false;
  setTimeout(() => $('input', drawer)?.focus(), 30);
}
function closeValues() { if (!drawer) return; drawer.hidden = true; drawer.lastFocus?.focus?.(); }

function trapFocus(e, container) {
  if (e.key !== 'Tab') return;
  const f = $$('a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])', container).filter((x) => x.offsetParent !== null);
  if (!f.length) return;
  const first = f[0], last = f[f.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
}

// Copy buttons in code blocks (copies with personalised values, without prompts like "$ ").
function codeTextFor(block) {
  const panel = block.classList.contains('code-tabs') ? $('.code-panel:not([hidden])', block) : block;
  const pre = $('pre', panel);
  if (!pre) return '';
  const clone = pre.cloneNode(true);
  const v = getValues();
  $$('.ph[data-ph]', clone).forEach((el) => { el.textContent = (v[el.dataset.ph] || '').trim() || `<${el.dataset.ph}>`; });
  return clone.textContent.replace(/\n$/, '');
}
function initCopy() {
  document.addEventListener('click', async (e) => {
    const btn = e.target.closest('.copy-btn');
    if (!btn) return;
    const ok = await copyText(codeTextFor(btn.closest('.code')));
    const label = $('span', btn);
    btn.classList.add('copied');
    if (label) label.textContent = ok ? 'Copied' : 'Failed';
    setTimeout(() => { btn.classList.remove('copied'); if (label) label.textContent = 'Copy'; }, 1600);
  });
  $$('[data-copy-md]').forEach((b) => b.addEventListener('click', async () => {
    try {
      const res = await fetch(b.dataset.copyMd);
      const ok = await copyText(await res.text());
      toast(ok ? 'Lab copied as Markdown' : 'Copy failed');
    } catch { toast('Could not load the Markdown source', IC.info); }
  }));
  $$('[data-values-open]').forEach((b) => b.addEventListener('click', openValues));
}

/* 02-search.js */
// Search (Ctrl/Cmd + K) over search.json.
let searchIndex = null, searchModal, searchSel = 0, searchItems = [];

async function loadSearch() {
  if (searchIndex) return searchIndex;
  try { searchIndex = await (await fetch(`${D.rel}search.json`)).json(); } catch { searchIndex = []; }
  return searchIndex;
}
const norm = (s) => String(s || '').toLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g, '');
function hl(text, terms) {
  let out = escHtml(text);
  terms.filter((t) => t.length > 1).forEach((t) => {
    out = out.replace(new RegExp(`(${t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'ig'), '<mark>$1</mark>');
  });
  return out;
}
function snippet(text, terms) {
  const n = norm(text);
  const i = terms.reduce((best, t) => { const k = n.indexOf(t); return k >= 0 && (best < 0 || k < best) ? k : best; }, -1);
  if (i < 0) return '';
  const start = Math.max(0, i - 50);
  return (start ? '…' : '') + text.slice(start, start + 140).replace(/\s+/g, ' ') + '…';
}

function runSearch(q) {
  const terms = norm(q).split(/\s+/).filter(Boolean);
  const res = [];
  for (const lab of searchIndex || []) {
    const url = `${D.rel}labs/${lab.slug}/`;
    if (!terms.length) { res.push({ score: 100 - Number(lab.num), lab, url, kind: 'lab' }); continue; }
    const fields = { title: norm(lab.title), num: lab.num, summary: norm(lab.summary), tags: norm((lab.tags || []).join(' ')), text: norm(lab.text) };
    let score = 0, all = true;
    for (const t of terms) {
      let s = 0;
      if (fields.num === t) s += 40;
      if (fields.title.includes(t)) s += fields.title.split(/\W+/).includes(t) ? 24 : 16;
      if (fields.tags.includes(t)) s += 10;
      if (fields.summary.includes(t)) s += 6;
      if (fields.text.includes(t)) s += 2;
      if (!s) all = false;
      score += s;
    }
    if (all && score) res.push({ score, lab, url, kind: 'lab', snip: score < 16 * terms.length ? snippet(lab.text, terms) : '' });
    for (const hd of lab.headings || []) {
      const ht = norm(hd.text);
      if (terms.length && terms.every((t) => ht.includes(t))) res.push({ score: score * 0.4 + 8 + (hd.level === 2 ? 2 : 0), lab, url: `${url}#${hd.id}`, kind: 'section', heading: hd.text });
    }
  }
  res.sort((a, b) => b.score - a.score);
  return { terms, items: res.slice(0, terms.length ? 24 : 30) };
}

function renderSearch(q) {
  const { terms, items } = runSearch(q);
  searchItems = items; searchSel = 0;
  const box = $('.search-results', searchModal);
  if (!items.length) { box.innerHTML = `<div class="search-empty">No results for “${escHtml(q)}”. Try “budget”, “MCP” or “Entra”.</div>`; return; }
  const labsHtml = items.filter((x) => x.kind === 'lab');
  const secs = items.filter((x) => x.kind === 'section');
  const row = (x, i) => `<a class="sr-item" href="${x.url}" role="option" id="sr-${i}" aria-selected="${i === 0}">
    <span class="sr-num">${x.lab.num}</span><span class="sr-body">
    <span class="sr-title">${hl(x.kind === 'section' ? x.heading : x.lab.title, terms)}</span>
    <span class="sr-sub">${x.kind === 'section' ? `in ${escHtml(x.lab.title)}` : escHtml(x.lab.summary)}</span>
    ${x.snip ? `<span class="sr-snippet">${hl(x.snip, terms)}</span>` : ''}</span></a>`;
  let i = 0;
  const ordered = [...labsHtml, ...secs];
  searchItems = ordered;
  box.innerHTML = (labsHtml.length ? `<div class="search-group">${terms.length ? 'Labs' : 'All labs'}</div>${labsHtml.map((x) => row(x, i++)).join('')}` : '')
    + (secs.length ? `<div class="search-group">Sections</div>${secs.map((x) => row(x, i++)).join('')}` : '');
}
function moveSel(d) {
  const els = $$('.sr-item', searchModal);
  if (!els.length) return;
  searchSel = (searchSel + d + els.length) % els.length;
  els.forEach((el, i) => el.setAttribute('aria-selected', i === searchSel));
  els[searchSel].scrollIntoView({ block: 'nearest' });
  $('input', searchModal).setAttribute('aria-activedescendant', els[searchSel].id);
}

async function openSearch() {
  if (!searchModal) {
    searchModal = h(`<div class="modal search-modal" role="dialog" aria-modal="true" aria-label="Search labs" hidden>
      <div class="modal-scrim" data-close></div>
      <div class="modal-card">
        <div class="search-box">${IC.search}<input type="search" placeholder="Search labs, policies, steps…" aria-label="Search" role="combobox" aria-expanded="true" aria-controls="search-results" autocomplete="off" spellcheck="false"><kbd>Esc</kbd></div>
        <div class="search-results" id="search-results" role="listbox"></div>
        <div class="search-foot"><span><kbd>↑</kbd><kbd>↓</kbd>navigate</span><span><kbd>↵</kbd>open</span><span><kbd>Esc</kbd>close</span></div>
      </div></div>`);
    document.body.append(searchModal);
    const input = $('input', searchModal);
    input.addEventListener('input', () => renderSearch(input.value));
    searchModal.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { e.preventDefault(); closeSearch(); }
      else if (e.key === 'ArrowDown') { e.preventDefault(); moveSel(1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); moveSel(-1); }
      else if (e.key === 'Enter') { const el = $$('.sr-item', searchModal)[searchSel]; if (el) { e.preventDefault(); location.href = el.href; closeSearch(); } }
      else trapFocus(e, $('.modal-card', searchModal));
    });
    $$('[data-close]', searchModal).forEach((b) => b.addEventListener('click', closeSearch));
    searchModal.addEventListener('click', (e) => { if (e.target.closest('.sr-item')) closeSearch(); });
  }
  searchModal.lastFocus = document.activeElement;
  searchModal.hidden = false;
  document.body.style.overflow = 'hidden';
  const input = $('input', searchModal);
  input.select(); input.focus();
  await loadSearch();
  renderSearch(input.value);
}
function closeSearch() {
  if (!searchModal || searchModal.hidden) return;
  searchModal.hidden = true; document.body.style.overflow = '';
  searchModal.lastFocus?.focus?.();
}
function initSearch() {
  $$('[data-search-open]').forEach((b) => b.addEventListener('click', openSearch));
  document.addEventListener('keydown', (e) => {
    const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName) || document.activeElement?.isContentEditable;
    if ((e.key === 'k' || e.key === 'K') && (e.metaKey || e.ctrlKey)) { e.preventDefault(); openSearch(); }
    else if (e.key === '/' && !typing) { e.preventDefault(); openSearch(); }
  });
}

/* 03-lab.js */
// Lab page: tracks, code tabs, step progress, TOC, read progress, completion, lightbox, nav, mermaid, paths.
const LAB = $('.lab-main[data-lab]')?.dataset.lab || null;

function selectTrack(id, { persist = true, scroll = false } = {}) {
  let changed = false;
  $$('.tracks').forEach((group) => {
    const tabs = $$('.track-tab', group);
    if (!tabs.some((t) => t.dataset.track === id)) return;
    tabs.forEach((t) => { const on = t.dataset.track === id; t.setAttribute('aria-selected', on); t.tabIndex = on ? 0 : -1; });
    $$(':scope > .track-panel', group).forEach((p) => { p.hidden = p.dataset.track !== id; });
    changed = true;
  });
  if (!changed) return;
  if (persist) {
    store.set('track', id);
    const u = new URL(location.href); u.searchParams.set('track', id); history.replaceState(null, '', u);
  }
  updateProgressUI();
  if (scroll) { const first = $('.tracks'); first && first.getBoundingClientRect().top < 0 && first.scrollIntoView({ block: 'start' }); }
}
function initTracks() {
  const groups = $$('.tracks');
  if (!groups.length) return;
  groups.forEach((g) => {
    const tabs = $$('.track-tab', g);
    tabs.forEach((t, i) => {
      t.addEventListener('click', () => selectTrack(t.dataset.track, { scroll: true }));
      t.addEventListener('keydown', (e) => {
        const d = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
        if (!d) return;
        e.preventDefault();
        const n = tabs[(i + d + tabs.length) % tabs.length];
        n.focus(); selectTrack(n.dataset.track);
      });
    });
  });
  const fromUrl = new URLSearchParams(location.search).get('track');
  const pref = fromUrl || store.get('track', null);
  if (pref) selectTrack(pref, { persist: !!fromUrl });
}

function initCodeTabs() {
  const pick = (label) => {
    $$('.code-tabs').forEach((block) => {
      const tabs = $$('.code-tab', block);
      const t = tabs.find((x) => x.dataset.tabLabel === label);
      if (!t) return;
      tabs.forEach((x) => { const on = x === t; x.setAttribute('aria-selected', on); x.tabIndex = on ? 0 : -1; });
      $$('.code-panel', block).forEach((p) => { p.hidden = p.id !== t.getAttribute('aria-controls'); });
    });
  };
  $$('.code-tabs').forEach((block) => {
    const tabs = $$('.code-tab', block);
    tabs.forEach((t, i) => {
      t.addEventListener('click', () => { pick(t.dataset.tabLabel); store.set('codeTab', t.dataset.tabLabel); });
      t.addEventListener('keydown', (e) => {
        const d = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
        if (!d) return;
        e.preventDefault();
        const n = tabs[(i + d + tabs.length) % tabs.length]; n.focus(); n.click();
      });
    });
  });
  const pref = store.get('codeTab', null);
  if (pref) pick(pref);
  document.addEventListener('click', (e) => {
    const b = e.target.closest('.code-expand');
    if (!b) return;
    const block = b.closest('.code');
    const open = block.classList.toggle('expanded');
    $('span', b).textContent = open ? 'Show less' : b.dataset.label || 'Show all';
    if (!open) block.scrollIntoView({ block: 'nearest' });
  });
  $$('.code-expand').forEach((b) => { b.dataset.label = $('span', b).textContent; });
}

// Steps that count toward progress: outside tracks, or inside the visible track panel.
const countedSteps = () => $$('#lab-content .step').filter((s) => { const p = s.closest('.track-panel'); return !p || !p.hidden; });
function updateProgressUI() {
  if (!LAB) return;
  const prog = labProgress(LAB);
  const steps = countedSteps();
  $$('#lab-content .step').forEach((s) => {
    const on = !!prog.steps[s.dataset.step];
    s.classList.toggle('done', on);
    $('.step-check', s)?.setAttribute('aria-pressed', on);
  });
  const done = steps.filter((s) => prog.steps[s.dataset.step]).length;
  const total = steps.length;
  if (prog.total !== total) saveLabProgress(LAB, { total });
  const ratio = prog.done ? 1 : total ? done / total : 0;
  const ring = $('.ring-fill'); if (ring) ring.style.setProperty('--p', ratio);
  const label = $('#progress-label');
  if (label) label.textContent = prog.done ? 'Lab complete' : `${done} of ${total} steps`;
  const box = $('#lab-complete');
  if (box) {
    box.classList.toggle('done', prog.done);
    const btn = $('[data-complete-lab] span', box);
    if (btn) btn.textContent = prog.done ? 'Completed' : 'Mark lab complete';
    const h2 = $('h2', box); if (h2) h2.textContent = prog.done ? 'Nice work. Lab complete.' : 'Finished the lab?';
  }
  updateLabLinks();
}
function initSteps() {
  if (!LAB) return;
  document.addEventListener('click', (e) => {
    const b = e.target.closest('.step-check');
    if (!b) return;
    const step = b.closest('.step');
    const prog = labProgress(LAB);
    const on = !prog.steps[step.dataset.step];
    prog.steps[step.dataset.step] = on;
    if (!on) delete prog.steps[step.dataset.step];
    saveLabProgress(LAB, { steps: prog.steps });
    updateProgressUI();
    const steps = countedSteps();
    if (on && steps.every((s) => labProgress(LAB).steps[s.dataset.step])) toast('All steps done. Mark the lab complete at the end.', IC.check);
  });
  $('[data-complete-lab]')?.addEventListener('click', () => {
    const p = labProgress(LAB);
    saveLabProgress(LAB, { done: !p.done });
    updateProgressUI();
    if (!p.done) toast('Lab marked complete', IC.check);
  });
  $$('[data-reset-progress]').forEach((b) => b.addEventListener('click', () => {
    saveLabProgress(LAB, { steps: {}, done: false });
    updateProgressUI(); toast('Progress reset for this lab', IC.reset);
  }));
  updateProgressUI();
}

// Progress markers across the site (sidebar, cards, path lists, path buttons).
function updateLabLinks() {
  $$('[data-lab-link]').forEach((a) => {
    const r = labRatio(a.dataset.labLink);
    const st = $('.side-state', a);
    if (st) { st.classList.toggle('done', r >= 1); st.classList.toggle('partial', r > 0 && r < 1); }
    const li = a.closest('.path-steps li'); if (li) li.classList.toggle('done', r >= 1);
  });
  $$('[data-progress-for]').forEach((el) => {
    const r = labRatio(el.dataset.progressFor);
    el.hidden = r <= 0; el.style.setProperty('--p', r);
    el.closest('.lab-card')?.classList.toggle('done', r >= 1);
  });
  $$('[data-path-start]').forEach((a) => {
    const p = D.paths.find((x) => x.id === a.dataset.pathStart);
    if (!p) return;
    const ratios = p.labs.map(labRatio);
    if (!ratios.some((r) => r > 0)) return;
    const next = p.labs.find((s, i) => ratios[i] < 1);
    a.href = `${D.rel}labs/${next || p.labs[0]}/?path=${p.id}`;
    a.firstChild.textContent = next ? 'Continue path ' : 'Review path ';
  });
}

function initPathBanner() {
  const banner = $('#path-banner');
  if (!banner || !LAB) return;
  const q = new URLSearchParams(location.search).get('path');
  let pid = q || store.get('activePath', null);
  const path = D.paths.find((p) => p.id === pid && p.labs.includes(LAB));
  if (!path) return;
  store.set('activePath', path.id);
  const i = path.labs.indexOf(LAB);
  const ratio = path.labs.filter((s) => labRatio(s) >= 1).length / path.labs.length;
  const link = (s, dir) => { const l = D.labs.find((x) => x.slug === s); return `<a href="${D.rel}labs/${s}/?path=${path.id}">${dir === 'prev' ? '← ' : ''}${escHtml(l?.short || s)}${dir === 'next' ? ' →' : ''}</a>`; };
  banner.innerHTML = `<strong>${IC.flag}${escHtml(path.title)}</strong><p>Lab ${i + 1} of ${path.labs.length} in this learning path</p>
    <div class="path-banner-bar"><span style="--p:${ratio}"></span></div>
    <div class="path-banner-nav">${i > 0 ? link(path.labs[i - 1], 'prev') : '<span></span>'}${i < path.labs.length - 1 ? link(path.labs[i + 1], 'next') : '<span></span>'}</div>
    <button class="link-btn" type="button" data-leave-path>Leave path</button>`;
  banner.hidden = false;
  $$('.sidebar [data-lab-link]').forEach((a) => a.classList.toggle('in-path', path.labs.includes(a.dataset.labLink)));
  $('[data-leave-path]', banner).addEventListener('click', () => {
    store.del('activePath'); banner.hidden = true;
    $$('.sidebar .in-path').forEach((a) => a.classList.remove('in-path'));
    const u = new URL(location.href); u.searchParams.delete('path'); history.replaceState(null, '', u);
  });
  $$('[data-pager]').forEach((a) => {
    const target = path.labs[i + (a.dataset.pager === 'next' ? 1 : -1)];
    if (target) a.href = `${D.rel}labs/${target}/?path=${path.id}`;
  });
}

function initToc() {
  const links = $$('.toc-list a[data-toc], .rn-nav-list a[data-toc]');
  if (!links.length) return;
  const map = new Map(links.map((a) => [a.dataset.toc, a]));
  const heads = links.map((a) => document.getElementById(a.dataset.toc)).filter(Boolean);
  let current = null;
  const setActive = (id) => {
    if (id === current) return; current = id;
    links.forEach((a) => a.classList.toggle('active', a.dataset.toc === id));
    const a = map.get(id); const box = $('.toc-inner');
    if (a && box && (a.offsetTop < box.scrollTop || a.offsetTop > box.scrollTop + box.clientHeight - 40)) box.scrollTop = a.offsetTop - box.clientHeight / 3;
  };
  const onScroll = () => {
    const y = 140;
    let id = heads[0]?.id;
    for (const hd of heads) { if (hd.offsetParent === null) continue; if (hd.getBoundingClientRect().top - y <= 0) id = hd.id; else break; }
    setActive(id);
    const main = $('.lab-main');
    if (main) {
      const r = main.getBoundingClientRect();
      const ratio = Math.min(1, Math.max(0, -r.top / Math.max(1, r.height - innerHeight)));
      $('.read-progress span')?.style.setProperty('--read', ratio.toFixed(4));
    }
  };
  let ticking = false;
  addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(() => { onScroll(); ticking = false; }); } }, { passive: true });
  onScroll();
}

function initLightbox() {
  let box;
  document.addEventListener('click', (e) => {
    const z = e.target.closest('button.zoom');
    if (!z) return;
    const img = $('img', z);
    if (!box) {
      box = h(`<div class="lightbox" role="dialog" aria-modal="true" aria-label="Image preview" hidden><button class="icon-btn lightbox-close" type="button" aria-label="Close">${IC.close}</button><p class="lightbox-cap"></p></div>`);
      box.insertBefore(document.createElement('img'), $('.lightbox-cap', box));
      document.body.append(box);
      const close = () => { box.hidden = true; document.body.style.overflow = ''; box.lastFocus?.focus?.(); };
      box.addEventListener('click', close);
      box.addEventListener('keydown', (ev) => { if (ev.key === 'Escape' || ev.key === 'Tab') { ev.preventDefault(); close(); } });
    }
    $('img', box).src = img.currentSrc || img.src;
    $('img', box).alt = img.alt;
    $('.lightbox-cap', box).textContent = z.closest('figure')?.querySelector('figcaption')?.textContent || img.alt || '';
    box.lastFocus = z; box.hidden = false; document.body.style.overflow = 'hidden';
    $('.lightbox-close', box).focus();
  });
}

// Edge's scareware blocker scans full-screen pages and can mistake a narrated product walkthrough for a scam,
// so lab videos never use the Fullscreen API: Expand, double-click, and F open an in-page theater view.
function initVideos() {
  const frames = $$('.figure-video .video-frame');
  if (!frames.length) return;
  let stage, current, holder;
  const close = () => {
    if (!current) return;
    const frame = current;
    holder.replaceWith(frame);
    stage.hidden = true; document.body.style.overflow = '';
    current = holder = null;
    $('.video-expand', frame)?.focus();
  };
  const open = (frame) => {
    if (current) close();
    if (!stage) {
      stage = h(`<div class="video-theater" role="dialog" aria-modal="true" hidden><button class="icon-btn video-theater-close" type="button" aria-label="Close video">${IC.close}</button><p class="video-theater-cap"></p></div>`);
      document.body.append(stage);
      stage.addEventListener('click', (e) => { if (e.target === stage) close(); });
      $('.video-theater-close', stage).addEventListener('click', close);
      stage.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') { e.preventDefault(); close(); }
        else if (e.key === 'Tab') { e.preventDefault(); const b = $('.video-theater-close', stage); (document.activeElement === b ? $('video', stage) : b).focus(); }
      });
    }
    const caption = frame.closest('figure')?.querySelector('figcaption')?.textContent || '';
    holder = h('<div class="video-holder" aria-hidden="true"></div>');
    holder.style.height = `${frame.offsetHeight}px`;
    // Moving a playing <video> within the document keeps it playing.
    frame.replaceWith(holder);
    stage.insertBefore(frame, $('.video-theater-cap', stage));
    $('.video-theater-cap', stage).textContent = caption;
    stage.setAttribute('aria-label', caption || 'Video');
    current = frame; stage.hidden = false; document.body.style.overflow = 'hidden';
    $('video', frame).focus();
  };
  const toggle = (frame) => (current === frame ? close() : open(frame));
  for (const frame of frames) {
    const video = $('video', frame);
    const btn = h(`<button class="video-expand" type="button" title="Expand (F)">${IC.expand}<span>Expand</span></button>`);
    frame.append(btn);
    btn.addEventListener('click', () => open(frame));
    const onBar = (e) => e.clientY > video.getBoundingClientRect().bottom - 72;
    const setPaused = (p) => { if (video.paused !== p) { if (p) video.pause(); else video.play().catch(() => {}); } };
    let before;
    // Chromium has no click-to-play on the video surface (Firefox does), so toggle only when the browser didn't.
    video.addEventListener('click', (e) => {
      if (e.detail > 1 || onBar(e)) return;
      const was = before = video.paused;
      setTimeout(() => { if (video.paused === was) setPaused(!was); }, 0);
    });
    // Double-click only expands/collapses: restore the play state from before the first click.
    video.addEventListener('dblclick', (e) => {
      e.preventDefault();
      const restore = onBar(e) ? undefined : before;
      toggle(frame);
      if (restore !== undefined) setTimeout(() => setPaused(restore), 0);
    }, true);
    video.addEventListener('keydown', (e) => {
      if ((e.key === 'f' || e.key === 'F') && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); toggle(frame); }
    });
    const sync = () => frame.classList.toggle('is-playing', !video.paused);
    video.addEventListener('play', sync); video.addEventListener('pause', sync);
  }
  // Last resort if a browser still enters full screen (e.g. a context-menu item): leave it and use the theater view.
  document.addEventListener('fullscreenchange', () => {
    const frame = document.fullscreenElement?.closest?.('.video-frame') || frames.find((f) => f.contains(document.fullscreenElement));
    if (frame) document.exitFullscreen().catch(() => {}).finally(() => open(frame));
  });
}

function initNav() {
  const toggle = $('.nav-toggle');
  if (!toggle) return;
  const scrim = $('.sidebar-scrim');
  const set = (open) => {
    document.body.classList.toggle('nav-open', open);
    toggle.setAttribute('aria-expanded', open);
    if (scrim) scrim.hidden = !open;
    if (open) centerSidebar();
  };
  toggle.addEventListener('click', () => set(!document.body.classList.contains('nav-open')));
  $$('[data-nav-close]').forEach((x) => x.addEventListener('click', () => set(false)));
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && document.body.classList.contains('nav-open')) { set(false); toggle.focus(); } });
}
function centerSidebar() {
  const inner = $('.sidebar-inner'); const cur = $('.sidebar-inner a[aria-current]');
  if (inner && cur) inner.scrollTop = Math.max(0, cur.offsetTop - inner.clientHeight / 2);
}

async function initMermaid() {
  const blocks = $$('pre.mermaid');
  if (!blocks.length) return;
  blocks.forEach((b) => { b.dataset.src = b.textContent; });
  let mermaid;
  const render = async () => {
    try {
      mermaid = mermaid || (await import('https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs')).default;
      const dark = document.documentElement.dataset.theme === 'dark';
      mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme: dark ? 'dark' : 'neutral', fontFamily: getComputedStyle(document.body).fontFamily });
      blocks.forEach((b) => { b.removeAttribute('data-processed'); b.textContent = b.dataset.src; });
      await mermaid.run({ nodes: blocks });
    } catch (e) { console.warn('Mermaid failed to load', e); }
  };
  const io = new IntersectionObserver((ents) => { if (ents.some((x) => x.isIntersecting)) { io.disconnect(); render(); } }, { rootMargin: '400px' });
  blocks.forEach((b) => io.observe(b));
  document.addEventListener('aigw:theme', () => { if (mermaid) render(); });
}

/* 04-catalog.js */
// Catalog filters (URL-synced) and home page bits.
function initCatalog() {
  const grid = $('#lab-grid');
  if (!grid || !$('.page-catalog')) return;
  const cards = $$('.lab-card', grid);
  const q = $('#catalog-q');
  const count = $('#catalog-count');
  const empty = $('#catalog-empty');
  const clear = $('#filters-clear');
  const chips = $$('.chip[data-filter]');
  const state = { category: new Set(), level: new Set(), track: new Set(), path: new Set(), status: new Set(), q: '' };

  const params = new URLSearchParams(location.search);
  for (const k of ['category', 'level', 'track', 'path', 'status']) (params.get(k) || '').split(',').filter(Boolean).forEach((v) => state[k].add(v));
  state.q = params.get('q') || '';
  q.value = state.q;

  const apply = (push = true) => {
    const terms = norm(state.q).split(/\s+/).filter(Boolean);
    let n = 0;
    cards.forEach((c) => {
      const d = c.dataset;
      const ok = (!state.category.size || state.category.has(d.category))
        && (!state.level.size || state.level.has(d.level))
        && (!state.track.size || d.tracks.split(' ').some((t) => state.track.has(t)))
        && (!state.path.size || d.paths.split(' ').some((p) => state.path.has(p)))
        && (!state.status.size || state.status.has(d.status))
        && terms.every((t) => norm(d.text).includes(t) || d.lab.startsWith(t));
      c.hidden = !ok; if (ok) n++;
    });
    chips.forEach((ch) => ch.setAttribute('aria-pressed', state[ch.dataset.filter].has(ch.dataset.value)));
    const any = state.q || Object.entries(state).some(([k, v]) => k !== 'q' && v.size);
    count.textContent = any ? `${n} of ${cards.length} labs` : `${cards.length} labs`;
    empty.hidden = n > 0;
    clear.hidden = !any;
    if (push) {
      const u = new URL(location.href);
      for (const k of ['category', 'level', 'track', 'path', 'status']) state[k].size ? u.searchParams.set(k, [...state[k]].join(',')) : u.searchParams.delete(k);
      state.q ? u.searchParams.set('q', state.q) : u.searchParams.delete('q');
      history.replaceState(null, '', u);
    }
  };
  chips.forEach((ch) => ch.addEventListener('click', () => {
    const set = state[ch.dataset.filter];
    set.has(ch.dataset.value) ? set.delete(ch.dataset.value) : set.add(ch.dataset.value);
    apply();
  }));
  let t;
  q.addEventListener('input', () => { clearTimeout(t); t = setTimeout(() => { state.q = q.value.trim(); apply(); }, 120); });
  const reset = () => { for (const k of ['category', 'level', 'track', 'path', 'status']) state[k].clear(); state.q = ''; q.value = ''; apply(); };
  clear.addEventListener('click', reset);
  $$('[data-clear-filters]').forEach((b) => b.addEventListener('click', reset));
  apply(false);
}

// Hero: pause the decorative animation when off-screen.
function initHero() {
  const svg = $('.hero-diagram');
  if (!svg || reduceMotion) return;
  new IntersectionObserver(([e]) => {
    svg.style.setProperty('--play', e.isIntersecting ? 'running' : 'paused');
    $$('*', svg).forEach((n) => { n.style.animationPlayState = e.isIntersecting ? 'running' : 'paused'; });
  }).observe(svg);
}

// Inlined diagrams: pause flows when off-screen.
function initDiagrams() {
  const figs = $$('.figure-svg svg');
  if (!figs.length || reduceMotion || !('IntersectionObserver' in window)) return;
  const io = new IntersectionObserver((ents) => ents.forEach((e) => e.target.classList.toggle('dg-paused', !e.isIntersecting)), { rootMargin: '100px' });
  figs.forEach((f) => io.observe(f));
}

/* 05-widgets-quota.js */
// Widget framework and the quota simulator (token-limit, request-rate, budget).
const WIDGETS = {};
const wdIcon = (name) => IC[name] || IC.sparkle;
function wdShell({ icon, title, desc, kicker = 'Interactive simulation', controls = '', body = '', foot = '' }) {
  return `<div class="wd"><div class="wd-head"><span class="wd-head-icon" aria-hidden="true">${wdIcon(icon)}</span><div><span class="wd-kicker">${kicker}</span><h3 class="wd-title">${title}</h3><p class="wd-desc">${desc}</p></div></div>`
    + (controls ? `<div class="wd-controls">${controls}</div>` : '') + body + (foot ? `<div class="wd-foot">${foot}</div>` : '') + '</div>';
}
function renderWidgets(root = document) {
  $$('.widget[data-widget]', root).forEach((el) => {
    const fn = WIDGETS[el.dataset.widget];
    if (!fn || el.dataset.ready) return;
    let cfg = {};
    try { cfg = JSON.parse(el.dataset.config || '{}'); } catch { console.warn('Bad widget config', el.dataset.config); }
    el.dataset.ready = '1';
    try { fn(el, cfg); } catch (e) { console.error(`Widget ${el.dataset.widget} failed`, e); el.hidden = true; }
  });
}
const wdSeg = (name, opts, sel, multi = false) => `<div class="wd-seg" role="group" data-seg="${name}"${multi ? ' data-multi' : ''}>${opts.map(([v, l]) => `<button type="button" data-v="${v}" aria-pressed="${multi ? sel.includes(v) : sel === v}">${l}</button>`).join('')}</div>`;
const wdField = (label, input, cls = '') => `<label class="wd-field ${cls}"><span>${label}</span>${input}</label>`;
const wdGroup = (label, inner) => `<div class="wd-field"><span>${label}</span>${inner}</div>`;
const wdSelect = (name, opts, sel) => `<select data-k="${name}">${opts.map(([v, l]) => `<option value="${v}"${String(v) === String(sel) ? ' selected' : ''}>${l}</option>`).join('')}</select>`;
const wdRand = (a, b) => a + Math.random() * (b - a);
const wdNow = () => performance.now();
function wdBindSeg(root, onChange) {
  $$('.wd-seg', root).forEach((g) => g.addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b || b.disabled) return;
    if (g.hasAttribute('data-multi')) b.setAttribute('aria-pressed', b.getAttribute('aria-pressed') !== 'true');
    else $$('button', g).forEach((x) => x.setAttribute('aria-pressed', x === b));
    onChange(g.dataset.seg, $$('button[aria-pressed="true"]', g).map((x) => x.dataset.v));
  }));
}
// Runs fn on an interval only while the element is on-screen and the tab is visible.
function wdTicker(el, fn, ms = 250) {
  let vis = false, id = null;
  const sync = () => { const on = vis && !document.hidden; if (on && !id) id = setInterval(fn, ms); if (!on && id) { clearInterval(id); id = null; } };
  new IntersectionObserver(([e]) => { vis = e.isIntersecting; sync(); }).observe(el);
  document.addEventListener('visibilitychange', sync);
}

const QUOTA_CALLERS = [
  { id: 'a', name: 'App A', av: '#0f6cbd', ident: 'API key · app-a', ip: '203.0.113.10' },
  { id: 'b', name: 'App B', av: '#8a3ffc', ident: 'API key · app-b', ip: '203.0.113.10' },
  { id: 'c', name: 'Batch job', av: '#0e7a5f', ident: 'Entra · managed identity', ip: '198.51.100.24' },
];
const SIM_MS = 20000;
const QUOTA_MODES = {
  'token-limit': {
    icon: 'gauge', title: 'Token rate limit simulator', unit: 'tokens', rolling: true,
    desc: 'Send requests from three callers and watch tokens accumulate against the limit. Change the counter dimensions to see who shares a counter.',
    periods: [['minute', 'Per minute', 60], ['hour', 'Per hour', 3600], ['day', 'Per day', 86400]],
    defaults: (c) => ({ limit: +c.limit || 1000, period: c.period || 'minute' }),
    limitLabel: 'Allowed tokens', periodLabel: 'Time period',
    cost: (s) => Math.max(20, Math.round(s.limit * wdRand(0.14, 0.34))),
    fmt: (v) => Math.round(v).toLocaleString('en-US'),
  },
  'request-rate': {
    icon: 'gauge', title: 'Request rate limit simulator', unit: 'calls',
    desc: 'Each request counts as one call. When a counter reaches the limit, the gateway returns 429 until the renewal period resets.',
    periods: [['30', '30 seconds', 30], ['60', '60 seconds', 60], ['120', '2 minutes', 120], ['300', '5 minutes', 300]],
    defaults: (c) => ({ limit: +c.calls || 5, period: String(c.window || 60) }),
    limitLabel: 'Calls', periodLabel: 'Renewal period',
    cost: () => 1, fmt: (v) => String(Math.round(v)),
  },
  budget: {
    icon: 'coins', title: 'Cost limit simulator', unit: 'USD', budget: true,
    desc: 'Each request adds its estimated cost to the counter. Once spend reaches the budget, the gateway blocks requests until the period renews.',
    periods: [['hour', 'Hourly', 3600], ['day', 'Daily', 86400], ['week', 'Weekly', 604800], ['month', 'Monthly', 2592000], ['year', 'Yearly', 31536000]],
    defaults: (c) => ({ limit: +c.amount || 5, period: c.period || 'day' }),
    limitLabel: 'Budget amount ($)', periodLabel: 'Renewal period',
    cost: (s) => +(s.limit * wdRand(0.12, 0.3)).toFixed(2),
    fmt: (v) => `$${v.toFixed(2)}`,
  },
};

function quotaWidget(el, cfg, mode) {
  const M = QUOTA_MODES[mode];
  const s = { ...M.defaults(cfg), dims: ['identity'], override: false };
  const periodSecs = () => M.periods.find((p) => p[0] === s.period)?.[2] || 60;
  const periodName = () => M.periods.find((p) => p[0] === s.period)?.[1] || s.period;
  let counters = new Map(), winStart = wdNow(), log = [];
  const ovAmount = () => +(s.limit * 3).toFixed(2);

  const controls = wdField(M.limitLabel, `<input type="number" min="1" step="${M.budget ? '0.5' : '1'}" value="${s.limit}" data-k="limit">`)
    + wdField(M.periodLabel, wdSelect('period', M.periods, s.period))
    + wdGroup('Counter dimensions', wdSeg('dims', [['identity', 'Caller identity'], ['ip', 'Caller IP address']], s.dims, true))
    + (M.budget ? wdGroup('Overrides', wdSeg('override', [['off', 'None'], ['on', 'Batch job identity']], 'off')) : '');
  const body = `<div class="wd-body"><div class="wd-pane"><p class="wd-pane-title">Callers</p><div class="wd-window"><span data-r="wlabel"></span><span class="wd-window-bar"><span></span></span><b data-r="wleft"></b></div><p class="wd-shared" data-r="shared" hidden></p><div class="wd-callers">${QUOTA_CALLERS.map((c) => `
    <div class="wd-caller" data-caller="${c.id}"><div><div class="wd-caller-name"><span class="wd-avatar" style="--av:${c.av}" aria-hidden="true">${c.name.split(' ').map((w) => w[0]).join('')}</span>${c.name}<span class="wd-tag ov" data-r="ov" hidden>Override</span></div><div class="wd-caller-id" data-r="cid"></div></div>
    <button class="btn btn-secondary btn-sm" type="button" data-send="${c.id}">${IC.play}Send</button>
    <div class="wd-meter"><span class="wd-meter-bar"><span></span></span><span data-r="mval"></span></div></div>`).join('')}</div></div>
    <div class="wd-pane"><p class="wd-pane-title"><span>Gateway responses</span><button class="link-btn" type="button" data-burst>Burst from App A ×5</button></p><div class="wd-log" aria-live="polite"></div></div></div>`;
  const foot = `<span>${IC.info}Simulated time: one ${M.rolling ? 'rolling window' : 'renewal period'} (${periodName().toLowerCase()}) runs in 20 seconds. Values are illustrative.</span><button class="btn btn-ghost btn-sm" type="button" data-reset>${IC.reset}Reset</button>`;
  el.innerHTML = wdShell({ icon: M.icon, title: M.title, desc: M.desc, controls, body, foot });
  const logEl = $('.wd-log', el);

  const callerKey = (c) => {
    if (M.budget && s.override && c.id === 'c') return 'ov:c';
    const parts = [];
    if (s.dims.includes('identity')) parts.push(c.ident);
    if (s.dims.includes('ip')) parts.push(c.ip);
    return parts.join('|') || 'shared';
  };
  const limitFor = (c) => (M.budget && s.override && c.id === 'c' ? ovAmount() : s.limit);
  const used = (key) => {
    const ct = counters.get(key);
    if (!ct) return 0;
    if (M.rolling) { const now = wdNow(); ct.entries = ct.entries.filter((e) => now - e.t < SIM_MS); return ct.entries.reduce((a, e) => a + e.v, 0); }
    return ct.used;
  };
  const add = (key, v) => {
    const ct = counters.get(key) || { entries: [], used: 0 };
    ct.entries.push({ t: wdNow(), v }); ct.used += v; counters.set(key, ct);
  };
  const toReal = (ms) => Math.max(1, Math.ceil((ms / SIM_MS) * periodSecs()));
  const fmtDur = (sec) => sec < 120 ? `${sec}s` : sec < 7200 ? `${Math.round(sec / 60)} min` : sec < 172800 ? `${Math.round(sec / 3600)} h` : `${Math.round(sec / 86400)} days`;
  const retryMs = (key) => {
    if (!M.rolling) return SIM_MS - (wdNow() - winStart);
    const ct = counters.get(key);
    return ct?.entries.length ? SIM_MS - (wdNow() - ct.entries[0].t) : 0;
  };

  function send(cid) {
    const c = QUOTA_CALLERS.find((x) => x.id === cid);
    const key = callerKey(c), lim = limitFor(c), u = used(key);
    let row;
    if (u >= lim) {
      const ra = toReal(retryMs(key));
      row = M.budget
        ? { code: 403, msg: `${c.name} blocked: budget exhausted`, hdr: `LlmCostQuotaExceeded · renews in ~${fmtDur(ra)}` }
        : { code: 429, msg: `${c.name} throttled`, hdr: `Retry-After: ${ra}` };
    } else {
      const v = M.cost(s);
      add(key, v);
      const left = Math.max(0, lim - u - v);
      row = M.budget
        ? { code: 200, msg: `${c.name} · ${M.fmt(v)} <small>estimated cost</small>`, hdr: `Remaining budget ${M.fmt(left)}${u + v > lim ? ` · overshoot ${M.fmt(u + v - lim)}` : ''}` }
        : mode === 'token-limit'
          ? { code: 200, msg: `${c.name} · ${M.fmt(v)} <small>tokens</small>`, hdr: `${M.fmt(left)} tokens left this period` }
          : { code: 200, msg: `${c.name} · 1 call <small>${M.fmt(u + 1)} of ${M.fmt(lim)} this period</small>`, hdr: '' };
    }
    log.unshift(row); log = log.slice(0, 30);
    renderLog(); paint();
  }
  function renderLog() {
    logEl.innerHTML = log.length ? log.map((r) => `<div class="wd-log-row"><span class="wd-code s${r.code}">${r.code}</span><span class="wd-log-msg">${r.msg}</span>${r.hdr ? `<span class="wd-log-hdr">${escHtml(r.hdr)}</span>` : ''}</div>`).join('')
      : '<p class="wd-log-empty">Press Send on a caller to make a request.</p>';
  }
  function paint() {
    const now = wdNow();
    if (!M.rolling && now - winStart >= SIM_MS) { winStart = now; counters = new Map(); }
    // Window indicator
    let p, left;
    if (M.rolling) {
      const oldest = Math.min(...[...counters.values()].flatMap((ct) => ct.entries.map((e) => e.t)).filter((t) => now - t < SIM_MS), Infinity);
      p = oldest === Infinity ? 0 : 1 - (now - oldest) / SIM_MS;
      left = oldest === Infinity ? '' : `${fmtDur(toReal(SIM_MS - (now - oldest)))}`;
      $('[data-r="wlabel"]', el).textContent = oldest === Infinity ? 'Rolling window: no recent usage' : 'Oldest usage frees up in';
    } else {
      p = (now - winStart) / SIM_MS;
      left = fmtDur(toReal(SIM_MS - (now - winStart)));
      $('[data-r="wlabel"]', el).textContent = 'Period renews in';
    }
    $('.wd-window-bar span', el).style.setProperty('--p', Math.max(0, Math.min(1, p)).toFixed(3));
    $('[data-r="wleft"]', el).textContent = left;
    // Callers
    const keys = QUOTA_CALLERS.map(callerKey);
    QUOTA_CALLERS.forEach((c, i) => {
      const row = $(`[data-caller="${c.id}"]`, el);
      const lim = limitFor(c), u = used(keys[i]), r = Math.min(1, u / lim);
      const m = $('.wd-meter', row);
      m.classList.toggle('warn', r >= 0.75 && r < 1); m.classList.toggle('full', r >= 1);
      $('.wd-meter-bar span', m).style.setProperty('--p', r.toFixed(3));
      $('[data-r="mval"]', row).textContent = `${M.fmt(u)} / ${M.fmt(lim)}`;
      row.classList.toggle('blocked', u >= lim);
      const ov = M.budget && s.override && c.id === 'c';
      $('[data-r="ov"]', row).hidden = !ov;
      $('[data-r="cid"]', row).textContent = [s.dims.includes('identity') || ov ? c.ident : null, s.dims.includes('ip') && !ov ? c.ip : null].filter(Boolean).join(' · ') || 'Shared counter';
    });
    const shared = $('[data-r="shared"]', el);
    const groups = {};
    keys.forEach((k, i) => (groups[k] = groups[k] || []).push(QUOTA_CALLERS[i].name));
    const multi = Object.values(groups).filter((g) => g.length > 1);
    shared.hidden = !multi.length;
    if (multi.length) shared.textContent = keys.every((k) => k === 'shared')
      ? 'No counter dimension selected: all callers share one counter.'
      : Object.entries(groups).filter(([, g]) => g.length > 1).map(([k, g]) => `${g.join(' and ')} share ${k === 'shared' ? 'one counter because no counter dimension is selected' : 'a counter because they call from the same NAT IP address'}.`).join(' ');
  }
  wdBindSeg(el, (seg, vals) => {
    if (seg === 'dims') s.dims = vals;
    if (seg === 'override') {
      s.override = vals[0] === 'on';
      // Caller IP address can't be a counter dimension while overrides exist.
      const ipBtn = $('[data-seg="dims"] [data-v="ip"]', el);
      ipBtn.disabled = s.override; ipBtn.title = s.override ? 'Caller IP address cannot be used while overrides exist' : '';
      if (s.override) { ipBtn.setAttribute('aria-pressed', 'false'); s.dims = s.dims.filter((d) => d !== 'ip'); }
    }
    reset();
  });
  $$('[data-k]', el).forEach((inp) => inp.addEventListener('change', () => {
    if (inp.dataset.k === 'limit') { const v = +inp.value; if (v > 0) s.limit = v; else inp.value = s.limit; } else s[inp.dataset.k] = inp.value;
    $('.wd-foot span', el).lastChild.textContent = `Simulated time: one ${M.rolling ? 'rolling window' : 'renewal period'} (${periodName().toLowerCase()}) runs in 20 seconds. Values are illustrative.`;
    reset();
  }));
  function reset() { counters = new Map(); winStart = wdNow(); log = []; renderLog(); paint(); }
  el.addEventListener('click', (e) => {
    const b = e.target.closest('[data-send]');
    if (b) return send(b.dataset.send);
    if (e.target.closest('[data-reset]')) return reset();
    if (e.target.closest('[data-burst]')) for (let i = 0; i < 5; i++) setTimeout(() => send('a'), i * 140);
  });
  renderLog(); paint();
  wdTicker(el, paint);
}
WIDGETS['token-limit'] = (el, c) => quotaWidget(el, c, 'token-limit');
WIDGETS['request-rate'] = (el, c) => quotaWidget(el, c, 'request-rate');
WIDGETS.budget = (el, c) => quotaWidget(el, c, 'budget');

/* 06-widgets.js */
// Widgets: request lifecycle, alias retarget, alias routing, tool patterns, policy layers.
const LC_STAGES = [
  ['client', 'Client app', 'SDK or agent', 'app'],
  ['auth', 'Auth', 'key or Entra', 'key', 1],
  ['ip', 'IP filter', 'allow / deny', 'globe', 1],
  ['rate', 'Request rate', 'calls / window', 'filter', 1],
  ['tokens', 'Token limit', 'TPM / quota', 'gauge', 1],
  ['cost', 'Cost limit', 'budget', 'coins', 1],
  ['safety', 'Content safety', 'prompt', 'shield', 1],
  ['alias', 'Alias routing', 'alias → model', 'route', 1],
  ['backend', 'Backend model', 'managed identity', 'models'],
  ['screen', 'Response', 'screening', 'eye', 1],
  ['telemetry', 'Telemetry', 'Monitoring', 'chart', 1],
];
const LC_SCENARIOS = [
  { id: 'ok', label: 'Happy path', code: 200, dc: 'var(--success)', text: '<strong>200 OK.</strong> Every policy passed, the alias resolved to its backend model, and the gateway called it with its managed identity. Tokens, cost, and policy outcomes are recorded for Monitoring.' },
  { id: 'auth', label: 'Missing key', code: 401, fail: 'auth', dc: 'var(--danger)', text: '<strong>401 Unauthorized.</strong> No valid API key or Entra token. The gateway rejects the request before any policy runs or any backend is called.' },
  { id: 'ip', label: 'Blocked IP', code: 403, fail: 'ip', dc: 'var(--danger)', text: '<strong>403 Forbidden.</strong> The caller\'s address doesn\'t match the IP filter. Nothing reaches the model.' },
  { id: 'rate', label: 'Too many requests', code: 429, fail: 'rate', dc: 'var(--warning)', text: '<strong>429 Too Many Requests.</strong> The caller used all calls for this renewal period. The <code>Retry-After</code> header says when to try again.' },
  { id: 'tokens', label: 'Token limit hit', code: 429, fail: 'tokens', dc: 'var(--warning)', text: '<strong>429 Too Many Requests.</strong> The caller\'s token counter is spent for the window. Clients should back off using <code>Retry-After</code>.' },
  { id: 'cost', label: 'Over budget', code: 403, fail: 'cost', dc: 'var(--danger)', text: '<strong>403 <code>LlmCostQuotaExceeded</code>.</strong> Spend reached the cost limit for this renewal period, so the gateway stops forwarding requests until it renews.' },
  { id: 'safety', label: 'Harmful prompt', code: 400, fail: 'safety', dc: 'var(--warning)', text: '<strong>400 Bad Request.</strong> Content safety flagged the prompt at or above the configured severity. The model never sees it.' },
];
const LC_FOCUS = { auth: 'auth', ipFilter: 'ip', requestRate: 'rate', tokenLimit: 'tokens', costLimit: 'cost', contentSafety: 'safety', alias: 'alias', telemetry: 'telemetry', backend: 'backend' };

WIDGETS['request-lifecycle'] = (el, cfg) => {
  const focus = LC_FOCUS[cfg.focus] || null;
  let cur = LC_SCENARIOS.find((x) => x.fail === focus) || LC_SCENARIOS[0];
  let timer = null, played = false;
  const pills = `<div class="wd-scenarios" role="group" aria-label="Scenario">${LC_SCENARIOS.map((x) => `<button type="button" class="wd-scenario" data-sc="${x.id}" aria-pressed="${x === cur}" style="--dc:${x.dc}"><span class="wd-dot"></span>${x.label}</button>`).join('')}</div>`;
  const pipe = `<div class="wd-pipe">${LC_STAGES.map(([id, l, sub, ic, gw]) => `<div class="wd-stage${gw ? ' gw' : ''}${id === focus ? ' focus' : ''}" data-st="${id}"><span class="wd-node">${IC[ic]}</span><span class="wd-stage-label">${l}</span><span class="wd-stage-sub">${sub}</span></div>`).join('')}</div>`;
  const body = pills + pipe + `<div class="wd-zone"><span><i></i>Runs in the AI gateway</span></div><div class="wd-result" aria-live="polite"><span class="wd-code">…</span><p></p></div>`;
  const foot = `<span>${IC.info}Pick a scenario to follow one request. Stage order is simplified for illustration.</span><button class="btn btn-ghost btn-sm" type="button" data-replay>${IC.reset}Replay</button>`;
  el.innerHTML = wdShell({ icon: 'route', title: 'Follow a request through the gateway', desc: 'Every call is authenticated, checked against policies, routed by alias to a backend model, then logged. A blocked request never reaches the backend.', body, foot });
  const stages = $$('.wd-stage', el);
  const result = $('.wd-result', el);

  function play() {
    clearTimeout(timer);
    stages.forEach((s) => s.classList.remove('active', 'pass', 'fail', 'skip', 'reached'));
    $('.wd-code', result).className = 'wd-code'; $('.wd-code', result).textContent = '…';
    $('p', result).innerHTML = '<span class="muted">Request in flight…</span>';
    const failIdx = cur.fail ? stages.findIndex((s) => s.dataset.st === cur.fail) : -1;
    const tIdx = stages.length - 1;
    const seq = [];
    stages.forEach((s, i) => {
      if (failIdx >= 0 && i > failIdx && i < tIdx) return;
      seq.push(i);
    });
    const step = (k) => {
      const i = seq[k];
      if (k > 0) { const p = stages[seq[k - 1]]; p.classList.remove('active'); if (!p.classList.contains('fail')) p.classList.add('pass'); }
      if (i === undefined) return finish();
      const s = stages[i];
      s.classList.add('reached');
      if (i === failIdx) { s.classList.add('fail'); stages.forEach((x, j) => { if (j > failIdx && j < tIdx) x.classList.add('skip'); }); }
      else s.classList.add('active');
      timer = setTimeout(() => step(k + 1), reduceMotion ? 0 : i === failIdx ? 650 : 360);
    };
    const finish = () => {
      $('.wd-code', result).className = `wd-code s${cur.code}`;
      $('.wd-code', result).textContent = cur.code;
      $('p', result).innerHTML = cur.text;
    };
    step(0);
  }
  el.addEventListener('click', (e) => {
    const b = e.target.closest('[data-sc]');
    if (b) { cur = LC_SCENARIOS.find((x) => x.id === b.dataset.sc); $$('[data-sc]', el).forEach((x) => x.setAttribute('aria-pressed', x === b)); play(); }
    if (e.target.closest('[data-replay]')) play();
  });
  new IntersectionObserver(([en], io) => { if (en.isIntersecting && !played) { played = true; io.disconnect(); play(); } }, { threshold: 0.4 }).observe(el);
};

WIDGETS['alias-retarget'] = (el, cfg) => {
  const alias = cfg.alias || 'chat';
  const targets = cfg.targets || [
    { provider: 'Microsoft Foundry', model: 'gpt-6-luna', note: 'Lower cost', logo: 'microsoft-foundry' },
    { provider: 'Microsoft Foundry', model: 'gpt-6.1-sol', note: 'Higher quality', logo: 'microsoft-foundry' },
    { provider: 'Azure OpenAI', model: 'gpt-6-sol', note: 'Existing deployment', logo: 'azure-openai' },
  ];
  let sel = 0, moves = 0;
  const body = `<div class="wd-alias"><div class="wd-client"><pre>response = client.responses.create(
    model=<b>"${escHtml(alias)}"</b>,
    input="Summarize this ticket",
)</pre><p class="wd-client-cap">${IC.check}<span data-r="cap">Client code: unchanged</span></p></div>
    <div class="wd-alias-hub"><svg aria-hidden="true"><path data-in></path>${targets.map((_, i) => `<path data-p="${i}"></path>`).join('')}</svg><div class="wd-alias-chip"><small>Alias</small>${escHtml(alias)}</div></div>
    <div class="wd-targets" role="group" aria-label="Backend model for alias ${escHtml(alias)}">${targets.map((t, i) => `<button type="button" class="wd-target" data-t="${i}" aria-pressed="${i === sel}"><img src="${D.rel}labs/assets/providers/${t.logo}.png" alt="" width="22" height="22"><span><b>${escHtml(t.model)}</b><span>${escHtml(t.provider)} · ${escHtml(t.note)}</span></span></button>`).join('')}</div></div>`;
  const foot = `<span data-r="msg">${IC.info}Choose a different backend model. The alias name, client code, and alias policies stay the same.</span>`;
  el.innerHTML = wdShell({ icon: 'route', title: 'Retarget an alias', desc: `Clients call the alias <code>${escHtml(alias)}</code>, not a model. Point it at another backend model and every client follows on its next request.`, body, foot });
  const hub = $('.wd-alias-hub', el), svg = $('svg', hub);
  function draw() {
    const hr = hub.getBoundingClientRect();
    if (!hr.width) return;
    svg.setAttribute('viewBox', `0 0 ${hr.width} ${hr.height}`);
    const cy = hr.height / 2, w = hr.width;
    $('[data-in]', svg).setAttribute('d', `M0 ${cy} H${w / 2}`);
    $('[data-in]', svg).classList.add('on');
    $$('[data-t]', el).forEach((b, i) => {
      const r = b.getBoundingClientRect();
      const y = Math.max(4, Math.min(hr.height - 4, r.top + r.height / 2 - hr.top));
      const p = $(`[data-p="${i}"]`, svg);
      p.setAttribute('d', `M${w / 2} ${cy} C${w * 0.78} ${cy}, ${w * 0.7} ${y}, ${w} ${y}`);
      p.classList.toggle('on', i === sel);
    });
  }
  el.addEventListener('click', (e) => {
    const b = e.target.closest('[data-t]');
    if (!b || +b.dataset.t === sel) return;
    sel = +b.dataset.t; moves++;
    $$('[data-t]', el).forEach((x) => x.setAttribute('aria-pressed', +x.dataset.t === sel));
    const t = targets[sel];
    $('[data-r="msg"]', el).innerHTML = `${IC.check}Alias <code>${escHtml(alias)}</code> now routes to <strong>${escHtml(t.model)}</strong> (${escHtml(t.provider)}). Clients changed: 0. Alias policies kept: all. Retargets so far: ${moves}.`;
    $('[data-r="cap"]', el).textContent = `Client code: unchanged after ${moves} retarget${moves > 1 ? 's' : ''}`;
    draw();
  });
  new ResizeObserver(draw).observe(el);
  draw();
};

// Priority and weight routing: the lowest priority number wins, weights split traffic inside that tier.
WIDGETS['alias-routing'] = (el, cfg) => {
  const alias = cfg.alias || 'chat', N = 20;
  const COL = ['var(--cat-violet)', 'var(--cat-magenta)', 'var(--cat-azure)', 'var(--cat-cyan)', 'var(--cat-amber)'];
  const rows = (cfg.backends || [
    { model: 'gpt-6-luna', provider: 'Microsoft Foundry', logo: 'microsoft-foundry', priority: 0, weight: 80 },
    { model: 'gpt-6.1-sol', provider: 'Microsoft Foundry', logo: 'microsoft-foundry', priority: 0, weight: 20 },
    { model: 'gpt-6-sol', provider: 'Azure OpenAI', logo: 'azure-openai', priority: 1, weight: 1 },
  ]).map((b, i) => ({ ...b, priority: String(b.priority ?? 0), weight: String(b.weight ?? 1), c: COL[i % COL.length] }));
  const presets = cfg.presets || [
    ['canary', 'Canary 80/20', [[0, 80], [0, 20], [1, 1]]],
    ['ab', 'A/B 50/50', [[0, 50], [0, 50], [1, 1]]],
    ['prefer', 'Prefer by priority', [[0, 1], [1, 1], [2, 1]]],
  ];
  const bad = (v, k) => {
    const ok = /^\d+$/.test(String(v).trim()) && +v >= (k === 'weight' ? 1 : 0) && +v <= 100;
    return ok ? null : k === 'weight' ? 'Weight must be a whole number from 1 to 100.' : 'Priority must be a whole number from 0 to 100.';
  };
  const pct = (s) => (s > 0 && s < 0.001 ? '<0.1%' : `${+(s * 100).toFixed(1)}%`);
  const controls = wdGroup('Scenario', wdSeg('preset', presets.map(([v, l]) => [v, l]), presets[0][0]));
  const table = `<div class="wr-table" role="table" aria-label="Backend models of alias ${escHtml(alias)}"><div class="wr-row wr-head" role="row"><span role="columnheader">Backend model</span><span role="columnheader">Priority</span><span role="columnheader">Weight</span><span role="columnheader">Share within priority</span></div>`
    + rows.map((r, i) => `<div class="wr-row" role="row" data-i="${i}" style="--c:${r.c}"><span class="wr-model" role="cell"><i></i><img src="${D.rel}labs/assets/providers/${r.logo}.png" alt="" width="20" height="20"><span><b>${escHtml(r.model)}</b><small>${escHtml(r.provider)}</small></span></span>`
      + ['priority', 'weight'].map((k) => `<span role="cell"><input type="number" inputmode="numeric" step="1" min="${k === 'weight' ? 1 : 0}" max="100" data-k="${k}" data-i="${i}" value="${r[k]}" aria-label="${k === 'weight' ? 'Weight' : 'Priority'} for ${escHtml(r.model)}"></span>`).join('')
      + `<span class="wr-share" role="cell"><span class="wr-bar"><span></span></span><b data-r="share"></b><em data-r="tier"></em></span></div>`).join('') + '</div>';
  const body = `<div class="wr">${table}<p class="wr-err" role="alert" hidden></p>
    <div class="wr-run"><div><p class="wd-pane-title">Next ${N} requests with <code>"model": "${escHtml(alias)}"</code></p><div class="wr-dots" aria-hidden="true">${'<span></span>'.repeat(N)}</div></div><div class="wr-tally" aria-live="polite"></div></div></div>`;
  const foot = `<span>${IC.info}Shares match the alias settings. The gateway's exact request order can differ.</span><button class="btn btn-ghost btn-sm" type="button" data-send>${IC.play}Send ${N} requests</button>`;
  el.innerHTML = wdShell({ icon: 'route', title: 'Route one alias by priority and weight', desc: `Clients keep calling <code>${escHtml(alias)}</code>. The gateway uses the backend models with the lowest priority number, then splits traffic among them in proportion to their weights.`, controls, body, foot });
  const dots = $$('.wr-dots span', el);
  let timer = null;

  function plan() {
    const err = rows.flatMap((r) => [bad(r.priority, 'priority'), bad(r.weight, 'weight')]).find(Boolean);
    if (err) return { err };
    const top = Math.min(...rows.map((r) => +r.priority));
    const tier = rows.filter((r) => +r.priority === top);
    // Smooth weighted round robin: an even spread that converges on the exact weights.
    const tot = tier.reduce((a, r) => a + +r.weight, 0), cur = tier.map(() => 0), seq = [];
    for (let k = 0; k < N; k++) {
      let bi = 0;
      tier.forEach((r, i) => { cur[i] += +r.weight; if (cur[i] > cur[bi]) bi = i; });
      cur[bi] -= tot; seq.push(tier[bi]);
    }
    return { top, seq };
  }
  function render(animate) {
    clearTimeout(timer);
    const p = plan();
    $('.wr-err', el).hidden = !p.err;
    $('.wr-err', el).textContent = p.err || '';
    el.classList.toggle('wr-invalid', !!p.err);
    rows.forEach((r, i) => {
      const row = $(`.wr-row[data-i="${i}"]`, el);
      ['priority', 'weight'].forEach((k) => $(`[data-k="${k}"]`, row).setAttribute('aria-invalid', !!bad(r[k], k)));
      const same = rows.filter((x) => !bad(x.priority, 'priority') && x.priority.trim() === r.priority.trim());
      const sum = same.reduce((a, x) => a + (bad(x.weight, 'weight') ? 0 : +x.weight), 0);
      const share = p.err ? 0 : +r.weight / sum;
      const active = !p.err && +r.priority === p.top;
      row.classList.toggle('active', active);
      $('.wr-bar span', row).style.setProperty('--p', share);
      $('[data-r="share"]', row).textContent = p.err ? '--' : pct(share);
      $('[data-r="tier"]', row).textContent = p.err ? '' : active ? 'Preferred tier' : 'Lower preference';
    });
    if (p.err) { dots.forEach((d) => { d.style.removeProperty('--c'); d.className = ''; }); $('.wr-tally', el).innerHTML = ''; return; }
    const counts = new Map();
    const show = (k) => {
      if (k >= N) return;
      const r = p.seq[k];
      dots[k].style.setProperty('--c', r.c); dots[k].className = 'on'; dots[k].title = r.model;
      counts.set(r, (counts.get(r) || 0) + 1);
      $('.wr-tally', el).innerHTML = rows.map((x) => `<span style="--c:${x.c}"><i></i>${escHtml(x.model)}<b>${counts.get(x) || 0}</b></span>`).join('');
      if (animate && !reduceMotion) timer = setTimeout(() => show(k + 1), 70); else show(k + 1);
    };
    dots.forEach((d) => { d.className = ''; d.style.removeProperty('--c'); });
    show(0);
  }
  wdBindSeg(el, (seg, v) => {
    const ps = presets.find((x) => x[0] === v[0]);
    if (!ps) return;
    rows.forEach((r, i) => { const [pr, w] = ps[2][i] || [9, 1]; r.priority = String(pr); r.weight = String(w); $(`[data-k="priority"][data-i="${i}"]`, el).value = r.priority; $(`[data-k="weight"][data-i="${i}"]`, el).value = r.weight; });
    render(true);
  });
  $$('input[data-k]', el).forEach((inp) => inp.addEventListener('input', () => {
    rows[+inp.dataset.i][inp.dataset.k] = inp.value;
    $$('.wd-seg button', el).forEach((b) => b.setAttribute('aria-pressed', 'false'));
    render(false);
  }));
  $('[data-send]', el).addEventListener('click', () => render(true));
  render(false);
  new IntersectionObserver(([en], io) => { if (en.isIntersecting) { io.disconnect(); render(true); } }, { threshold: 0.4 }).observe(el);
};

const globRe = (g) => new RegExp(`^${g.trim().replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*').replace(/\?/g, '.')}$`);
const splitPats = (v) => (Array.isArray(v) ? v : String(v || '').split(/[,\n]/)).map((x) => x.trim()).filter(Boolean);
WIDGETS['tool-patterns'] = (el, cfg) => {
  const tools = cfg.tools || ['aigw-github_github_list_issues', 'aigw-github_github_get_issue', 'aigw-github_github_create_issue', 'aigw-github_github_delete_repository',
    'learn_microsoft_docs_search', 'learn_microsoft_docs_fetch', 'crm_get_customer', 'crm_update_customer', 'crm_delete_customer'];
  const s = { mode: 'patterns', allow: splitPats(cfg.allow || ['*']).join(', '), block: splitPats(cfg.block || ['*_delete_*']).join(', ') };
  const controls = wdGroup('Tool availability', wdSeg('mode', [['all', 'Allow all tools'], ['patterns', 'Use name patterns'], ['server', 'Block the MCP server']], s.mode))
    + wdField('Allowed patterns', `<input type="text" data-k="allow" value="${escHtml(s.allow)}" spellcheck="false" placeholder="aigw-github_github_*">`, 'grow')
    + wdField('Blocked tool patterns', `<input type="text" data-k="block" value="${escHtml(s.block)}" spellcheck="false" placeholder="*_delete_*">`, 'grow');
  const body = `<div class="wd-body"><div class="wd-pane"><p class="wd-pane-title">Backend tools</p><div class="wd-tools"></div><div class="wd-summary"></div></div><div class="wd-pane"><p class="wd-pane-title">What clients get from tools/list</p><div class="wd-client"><pre data-r="list"></pre></div><p class="wd-note">${IC.info} Use <code>*</code> for any characters and <code>?</code> for one. Blocked patterns win over allowed ones. Separate patterns with commas.</p></div></div>`;
  el.innerHTML = wdShell({ icon: 'tools', title: 'Try tool availability patterns', desc: 'Decide which backend tools an MCP server exposes. Names are namespaced per backend, so one pattern can cover a whole backend or a single verb.', controls, body });
  const list = $('.wd-tools', el);
  function evalAll() {
    const allow = splitPats(s.allow), block = splitPats(s.block);
    let ok = 0, bl = 0, hid = 0;
    const rows = tools.map((t) => {
      let cls = 'ok', why = 'Allowed', icon = IC.ok;
      const b = block.find((p) => { try { return globRe(p).test(t); } catch { return false; } });
      const a = allow.find((p) => { try { return globRe(p).test(t); } catch { return false; } });
      if (s.mode === 'server') { cls = 'blocked'; why = 'Server blocked'; icon = IC.lock; }
      else if (b) { cls = 'blocked'; why = `Blocked by ${b}`; icon = IC.x; }
      else if (s.mode === 'patterns' && !a) { cls = 'hidden-tool'; why = 'Not allowed'; icon = IC.minus; }
      else if (s.mode === 'patterns') why = `Allowed by ${a}`;
      cls === 'ok' ? ok++ : cls === 'blocked' ? bl++ : hid++;
      return { t, cls, why, icon };
    });
    list.innerHTML = rows.map((r) => `<div class="wd-tool ${r.cls}">${r.icon}<span class="wd-tool-name" title="${escHtml(r.t)}">${escHtml(r.t)}</span><span class="wd-tool-why">${escHtml(r.why)}</span></div>`).join('');
    $('.wd-summary', el).innerHTML = `<span><b>${ok}</b> available</span><span><b>${bl}</b> blocked</span><span><b>${hid}</b> not allowed</span>`;
    const vis = rows.filter((r) => r.cls === 'ok');
    $('[data-r="list"]', el).textContent = s.mode === 'server'
      ? 'HTTP 403\n// The MCP server is blocked.\n// No tools are reachable.'
      : `{\n  "tools": [${vis.map((r) => `\n    { "name": "${r.t}" }`).join(',')}${vis.length ? '\n  ' : ''}]\n}`;
    $$('[data-k]', el).forEach((i) => { i.disabled = s.mode === 'server' || (i.dataset.k === 'allow' && s.mode === 'all'); });
  }
  wdBindSeg(el, (seg, v) => { s.mode = v[0]; evalAll(); });
  $$('[data-k]', el).forEach((i) => i.addEventListener('input', () => { s[i.dataset.k] = i.value; evalAll(); }));
  evalAll();
};

WIDGETS['policy-layers'] = (el) => {
  const L = [
    { id: 'gw', name: 'Gateway', sub: 'All compatible assets, including future ones', icon: 'globe', c: 'var(--cat-azure)',
      pols: [['IP filter', 'filter', ['model', 'mcp']], ['Content safety', 'shield', ['model', 'mcp']], ['Cost limit', 'coins', ['model']]] },
    { id: 'chat', name: 'Alias chat', sub: 'Individual asset', icon: 'route', c: 'var(--cat-violet)', pols: [['Token rate limit', 'gauge', ['model']]] },
    { id: 'batch', name: 'Alias chat-batch', sub: 'Individual asset', icon: 'route', c: 'var(--cat-magenta)', pols: [['Token rate limit', 'gauge', ['model']], ['Cost limit', 'coins', ['model']]] },
    { id: 'model', name: 'Backend model gpt-6-luna', sub: 'Applies through every alias', icon: 'models', c: 'var(--cat-green)', pols: [['Request rate limit', 'filter', ['model']]] },
    { id: 'mcp', name: 'MCP server github-tools', sub: 'Individual asset', icon: 'tools', c: 'var(--cat-amber)', pols: [['Request rate limit', 'filter', ['mcp']], ['Agent 365 tool threat protection', 'shield', ['mcp']]] },
  ];
  const T = {
    chat: { label: 'Alias chat', kind: 'model', layers: ['gw', 'chat', 'model'], note: 'Both aliases point to the same backend model, so its request rate limit applies to each. Alias policies apply only to calls through that alias.' },
    batch: { label: 'Alias chat-batch', kind: 'model', layers: ['gw', 'batch', 'model'], note: 'Same backend model as chat, but different alias policies: a separate token limit and budget for batch traffic.' },
    mcp: { label: 'MCP tool call', kind: 'mcp', layers: ['gw', 'mcp'], note: 'Cost limit only applies to models, so the gateway-scope cost limit is skipped for tool calls. IP filter and content safety still apply.' },
  };
  let cur = 'chat';
  const controls = wdGroup('Send a request to', wdSeg('target', Object.entries(T).map(([k, v]) => [k, v.label]), cur));
  const body = `<div class="wd-body"><div class="wd-pane"><p class="wd-pane-title">Policy scopes</p><div class="wd-layers">${L.map((l) => `<div class="wd-layer" data-l="${l.id}" style="--lc:${l.c}"><div class="wd-layer-head">${IC[l.icon]}<span>${l.name}</span><small>${l.sub}</small></div><div class="wd-pols">${l.pols.map(([n, ic]) => `<span class="wd-pol">${IC[ic]}${n}</span>`).join('')}</div></div>`).join('')}</div></div>
    <div class="wd-pane"><p class="wd-pane-title">Policies evaluated for this request</p><div class="wd-eval"></div><p class="wd-note" data-r="note"></p></div></div>`;
  const foot = `<span>${IC.info}Every applicable policy is evaluated. If any one blocks, the request is rejected before the backend is called.</span>`;
  el.innerHTML = wdShell({ icon: 'layers', title: 'Which policies apply?', desc: 'Policies attach at gateway scope or to individual assets. Pick a request to see which layers take part.', controls, body, foot });
  function paint() {
    const t = T[cur];
    const rows = [];
    L.forEach((l) => {
      const on = t.layers.includes(l.id);
      const node = $(`[data-l="${l.id}"]`, el);
      node.classList.toggle('on', on); node.classList.toggle('off', !on);
      if (on) l.pols.forEach(([n, , kinds]) => { if (kinds.includes(t.kind)) rows.push(`<div class="wd-eval-row">${n}<small>${l.name}</small></div>`); });
    });
    $('.wd-eval', el).innerHTML = rows.join('');
    $('[data-r="note"]', el).textContent = t.note;
  }
  wdBindSeg(el, (seg, v) => { cur = v[0]; paint(); });
  paint();
};

// Streaming usage: what a streaming client receives versus what the gateway counts.
WIDGETS['stream-usage'] = (el, cfg) => {
  const LIMIT = cfg.limit || 1000, WIN = cfg.window || 30, alias = cfg.alias || 'gpt-6-luna-stream';
  const REPLY = cfg.reply || 'Streaming sends the reply in small chunks as the model writes it, so people see words right away instead of waiting for the full answer.';
  const words = REPLY.match(/\S+\s*/g);
  const fmt = (n) => n.toLocaleString('en-US');
  const controls = wdGroup('Client sets <code>stream_options.include_usage</code>', wdSeg('usage', [['off', 'Not set'], ['on', 'true']], 'off'));
  const body = `<div class="wd-body"><div class="wd-pane"><p class="wd-pane-title"><span>Client receives</span><span class="ws-status" data-r="status"></span></p>
    <code class="ws-req" data-r="req"></code><pre class="ws-sse" data-r="sse" tabindex="0" aria-label="Server-sent events the client receives"></pre>
    <div class="ws-reply"><span class="ws-label">Reply so far</span><p data-r="reply"></p></div><p class="ws-usage" data-r="usage" aria-live="polite"></p></div>
    <div class="wd-pane"><p class="wd-pane-title"><span>Gateway counts</span><button class="link-btn" type="button" data-burst>Send until throttled</button></p>
    <div class="ws-limit"><div class="ws-limit-head"><code>${escHtml(alias)}</code><span>Token limit: ${fmt(LIMIT)} per minute</span></div>
    <div class="wd-meter"><span class="wd-meter-bar"><span></span></span><b data-r="used"></b></div>
    <div class="wd-window"><span>Window</span><span class="wd-window-bar"><span></span></span><b data-r="left"></b></div></div>
    <div class="wd-log" aria-live="polite"></div></div></div>`;
  const foot = `<span>${IC.info}Simulated: one minute runs in ${WIN} seconds. Token counts are illustrative.</span><span class="ws-actions"><button class="btn btn-ghost btn-sm" type="button" data-reset>${IC.reset}Reset</button><button class="btn btn-primary btn-sm" type="button" data-send>${IC.play}Send a streaming request</button></span>`;
  el.innerHTML = wdShell({ icon: 'stream', title: 'Stream a reply and watch the gateway count it', desc: 'The client sees chunks as they arrive, and a usage chunk only when it asks for one. The gateway counts every stream either way, and a full token limit returns a JSON 429 before any stream starts.', controls, body, foot });
  const r = (k) => $(`[data-r="${k}"]`, el);
  const sse = r('sse'), logEl = $('.wd-log', el);
  let usage = false, used = 0, start = wdNow(), n = 0, busy = false, log = [];
  const left = () => Math.max(0, WIN - (wdNow() - start) / 1000);
  function roll() { if (left() <= 0) { used = 0; start = wdNow(); } }
  function paint() {
    roll();
    const p = Math.min(1, used / LIMIT), m = $('.wd-meter', el);
    $('.wd-meter-bar span', m).style.setProperty('--p', p);
    m.classList.toggle('warn', p >= 0.7 && p < 1); m.classList.toggle('full', p >= 1);
    r('used').textContent = `${fmt(used)} / ${fmt(LIMIT)}`;
    $('.wd-window-bar span', el).style.setProperty('--p', 1 - left() / WIN);
    r('left').textContent = `${Math.ceil(left())}s left`;
  }
  function paintLog() {
    logEl.innerHTML = log.length ? log.map((x) => `<div class="wd-log-row"><span class="wd-code s${x.code}">${x.code}</span><span class="wd-log-msg">${x.msg}</span><span class="wd-log-hdr">${escHtml(x.hdr)}</span></div>`).join('')
      : '<p class="wd-log-empty">Send a streaming request to see what the gateway counts.</p>';
  }
  function paintReq() {
    r('req').textContent = JSON.stringify({ model: alias, stream: true, ...(usage ? { stream_options: { include_usage: true } } : {}) });
  }
  function idle() {
    r('status').innerHTML = '';
    sse.innerHTML = '<span class="ws-l ws-k-hint">Press Send a streaming request.</span>';
    r('reply').textContent = ''; r('usage').className = 'ws-usage'; r('usage').textContent = '';
  }
  const line = (txt, kind) => { sse.insertAdjacentHTML('beforeend', `<span class="ws-l ws-k-${kind}">${escHtml(txt)}</span>`); sse.scrollTop = sse.scrollHeight; };
  const wait = (ms) => new Promise((res) => setTimeout(res, reduceMotion ? 0 : ms));
  async function send(fast = false) {
    if (busy) return false;
    paint(); n++;
    sse.innerHTML = ''; r('reply').textContent = '';
    const u = r('usage');
    if (used >= LIMIT) {
      const after = Math.max(1, Math.ceil(left()));
      r('status').innerHTML = '<span class="wd-code s429">429</span>application/json';
      ['HTTP/2 429', 'content-type: application/json', `retry-after: ${after}`, ''].forEach((t) => line(t, 'hdr'));
      line(`{ "statusCode": 429, "message": "Token limit is exceeded. Try again in ${after} seconds." }`, 'err');
      r('reply').innerHTML = '<span class="ws-none">No reply. The gateway rejected the request before streaming.</span>';
      u.className = 'ws-usage err'; u.textContent = `No stream started. Wait ${after} seconds (Retry-After), then try again.`;
      log.unshift({ code: 429, msg: `Request ${n} · <b>throttled</b> <small>before the stream</small>`, hdr: `JSON body, retry-after: ${after}` });
      paintLog();
      return false;
    }
    busy = true; el.classList.add('ws-busy');
    $$('[data-send], [data-burst]', el).forEach((b) => { b.disabled = true; });
    const withUsage = usage, prompt = 14 + Math.round(wdRand(0, 6)), completion = Math.round(wdRand(170, 240));
    const reasoning = completion - words.length - 2;
    r('status').innerHTML = '<span class="wd-code s200">200</span>text/event-stream';
    u.className = 'ws-usage'; u.textContent = 'Streaming…';
    $('.ws-reply', el).classList.add('live');
    const step = fast ? 8 : 70;
    line('data: {"choices":[],"prompt_filter_results":[…]}', 'filter'); await wait(step * 2);
    line('data: {"choices":[{"delta":{"role":"assistant","content":""}}]}', 'role'); await wait(step * 2);
    for (const w of words) {
      line(`data: {"choices":[{"delta":{"content":${JSON.stringify(w)}}}]}`, 'delta');
      r('reply').textContent += w;
      await wait(step);
    }
    line('data: {"choices":[{"delta":{},"finish_reason":"stop"}]}', 'role'); await wait(step * 2);
    if (withUsage) { line(`data: {"choices":[],"usage":{"prompt_tokens":${prompt},"completion_tokens":${completion},"total_tokens":${prompt + completion}}}`, 'usage'); await wait(step * 2); }
    line('data: [DONE]', 'done');
    $('.ws-reply', el).classList.remove('live');
    roll(); used += prompt + completion;
    u.className = `ws-usage ${withUsage ? 'yes' : 'no'}`;
    u.innerHTML = withUsage
      ? `${IC.ok}<span>The client saw usage: <b>${prompt}</b> prompt + <b>${completion}</b> completion (${reasoning} reasoning) = <b>${prompt + completion}</b> tokens.</span>`
      : `${IC.minus}<span>No usage chunk reached the client. The gateway counted <b>${prompt + completion}</b> tokens anyway.</span>`;
    log.unshift({ code: 200, msg: `Request ${n} · <b>${prompt + completion}</b> tokens counted`, hdr: `stream finished, usage chunk to client: ${withUsage ? 'yes' : 'no'}` });
    paintLog(); paint();
    busy = false; el.classList.remove('ws-busy');
    $$('[data-send], [data-burst]', el).forEach((b) => { b.disabled = false; });
    return true;
  }
  wdBindSeg(el, (seg, v) => { usage = v[0] === 'on'; paintReq(); });
  $('[data-send]', el).addEventListener('click', () => send());
  $('[data-burst]', el).addEventListener('click', async () => { for (let i = 0; i < 12 && await send(true); i++); });
  $('[data-reset]', el).addEventListener('click', () => { if (busy) return; used = 0; start = wdNow(); n = 0; log = []; idle(); paintLog(); paint(); });
  paintReq(); idle(); paintLog(); paint();
  wdTicker(el, paint, 500);
};

/* 99-init.js */
// Boot. The script is loaded with `defer`, so the DOM is ready.
function boot() {
  const run = (name, fn) => { try { fn(); } catch (e) { console.error(`[labs] ${name} failed`, e); } };
  run('theme', initTheme);
  run('copy', initCopy);
  run('search', initSearch);
  run('values', () => applyValues(document));
  run('nav', initNav);
  run('tracks', initTracks);
  run('codeTabs', initCodeTabs);
  run('steps', initSteps);
  run('pathBanner', initPathBanner);
  run('toc', initToc);
  run('lightbox', initLightbox);
  run('videos', initVideos);
  run('catalog', initCatalog);
  run('hero', initHero);
  run('diagrams', initDiagrams);
  run('widgets', () => renderWidgets(document));
  run('labLinks', updateLabLinks);
  run('mermaid', () => { initMermaid(); });
  addEventListener('storage', (e) => { if (e.key === 'aigw-progress') { if (LAB) updateProgressUI(); else updateLabLinks(); } });
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
else boot();

})();
