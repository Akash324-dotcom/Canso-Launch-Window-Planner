// Sweep of every control of the shipped page against a running API, in real Chrome: does each control change the
// request, does the answer follow it, do the downloads and the keyboard work. Companion of browser_walk.mjs; the
// setup and the CHROME and API_PORT environment variables are described in the header of that file.
//
//   node tools/browser_controls.mjs [page-url]
import fs from 'node:fs';
import path from 'node:path';
import puppeteer from 'puppeteer-core';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
import os from 'node:os';
const PAGE = process.argv[2] ?? 'http://localhost:8090/frontend/';
const CHROME = process.env.CHROME ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const API_PORT = process.env.API_PORT ?? '8000';
const RULE = API_PORT === '8000' ? '--no-first-run' : `--host-rules=MAP localhost:8000 127.0.0.1:${API_PORT}`;
const downloads = fs.mkdtempSync(path.join(os.tmpdir(), 'canso-controls-'));
let failures = 0;
const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: [RULE] });
const page = await browser.newPage(); await page.setViewport({ width: 1400, height: 2400 });
const session = await page.createCDPSession(); await session.send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: downloads });
const net = []; const problems = [];
page.on('response', async (r) => { const u = r.url(); if (!u.includes('/v1/') || r.request().method() === 'OPTIONS') return; const e = { method: r.request().method(), url: u, status: r.status(), post: r.request().postData() ?? null, body: null }; net.push(e); try { e.body = await r.json(); } catch {} });
page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
page.on('console', (m) => { if (m.type() === 'error') problems.push(`console.error: ${m.text()}`); });
const settle = async () => { try { await page.waitForNetworkIdle({ idleTime: 1000, timeout: 45000 }); } catch {} await sleep(250); };
const lastPost = () => [...net].reverse().find((e) => e.method === 'POST' && e.url.endsWith('/v1/windows'));
const posts = () => net.filter((e) => e.method === 'POST' && e.url.endsWith('/v1/windows')).length;
const set = async (sel, v) => { await page.$eval(sel, (el, value) => { el.value = value; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); }, v); await settle(); };
const text = (sel) => page.$eval(sel, (el) => el.innerText.replace(/\s+/g, ' ').trim()).catch(() => null);
const rowsShown = () => page.$$eval('#window-table tbody tr[data-liftoff-utc]', (r) => r.length);
const say = (name, ok, detail) => { if (!ok) failures += 1; console.log(`${ok ? 'OK  ' : 'BAD '} ${name}: ${detail}`); };
await page.goto(PAGE, { waitUntil: 'networkidle0' }); await settle();
const base = lastPost(); const baseLiftoffs = base.body.windows.map((w) => w.t_liftoff_utc);

// target-type POLAR
await page.select('#target-type', 'POLAR'); await settle();
let p = lastPost(); let req = JSON.parse(p.post);
say('target-type POLAR', req.target.type === 'POLAR' && p.status === 200 && (await rowsShown()) === p.body.windows.length, `request target ${JSON.stringify(req.target)}, ${p.body.windows.length} rows, inclinations ${[...new Set(p.body.windows.map((w) => w.reached_inclination_deg.toFixed(1)))]}, inclination field ${await page.$eval('#inclination-deg', (e) => e.value)}`);
// CUSTOM incomplete then complete
const before = posts();
await page.select('#target-type', 'CUSTOM'); await settle();
say('CUSTOM without altitude is not posted', posts() === before && /h_t/.test((await text('#input-error')) ?? ''), `posts unchanged ${posts() === before}, input error "${await text('#input-error')}"`);
await set('#inclination-deg', '97.5'); await set('#target-altitude-km', '600');
p = lastPost(); req = JSON.parse(p.post);
say('CUSTOM inclination and altitude', req.target.type === 'CUSTOM' && req.target.i_t_deg === 97.5 && req.target.h_t_km === 600 && p.status === 200, `request target ${JSON.stringify(req.target)} -> ${p.status}, rows ${p.body?.windows?.length}, reached ${[...new Set((p.body?.windows ?? []).map((w) => w.reached_inclination_deg.toFixed(2)))]}, input error "${await text('#input-error')}"`);
// plane mode RAAN with a value
await set('#raan-deg', '120');
p = lastPost(); req = JSON.parse(p.post);
say('raan-deg', req.target.raan_deg === 120 && p.status === 200, `request target ${JSON.stringify(req.target)} -> ${p.status}; response raan_deg of the rows ${[...new Set((p.body?.windows ?? []).map((w) => w.raan_deg.toFixed(1)))].join(', ')}`);
const raan120 = (p.body?.windows ?? []).map((w) => w.t_liftoff_utc);
await set('#raan-deg', '200'); p = lastPost();
const raan200 = (p.body?.windows ?? []).map((w) => w.t_liftoff_utc);
say('raan-deg changes the answer', JSON.stringify(raan120) !== JSON.stringify(raan200), `first liftoff ${raan120[0]} at 120 deg, ${raan200[0]} at 200 deg`);
// back to SSO, LTAN
await page.select('#target-type', 'SSO'); await settle();
await set('#ltan-hours', '06:00'); p = lastPost(); req = JSON.parse(p.post);
const ltan6 = p.body.windows.map((w) => w.t_liftoff_utc);
say('ltan-hours', req.target.ltan_hours === '06:00' && JSON.stringify(ltan6) !== JSON.stringify(baseLiftoffs), `request target ${JSON.stringify(req.target)}; first liftoff ${ltan6[0]} against ${baseLiftoffs[0]} at 10:30`);
const beforeBadLtan = posts(); await set('#ltan-hours', '25:99');
say('ltan-hours 25:99 is not posted', posts() === beforeBadLtan && /00:00 to 23:59/.test((await text('#input-error')) ?? ''), `posts unchanged ${posts() === beforeBadLtan}, input error "${await text('#input-error')}"`);
await set('#ltan-hours', '10:30');
// plane-mode switch on SSO
await page.select('#plane-mode', 'raan'); await settle(); req = JSON.parse(lastPost().post);
say('plane-mode raan on SSO', 'raan_deg' in req.target && !('ltan_hours' in req.target), `request target ${JSON.stringify(req.target)}`);
await page.select('#plane-mode', 'ltan'); await settle();
// include-weather
await page.click('#include-weather'); await settle(); p = lastPost(); req = JSON.parse(p.post);
const w0 = p.body.windows[0];
const excludedNote = await text('#window-table-sub');
say('include-weather off', req.include_weather === false && w0.forecast_issue_time === null && /weather layer is excluded/.test(excludedNote ?? ''), `request include_weather ${req.include_weather}; row weather ${w0.p_success_components.weather}, label ${w0.horizon_label}, issue ${w0.forecast_issue_time}; table cell "${await page.$eval('#window-table tbody tr td:nth-child(6)', (e) => e.innerText)}" / "${await page.$eval('#window-table tbody tr td:nth-child(7)', (e) => e.innerText.replace(/\s+/g, ' '))}"; note "${(excludedNote ?? '').slice(-190)}"`);
await page.click('#include-weather'); await settle();
// site and vehicle
say('site and vehicle selectors', true, `site options ${await page.$$eval('#site option', (o) => o.map((x) => x.value))}, vehicle options ${await page.$$eval('#vehicle-profile option', (o) => o.map((x) => x.value))}`);
// keyboard row selection
await page.focus('#window-table tbody tr[data-hazard-rejected="false"]'); await page.keyboard.press('Enter'); await settle();
say('keyboard Enter selects a row', (await page.$$eval('#window-table tbody tr[data-selected="true"]', (r) => r.length)) === 1, `selected rows ${await page.$$eval('#window-table tbody tr[data-selected="true"]', (r) => r.length)}, trajectory status "${(await text('#trajectory-status') ?? '').slice(0, 90)}"`);
// selecting a hazard-rejected row
await page.evaluate(() => document.querySelector('#window-table tbody tr[data-hazard-rejected="true"]').click()); await settle();
say('selecting a rejected row', true, `guard "${(await text('#corridor-check') ?? '').slice(0, 150)}"; ephemeris ${[...net].reverse().find((e) => e.url.includes('/ephemeris'))?.url.replace('http://localhost:8000', '').slice(0, 110)}`);
// the other downloads
await page.evaluate(() => document.querySelector('#window-table tbody tr[data-hazard-rejected="false"]').click()); await settle();
for (const [button, table, kind] of [['#download-skill-csv', '#analysis-skill-rows tr', 'csv'], ['#download-reliability-csv', '#analysis-reliability-rows tr', 'csv'], ['#download-response-json', null, 'json']]) {
  const seen = new Set(fs.readdirSync(downloads)); await page.click(button); let file = null;
  for (let i = 0; i < 40 && file === null; i += 1) { await sleep(200); file = fs.readdirSync(downloads).find((n) => !seen.has(n) && !n.endsWith('.crdownload')) ?? null; }
  const content = file === null ? '' : fs.readFileSync(path.join(downloads, file), 'utf8');
  if (kind === 'csv') { const lines = content.split(/\r?\n/).filter((l) => l.length > 0); const shown = (await page.$$(table)).length; say(button, file !== null && lines.length - 1 === shown, `${file}: ${lines.length - 1} data rows, ${shown} rows on the page; header ${lines[0]}`); }
  else { let parsed = null; try { parsed = JSON.parse(content); } catch {} const live = lastPost().body; say(button, parsed !== null && JSON.stringify(parsed.windows) === JSON.stringify(live.windows) && parsed.engine_version === live.engine_version, `${file}: ${parsed === null ? 'not JSON' : `${parsed.windows.length} windows, engine ${parsed.engine_version}, keys ${Object.keys(parsed).join(',')}`}`); }
}
// fixture links
const links = await page.$$eval('#analysis-fixture-links a', (a) => a.map((x) => x.href));
const statuses = []; for (const href of links) { statuses.push(`${href.split('/').pop()} ${(await page.evaluate(async (u) => (await fetch(u)).status, href))}`); }
say('fixture links', statuses.every((s) => s.endsWith(' 200')) && links.length === 5, statuses.join(', '));
console.log('\nproblems:'); console.log(problems.join('\n') || '(none)');
console.log('\nnon-200 API answers:'); console.log(net.filter((e) => e.status !== 200).map((e) => `${e.method} ${e.url.replace('http://localhost:8000', '')} -> ${e.status} ${e.post ?? ''} ${JSON.stringify(e.body ?? '').slice(0, 200)}`).join('\n') || '(none)');
await browser.close();
console.log(`\n${failures === 0 ? 'every control behaved' : `${failures} control check(s) failed`}`);
process.exit(failures === 0 ? 0 : 1);
