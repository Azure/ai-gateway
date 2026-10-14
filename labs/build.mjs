#!/usr/bin/env node
// Builds the Azure AI Gateway Labs site from labs/<NN-slug>/README.md into ../docs (GitHub Pages).
//   node build.mjs           build once
//   node build.mjs --watch   rebuild on change
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import matter from 'gray-matter';
import { initHighlighter, renderLab, escapeHtml } from './site/markdown.mjs';
import { layout, homePage, catalogPage, labPage, notFoundPage } from './site/templates.mjs';

const LABS = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(LABS, '..');
// LABS_OUT and LABS_SITE_URL build a copy for another host (see tools/deploy-swa.sh).
const OUT = process.env.LABS_OUT ? path.resolve(process.env.LABS_OUT) : path.join(ROOT, 'docs');
const SITE_SRC = path.join(LABS, 'site');
const BASE_URL = (process.env.LABS_SITE_URL || 'https://azure.github.io/ai-gateway/').replace(/\/?$/, '/');
const BASE_PATH = new URL(BASE_URL).pathname;
const GENERATED = ['index.html', '404.html', 'labs', 'assets', 'search.json', 'llms.txt', 'llms-full.txt', 'sitemap.xml', 'robots.txt', '.nojekyll'];
const MEDIA_RE = /\.(png|jpe?g|gif|webp|svg|mp4|webm|avif)$/i;
const REQUIRED = ['title', 'summary', 'category', 'level', 'duration', 'tracks', 'objectives'];

const warnings = [];
const warn = (msg) => warnings.push(msg);

function rmGenerated() {
  fs.mkdirSync(OUT, { recursive: true });
  for (const f of GENERATED) fs.rmSync(path.join(OUT, f), { recursive: true, force: true });
}

function copyDir(src, dest, filter = () => true) {
  if (!fs.existsSync(src)) return;
  for (const e of fs.readdirSync(src, { withFileTypes: true })) {
    if (e.name.startsWith('.')) continue;
    const s = path.join(src, e.name);
    const d = path.join(dest, e.name);
    if (e.isDirectory()) copyDir(s, d, filter);
    else if (filter(s)) { fs.mkdirSync(dest, { recursive: true }); fs.copyFileSync(s, d); }
  }
}

function write(rel, content) {
  const f = path.join(OUT, rel);
  fs.mkdirSync(path.dirname(f), { recursive: true });
  fs.writeFileSync(f, content);
}

function gitUpdated(dir) {
  try {
    const out = execFileSync('git', ['log', '-1', '--format=%cI', '--', path.relative(ROOT, dir)], { cwd: ROOT, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
    return out || null;
  } catch { return null; }
}

// Prefix ids inside inlined SVGs so several diagrams can share one page.
let svgCounter = 0;
function prefixSvgIds(svg) {
  const p = `s${(svgCounter += 1)}-`;
  const ids = [...svg.matchAll(/\bid="([^"]+)"/g)].map((m) => m[1]);
  let out = svg;
  for (const id of ids) {
    const esc = id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    out = out
      .replace(new RegExp(`\\bid="${esc}"`, 'g'), `id="${p}${id}"`)
      .replace(new RegExp(`url\\(#${esc}\\)`, 'g'), `url(#${p}${id})`)
      .replace(new RegExp(`(xlink:)?href="#${esc}"`, 'g'), (m, x) => `${x || ''}href="#${p}${id}"`)
      .replace(new RegExp(`(aria-labelledby|aria-describedby)="${esc}"`, 'g'), `$1="${p}${id}"`);
  }
  return out;
}

function loadLabs(catalog) {
  const dirs = fs.readdirSync(LABS, { withFileTypes: true })
    .filter((d) => d.isDirectory() && /^\d{2}-[a-z0-9-]+$/.test(d.name) && fs.existsSync(path.join(LABS, d.name, 'README.md')))
    .map((d) => d.name);
  const cats = new Set(catalog.categories.map((c) => c.id));
  const labs = dirs.map((slug) => {
    const raw = fs.readFileSync(path.join(LABS, slug, 'README.md'), 'utf8');
    const { data, content } = matter(raw);
    for (const k of REQUIRED) if (data[k] == null) warn(`${slug}: missing front matter "${k}"`);
    if (data.category && !cats.has(data.category)) warn(`${slug}: unknown category "${data.category}"`);
    return {
      ...data,
      slug,
      num: slug.slice(0, 2),
      short: catalog.shortTitles?.[slug] || data.title,
      tracks: data.tracks || [],
      tags: (data.tags || []).map(String),
      duration: Number(data.duration) || 0,
      order: data.order ?? Number(slug.slice(0, 2)),
      paths: catalog.paths.filter((p) => p.labs.includes(slug)).map((p) => p.id),
      updated: gitUpdated(path.join(LABS, slug)),
      raw,
      content,
      dir: path.join(LABS, slug),
    };
  });
  labs.sort((a, b) => a.order - b.order || a.slug.localeCompare(b.slug));
  const known = new Set(labs.map((l) => l.slug));
  for (const p of catalog.paths) for (const s of p.labs) if (!known.has(s)) warn(`path "${p.id}" references missing lab ${s}`);
  for (const l of labs) for (const s of l.prereqs || []) if (!known.has(s)) warn(`${l.slug}: prereq ${s} not found`);
  return labs;
}

function makeCtx(lab, site, knownSlugs) {
  const ghBase = `${site.repo}/blob/${site.branch}`;
  const media = new Set();
  const ctx = {
    labDir: lab.dir,
    media,
    ghBlob: (file) => `${ghBase}/labs/${lab.slug}/${file}`,
    resolveAsset(href) {
      if (/^(https?:)?\/\//.test(href) || href.startsWith('data:')) return href;
      const abs = path.resolve(lab.dir, decodeURI(href.split(/[?#]/)[0]));
      if (!fs.existsSync(abs)) warn(`${lab.slug}: missing image ${href}`);
      else if (abs.startsWith(lab.dir + path.sep)) media.add(path.relative(lab.dir, abs));
      return href;
    },
    inlineSvg(href) {
      if (/^(https?:)?\/\//.test(href)) return null;
      const abs = path.resolve(lab.dir, href);
      if (!abs.startsWith(path.join(LABS, 'assets', 'diagrams') + path.sep) || !fs.existsSync(abs)) return null;
      const svg = fs.readFileSync(abs, 'utf8').replace(/<\?xml[^>]*>\s*/, '').replace(/<!--[\s\S]*?-->/g, '');
      return prefixSvgIds(svg);
    },
    resolveLink(href) {
      if (/^(https?:|mailto:)/.test(href)) return { url: href, external: !href.startsWith(BASE_URL) };
      if (href.startsWith('#')) return { url: href, external: false };
      const [p, hash] = href.split('#');
      const h = hash ? `#${hash}` : '';
      const abs = path.resolve(lab.dir, decodeURI(p));
      const relLabs = path.relative(LABS, abs).split(path.sep).join('/');
      const m = relLabs.match(/^(\d{2}-[a-z0-9-]+)(?:\/(?:README\.md)?)?$/);
      if (m) {
        if (!knownSlugs.has(m[1])) warn(`${lab.slug}: link to unknown lab ${href}`);
        return { url: m[1] === lab.slug ? (h || './') : `../${m[1]}/${h}`, external: false };
      }
      if (!fs.existsSync(abs)) warn(`${lab.slug}: broken link ${href}`);
      if (relLabs.startsWith('assets/') || (abs.startsWith(lab.dir + path.sep) && MEDIA_RE.test(abs))) {
        if (abs.startsWith(lab.dir + path.sep)) media.add(path.relative(lab.dir, abs));
        return { url: href, external: false };
      }
      const relRepo = path.relative(ROOT, abs).split(path.sep).join('/');
      if (relRepo.startsWith('..')) { warn(`${lab.slug}: link escapes repo ${href}`); return { url: href, external: false }; }
      const isDir = p.endsWith('/') || (fs.existsSync(abs) && fs.statSync(abs).isDirectory());
      return { url: `${site.repo}/${isDir ? 'tree' : 'blob'}/${site.branch}/${relRepo}${h}`, external: true };
    },
  };
  return ctx;
}

const htmlToText = (html) => html
  .replace(/<(script|style|svg)[\s\S]*?<\/\1>/g, ' ')
  .replace(/<pre[\s\S]*?<\/pre>/g, ' ')
  .replace(/<[^>]+>/g, ' ')
  .replace(/&nbsp;/g, ' ').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&')
  .replace(/\s+/g, ' ').trim();

function checkAnchors(lab, html, allHtml) {
  const ids = new Set([...html.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]));
  for (const m of html.matchAll(/href="#([^"]+)"/g)) if (!ids.has(m[1])) warn(`${lab.slug}: anchor #${m[1]} not found`);
  for (const m of html.matchAll(/href="\.\.\/(\d{2}-[a-z0-9-]+)\/#([^"]+)"/g)) {
    const other = allHtml.get(m[1]);
    if (other && !other.includes(` id="${m[2]}"`)) warn(`${lab.slug}: anchor ../${m[1]}/#${m[2]} not found`);
  }
}

export async function build() {
  const t0 = Date.now();
  warnings.length = 0;
  svgCounter = 0;
  const catalog = JSON.parse(fs.readFileSync(path.join(LABS, 'catalog.json'), 'utf8'));
  const site = { ...catalog.site, baseUrl: BASE_URL };
  const labs = loadLabs(catalog);
  const known = new Set(labs.map((l) => l.slug));
  rmGenerated();

  // Static assets
  copyDir(path.join(LABS, 'assets'), path.join(OUT, 'labs', 'assets'));
  fs.mkdirSync(path.join(OUT, 'assets'), { recursive: true });
  const parts = (dir, ext) => fs.readdirSync(path.join(SITE_SRC, dir)).filter((f) => f.endsWith(ext)).sort()
    .map((f) => `/* ${f} */\n${fs.readFileSync(path.join(SITE_SRC, dir, f), 'utf8').trim()}\n`).join('\n');
  fs.writeFileSync(path.join(OUT, 'assets', 'site.css'), parts('css', '.css'));
  fs.writeFileSync(path.join(OUT, 'assets', 'site.js'), `(() => {\n'use strict';\n${parts('js', '.js')}\n})();\n`);
  for (const f of ['favicon.svg', 'og-image.jpg']) fs.copyFileSync(path.join(SITE_SRC, f), path.join(OUT, 'assets', f));
  fs.writeFileSync(path.join(OUT, '.nojekyll'), '');

  const shared = {
    labs: labs.map((l) => ({ slug: l.slug, num: l.num, title: l.title, short: l.short })),
    paths: catalog.paths.map((p) => ({ id: p.id, title: p.title, labs: p.labs.filter((s) => known.has(s)) })),
  };

  // Labs
  const rendered = new Map();
  const searchIndex = [];
  for (const lab of labs) {
    const ctx = makeCtx(lab, site, known);
    try {
      const { html, toc, tracks: used } = await renderLab(lab.content, ctx);
      Object.assign(lab, { html, toc, usedTracks: used });
      for (const t of used) if (!lab.tracks.includes(t)) warn(`${lab.slug}: track "${t}" used in the body but missing from front matter tracks`);
    } catch (e) {
      throw new Error(`${lab.slug}: ${e.message}`);
    }
    rendered.set(lab.slug, lab.html);
    for (const m of ctx.media) {
      const dest = path.join(OUT, 'labs', lab.slug, m);
      fs.mkdirSync(path.dirname(dest), { recursive: true });
      fs.copyFileSync(path.join(lab.dir, m), dest);
    }
    const headings = [...lab.html.matchAll(/<h([23]) id="([^"]+)"><a class="anchor"[^>]*>#<\/a>([\s\S]*?)<\/h\1>/g)]
      .map((m) => ({ id: m[2], text: htmlToText(m[3]), level: Number(m[1]) }));
    searchIndex.push({
      slug: lab.slug, num: lab.num, title: lab.title, summary: lab.summary, category: lab.category,
      level: lab.level, duration: lab.duration, tracks: lab.tracks, tags: lab.tags,
      headings: headings.filter((h, i, a) => a.findIndex((x) => x.text === h.text) === i).slice(0, 60),
      text: htmlToText(lab.html).slice(0, 6000),
    });
  }

  for (const [i, lab] of labs.entries()) {
    checkAnchors(lab, lab.html, rendered);
    const rel = '../../';
    const body = labPage({ rel, site, catalog, labs, lab, html: lab.html, toc: lab.toc, prev: labs[i - 1], next: labs[i + 1] });
    write(`labs/${lab.slug}/index.html`, layout({
      rel, site, kind: 'lab', title: lab.title, description: lab.summary, body,
      canonical: `${BASE_URL}labs/${lab.slug}/`,
      data: { ...shared, lab: lab.slug, tracks: lab.tracks, mermaid: lab.html.includes('class="mermaid"') },
    }));
    write(`labs/${lab.slug}/index.md`, lab.raw);
  }

  const totals = { labs: labs.length, minutes: labs.reduce((a, l) => a + l.duration, 0) };
  write('index.html', layout({ rel: '', site, kind: 'home', title: '', description: site.tagline, body: homePage({ rel: '', site, catalog, labs, totals }), canonical: BASE_URL, data: shared }));
  write('labs/index.html', layout({ rel: '../', site, kind: 'catalog', title: 'All labs', description: `${labs.length} hands-on labs for Azure AI Gateway.`, body: catalogPage({ rel: '../', catalog, labs }), canonical: `${BASE_URL}labs/`, data: shared }));
  write('404.html', layout({ rel: BASE_PATH, site, kind: 'notfound', title: 'Page not found', body: notFoundPage({ rel: BASE_PATH }), data: shared }));
  write('search.json', JSON.stringify(searchIndex));

  // Agent and crawler friendly outputs
  const llms = [`# ${site.title}`, '', `> ${site.tagline}`, '',
    'Hands-on labs for the AI Gateway tier of Azure API Management. Each lab has portal, Azure CLI, REST, Bicep, or code tracks.', '',
    `Product docs: ${site.docs}`, `Portal: ${site.portal}`, `Source: ${site.repo}/tree/${site.branch}/labs`, '', '## Labs', '',
    ...labs.map((l) => `- [${l.num} ${l.title}](${BASE_URL}labs/${l.slug}/index.md): ${l.summary}`), '',
    '## Learning paths', '', ...catalog.paths.map((p) => `- ${p.title}: ${p.labs.filter((s) => known.has(s)).join(', ')}`), ''].join('\n');
  write('llms.txt', llms);
  write('llms-full.txt', labs.map((l) => `<!-- ${BASE_URL}labs/${l.slug}/ -->\n${l.raw.trim()}\n`).join('\n\n'));
  const urls = ['', 'labs/', ...labs.map((l) => `labs/${l.slug}/`)];
  write('sitemap.xml', `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.map((u) => `  <url><loc>${escapeHtml(BASE_URL + u)}</loc></url>`).join('\n')}\n</urlset>\n`);
  write('robots.txt', `User-agent: *\nAllow: /\nSitemap: ${BASE_URL}sitemap.xml\n`);

  console.log(`Built ${labs.length} labs into ${path.relative(process.cwd(), OUT) || '.'} in ${Date.now() - t0} ms`);
  if (warnings.length) {
    console.warn(`\n${warnings.length} warning(s):`);
    for (const w of warnings) console.warn(`  - ${w}`);
  }
  return { labs, warnings: [...warnings] };
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  await initHighlighter();
  const strict = process.argv.includes('--strict');
  const result = await build();
  if (strict && result.warnings.length) process.exitCode = 1;
  if (process.argv.includes('--watch')) {
    let timer;
    console.log('Watching labs/ for changes…');
    fs.watch(LABS, { recursive: true }, (_, file) => {
      if (!file || file.includes('node_modules') || file.startsWith('.')) return;
      clearTimeout(timer);
      timer = setTimeout(() => build().catch((e) => console.error(e.message)), 150);
    });
  }
}
