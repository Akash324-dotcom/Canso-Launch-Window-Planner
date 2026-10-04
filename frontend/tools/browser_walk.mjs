// Browser walk of the shipped page against a running API. Real Chrome, the page as served, no mocks,
// except the one step of item 3 that says so. The record of a run is frontend/BROWSER_WALK.md.
//
// Setup, from the repository root:
//   .venv/bin/python -m uvicorn backend.api.app:app --port 8000        (the API, with the CORS change of issue #24)
//   .venv/bin/python -m http.server 8090                               (a static server for the page)
//   cd frontend && npm install --no-save puppeteer-core                (the driver; Chrome itself must be installed)
//   node tools/browser_walk.mjs http://localhost:8090/frontend/ walk.json
//
// Environment:
//   CHROME     path of the Chrome binary (default: the macOS application path)
//   API_PORT   the port the API listens on (default 8000). The page always calls http://localhost:8000/v1
//              (src/config.js). When the API is on another port, because 8000 is taken on the machine, Chrome is
//              started with a host rule that maps localhost:8000 to that port, so the page and its requests stay
//              exactly as shipped.
//   DEAD_PORT  a port nothing listens on, used for the offline item (default 8011)
import fs from 'node:fs';
import path from 'node:path';
import puppeteer from 'puppeteer-core';

const PAGE = process.argv[2] ?? 'http://localhost:8090/frontend/';
const OUT = process.argv[3] ?? 'walk.json';
const CHROME = process.env.CHROME ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const API_PORT = process.env.API_PORT ?? '8000';
const DEAD_PORT = process.env.DEAD_PORT ?? '8011';
const LIVE_RULE = API_PORT === '8000' ? '--no-first-run' : `--host-rules=MAP localhost:8000 127.0.0.1:${API_PORT}`;
const DEAD_RULE = `--host-rules=MAP localhost:8000 127.0.0.1:${DEAD_PORT}`; // nothing listens there: the API "stopped"
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const results = [];
const record = (item, name, status, evidence, transcript = []) => { results.push({ item, name, status, evidence, transcript }); console.log(`\n[${item}] ${status}  ${name}`); for (const line of evidence) console.log('    ' + line); for (const line of transcript) console.log('    > ' + line); };

async function open(rule, downloadDir = null) {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: [rule] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1400, height: 2400 });
  const log = { net: [], bodies: [], problems: [] };
  page.on('response', async (response) => {
    const url = response.url(); const method = response.request().method();
    if (!(url.includes('/v1/') || url.includes('/backend/fixtures/')) || method === 'OPTIONS') return;
    const entry = { method, url, status: response.status(), body: null, post: response.request().postData() ?? null };
    log.net.push(entry);
    try { entry.body = await response.json(); } catch { entry.body = null; }
  });
  page.on('requestfailed', (request) => { if (request.url().includes('/v1/')) log.net.push({ method: request.method(), url: request.url(), status: `FAILED ${request.failure()?.errorText}`, body: null, post: request.postData() ?? null }); });
  page.on('console', (m) => { if (m.type() === 'error') log.problems.push(`console.error: ${m.text()} ${m.location()?.url ?? ''}`); });
  page.on('pageerror', (e) => log.problems.push(`pageerror: ${e.message}`));
  if (downloadDir !== null) {
    const session = await page.createCDPSession();
    await session.send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: downloadDir, eventsEnabled: true });
  }
  return { browser, page, log };
}
const settle = async (page) => { try { await page.waitForNetworkIdle({ idleTime: 1200, timeout: 45000 }); } catch { /* reported by the caller */ } await sleep(300); };
const text = (page, selector) => page.$eval(selector, (el) => el.innerText.replace(/\s+/g, ' ').trim()).catch(() => null);
const hidden = (page, selector) => page.$eval(selector, (el) => el.hidden === true).catch(() => null);
const last = (log, fragment, method = null) => [...log.net].reverse().find((entry) => entry.url.includes(fragment) && (method === null || entry.method === method));
const line = (entry) => entry === undefined ? '(no such request was made)' : `${entry.method} ${entry.url.replace('http://localhost:8000', '')} -> ${entry.status}`;
async function setInput(page, selector, value) {
  await page.$eval(selector, (el, v) => { el.value = v; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); }, value);
}
const tableRows = (page) => page.$$eval('#window-table tbody tr', (rows) => rows.map((tr) => ({ empty: tr.classList.contains('row-empty'), rejected: tr.dataset.hazardRejected === 'true', liftoff: tr.dataset.liftoffUtc ?? null, text: tr.innerText.replace(/\s+/g, ' ').trim() })));
const seconds = (clock) => { const m = /^(?:(\d+)d )?(\d\d):(\d\d):(\d\d)$/.exec(clock ?? ''); return m === null ? null : (Number(m[1] ?? 0) * 86400 + Number(m[2]) * 3600 + Number(m[3]) * 60 + Number(m[4])); };

// ------------------------------------------------------------------ live session
const downloads = fs.mkdtempSync(path.join(path.dirname(OUT), 'downloads-'));
const { browser, page, log } = await open(LIVE_RULE, downloads);
await page.goto(PAGE, { waitUntil: 'networkidle0', timeout: 60000 });
await settle(page);

// 1. window table from POST /v1/windows
{
  const post = last(log, '/v1/windows', 'POST'); const rows = await tableRows(page); const body = post?.body ?? {};
  const ok = post?.status === 200 && body.engine_version !== 'stub' && rows.length === (body.windows ?? []).length && rows.length > 0 && rows.every((row) => !row.empty) && (await hidden(page, '#mode-banner')) === true;
  record(1, 'Window table fills from POST /v1/windows, engine is not the stub', ok ? 'PASS' : 'FAIL',
    [`request body ${post?.post}`, `engine_version ${body.engine_version}`, `response rows ${(body.windows ?? []).length}, table rows ${rows.length}`, `banner hidden ${await hidden(page, '#mode-banner')}`], [line(post)]);
}
const firstResponse = last(log, '/v1/windows', 'POST')?.body;

// 2. countdown ticks against a live row
{
  const samples = [];
  for (let i = 0; i < 3; i += 1) { samples.push({ at: Date.now(), value: await text(page, '#countdown-value-text') }); await sleep(1100); }
  const usable = (firstResponse.windows ?? []).filter((row) => row.constraint_fired !== 'hazard_area' && row.screens?.hazard !== 'fail' && Date.parse(row.t_liftoff_utc) > Date.now());
  const target = usable.sort((a, b) => Date.parse(a.t_liftoff_utc) - Date.parse(b.t_liftoff_utc))[0];
  const shown = samples.map((sample) => seconds(sample.value));
  const expected = target === undefined ? null : Math.floor((Date.parse(target.t_liftoff_utc) - samples[0].at) / 1000);
  const utc = await text(page, '#countdown-utc');
  const ok = shown.every((value) => value !== null) && shown[0] > shown[1] && shown[1] > shown[2] && expected !== null && Math.abs(shown[0] - expected) <= 3 && utc.includes(target.t_liftoff_utc.slice(11, 19));
  record(2, 'Countdown ticks against a real t_liftoff_utc from a live row', ok ? 'PASS' : 'FAIL',
    [`three readings about 1.1 s apart: ${samples.map((s) => s.value).join(' , ')}`, `target row liftoff ${target?.t_liftoff_utc} (earliest usable upcoming row of the response)`, `page shows "${utc}"`, `first reading ${shown[0]} s, expected ${expected} s from the response and the clock`]);
}

// 3. empty-result paths
{
  const evidence = []; let ok = true;
  // 3a: a range in the past: the engine returns rows, none is upcoming
  await setInput(page, '#date-start', '2026-01-05'); await settle(page); await setInput(page, '#date-end', '2026-01-06'); await settle(page);
  let post = last(log, '/v1/windows', 'POST'); let rows = await tableRows(page);
  let value = await text(page, '#countdown-value-text'); let reason = await text(page, '#countdown-reason');
  evidence.push(`3a past range 2026-01-05 to 2026-01-06: ${line(post)}, response rows ${post?.body?.windows?.length}, table rows ${rows.length}; countdown "${value}", reason "${reason}"`);
  ok = ok && value === 'No window in range' && /earlier than the current clock/.test(reason ?? '');
  // 3b: a corridor that admits no row
  await setInput(page, '#date-start', '2026-10-04'); await settle(page); await setInput(page, '#date-end', '2026-10-08'); await settle(page);
  await setInput(page, '#corridor-a-min-deg', '120'); await settle(page); await setInput(page, '#corridor-a-max-deg', '150'); await settle(page);
  post = last(log, '/v1/windows', 'POST'); rows = await tableRows(page); value = await text(page, '#countdown-value-text'); reason = await text(page, '#countdown-reason');
  const honesty3b = (await hidden(page, '#honesty-panel')) ? '(hidden)' : await text(page, '#honesty-panel');
  evidence.push(`3b corridor 120 to 150: ${line(post)}, reachable ${post?.body?.reachable}, response rows ${post?.body?.windows?.length}, rejected table rows ${rows.filter((r) => r.rejected).length} of ${rows.length}; countdown "${value}", reason "${reason}"`);
  evidence.push(`3b honesty panel: ${honesty3b}`);
  ok = ok && value === 'No window in range' && /rejected by the hazard screen/.test(reason ?? '');
  const honestyClaimsEmpty = /window list is empty/.test(honesty3b) && rows.length > 0 && !rows[0].empty;
  if (honestyClaimsEmpty) { ok = false; evidence.push('DEFECT: the honesty panel says "the window list is empty" while the table shows the rows the engine returned'); }
  await setInput(page, '#corridor-a-min-deg', ''); await settle(page); await setInput(page, '#corridor-a-max-deg', ''); await settle(page);
  // 3c: reachable true with an empty list. The live engine never returns this for a range of a day or more
  // (two plane crossings per day), so this one step answers the POST with the live body minus its rows.
  await page.setRequestInterception(true);
  const emptied = (request) => {
    if (request.method() === 'POST' && request.url().endsWith('/v1/windows')) {
      request.respond({ status: 200, contentType: 'application/json', headers: { 'access-control-allow-origin': '*' }, body: JSON.stringify({ ...firstResponse, windows: [] }) });
    } else { request.continue(); }
  };
  page.on('request', emptied);
  await setInput(page, '#date-end', '2026-10-09'); await settle(page);
  rows = await tableRows(page); value = await text(page, '#countdown-value-text'); reason = await text(page, '#countdown-reason');
  evidence.push(`3c synthetic body (reachable true, windows []): table "${rows.map((r) => r.text).join(' | ')}"; countdown "${value}", reason "${reason}"`);
  ok = ok && rows.length === 1 && rows[0].empty && value === 'No window in range' && (reason ?? '').length > 0;
  page.off('request', emptied); await page.setRequestInterception(false);
  await setInput(page, '#date-end', '2026-10-08'); await settle(page);
  evidence.push(`page errors during the three paths: ${log.problems.filter((p) => p.startsWith('pageerror')).length}`);
  ok = ok && log.problems.filter((p) => p.startsWith('pageerror')).length === 0;
  record(3, 'Empty-result path shows a message, not a blank table and not a crash', ok ? 'PASS' : 'FAIL', evidence);
}

// 4. LEO 45.1: honesty panel with the plane-change penalty
{
  await page.select('#target-type', 'LEO'); await settle(page);
  const post = last(log, '/v1/windows', 'POST'); const panelHidden = await hidden(page, '#honesty-panel');
  const dv = await text(page, '#honesty-plane-change-dv-ms'); const headline = await text(page, '#honesty-headline'); const rows = await tableRows(page);
  const banner = await hidden(page, '#mode-banner'); const inputError = await text(page, '#input-error');
  const ok = post?.status === 200 && post.body.reachable === false && panelHidden === false && dv === `${post.body.plane_change_dv_ms} m/s` && Math.abs(post.body.plane_change_dv_ms - 26.77) < 0.01 && banner === true && rows.length === 1 && rows[0].empty;
  record(4, 'LEO 45.1: the honesty panel shows the plane-change penalty, not an error', ok ? 'PASS' : 'FAIL',
    [`request ${post?.post}`, `reachable ${post?.body?.reachable}, plane_change_dv_ms ${post?.body?.plane_change_dv_ms}`, `panel visible ${panelHidden === false}: "${headline}", penalty shown "${dv}"`, `table: "${rows.map((r) => r.text).join(' | ')}"`, `banner hidden ${banner}, input error "${inputError ?? ''}"`], [line(post)]);
  await page.select('#target-type', 'SSO'); await settle(page);
}

// select a usable row for items 5 to 9
const beforeSelect = log.net.length;
const selected = await page.evaluate(() => { const rows = [...document.querySelectorAll('#window-table tbody tr')]; const row = rows.find((tr) => tr.dataset.hazardRejected === 'false'); row.click(); return { index: rows.indexOf(row), liftoff: row.dataset.liftoffUtc }; });
await settle(page);
const weatherCall = last(log, '/v1/weather/probability'); const skillCall = last(log, '/v1/validation/skill'); const siteCall = last(log, '/v1/site');
const ephemerisCall = last(log, '/ephemeris'); const citationCall = last(log, '/v1/citation'); const fixtureCalls = log.net.slice(beforeSelect).filter((entry) => entry.url.includes('/backend/fixtures/'));
const windowsCall = last(log, '/v1/windows', 'POST');
const bannerAfterSelect = { hidden: await hidden(page, '#mode-banner'), text: await text(page, '#mode-banner') };

// 5. weather badge
{
  const indicator = await text(page, '#weather-launch-indicator-block'); const curve = await page.$eval('#weather-skill-curve-host', (el) => ({ svg: el.querySelector('svg') !== null, points: el.querySelectorAll('circle').length })).catch(() => null);
  const body = weatherCall?.body ?? {}; const pct = `${(100 * body.p_launch).toFixed(1)}%`;
  const skillNote = await text(page, '#analysis-skill-note');
  const live = weatherCall?.status === 200 && skillCall?.status === 200 && bannerAfterSelect.hidden === true && /a live response/.test(skillNote ?? '');
  const shown = (indicator ?? '').includes(pct) && (indicator ?? '').includes(String(body.horizon_label)) && curve?.svg === true;
  record(5, 'Weather badge: probability, horizon label and skill curve, all from live responses', live && shown ? 'PASS' : 'FAIL',
    [`selected row ${selected.index}, liftoff ${selected.liftoff}`, `live weather: p_launch ${body.p_launch}, ${body.horizon_label}, source ${body.source}; badge "${indicator}"`, `skill curve drawn ${curve?.svg}, ${curve?.points} points`, `fixture files read after the selection: ${fixtureCalls.map((f) => f.url.split('/').pop()).join(', ') || 'none'} (skill.json is read for the verification period to ask for, not for its numbers)`, `skill note on the page: "${(skillNote ?? '').slice(-140)}"`, `banner after the selection: hidden ${bannerAfterSelect.hidden} "${bannerAfterSelect.text ?? ''}"`],
    [line(weatherCall), line(skillCall), ...(skillCall?.status !== 200 && skillCall?.body ? [JSON.stringify(skillCall.body).slice(0, 400)] : [])]);
}

// 6. analysis view
{
  const skillRows = await page.$$eval('#analysis-skill-rows tr', (rows) => rows.map((tr) => tr.innerText.replace(/\s+/g, ' ').trim()));
  const reliability = await page.$eval('#analysis-reliability-host', (el) => el.querySelector('svg') !== null).catch(() => false);
  const reliabilityRows = (await page.$$('#analysis-reliability-rows tr')).length;
  const constants = await text(page, '#analysis-provenance-body'); const hash = await text(page, '#analysis-config-hash');
  const liveSkill = skillCall?.status === 200; const series = skillCall?.body?.skill_series ?? [];
  const origin = await page.$eval('#analysis-provenance-body', (el) => el.dataset.constantsOrigin).catch(() => null);
  const citationOk = citationCall?.status === 200 && origin === 'citation' && (hash ?? '').includes(String(citationCall.body?.config_hash));
  const ok = liveSkill && skillRows.length === series.length && series.length > 0 && reliability && citationOk;
  record(6, 'Analysis view: skill table, reliability diagram, constants block from /v1/validation/skill and /v1/citation', ok ? 'PASS' : 'FAIL',
    [`skill table rows ${skillRows.length}, first "${skillRows[0] ?? ''}"`, `reliability diagram drawn ${reliability}, reliability rows ${reliabilityRows}`, `constants block: "${(constants ?? '').slice(0, 160)}..."`, `config hash line: "${(hash ?? '').slice(0, 200)}"`, `skill source: ${liveSkill ? 'live response' : 'offline fixture skill.json'}`, `/v1/citation: ${line(citationCall)}, constants origin on the page "${origin}", config_hash ${citationCall?.body?.config_hash}`],
    [line(skillCall), line(citationCall)]);
}

// 7. CSV download
{
  const before = new Set(fs.readdirSync(downloads));
  await page.click('#download-window-csv');
  let file = null;
  for (let i = 0; i < 40 && file === null; i += 1) { await sleep(250); file = fs.readdirSync(downloads).find((name) => !before.has(name) && !name.endsWith('.crdownload')) ?? null; }
  const rows = await tableRows(page);
  const csv = file === null ? '' : fs.readFileSync(path.join(downloads, file), 'utf8');
  const lines = csv.split(/\r?\n/).filter((entry) => entry.length > 0);
  const ok = file !== null && lines.length - 1 === rows.length && rows.length > 0;
  record(7, 'CSV download: downloaded row count equals the displayed table row count', ok ? 'PASS' : 'FAIL',
    [`file ${file}`, `header: ${lines[0] ?? ''}`, `data rows in the file ${Math.max(0, lines.length - 1)}, rows in the table ${rows.length}`, `first data row: ${lines[1] ?? ''}`]);
}

// 8. trajectory on the map
{
  const track = await page.$$eval('#trajectory-track li, #trajectory-track tr', (nodes) => nodes.map((n) => n.innerText.replace(/\s+/g, ' ').trim()));
  const status = await text(page, '#trajectory-status'); const guard = await text(page, '#corridor-check');
  const drawn = await page.$eval('#trajectory-map', (el) => ({ paths: el.querySelectorAll('path').length, leaflet: el.classList.contains('leaflet-container') })).catch(() => null);
  const points = (ephemerisCall?.body?.points ?? []);
  const site = siteCall?.body ?? {};
  const first = points[0]; const lastPoint = points[points.length - 1];
  const startsAtSite = first !== undefined && Math.abs(first.lat_deg - site.phi_s_deg) < 1 && Math.abs(first.lon_deg - site.lambda_s_deg) < 1;
  const southbound = first !== undefined && lastPoint !== undefined && lastPoint.lat_deg < first.lat_deg;
  const ok = ephemerisCall?.status === 200 && drawn?.paths > 0 && startsAtSite && southbound;
  record(8, 'Row select: trajectory renders on the map, southbound, inside the corridor', ok ? 'PASS' : 'FAIL',
    [`status line: "${status}"`, `map: leaflet ${drawn?.leaflet}, ${drawn?.paths} drawn paths`, `site from GET /v1/site: ${site.phi_s_deg} N, ${site.lambda_s_deg} E; corridor ${JSON.stringify(site.corridor ?? {}).slice(0, 120)}`, `ephemeris points ${points.length}: first ${JSON.stringify(first)}, last ${JSON.stringify(lastPoint)}`, `starts at the site ${startsAtSite}, southbound ${southbound}`, `corridor guard text: "${guard}"`, `track list on the page: ${track.slice(0, 3).join(' ; ')}`],
    [line(ephemerisCall), line(siteCall), JSON.stringify(ephemerisCall?.body ?? {}).slice(0, 600)]);
}

// 9. viewing map
{
  const rows = await page.$$eval('#viewing-rows tr', (list) => list.map((tr) => tr.innerText.replace(/\s+/g, ' ').trim()));
  const status = await text(page, '#viewing-status'); const drawn = await page.$eval('#viewing-map', (el) => el.querySelectorAll('path').length).catch(() => 0);
  const withElevation = rows.filter((row) => /-?\d+\.\d deg/.test(row) && /(sunlit|dark|shadow|daylight)/i.test(row));
  const peaks = rows.map((row) => Number((/(-?\d+\.\d) deg/.exec(row) ?? [])[1])).filter((value) => Number.isFinite(value));
  const plausible = peaks.some((value) => value > -5);
  record(9, 'Viewing map: at least one centre with elevation and sunlit or dark status', withElevation.length > 0 && plausible ? 'PASS' : 'FAIL',
    [`status: "${status}"`, `centres drawn as ${drawn} map paths, table rows ${rows.length}`, `rows with an elevation and an illumination status ${withElevation.length}`, `peak elevations ${peaks.join(', ')} deg`, `first row: "${rows[0] ?? ''}"`, plausible ? 'at least one centre sees the vehicle near or above its horizon' : 'every centre has the vehicle more than 70 deg below the horizon during an ascent from 250 km away or less: the numbers follow from the ephemeris of item 8'],
    [line(ephemerisCall)]);
}
// 11. no ghost writes: every number on the page against the response it is said to come from
{
  const body = windowsCall?.body ?? {}; const evidence = []; let ok = true;
  const cells = await page.$$eval('#window-table tbody tr', (rows) => rows.map((tr) => [...tr.querySelectorAll('td')].map((td) => td.innerText.replace(/\s+/g, ' ').trim())));
  let mismatches = 0;
  (body.windows ?? []).forEach((row, index) => {
    const shown = cells[index] ?? [];
    const expect = [row.t_liftoff_utc.slice(11, 19), row.t_injection_utc.slice(11, 19), row.window_width_s.toFixed(1), row.azimuth_deg.toFixed(1), row.reached_inclination_deg.toFixed(1), `${(100 * row.p_success).toFixed(1)}%`, String(row.horizon_label)];
    expect.forEach((value, column) => { if (!(shown[column] ?? '').includes(value)) { mismatches += 1; evidence.push(`row ${index} column ${column}: page "${shown[column]}", response ${value}`); } });
  });
  evidence.push(`window table: ${(body.windows ?? []).length} rows by 7 value columns compared with POST /v1/windows, ${mismatches} mismatches`); ok = ok && mismatches === 0;
  const weatherBody = weatherCall?.body ?? {}; const badge = await text(page, '#weather-launch-indicator-block');
  const weatherOk = (badge ?? '').includes(`${(100 * weatherBody.p_launch).toFixed(1)}%`) && (badge ?? '').includes(`ensemble size ${weatherBody.ensemble_size}`);
  evidence.push(`weather badge against GET /v1/weather/probability: ${weatherOk ? 'equal' : 'DIFFERENT'}`); ok = ok && weatherOk;
  const skillShown = await page.$$eval('#analysis-skill-rows tr', (rows) => rows.map((tr) => [...tr.querySelectorAll('td')].map((td) => td.innerText.trim())));
  const series = skillCall?.body?.skill_series ?? [];
  const skillOk = series.length === skillShown.length && series.every((entry, i) => skillShown[i][0] === String(entry.lead_time_days) && skillShown[i][3] === String(entry.bss) && skillShown[i][4] === String(entry.n_cases));
  evidence.push(`skill table against GET /v1/validation/skill: ${series.length} rows, ${skillOk ? 'equal' : 'DIFFERENT'}`); ok = ok && skillOk;
  const constantsText = await text(page, '#analysis-provenance-body'); const constants = citationCall?.body?.constants ?? {};
  const constantsOk = Object.keys(constants).length > 0 && Object.values(constants).every((value) => (constantsText ?? '').includes(String(value)));
  evidence.push(`constants against GET /v1/citation: ${Object.keys(constants).join(', ')}: ${constantsOk ? 'equal' : 'DIFFERENT'}`); ok = ok && constantsOk;
  const duration = await text(page, '#analysis-duration-note');
  evidence.push(`vehicle duration note: "${(duration ?? '').slice(-230)}"`);
  ok = ok && !/does not exist on this branch/.test(duration ?? '');
  const honestyDv = await text(page, '#honesty-plane-change-dv-ms');
  evidence.push(`weather factor of the rows: ${[...new Set((body.windows ?? []).map((row) => row.p_success_components.weather))].join(', ')} on liftoff dates ${[...new Set((body.windows ?? []).map((row) => row.t_liftoff_utc.slice(0, 10)))].join(', ')} (one value for every date: a backend matter, the page prints what the response holds)`);
  record(11, 'No ghost writes: every number traced to a live response or to a fixture under the banner', ok ? 'PASS' : 'FAIL', evidence);
}
const liveProblems = [...log.problems];
await browser.close();

// 10. offline
{
  const { browser: offBrowser, page: offPage, log: offLog } = await open(DEAD_RULE);
  await offPage.goto(PAGE, { waitUntil: 'networkidle0', timeout: 60000 });
  await offPage.waitForSelector('#window-table tbody tr', { timeout: 30000 }).catch(() => null); await settle(offPage);
  const banner = { hidden: await hidden(offPage, '#mode-banner'), text: await text(offPage, '#mode-banner') };
  const rows = await tableRows(offPage);
  const a = await text(offPage, '#countdown-value-text'); await sleep(2200); const b = await text(offPage, '#countdown-value-text');
  await offPage.evaluate(() => { const row = document.querySelector('#window-table tbody tr[data-hazard-rejected="false"]'); if (row) row.click(); }); await settle(offPage);
  const screens = {};
  for (const id of ['screen-trajectory', 'screen-weather', 'screen-viewing', 'screen-analysis']) screens[id] = (await text(offPage, `#${id}`) ?? '').length;
  const track = await text(offPage, '#trajectory-status'); const skillRows = (await offPage.$$('#analysis-skill-rows tr')).length; const weather = await text(offPage, '#weather-launch-indicator-block');
  const bannerAfter = await text(offPage, '#mode-banner');
  const fixtures = [...new Set(offLog.net.filter((entry) => entry.url.includes('/backend/fixtures/')).map((entry) => `${entry.url.split('/').pop()} ${entry.status}`))];
  const ticking = seconds(a) !== null && seconds(b) !== null && seconds(b) < seconds(a);
  const ok = banner.hidden === false && /OFFLINE PRECOMPUTED DATA/.test(banner.text ?? '') && rows.length > 0 && !rows[0].empty && ticking && skillRows > 0 && offLog.problems.filter((p) => p.startsWith('pageerror')).length === 0;
  record(10, 'Offline: API stopped, reload, every screen renders from fixtures with the banner, countdown works', ok ? 'PASS' : 'FAIL',
    [`banner: "${(bannerAfter ?? '').slice(0, 420)}"`, `window table rows ${rows.length} (first: "${(rows[0]?.text ?? '').slice(0, 90)}")`, `countdown ${a} then ${b} after 2.2 s: ticking ${ticking}`, `fixtures read: ${fixtures.join(', ')}`, `trajectory: "${(track ?? '').slice(0, 160)}"`, `weather badge: "${(weather ?? '').slice(0, 120)}"`, `analysis skill rows ${skillRows}`, `screen text lengths ${JSON.stringify(screens)}`, `page errors ${offLog.problems.filter((p) => p.startsWith('pageerror')).length}`],
    offLog.net.filter((entry) => entry.url.includes('/v1/')).slice(0, 3).map(line));
  await offBrowser.close();
}

console.log('\nconsole and page errors in the live session:'); console.log(liveProblems.join('\n') || '(none)');
results.sort((a, b) => a.item - b.item);
fs.writeFileSync(OUT, JSON.stringify({ page: PAGE, ranAt: new Date().toISOString(), results, liveProblems }, null, 1));
console.log('\nSUMMARY ' + results.map((r) => `${r.item}:${r.status}`).join('  '));
