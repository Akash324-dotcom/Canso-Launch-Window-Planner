/** Issue 26, control 6: parameters that re-query the service and visibly change the result. */
import { afterEach, describe, expect, it } from 'vitest';
import { clone, loadExample, textOf } from './helpers.js';
import { STUB, change, displayedRows, settle, start } from './researcherHelpers.js';

const UNREACHABLE = 'windows_response_good_unreachable.json';

afterEach(() => {
  document.body.innerHTML = '';
});

/** A service that answers from the request, the way the live engine does for these parameters. */
function echoing(body) {
  const response = clone(loadExample(body.target.type === 'LEO' ? UNREACHABLE : STUB));
  const tolerance = body.raan_tolerance_deg ?? 1;
  for (const row of response.windows) {
    row.window_width_s = 480 * tolerance;
    row.t_liftoff_utc = `${body.date_range.start}T13:42:11Z`;
    row.t_injection_utc = `${body.date_range.start}T13:47:26Z`;
    if (body.include_weather === false) {
      row.p_success_components.weather = 1.0;
      row.p_success = 1.0;
      row.horizon_label = 'CLIMATOLOGY';
      row.forecast_issue_time = null;
    }
  }
  if (body.corridor !== undefined) {
    response.provenance_block.corridor = { ...response.provenance_block.corridor, ...body.corridor };
  }
  return response;
}

describe('researcher layer, live parameters', () => {
  it('sends the RAAN tolerance and shows the window width the service answered with', async () => {
    const { app, posts } = await start({ windows: echoing });
    expect(posts().at(-1).body.raan_tolerance_deg).toBeUndefined();
    expect(textOf('#raan-tolerance-effect')).toContain('window_width_s of this response: 480.0 s');
    expect(textOf('#raan-tolerance-effect')).toContain('no raan_tolerance_deg was sent');

    change('raan-tolerance-deg', '2');
    await settle();

    expect(posts().at(-1).body.raan_tolerance_deg).toBe(2);
    expect(textOf('#raan-tolerance-effect')).toContain('window_width_s of this response: 960.0 s');
    expect(textOf('#raan-tolerance-effect')).toContain('raan_tolerance_deg 2 was sent');
    expect(displayedRows()[0].textContent).toContain('960.0 s');
    expect(document.querySelector('label[for="raan-tolerance-deg"]').textContent).toContain('governs the window width');
    app.stop();
  });

  it.each(['0', '-1', 'abc'])('refuses the RAAN tolerance %s on the page and posts nothing', async (value) => {
    const { app, posts } = await start({ windows: echoing });
    const before = posts().length;

    change('raan-tolerance-deg', value);
    await settle();

    expect(posts()).toHaveLength(before);
    expect(textOf('#input-error')).toContain('raan_tolerance_deg');
    app.stop();
  });

  it('re-queries when the target class changes and shows the answer for that class', async () => {
    const { app, posts } = await start({ windows: echoing });
    expect(displayedRows().length).toBeGreaterThan(0);

    change('target-type', 'LEO');
    await settle();

    expect(posts().at(-1).body.target.type).toBe('LEO');
    expect(displayedRows()).toHaveLength(0);
    expect(document.getElementById('honesty-panel').hidden).toBe(false);
    expect(textOf('#request-echo')).toContain('"type":"LEO"');
    app.stop();
  });

  it('re-queries when the date range changes and shows the rows of the new range', async () => {
    const { app, posts } = await start({ windows: echoing });

    change('date-start', '2026-11-02');
    await settle();
    change('date-end', '2026-11-09');
    await settle();

    expect(posts().at(-1).body.date_range).toEqual({ start: '2026-11-02', end: '2026-11-09' });
    expect(displayedRows()[0].getAttribute('data-liftoff-utc')).toBe('2026-11-02T13:42:11Z');
    expect(textOf('#request-echo')).toContain('"start":"2026-11-02","end":"2026-11-09"');
    app.stop();
  });

  it('re-queries with the corridor override and surfaces the corridor of the answer with its flags', async () => {
    const stub = loadExample(STUB);
    const { app, posts } = await start({ windows: echoing });
    let flags = textOf('#corridor-flags');
    expect(flags).toContain(`A_min_deg ${stub.provenance_block.corridor.A_min_deg}, A_max_deg ${stub.provenance_block.corridor.A_max_deg}`);
    expect(flags).toContain('corridor_A_min_deg ASSUMPTION');
    expect(flags).toContain('corridor_A_max_deg ASSUMPTION');
    expect(flags).toContain('no override was sent');

    change('corridor-a-min-deg', '120');
    await settle();
    change('corridor-a-max-deg', '150');
    await settle();

    expect(posts().at(-1).body.corridor).toEqual({ A_min_deg: 120, A_max_deg: 150 });
    flags = textOf('#corridor-flags');
    expect(flags).toContain('A_min_deg 120, A_max_deg 150');
    expect(flags).toContain('override sent: A_min_deg 120, A_max_deg 150');
    app.stop();
  });

  it('re-queries when the weather layer is switched off and shows the neutral values of the answer', async () => {
    const { app, posts } = await start({ windows: echoing });
    expect(displayedRows()[0].textContent).toContain('FORECAST');

    change('include-weather', false);
    await settle();

    expect(posts().at(-1).body.include_weather).toBe(false);
    expect(displayedRows()[0].textContent).toContain('CLIMATOLOGY');
    expect(displayedRows()[0].textContent).toContain('100.0%');
    expect(textOf('#window-table-sub')).toContain('The weather layer is excluded from this request');
    app.stop();
  });

  it('explains why the vehicle profile cannot change the result', async () => {
    const { app, posts } = await start({ windows: echoing });

    expect([...document.getElementById('vehicle-profile').options].map((option) => option.value)).toEqual(['cyclone4m']);
    expect(posts().at(-1).body.vehicle_profile_id).toBe('cyclone4m');
    expect(textOf('#vehicle-profile-effect')).toContain('One vehicle profile is offered, cyclone4m');
    expect(textOf('#vehicle-profile-effect')).toContain('cannot change the result');
    expect(textOf('#vehicle-profile-effect')).toContain('no endpoint that lists vehicle profiles');
    app.stop();
  });

  it('echoes the request that produced the visible rows, and says so when the rows are the offline fixture', async () => {
    const { app, posts } = await start({ windows: echoing });

    expect(textOf('#request-echo')).toContain('Request that produced the rows below');
    expect(textOf('#request-echo')).toContain(JSON.stringify(posts().at(-1).body));
    expect(document.getElementById('request-echo').getAttribute('data-origin')).toBe('api');
    app.stop();
  });
});
