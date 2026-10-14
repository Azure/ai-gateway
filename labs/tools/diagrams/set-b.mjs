import { box, node, zone, pill, pills, arrow, label, list, text, icon, bar, svgDoc } from './lib.mjs';

export const observability = () => svgDoc('observability', {
  title: 'Observability with OpenTelemetry',
  desc: 'The gateway emits OpenTelemetry metrics, logs and traces for model calls, tool calls and policy decisions. Signals go to Application Insights, which powers the built-in Monitoring dashboard, or to any OTLP endpoint.',
  h: 420,
  body: () => {
    let o = zone(16, 20, 290, 340, 'AI Gateway', { gw: true, ic: 'sparkle' });
    [['models', 'Model calls', 'Tokens, latency, estimated cost', 'azure'], ['tools', 'Tool calls', 'tools/list and tools/call', 'amber'], ['shield', 'Policy decisions', 'Allowed, blocked, and why', 'magenta']].forEach(([ic, t, s, tone], i) => {
      const y = 56 + i * 96;
      o += box(28, y, 266, 72, { t, s, icon: ic, tone });
      o += arrow(`M296 ${y + 36} C326 ${y + 36} 326 ${88 + i * 96} 358 ${88 + i * 96}`, { tone: 'green' });
    });
    o += zone(346, 20, 250, 340, 'OpenTelemetry (OTLP)', { ic: 'chart', tone: 'green' });
    [['chart', 'Metrics', 'Token usage and cost'], ['doc', 'Logs', 'Requests and outcomes'], ['layers', 'Traces', 'Policy spans per request']].forEach(([ic, t, s], i) => {
      const y = 56 + i * 96;
      o += box(362, y, 218, 72, { t, s, icon: ic, tone: 'green', accent: true });
    });
    o += arrow('M582 92 C614 92 614 98 646 98', { tone: 'green' }) + arrow('M582 188 C614 188 614 98 646 98', { tone: 'green' }) + arrow('M582 284 C614 284 614 98 646 98', { tone: 'green' });
    o += arrow('M582 284 C614 284 614 300 646 300', { tone: 'green' });
    o += zone(636, 20, 308, 340, 'Destinations', { ic: 'cloud', tone: 'azure' });
    o += box(652, 56, 276, 84, { t: 'Application Insights', s: 'Powers the built-in', s2: 'Monitoring dashboard', icon: 'chart', tone: 'azure', accent: true });
    o += text(656, 166, 'DASHBOARD TABS', 'dg-cap');
    o += pills(652, 176, ['Overview', 'Models', 'Tools', 'Policies', 'Traces'], { tone: 'azure', maxW: 276 });
    o += box(652, 268, 276, 64, { t: 'Any OTLP endpoint', s: 'Your observability backend', icon: 'globe', tone: 'azure' });
    o += text(16, 386, 'Token metric', 'dg-s') + text(100, 386, 'gen_ai_client_token_usage', 'dg-m');
    o += text(16, 408, 'Claim attribute', 'dg-s') + text(116, 408, 'azure.ai_gateway.identity.claims.<claim>', 'dg-m');
    return o;
  },
});

export const privateNetworking = () => svgDoc('private-networking', {
  title: 'Private networking for Azure AI Gateway',
  desc: 'Inbound, clients in your virtual network reach the gateway through a private endpoint with group ID Gateway, resolved by the privatelink.azure-api.net private DNS zone, and public network access is disabled. Outbound, VNet integration sends backend traffic through an integration subnet of at least /27 delegated to Microsoft.Web/serverFarms.',
  h: 430,
  body: () => {
    let o = zone(16, 20, 274, 330, 'Your virtual network', { ic: 'network', tone: 'azure' });
    o += box(28, 56, 250, 64, { t: 'App or agent', s: 'Calls the gateway hostname', icon: 'app', tone: 'azure' });
    o += arrow('M153 122 V146', { tone: 'azure' });
    o += box(28, 150, 250, 72, { t: 'Private endpoint', s: 'groupId: Gateway', icon: 'plug', tone: 'azure', accent: true, mono: true });
    o += `<path class="dg-ghost" d="M153 224 V250"/>`;
    o += box(28, 252, 250, 72, { t: 'Private DNS zone', s: 'privatelink.azure-api.net', icon: 'dns', tone: 'azure', mono: true });
    o += zone(334, 20, 292, 330, 'AI Gateway', { gw: true, ic: 'sparkle' });
    o += box(350, 56, 268, 72, { t: 'Inbound', s: 'Private endpoint only', icon: 'lock', accent: true });
    o += pill(350, 138, 'publicNetworkAccess: Disabled', { tone: 'red', mono: true });
    o += box(350, 252, 268, 72, { t: 'Outbound', s: 'VNet integration', s2: 'virtualNetworkType: External', icon: 'network', tone: 'green', accent: true, mono: true });
    o += arrow('M280 186 C314 186 314 92 346 92', { tone: 'azure' });
    o += zone(670, 20, 274, 330, 'Integration subnet', { ic: 'network', tone: 'green' });
    o += text(686, 60, 'At least /27, delegated to', 'dg-s') + text(686, 78, 'Microsoft.Web/serverFarms', 'dg-m');
    o += box(682, 100, 250, 72, { t: 'Private backends', s: 'Foundry and Azure OpenAI', s2: 'through private endpoints', icon: 'models', tone: 'green' });
    o += text(686, 212, 'NSG: ALLOW OUTBOUND 443 TO', 'dg-cap');
    o += pills(682, 222, ['Storage', 'AzureKeyVault'], { tone: 'green' });
    o += arrow('M620 288 C648 288 648 136 678 136', { tone: 'green' });
    o += `<g class="tn-red">${icon('block', 16, 372, 20)}</g>` + text(44, 387, 'Calls from the public internet are rejected once public network access is disabled.', 'dg-s');
    o += `<g class="tn-amber">${icon('dns', 16, 400, 20)}</g>` + text(44, 415, 'DNS is the most common pitfall: the gateway hostname must resolve to the private endpoint IP.', 'dg-s');
    return o;
  },
});

export const hostedAgent = () => svgDoc('hosted-agent', {
  title: 'Foundry hosted agent behind Azure AI Gateway',
  desc: 'azd up provisions the infrastructure and deploys a hosted agent to Microsoft Foundry. You invoke the agent or dispatch the daily-repo-digest routine. The agent calls a model alias and GitHub MCP tools only through the AI gateway, which applies policies and forwards to Foundry models and GitHub.',
  h: 400,
  body: () => {
    let o = zone(16, 20, 220, 340, 'You', { ic: 'user', tone: 'azure' });
    o += box(28, 56, 196, 72, { t: 'azd up', s: 'Provision and deploy', icon: 'terminal', tone: 'azure', accent: true });
    o += box(28, 150, 196, 72, { t: 'Invoke or chat', s: 'Responses API', icon: 'user', tone: 'azure' });
    o += box(28, 244, 196, 72, { t: 'Routine', s: 'daily-repo-digest', icon: 'clock', tone: 'azure', mono: true });
    o += zone(266, 20, 200, 340, 'Microsoft Foundry', { ic: 'cloud', tone: 'cyan' });
    o += box(278, 132, 176, 100, { t: 'Hosted agent', s: 'Agent Framework', s2: 'Python or .NET', icon: 'agent', tone: 'cyan', accent: true });
    o += arrow('M226 92 C252 92 252 160 274 160', { tone: 'azure', dashed: true });
    o += arrow('M226 186 H274', { tone: 'azure' });
    o += arrow('M226 280 C252 280 252 210 274 210', { tone: 'azure' });
    o += zone(496, 20, 240, 340, 'AI Gateway', { gw: true, ic: 'sparkle' });
    o += box(510, 70, 212, 72, { t: 'Model alias', s: 'OpenAI-compatible', icon: 'route', accent: true });
    o += box(510, 166, 212, 72, { t: 'MCP server', s: 'GitHub tools', icon: 'tools', tone: 'amber', accent: true });
    o += pills(510, 262, ['Access key', 'Token limits', 'Content safety'], { tone: 'magenta', maxW: 212 });
    o += arrow('M456 170 C484 170 480 106 506 106') + arrow('M456 194 C484 194 480 202 506 202', { tone: 'amber' });
    o += zone(766, 20, 178, 340, 'Backends', { ic: 'models', tone: 'azure' });
    o += box(778, 70, 154, 72, { t: 'Foundry', s: 'models', icon: 'models', tone: 'azure' });
    o += box(778, 166, 154, 72, { t: 'GitHub', s: 'remote MCP', icon: 'globe', tone: 'amber' });
    o += arrow('M724 106 H774', { tone: 'azure' }) + arrow('M724 202 H774', { tone: 'amber' });
    o += text(16, 388, 'The agent reaches models and tools only through the gateway, so every call gets the same keys, limits, and telemetry.', 'dg-s');
    return o;
  },
});

export const agent365 = () => svgDoc('agent-365', {
  title: 'Govern MCP servers with Microsoft Agent 365',
  desc: 'The Microsoft 365 admin center inventories API Management gateways and MCP servers. Admins block or unblock MCP servers, and block individual tools when the server has a static allow list. The gateway enforces the decisions for agents and sends runtime signals back for audit.',
  h: 400,
  body: () => {
    let o = zone(16, 20, 290, 340, 'Microsoft 365 admin center', { ic: 'm365', tone: 'azure' });
    o += box(28, 56, 266, 72, { t: 'Inventory', s: 'API Management gateways', s2: 'and MCP servers', icon: 'grid', tone: 'azure' });
    o += box(28, 148, 266, 72, { t: 'Block or unblock', s: 'Whole MCP servers', icon: 'block', tone: 'red', accent: true });
    o += box(28, 240, 266, 84, { t: 'Block individual tools', s: 'Requires a static allow list', s2: 'on the MCP server', icon: 'filter', tone: 'red' });
    o += zone(350, 20, 290, 340, 'AI Gateway', { gw: true, ic: 'sparkle' });
    o += box(366, 56, 258, 72, { t: 'MCP server: github-tools', s: 'Allowed tools only', icon: 'tools', tone: 'amber', accent: true });
    o += box(366, 148, 258, 72, { t: 'MCP server: crm-tools', s: 'Blocked by admin', icon: 'block', tone: 'red' });
    o += box(366, 240, 258, 84, { t: 'Tool threat protection', s: 'Defender and Purview', s2: 'before and after tool calls', icon: 'shield', tone: 'magenta' });
    o += arrow('M296 184 H362', { tone: 'red' }) + arrow('M296 282 C330 282 330 92 362 92', { tone: 'red' });
    o += arrow('M366 312 C336 312 330 342 296 342', { tone: 'green', dashed: true });
    o += label(206, 346, 'Runtime signals for audit', { cls: 'dg-s' });
    o += zone(684, 20, 260, 340, 'Agents', { ic: 'agent', tone: 'cyan' });
    [['agent', 'Copilot agents', 'Built in Microsoft 365'], ['cloud', 'Hosted agents', 'Microsoft Foundry'], ['terminal', 'Coding agents', 'IDEs and CLIs']].forEach(([ic, t, s], i) => {
      const y = 56 + i * 92;
      o += box(696, y, 236, 72, { t, s, icon: ic, tone: 'cyan' });
      o += arrow(`M694 ${y + 36} C664 ${y + 36} 664 ${92 + Math.min(i, 1) * 92} 628 ${92 + Math.min(i, 1) * 92}`, { tone: 'cyan' });
    });
    o += text(16, 388, 'Decisions made by Microsoft 365 admins are enforced by the gateway on every tool call.', 'dg-s');
    return o;
  },
});

export const threatProtection = () => svgDoc('threat-protection', {
  title: 'Agent 365 tool threat protection',
  desc: 'An agent calls an MCP tool with a delegated Microsoft Entra token. Before invocation, Microsoft Defender and Microsoft Purview check the tool input for malicious content, prompt injection and sensitive data. If blocked, the tool never runs. After invocation they check the tool result. A denial after invocation withholds the result, but the tool already ran.',
  h: 430,
  body: () => {
    let o = zone(120, 16, 660, 370, 'AI Gateway · MCP server', { gw: true, ic: 'sparkle' });
    o += node(56, 130, 'agent', 'Agent', { tone: 'cyan', sub: 'calls a tool', accent: false });
    o += node(240, 60, 'key', 'Entra token', { sub: 'delegated (OBO)' });
    o += node(450, 60, 'eye', 'Before invocation', { tone: 'magenta', sub: 'checks tool input' });
    o += node(880, 150, 'tools', 'MCP tool', { tone: 'amber', sub: 'runs the call', accent: false });
    o += node(620, 230, 'eye', 'After invocation', { tone: 'magenta', sub: 'checks tool result' });
    o += arrow('M86 150 C140 150 160 88 208 88', { tone: 'cyan' }) + arrow('M270 88 H418');
    o += arrow('M480 88 C720 88 800 120 850 160', { tone: 'amber' });
    o += arrow('M850 192 C780 250 720 258 652 258', { tone: 'amber' });
    o += arrow('M588 258 C320 258 160 172 90 172', { tone: 'cyan' });
    o += pill(240, 164, 'App-only tokens not supported', { tone: 'violet', anchor: 'middle' });
    o += pill(450, 164, 'Deny: tool never runs', { tone: 'red', anchor: 'middle' });
    o += pill(620, 330, 'Deny: result withheld, tool already ran', { tone: 'amber', anchor: 'middle' });
    o += text(150, 296, 'DEFENDER + PURVIEW CHECK FOR', 'dg-cap');
    o += list(150, 320, ['Malicious content', 'Prompt injection', 'Sensitive data'], { tone: 'magenta', gap: 20 });
    o += text(16, 414, 'Choose before, after, or both. Do not auto-retry after a post-invocation denial: the side effect already happened.', 'dg-s');
    return o;
  },
});

export const tokenLimits = () => svgDoc('token-limits', {
  title: 'Token limits give each caller its own allowance',
  desc: 'A token limit of 1,000 tokens per minute with the Caller identity counter keeps a separate counter for each caller. App A and the batch job are under the limit and get 200 with a remaining-tokens header. App B exhausted its counter and gets 429 with Retry-After, without the backend being called.',
  h: 410,
  body: () => {
    let o = zone(16, 20, 210, 340, 'Callers', { ic: 'users', tone: 'azure' });
    o += zone(260, 20, 440, 340, 'AI Gateway', { gw: true, ic: 'sparkle' });
    o += box(276, 56, 408, 64, { t: 'Token limit · 1,000 tokens per minute', s: 'Counter dimension: Caller identity', icon: 'gauge', accent: true });
    o += zone(734, 20, 210, 340, 'Responses', { ic: 'doc', tone: 'green' });
    const rows = [['app', 'App A', 420, 'green', '200 OK', 'remaining-tokens: 580'], ['app', 'App B', 1000, 'red', '429 Too Many', 'Retry-After: 18'], ['server', 'Batch job', 760, 'amber', '200 OK', 'remaining-tokens: 240']];
    rows.forEach(([ic, n, used, tone, st, hdr], i) => {
      const y = 140 + i * 72;
      o += box(28, y, 186, 56, { t: n, s: i === 2 ? 'Managed identity' : 'API key', icon: ic, tone: 'azure' });
      o += arrow(`M216 ${y + 28} H272`, { tone: 'azure' });
      o += text(286, y + 22, `${n} counter`, 'dg-t', 'start', ' style="font-size:12.5px"') + text(668, y + 22, `${used.toLocaleString('en-US')} / 1,000`, 'dg-m', 'end');
      o += bar(286, y + 32, 382, used / 1000, { tone, h: 10 });
      o += arrow(`M690 ${y + 28} H742`, { tone: tone === 'red' ? 'red' : 'green' });
      o += pill(746, y + 4, st, { tone: tone === 'red' ? 'red' : 'green' });
      o += text(748, y + 46, hdr, 'dg-m');
    });
    o += text(16, 394, 'Each caller is counted separately. The backend is never called for a 429.', 'dg-s');
    return o;
  },
});
