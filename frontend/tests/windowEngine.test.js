import { afterEach, describe, expect, it } from 'vitest';
import { ORBIT_PRESETS } from '../src/config.js';
import {
  boot,
  flush,
  installWindowsApi,
  jsonResponse,
  loadExample,
  textOf,
  windowsPosts,
  withRowFlags,
} from './helpers.js';

const STUB = 'windows_response_good_stub.json';

afterEach(() => {
  document.body.innerHTML = '';
});

async function startWith(payload = loadExample(STUB)) {
  const fetchMock = installWindowsApi(() => jsonResponse(payload));
  const { app } = boot();
  app.start();
  await flush();
  return { app, fetchMock };
}

function lastRequestBody(fetchMock) {
  return JSON.parse(windowsPosts(fetchMock).at(-1)[1].body);
}

function change(id) {
  const node = document.getElementById(id);
  node.dispatchEvent(new Event('change', { bubbles: true }));
  return node;
}

describe('F2 screen 1 inputs', () => {
  it('offers the slide orbit classes and pre-fills their inclinations', async () => {
    const { app } = await startWith();
    const select = document.getElementById('target-type');

    expect([...select.options].map((option) => option.value)).toEqual([
      'LEO',
      'POLAR',
      'SSO',
      'CUSTOM',
    ]);
    expect(ORBIT_PRESETS.find((p) => p.id === 'LEO').inclination_deg).toBe(45.1);
    expect(ORBIT_PRESETS.find((p) => p.id === 'POLAR').inclination_deg).toBe(87.9);
    expect(ORBIT_PRESETS.find((p) => p.id === 'SSO').inclination_deg).toBe(98.1);

    select.value = 'SSO';
    change('target-type');
    expect(document.getElementById('inclination-deg').value).toBe('98.1');
    expect(document.getElementById('plane-mode').value).toBe('ltan');
    expect(document.getElementById('ltan-hours').value).toBe('10:30');

    select.value = 'LEO';
    change('target-type');
    expect(document.getElementById('inclination-deg').value).toBe('45.1');
    expect(document.getElementById('plane-mode').value).toBe('raan');
    expect(document.getElementById('raan-deg').hidden).toBe(false);

    select.value = 'POLAR';
    change('target-type');
    expect(document.getElementById('inclination-deg').value).toBe('87.9');

    app.stop();
  });

  it('sends the target type for a preset and the explicit inclination once CUSTOM is chosen', async () => {
    const { app, fetchMock } = await startWith();

    expect(lastRequestBody(fetchMock).target).toEqual({ type: 'SSO', ltan_hours: '10:30' });

    const inclination = document.getElementById('inclination-deg');
    inclination.value = '82.5';
    change('inclination-deg');
    await flush();

    expect(document.getElementById('target-type').value).toBe('CUSTOM');
    expect(document.getElementById('plane-mode').value).toBe('raan');
    expect(textOf('#input-error')).toContain('h_t_km');

    document.getElementById('target-altitude-km').value = '700';
    change('target-altitude-km');
    await flush();

    expect(lastRequestBody(fetchMock).target).toEqual({
      type: 'CUSTOM',
      h_t_km: 700,
      i_t_deg: 82.5,
      raan_deg: null,
    });

    app.stop();
  });

  it('refuses to post an incomplete CUSTOM target and shows the reason', async () => {
    const { app, fetchMock } = await startWith();
    const callsBefore = windowsPosts(fetchMock).length;

    document.getElementById('target-type').value = 'CUSTOM';
    change('target-type');
    await flush();

    expect(windowsPosts(fetchMock)).toHaveLength(callsBefore);
    expect(textOf('#input-error')).toContain('h_t');
    expect(document.getElementById('input-error').hidden).toBe(false);

    app.stop();
  });

  it('sends the corridor override only when both bounds are given', async () => {
    const { app, fetchMock } = await startWith();
    expect(lastRequestBody(fetchMock).corridor).toBeUndefined();

    document.getElementById('corridor-a-min-deg').value = '100';
    change('corridor-a-min-deg');
    await flush();
    expect(lastRequestBody(fetchMock).corridor).toEqual({ A_min_deg: 100 });

    document.getElementById('corridor-a-max-deg').value = '140';
    change('corridor-a-max-deg');
    await flush();
    expect(lastRequestBody(fetchMock).corridor).toEqual({ A_min_deg: 100, A_max_deg: 140 });

    app.stop();
  });

  it('defaults the site to canso and the date range to the requested span', async () => {
    const { app, fetchMock } = await startWith();
    const body = lastRequestBody(fetchMock);

    expect(body.site).toBe('canso');
    expect(document.getElementById('site').value).toBe('canso');
    expect(body.date_range.start).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(body.date_range.end > body.date_range.start).toBe(true);

    app.stop();
  });
});

describe('F2 vehicle profile and table contract', () => {
  it('reports the T_to_inj flag from the response and names the owner when it is absent', async () => {
    const withoutFlag = await startWith();
    expect(textOf('#vehicle-flag')).toContain('backend/engine/data/vehicles/cyclone4m.json');
    expect(document.getElementById('vehicle-profile').selectedOptions[0].textContent).toContain(
      'cyclone4m',
    );
    withoutFlag.app.stop();

    const withFlag = await startWith(
      withRowFlags(loadExample(STUB), { T_to_inj_s: 'ASSUMPTION' }),
    );
    expect(textOf('#vehicle-flag')).toContain('ASSUMPTION');
    expect(document.getElementById('vehicle-profile').selectedOptions[0].textContent).toContain(
      'T_to_inj ASSUMPTION',
    );
    withFlag.app.stop();
  });

  it('renders the spec V.1 columns and the contract field values', async () => {
    const { app } = await startWith();
    const response = loadExample(STUB);
    const row = response.windows[0];

    expect([...document.querySelectorAll('#window-table thead th')].map((th) => th.textContent.trim()))
      .toEqual([
        't_liftoff_utc',
        't_injection_utc',
        'window_width_s',
        'azimuth_deg',
        'reached_inclination_deg',
        'p_success',
        'horizon_label',
        'constraint status',
      ]);

    const tr = document.querySelector('#window-rows tr[data-liftoff-utc]');
    expect(tr.getAttribute('data-liftoff-utc')).toBe(row.t_liftoff_utc);
    const cells = [...tr.querySelectorAll('td')].map((td) => td.textContent.replace(/\s+/g, ' ').trim());
    expect(cells[0]).toContain('2026-10-05 13:42:11Z');
    expect(cells[0]).toContain('10:42 ADT, Oct 5');
    expect(cells[1]).toContain('2026-10-05 13:47:26Z');
    expect(cells[2]).toBe('620.0 s');
    expect(cells[3]).toBe('118.4');
    expect(cells[4]).toBe('98.1');
    expect(cells[5]).toBe('62.0%');
    expect(cells[6]).toContain('FORECAST');
    expect(cells[6]).toContain('issued 2026-10-03 09:00Z');
    expect(cells[7]).toBe('hazard clear, conjunction clear');

    app.stop();
  });

  it('names every window table column of the frozen response schema that screen 1 shows', async () => {
    const { app } = await startWith();
    const headers = [...document.querySelectorAll('#window-table thead th')].map((th) =>
      th.textContent.trim(),
    );
    expect(headers).toContain('window_width_s');
    expect(headers).toContain('azimuth_deg');
    expect(headers).toContain('reached_inclination_deg');
    expect(headers).toContain('p_success');
    expect(headers).toContain('horizon_label');
    app.stop();
  });
});
