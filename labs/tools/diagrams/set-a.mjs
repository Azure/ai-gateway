import { box, node, zone, pill, pills, arrow, label, list, text, icon, svgDoc } from './lib.mjs';

export const architecture = () => svgDoc('architecture', {
  title: 'Azure AI Gateway architecture',
  desc: 'Apps, agents, coding agents and hosted agents call one AI gateway. The gateway authenticates callers, routes model calls through aliases to model providers, federates tools from MCP servers, OpenAPI specs, connectors and Foundry Toolbox, applies policies, and emits OpenTelemetry.',
  h: 450,
  body: () => {
    let o = zone(16, 20, 230, 410, 'Clients', { ic: 'users' });
    const clients = [['app', 'Apps & services', 'OpenAI-compatible SDKs'], ['agent', 'AI agents', 'Any agent framework'], ['terminal', 'Coding agents', 'Copilot, Claude Code'], ['cloud', 'Hosted agents', 'Microsoft Foundry']];
    clients.forEach(([ic, t, s], i) => { const y = 60 + i * 90; o += box(28, y, 206, 76, { t, s, icon: ic, tone: 'azure' }) + arrow(`M236 ${y + 38} H286`, { tone: 'azure' }); });
    o += zone(290, 20, 380, 410, 'Azure AI Gateway', { gw: true, ic: 'sparkle' });
    o += box(302, 56, 356, 56, { t: 'Access', s: 'API keys · Microsoft Entra ID', icon: 'key' });
    o += box(302, 124, 174, 88, { t: 'Models', s: 'Stable aliases', s2: 'Any provider', icon: 'models', tone: 'azure' });
    o += box(484, 124, 174, 88, { t: 'MCP servers', s: 'Federated tools', s2: 'Tool availability', icon: 'tools', tone: 'amber' });
    o += box(302, 224, 356, 52, { t: 'Policies', s: 'Gateway scope or individual assets', icon: 'shield', tone: 'magenta' });
    o += pills(302, 284, ['Token limits', 'Request rate', 'Cost limit', 'Content safety', 'IP filter', 'Threat protection'], { tone: 'magenta', maxW: 356 });
    o += box(302, 346, 356, 60, { t: 'Observability', s: 'OpenTelemetry metrics, logs, and traces', icon: 'chart', tone: 'green' });
    o += zone(714, 20, 230, 220, 'Model providers', { ic: 'models', tone: 'azure' });
    o += list(732, 64, ['Microsoft Foundry', 'Azure OpenAI', 'OpenAI', 'Anthropic', 'AWS Bedrock', 'Google Vertex AI', 'Custom endpoints'], { tone: 'azure', gap: 23, cls: 'dg-t' });
    o += zone(714, 252, 230, 178, 'Tool sources', { ic: 'tools', tone: 'amber' });
    o += list(732, 296, ['Remote MCP servers', 'OpenAPI specifications', 'Built-in connectors', 'Foundry Toolbox'], { tone: 'amber', gap: 25, cls: 'dg-t' });
    o += arrow('M672 130 H710', { tone: 'azure' }) + arrow('M672 341 H710', { tone: 'amber' });
    return o;
  },
});

export const requestLifecycle = () => svgDoc('request-lifecycle', {
  title: 'Request lifecycle through Azure AI Gateway',
  desc: 'A request is authenticated, checked by IP filter, rate and token limits, cost limit and content safety, then routed by alias to a backend model using the gateway managed identity. The response is screened and telemetry is recorded. A blocked request returns 401, 403, 429 or 400 and never reaches the backend.',
  h: 360,
  body: () => {
    let o = zone(120, 16, 640, 308, 'AI Gateway', { gw: true, ic: 'sparkle' });
    o += node(56, 130, 'app', 'Client', { tone: 'azure', sub: 'app or agent', accent: false });
    const req = [['key', 'Authenticate', 'key or Entra', '401', 'red'], ['globe', 'IP filter', 'allow · deny', '403', 'red'], ['gauge', 'Limits', 'rate · tokens', '429', 'amber'], ['coins', 'Cost limit', 'budget', '403', 'red'], ['shield', 'Content safety', 'prompt', '400', 'amber'], ['route', 'Alias routing', 'alias → model']];
    req.forEach(([ic, l, sub, code, tone], i) => {
      const cx = 180 + i * 96;
      o += node(cx, 60, ic, l, { sub, tone: 'violet' });
      if (code) o += pill(cx, 162, code, { tone, anchor: 'middle', w: 44 });
      if (i < req.length - 1) o += arrow(`M${cx + 31} 88 H${cx + 65}`);
    });
    o += arrow('M86 150 C118 150 118 88 148 88');
    o += node(868, 130, 'models', 'Backend model', { tone: 'azure', sub: 'managed identity', accent: false });
    o += arrow('M692 88 C790 88 800 150 836 150', { tone: 'azure' });
    o += node(640, 212, 'shield', 'Content safety', { tone: 'green', sub: 'response' });
    o += node(440, 212, 'chart', 'Telemetry', { tone: 'green', sub: 'tokens · cost · traces' });
    o += arrow('M838 172 C790 172 770 240 672 240', { tone: 'green' });
    o += arrow('M608 240 H472', { tone: 'green' });
    o += arrow('M408 240 C250 240 130 176 90 172', { tone: 'green' });
    o += text(440, 350, 'Blocked requests stop at the failing policy and never reach the backend.', 'dg-s', 'middle');
    return o;
  },
});

export const aliases = () => svgDoc('aliases', {
  title: 'Model aliases decouple clients from backend models',
  desc: 'Clients call stable aliases such as chat, chat-batch and reasoning. Each alias points to a backend model and carries its own policies. Two aliases can share a backend model. Retargeting an alias to another backend model needs no client change.',
  h: 420,
  body: () => {
    let o = zone(16, 20, 214, 360, 'Clients', { ic: 'users', tone: 'azure' });
    o += zone(290, 20, 280, 360, 'Aliases', { gw: true, ic: 'route' });
    o += zone(636, 20, 308, 360, 'Backend models', { ic: 'models', tone: 'azure' });
    const rows = [
      ['app', 'Chat app', 'model: chat', 'chat', 'Token rate limit', 'gpt-4.1-mini', 'Microsoft Foundry'],
      ['server', 'Batch job', 'model: chat-batch', 'chat-batch', 'Token rate limit · Cost limit', 'gpt-4.1', 'Microsoft Foundry'],
      ['agent', 'Research agent', 'model: reasoning', 'reasoning', 'Content safety', 'o4-mini', 'Microsoft Foundry'],
    ];
    rows.forEach(([ic, c, call, a, pol, m, prov], i) => {
      const y = 60 + i * 110;
      o += box(28, y, 190, 60, { t: c, s: call, icon: ic, tone: 'azure', mono: true });
      o += arrow(`M220 ${y + 30} H302`);
      o += box(306, y - 2, 248, 64, { t: a, s: pol, icon: 'route', accent: true });
      o += box(652, y, 276, 60, { t: m, s: prov, icon: 'models', tone: 'azure' });
    });
    o += arrow('M556 90 C600 90 610 86 648 86', { tone: 'violet' });
    o += arrow('M556 200 C606 200 606 98 648 98', { tone: 'magenta' });
    o += arrow('M556 310 C600 310 610 310 648 310', { tone: 'cyan' });
    o += arrow('M556 96 C606 104 606 196 648 196', { tone: 'violet', dashed: true });
    o += label(604, 150, 'retarget', { cls: 'dg-m' });
    o += text(16, 404, 'Dashed: retarget chat to gpt-4.1. Clients keep sending model: chat, and the alias keeps its policies.', 'dg-s');
    return o;
  },
});

export const mcpFederation = () => svgDoc('mcp-federation', {
  title: 'MCP tool federation through Azure AI Gateway',
  desc: 'MCP clients connect to one MCP server endpoint on the gateway. The server federates tools from remote MCP servers, OpenAPI specifications, built-in connectors and Foundry Toolbox. Tool names are namespaced per backend, tool availability rules decide which tools clients see, and policies apply to every call.',
  h: 420,
  body: () => {
    let o = zone(16, 20, 214, 380, 'MCP clients', { ic: 'users', tone: 'azure' });
    [['agent', 'AI agents', 'Agent Framework'], ['terminal', 'Coding agents', 'IDEs and CLIs'], ['cloud', 'Hosted agents', 'Microsoft Foundry'], ['app', 'Your apps', 'Any MCP client']].forEach(([ic, t, s], i) => {
      const y = 60 + i * 86;
      o += box(28, y, 190, 64, { t, s, icon: ic, tone: 'azure' });
    });
    o += zone(270, 20, 400, 380, 'AI Gateway', { gw: true, ic: 'sparkle' });
    [60, 146, 232, 318].forEach((y) => { o += arrow(`M220 ${y + 32} C252 ${y + 32} 252 95 282 95`, { tone: 'azure' }); });
    o += box(286, 56, 368, 78, { t: 'MCP server: github-tools', s: 'One endpoint, one key or Entra token', s2: '/default/toolservers/github-tools/mcp', icon: 'tools', accent: true, mono: true });
    o += box(286, 148, 368, 64, { t: 'Tool availability', s: 'Allow all · exact list · patterns · block', icon: 'filter', tone: 'amber' });
    o += box(286, 226, 368, 78, { t: 'Policies', s: 'IP filter · request rate · content safety', s2: 'Agent 365 tool threat protection', icon: 'shield', tone: 'magenta' });
    o += text(290, 332, 'Tools are namespaced per backend:', 'dg-s');
    o += text(290, 354, 'aigw-github___github_list_issues', 'dg-m') + text(290, 374, 'learn___microsoft_docs_search', 'dg-m');
    o += zone(714, 20, 230, 380, 'Tool sources', { ic: 'tools', tone: 'amber' });
    [['globe', 'Remote MCP server', 'SSE or Streamable HTTP'], ['doc', 'OpenAPI spec', 'Operations as tools'], ['plug', 'Connector', 'Microsoft 365, GitHub'], ['toolbox', 'Foundry Toolbox', 'Tools from Foundry']].forEach(([ic, t, s], i) => {
      const y = 60 + i * 86;
      o += box(726, y, 206, 64, { t, s, icon: ic, tone: 'amber' });
      o += arrow(`M672 210 C700 210 694 ${y + 32} 722 ${y + 32}`, { tone: 'amber' });
    });
    return o;
  },
});

export const policyScopes = () => svgDoc('policy-scopes', {
  title: 'Policy scopes in Azure AI Gateway',
  desc: 'Gateway-scope policies apply to all compatible assets, including assets added later. Individual-asset policies attach to a backend model, an alias or an MCP server. Every applicable policy is evaluated for a request.',
  h: 440,
  body: () => {
    let o = zone(16, 16, 928, 408, 'Gateway scope · applies to all compatible assets, including future ones', { gw: true, ic: 'globe' });
    o += pills(32, 48, [['Content safety', 'azure'], ['IP filter', 'azure'], ['Cost limit', 'azure']]);
    const cols = [
      ['Models', 'models', [['gpt-4.1-mini', 'Backend model', ['Request rate']]], 'Applies through every alias'],
      ['Aliases', 'route', [['chat', '→ gpt-4.1-mini', ['Token rate limit']], ['chat-batch', '→ gpt-4.1-mini', ['Token rate limit', 'Cost limit']]]],
      ['MCP servers', 'tools', [['github-tools', 'MCP server', ['Request rate', 'Threat protection']]]],
    ];
    const tones = ['green', 'violet', 'amber'];
    cols.forEach(([name, ic, assets, note], i) => {
      const x = 32 + i * 226, cx = x + 107;
      o += arrow(`M${cx} 76 V96`, { tone: 'azure' });
      o += zone(x, 100, 214, 300, name, { ic, tone: tones[i] });
      assets.forEach(([t, s, pols], j) => {
        const y = 138 + j * 128;
        o += box(x + 12, y, 190, 56, { t, s, icon: ic, tone: tones[i] });
        o += pills(x + 12, y + 64, pols, { tone: tones[i], maxW: 190 });
      });
      if (note) o += text(x + 14, 258, note, 'dg-s');
    });
    const fx = 710;
    o += arrow(`M${fx + 107} 76 V96`, { tone: 'azure' });
    o += `<rect class="dg-ghost" x="${fx}" y="100" width="214" height="300" rx="16"/>` + `<g class="tn-violet">${icon('sparkle', fx + 16, 110, 16)}</g>` + text(fx + 38, 123, 'FUTURE ASSETS', 'dg-cap');
    o += `<rect class="dg-ghost" x="${fx + 12}" y="138" width="190" height="56" rx="10"/>` + text(fx + 26, 162, 'New model or server', 'dg-t') + text(fx + 26, 180, 'Inherits gateway policies', 'dg-s');
    o += text(32, 416, 'Every applicable policy is evaluated for each request. Any one of them can block it.', 'dg-s');
    return o;
  },
});

export const identityBoundaries = () => svgDoc('identity-boundaries', {
  title: 'Identity boundaries in Azure AI Gateway',
  desc: 'Inbound, callers authenticate to the gateway with an API key or a Microsoft Entra token that carries an AI Gateway data-plane role. Outbound, the gateway calls backends with its own managed identity, or a provider API key it stores. Callers never receive backend credentials.',
  h: 360,
  body: () => {
    let o = pill(286, 10, 'Inbound: who is calling?', { tone: 'azure', anchor: 'middle' }) + pill(674, 10, 'Outbound: the gateway identity', { tone: 'green', anchor: 'middle' });
    o += `<path class="dg-ghost" d="M286 38 V324 M674 38 V324"/>`;
    o += zone(16, 44, 250, 280, 'Callers', { ic: 'users', tone: 'azure' });
    [['key', 'App with API key', 'api-key header'], ['user', 'User or agent', 'Entra token (delegated)'], ['cloud', 'Workload', 'Managed identity token']].forEach(([ic, t, s], i) => {
      const y = 82 + i * 80;
      o += box(28, y, 226, 64, { t, s, icon: ic, tone: 'azure' });
    });
    o += zone(306, 44, 348, 280, 'AI Gateway', { gw: true, ic: 'sparkle' });
    [82, 162, 242].forEach((y) => { o += arrow(`M256 ${y + 32} C290 ${y + 32} 292 124 318 124`, { tone: 'azure' }); });
    o += box(322, 82, 316, 84, { t: 'Inbound check', s: 'Valid key, or an Entra token with', s2: 'an AI Gateway data-plane role', icon: 'lock', accent: true });
    o += pills(322, 176, ['AI Gateway User', 'Models User', 'Tools User'], { tone: 'violet', maxW: 316 });
    o += box(322, 236, 316, 76, { t: 'Outbound identity', s: 'System- or user-assigned', s2: 'managed identity', icon: 'key', tone: 'green', accent: true });
    o += zone(694, 44, 250, 280, 'Backends', { ic: 'models', tone: 'green' });
    o += box(706, 82, 226, 84, { t: 'Microsoft Foundry', s: 'Managed identity with the', s2: 'Foundry User role', icon: 'models', tone: 'green' });
    o += box(706, 184, 226, 84, { t: 'Other providers', s: 'Provider API key', s2: 'stored by the gateway', icon: 'globe', tone: 'green' });
    o += arrow('M640 274 C672 274 672 124 702 124', { tone: 'green' }) + arrow('M640 274 C672 274 672 226 702 226', { tone: 'green' });
    o += text(16, 350, 'Callers never receive backend credentials. Each side is authorized separately.', 'dg-s');
    return o;
  },
});
