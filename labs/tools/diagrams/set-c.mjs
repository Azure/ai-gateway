import { box, zone, pills, pill, arrow, text, svgDoc } from './lib.mjs';

export const enterpriseReference = () => svgDoc('enterprise-reference', {
  title: 'Enterprise reference deployment for Azure AI Gateway',
  desc: 'GitHub Actions signs in with OpenID Connect, previews main.bicep with what-if, deploys dev and then prod, applies gateway-wide baselines, and runs a smoke test. One subscription-scope template creates two resource groups. The gateway group holds the AI Gateway with the chat alias, a Foundry model provider that uses the managed identity, the learn MCP server, per-app API keys, and Application Insights with Log Analytics. The Foundry group holds a Foundry account with key authentication disabled and the gpt-6-luna deployment. The gateway identity has the Foundry User role.',
  h: 468,
  body: () => {
    let o = zone(16, 16, 928, 104, 'Delivery · GitHub Actions with OpenID Connect', { ic: 'terminal', tone: 'cyan' });
    const steps = [
      ['Sign in with OIDC', 'Federated credential', 'lock'],
      ['Preview', 'what-if on main.bicep', 'eye'],
      ['Deploy', 'dev, then prod', 'layers'],
      ['Baseline + test', 'Merge, then verify', 'check'],
    ];
    steps.forEach(([t, s, ic], i) => {
      const x = 32 + i * 231;
      o += box(x, 44, 203, 60, { t, s, icon: ic, tone: 'cyan', accent: i === 2 });
    });
    o += zone(16, 146, 640, 288, '…-gateway resource group', { ic: 'grid', tone: 'azure' });
    o += zone(672, 146, 272, 288, 'Foundry resource group', { ic: 'grid', tone: 'violet' });
    o += box(32, 216, 164, 60, { t: 'App Insights', s: 'Dashboards', icon: 'chart', tone: 'green', accent: true });
    o += box(32, 286, 164, 60, { t: 'Workspace', s: 'Log Analytics', icon: 'doc', tone: 'green' });
    o += pill(32, 386, 'Connect in portal', { tone: 'green' });
    o += zone(228, 182, 412, 236, 'AI Gateway · aigateways', { gw: true, ic: 'sparkle' });
    o += box(240, 216, 190, 60, { t: 'Alias: chat', s: 'Token limit, safety', icon: 'route', tone: 'violet', accent: true });
    o += box(438, 216, 190, 60, { t: 'Model provider', s: 'Managed identity', icon: 'models', tone: 'violet' });
    o += box(240, 286, 190, 60, { t: 'MCP: learn', s: 'Learn docs tools', icon: 'tools', tone: 'amber' });
    o += box(438, 286, 190, 60, { t: 'API keys', s: 'web-chat, batch-jobs', icon: 'key', tone: 'amber' });
    o += text(244, 376, 'GATEWAY SCOPE BASELINE (SCRIPT)', 'dg-cap');
    o += pills(240, 386, ['Request rate limit', 'Cost limit'], { tone: 'magenta' });
    o += box(688, 216, 240, 60, { t: 'Foundry account', s: 'Key auth disabled', icon: 'cloud', tone: 'violet', accent: true });
    o += box(688, 286, 240, 60, { t: 'gpt-6-luna', s: 'Model deployment', icon: 'models', tone: 'violet' });
    o += text(692, 376, 'GATEWAY IDENTITY HAS', 'dg-cap');
    o += pill(688, 386, 'Foundry User role', { tone: 'violet' });
    // Arrows last so they sit above zones.
    [235, 466, 697].forEach((x) => { o += arrow(`M${x} 74 H${x + 24}`, { tone: 'cyan' }); });
    o += arrow('M560 104 V144', { tone: 'cyan' });
    o += arrow('M640 104 C640 126 808 122 808 144', { tone: 'cyan' });
    o += arrow('M228 246 H200', { tone: 'green' });
    o += arrow('M628 246 H686', { tone: 'violet' });
    o += text(16, 458, 'One subscription-scope main.bicep composes the modules. No module outputs a secret.', 'dg-s');
    return o;
  },
});
