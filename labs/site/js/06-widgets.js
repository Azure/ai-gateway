// Widgets: request lifecycle, alias retarget, tool patterns, policy layers.
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
    { provider: 'Microsoft Foundry', model: 'gpt-4.1-mini', note: 'Lower cost', logo: 'microsoft-foundry' },
    { provider: 'Microsoft Foundry', model: 'gpt-4.1', note: 'Higher quality', logo: 'microsoft-foundry' },
    { provider: 'Azure OpenAI', model: 'gpt-4o', note: 'Existing deployment', logo: 'azure-openai' },
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
    { id: 'model', name: 'Backend model gpt-4.1-mini', sub: 'Applies through every alias', icon: 'models', c: 'var(--cat-green)', pols: [['Request rate limit', 'filter', ['model']]] },
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
