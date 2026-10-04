// Browser check of `Canso Launch Prototype.html` (issue #27). Real Chrome, the page as served, the API as
// running. Four scenarios: live API, API unreachable (offline fixtures), inputs sent to the API, and a static
// check that the page needs nothing from the internet. Exit code 1 when any check fails.
//
// Setup, from the repository root:
//   python -m uvicorn backend.api.app:create_app --factory --port 8000     (the API)
//   python -m http.server 5500                                            (static server, repo root)
//   cd frontend && npm install --no-save puppeteer-core
//   CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" node tools/prototype_e2e.mjs
//
// Environment:
//   CHROME      path of the Chrome binary (default: the macOS application path)
//   PAGE        page URL (default http://localhost:5500/Canso%20Launch%20Prototype.html)
//   API_ORIGIN  origin of the API (default http://localhost:8000)
//   NO_SANDBOX  set to 1 to start Chrome with --no-sandbox (needed when running as root, for example in a container)
//   OUT         write the JSON record of the run to this path
//   SHOTS       directory to write two screenshots into (optional)
import fs from 'node:fs';
import puppeteer from 'puppeteer-core';

const PAGE = process.env.PAGE ?? 'http://localhost:5500/Canso%20Launch%20Prototype.html';
const API_ORIGIN = process.env.API_ORIGIN ?? 'http://localhost:8000';
const CHROME = process.env.CHROME ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const ARGS = ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'];
if (process.env.NO_SANDBOX === '1') ARGS.push('--no-sandbox');
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const pageOrigin = new URL(PAGE).origin;
const ALLOWED = new Set([pageOrigin, API_ORIGIN]);

const results = [];
function check(scenario, name, ok, detail = '') {
  results.push({ scenario, name, ok, detail });
  console.log(`${ok ? 'PASS' : 'FAIL'}  [${scenario}] ${name}${detail === '' ? '' : '  ' + detail}`);
}

async function open({ blockApi = false } = {}) {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ARGS });
  const page = await browser.newPage();
  await page.setViewport({ width: 1500, height: 900 });
  const log = { requests: [], posts: [], consoleErrors: [], pageErrors: [] };
  await page.setRequestInterception(true);
  page.on('request', (request) => {
    const url = request.url();
    log.requests.push({ method: request.method(), url });
    if (request.method() === 'POST' && url.includes('/v1/windows')) {
      log.posts.push(JSON.parse(request.postData() ?? 'null'));
    }
    if (blockApi && url.startsWith(API_ORIGIN)) {
      request.abort('connectionrefused');
    } else {
      request.continue();
    }
  });
  page.on('console', (message) => {
    const text = message.text();
    if (message.type() === 'error' && !text.includes('Failed to load resource')) log.consoleErrors.push(text);
  });
  page.on('pageerror', (error) => log.pageErrors.push(String(error.stack ?? error)));
  await page.goto(PAGE, { waitUntil: 'load' });
  await page.waitForFunction(() => document.querySelectorAll('#rows tr').length > 0 || !document.getElementById('fault').hidden, {
    timeout: 30000,
  });
  await sleep(1200);
  await page.evaluate(() => document.getElementById('skip')?.click());
  await page.evaluate(() => document.getElementById('mPlanner').click());
  await sleep(800);
  return { browser, page, log };
}

const text = (page, selector) => page.$eval(selector, (node) => node.innerText ?? node.textContent);
const pad = (n) => String(n).padStart(2, '0');
function utcCell(iso) {
  const d = new Date(iso);
  const month = d.toLocaleString('en', { month: 'short', timeZone: 'UTC' });
  return `${pad(d.getUTCDate())} ${month} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}Z`;
}
function externalRequests(log) {
  return log.requests.filter((r) => {
    if (r.url.startsWith('data:') || r.url.startsWith('blob:')) return false;
    return !ALLOWED.has(new URL(r.url).origin);
  });
}
const GHOSTS = ['Guysborough', 'Sherbrooke', 'JPSS', 'mock_windows', 'generic limits', 'Not scored in the demo engine',
  '45.10°N', '61.02°W', '82°–195°', 'Spin help', 'confidence'];

// ---------------------------------------------------------------------------------------------- live
async function live() {
  const s = 'live';
  const { browser, page, log } = await open();
  try {
    const rows = await page.$$eval('#rows tr', (trs) =>
      trs.map((tr) => ({ sub: tr.querySelector('.sub')?.textContent ?? '', cells: [...tr.querySelectorAll('td')].map((td) => td.textContent) })),
    );
    const body = log.posts[0];
    check(s, 'the page sent POST /v1/windows', body !== undefined, JSON.stringify(body));
    check(s, 'the page read GET /v1/site', log.requests.some((r) => r.url === `${API_ORIGIN}/v1/site`));
    check(s, 'no request leaves the page origin and the API', externalRequests(log).length === 0, externalRequests(log).map((r) => r.url).join(' '));
    const api = await (await fetch(`${API_ORIGIN}/v1/windows`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })).json();
    check(s, 'table row count equals the API row count', rows.length === api.windows.length, `${rows.length} vs ${api.windows.length}`);
    const sameTimes = api.windows.every((w, i) => rows[i] !== undefined && rows[i].sub.includes(utcCell(w.t_liftoff_utc)));
    check(s, 'every liftoff time equals t_liftoff_utc of the API row', sameTimes);
    const sameAim = api.windows.every((w, i) => rows[i] !== undefined && rows[i].cells[3].includes(`${w.azimuth_compass_deg.toFixed(1)}°`));
    check(s, 'every aim equals azimuth_compass_deg of the API row', sameAim);
    const sameInc = api.windows.every((w, i) => rows[i] !== undefined && rows[i].cells[4].includes(`${w.reached_inclination_deg.toFixed(2)}°`));
    check(s, 'every reached inclination equals the API row', sameInc);
    const sameP = api.windows.every((w, i) => rows[i] !== undefined && rows[i].cells[7].includes(`p_success ${w.p_success.toFixed(2)}`));
    check(s, 'every p_success equals the API row', sameP);
    const usable = api.windows.filter((w) => w.screens.hazard === 'pass').length;
    const pills = await page.$$eval('#rows tr .pill.is-ok', (n) => n.length);
    check(s, 'corridor pills equal the hazard screens of the API rows', pills === usable, `${pills} vs ${usable}`);
    const site = await (await fetch(`${API_ORIGIN}/v1/site`)).json();
    const brand = await text(page, '#brandSub');
    check(s, 'header coordinates come from GET /v1/site', brand.includes(`${site.phi_s_deg.toFixed(2)}°N`) && brand.includes(`${Math.abs(site.lambda_s_deg).toFixed(2)}°W`), brand);
    check(s, 'offline banner hidden', await page.$eval('#offline', (n) => n.hidden));
    const a = await text(page, '#cd');
    await sleep(2200);
    const b = await text(page, '#cd');
    check(s, 'countdown ticks', a !== b && /\d\d:\d\d:\d\d/.test(a), `${a} then ${b}`);
    const src = await text(page, '#src');
    check(s, 'source line names POST /v1/windows and the run id', src.includes('POST /v1/windows') && src.includes(api.constants_block.citation_id.slice(0, 8)), src);
    const all = await page.evaluate(() => document.body.innerText + document.documentElement.innerHTML.replace(/data:[^"')]+/g, ''));
    const found = GHOSTS.filter((g) => all.includes(g));
    check(s, 'no ghost string on the page', found.length === 0, found.join(', '));
    check(s, 'no console error, no page error', log.consoleErrors.length === 0 && log.pageErrors.length === 0, [...log.consoleErrors, ...log.pageErrors].join(' | '));
    const note = await text(page, '#rec');
    check(s, 'the ascent arc status is stated (drawn, or the reason it is not)', /Ascent arc:|No ascent arc drawn:/.test(note), note.split('\n').slice(-1)[0]);
    if (process.env.SHOTS) await page.screenshot({ path: `${process.env.SHOTS}/prototype_live.png` });
  } finally {
    await browser.close();
  }
}

// ---------------------------------------------------------------------------------------------- offline
async function offline() {
  const s = 'offline';
  const { browser, page, log } = await open({ blockApi: true });
  try {
    const banner = await text(page, '#offlineT');
    const visible = await page.$eval('#offline', (n) => !n.hidden);
    check(s, 'the offline banner is shown', visible && banner.startsWith('OFFLINE PRECOMPUTED DATA, mode offline_precomputed'), banner.slice(0, 220));
    check(s, 'the banner names the fixtures in use', banner.includes('windows.json') && banner.includes('site.json'));
    const fixtureWindows = JSON.parse(await (await fetch(`${pageOrigin}/backend/fixtures/windows.json`)).text());
    const rows = await page.$$eval('#rows tr', (n) => n.length);
    check(s, 'the table renders the fixture rows', rows === fixtureWindows.windows.length, `${rows} vs ${fixtureWindows.windows.length}`);
    check(s, 'the countdown renders', /\d\d:\d\d:\d\d/.test(await text(page, '#cd')), await text(page, '#cd'));
    check(s, 'the globe canvas is present', (await page.$('#stage canvas')) !== null);
    check(s, 'no request leaves the page origin and the API', externalRequests(log).length === 0, externalRequests(log).map((r) => r.url).join(' '));
    check(s, 'fonts and scripts load from vendor/prototype', log.requests.some((r) => r.url.includes('/vendor/prototype/three.min.js')) && log.requests.some((r) => r.url.includes('/vendor/prototype/fonts/')));
    check(s, 'no page error', log.pageErrors.length === 0 && log.consoleErrors.length === 0, [...log.consoleErrors, ...log.pageErrors].join(' | '));
    const srcLine = await text(page, '#src');
    check(s, 'the source line says offline fixture', srcLine.includes('Offline fixture'), srcLine);
    await page.evaluate(() => document.getElementById('mPublic').click());
    await page.evaluate(() => document.getElementById('watch').click());
    await sleep(800);
    const towns = await text(page, '#townsB');
    check(s, 'the viewing table gives numbers or states why not', /\d+°/.test(towns) || towns.includes('No viewing report'), towns.replace(/\s+/g, ' ').slice(0, 160));
    if (process.env.SHOTS) await page.screenshot({ path: `${process.env.SHOTS}/prototype_offline.png` });
  } finally {
    await browser.close();
  }
}

// ---------------------------------------------------------------------------------------------- inputs
async function inputs() {
  const s = 'inputs';
  const { browser, page, log } = await open();
  try {
    const choose = async (value) => {
      const before = log.posts.length;
      await page.select('#preset', value);
      await page.waitForFunction((n) => true, {}, before);
      for (let i = 0; i < 40 && log.posts.length === before; i += 1) await sleep(150);
      await sleep(900);
    };
    await choose('POLAR');
    check(s, 'POLAR sends target.type POLAR', log.posts.at(-1)?.target?.type === 'POLAR', JSON.stringify(log.posts.at(-1)?.target));
    check(s, 'POLAR renders rows', (await page.$$eval('#rows tr', (n) => n.length)) > 0);
    await choose('LEO');
    const unreachable = await page.$eval('#unreach', (n) => getComputedStyle(n).display !== 'none');
    check(s, 'LEO is unreachable at the pad latitude and says so', unreachable && (await text(page, '#unreachMath')).includes('reachable: false'), (await text(page, '#unreachMath')).slice(0, 160));
    await choose('LOW');
    check(s, 'the guided low example sends a CUSTOM target', log.posts.at(-1)?.target?.type === 'CUSTOM' && log.posts.at(-1)?.target?.i_t_deg === 30, JSON.stringify(log.posts.at(-1)?.target));
    await choose('SSO');
    check(s, 'SSO sends the LTAN of the preset', log.posts.at(-1)?.target?.type === 'SSO' && log.posts.at(-1)?.target?.ltan_hours === '10:30', JSON.stringify(log.posts.at(-1)?.target));
    const before = log.posts.length;
    await page.$eval('#days', (n) => { n.value = '2'; n.dispatchEvent(new Event('input', { bubbles: true })); });
    for (let i = 0; i < 40 && log.posts.length === before; i += 1) await sleep(150);
    const range = log.posts.at(-1)?.date_range;
    const span = (Date.parse(range.end) - Date.parse(range.start)) / 86400000;
    check(s, 'days=2 sends a two-day range', span === 1, JSON.stringify(range));
    const before2 = log.posts.length;
    await page.$eval('#wxon', (n) => n.click());
    for (let i = 0; i < 40 && log.posts.length === before2; i += 1) await sleep(150);
    await sleep(800);
    check(s, 'weather off sends include_weather false', log.posts.at(-1)?.include_weather === false);
    const chips = await page.$$eval('#rows tr td:last-child .wx', (n) => n.map((x) => x.textContent.trim()));
    check(s, 'weather off greys every weather chip', chips.length > 0 && chips.every((c) => c.includes('Unknown')), chips.join(','));
    const before3 = log.posts.length;
    await page.$eval('#alt', (n) => { n.value = ''; n.dispatchEvent(new Event('input', { bubbles: true })); });
    await sleep(1500);
    check(s, 'a CUSTOM target without an altitude is refused on the page, not sent', log.posts.length === before3 && (await page.$eval('#fault', (n) => !n.hidden)), await text(page, '#faultT'));
    check(s, 'no page error', log.pageErrors.length === 0 && log.consoleErrors.length === 0, [...log.consoleErrors, ...log.pageErrors].join(' | '));
  } finally {
    await browser.close();
  }
}

// ---------------------------------------------------------------------------------------------- static
async function staticPage() {
  const s = 'static';
  const html = await (await fetch(PAGE)).text();
  const external = [...html.matchAll(/(?:src|href)=["'](https?:\/\/[^"']+)["']/g)].map((m) => m[1]);
  check(s, 'the page references no external script, stylesheet or font', external.length === 0, external.join(' '));
  check(s, 'the page has no embedded mock window list', !/"mock"\s*:/.test(html) && !/findWindows|synthTrack|fromMock/.test(html));
  for (const file of ['three.min.js', 'OrbitControls.js', 'Line2.js', 'LineMaterial.js', 'gsap.min.js', 'fonts.css']) {
    const response = await fetch(new URL(`vendor/prototype/${file}`, PAGE));
    check(s, `vendor/prototype/${file} is served`, response.ok, String(response.status));
  }
}

const scenarios = { live, offline, inputs, staticPage };
const only = process.argv[2];
for (const [name, fn] of Object.entries(scenarios)) {
  if (only !== undefined && only !== name) continue;
  try {
    await fn();
  } catch (error) {
    check(name, 'scenario completed', false, String(error.stack ?? error).split('\n').slice(0, 3).join(' | '));
  }
}
const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length} passed, ${failed.length} failed`);
if (process.env.OUT) fs.writeFileSync(process.env.OUT, JSON.stringify(results, null, 2));
process.exit(failed.length === 0 ? 0 : 1);
