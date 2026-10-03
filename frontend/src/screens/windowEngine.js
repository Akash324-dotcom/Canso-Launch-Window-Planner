import {
  DEFAULT_RANGE_DAYS,
  DEFAULT_SITE,
  ORBIT_PRESETS,
  SITES,
  VEHICLE_PROFILE_IDS,
  VEHICLE_PROFILE_OWNER,
  WINDOW_TABLE_COLUMNS,
} from '../config.js';
import { el, field, replaceChildren } from '../dom.js';
import {
  constantsOf,
  isHazardRejected,
  planeChangeText,
  rowFlags,
  siteNameOf,
  vehicleTToInjFlag,
  windowRows,
} from '../selectors.js';
import {
  addDays,
  degrees,
  formatAtlantic,
  formatUtc,
  formatUtcShort,
  isoDate,
  percent,
  seconds,
} from '../time.js';

function option(value, label, selected = false) {
  return el('option', { value, text: label, selected });
}

function numberInput(id, attributes) {
  return el('input', { class: 'inp', type: 'number', step: '0.1', id, ...attributes });
}

function buildForm(onInputsChanged) {
  const targetSelect = el(
    'select',
    { class: 'inp', id: 'target-type' },
    ORBIT_PRESETS.map((preset) => option(preset.id, preset.label, preset.id === 'SSO')),
  );
  const inclination = numberInput('inclination-deg', { step: '0.1' });
  const altitude = numberInput('target-altitude-km', { step: '10', placeholder: 'backend default' });
  const planeMode = el(
    'select',
    { class: 'inp', id: 'plane-mode' },
    [option('ltan', 'Local time of the ascending node (LTAN)'), option('raan', 'RAAN in degrees', true)],
  );
  const ltan = el('input', { class: 'inp', type: 'text', id: 'ltan-hours', placeholder: '10:30', maxlength: '5' });
  const raan = numberInput('raan-deg', { step: '1', placeholder: 'any reachable plane' });
  const site = el(
    'select',
    { class: 'inp', id: 'site' },
    SITES.map((entry) => option(entry.id, entry.label, entry.id === DEFAULT_SITE)),
  );
  const today = new Date();
  const dateStart = el('input', { class: 'inp', type: 'date', id: 'date-start', value: isoDate(today) });
  const dateEnd = el('input', {
    class: 'inp',
    type: 'date',
    id: 'date-end',
    value: isoDate(addDays(today, DEFAULT_RANGE_DAYS)),
  });
  const vehicle = el(
    'select',
    { class: 'inp', id: 'vehicle-profile' },
    VEHICLE_PROFILE_IDS.map((id) => option(id, id)),
  );
  const corridorMin = numberInput('corridor-a-min-deg', { step: '0.1', placeholder: 'EA default' });
  const corridorMax = numberInput('corridor-a-max-deg', { step: '0.1', placeholder: 'EA default' });
  const includeWeather = el('input', { type: 'checkbox', id: 'include-weather' });
  includeWeather.checked = true;
  const inputError = el('p', { class: 'input-error', id: 'input-error', role: 'alert', hidden: true });
  const presetNote = el('p', { class: 'hint', id: 'preset-note' });
  const vehicleFlag = el('p', { class: 'hint', id: 'vehicle-flag' });

  const form = el('form', { class: 'inputs', id: 'inputs', novalidate: true }, [
    el('fieldset', { class: 'fs' }, [
      el('legend', { text: 'Target orbit' }),
      el('div', { class: 'grid-2' }, [
        field('Target orbit type', targetSelect),
        field('Inclination (deg)', inclination, 'Preset value for reference. Editing it switches the request to CUSTOM.'),
      ]),
      el('div', { class: 'grid-2' }, [
        field('Target altitude h_t (km)', altitude, 'Required for CUSTOM, otherwise the engine default applies.'),
        field('Target plane set by', planeMode),
      ]),
      el('div', { class: 'grid-2' }, [
        field('Node local time LTAN', ltan, 'Format HH:MM in Atlantic local time.'),
        field('RAAN (deg)', raan, 'Leave empty for any reachable plane.'),
      ]),
      presetNote,
    ]),
    el('fieldset', { class: 'fs' }, [
      el('legend', { text: 'Site and dates' }),
      el('div', { class: 'grid-3' }, [
        field('Site', site),
        field('Range start', dateStart),
        field('Range end', dateEnd),
      ]),
    ]),
    el('fieldset', { class: 'fs' }, [
      el('legend', { text: 'Vehicle and corridor' }),
      el('div', { class: 'grid-2' }, [
        field('Vehicle profile', vehicle),
        field('Include the weather layer', el('label', { class: 'check' }, [includeWeather, ' include_weather'])),
      ]),
      vehicleFlag,
      el('div', { class: 'grid-2' }, [
        field('Corridor override A_min (deg)', corridorMin),
        field('Corridor override A_max (deg)', corridorMax),
      ]),
    ]),
    inputError,
  ]);

  const controls = {
    targetSelect,
    inclination,
    altitude,
    planeMode,
    ltan,
    raan,
    site,
    dateStart,
    dateEnd,
    vehicle,
    includeWeather,
    corridorMin,
    corridorMax,
    inputError,
    presetNote,
    vehicleFlag,
  };

  form.addEventListener('change', (event) => {
    const id = event.target.id;
    if (id === 'target-type') {
      applyPreset(targetSelect.value, controls);
    } else if (id === 'plane-mode') {
      syncPlaneFields(planeMode, ltan, raan);
    } else if (id === 'inclination-deg' || id === 'target-altitude-km') {
      targetSelect.value = 'CUSTOM';
      planeMode.value = 'raan';
      syncPlaneFields(planeMode, ltan, raan);
    }
    onInputsChanged();
  });

  return { form, controls };
}

function syncPlaneFields(planeMode, ltan, raan) {
  ltan.parentElement.hidden = planeMode.value !== 'ltan';
  raan.parentElement.hidden = planeMode.value === 'ltan';
}

function applyPreset(presetId, controls) {
  const preset = ORBIT_PRESETS.find((entry) => entry.id === presetId);
  if (preset === undefined) {
    return;
  }
  if (preset.inclination_deg !== null) {
    controls.inclination.value = String(preset.inclination_deg);
  }
  if (preset.id === 'CUSTOM') {
    controls.altitude.value = '';
  }
  controls.planeMode.value = preset.plane_mode;
  if (preset.ltan_hours !== undefined) {
    controls.ltan.value = preset.ltan_hours;
  }
  syncPlaneFields(controls.planeMode, controls.ltan, controls.raan);
  controls.presetNote.textContent =
    preset.slide_clause === null
      ? 'CUSTOM sends h_t_km and i_t_deg as required by the frozen request schema.'
      : `Slide wording: ${preset.slide_clause}.`;
}

function buildCountdownHost() {
  return el('section', { class: 'panel glass', id: 'countdown-host' });
}

function buildHonestyPanel() {
  return el('section', { class: 'panel glass honesty', id: 'honesty-panel', hidden: true }, [
    el('p', { class: 'eyebrow caution', text: 'Honesty panel, the engine answered rather than failed' }),
    el('h2', { id: 'honesty-headline', text: 'Target not reachable from the site by direct ascent' }),
    el('p', { id: 'honesty-explanation' }),
    el('p', { class: 'readout' }, [
      'Computed plane change: ',
      el('b', { id: 'honesty-plane-change-dv-ms' }),
    ]),
    el('p', { class: 'hint', id: 'honesty-hint' }),
  ]);
}

function buildTable(body) {
  const head = el(
    'thead',
    {},
    el(
      'tr',
      {},
      WINDOW_TABLE_COLUMNS.map((column) => el('th', { scope: 'col', text: column.label })),
    ),
  );
  return el('div', { class: 'table-wrap' }, [
    el('table', { class: 'window-table', id: 'window-table' }, [head, body]),
  ]);
}

function buildProvenance() {
  return el('section', { class: 'panel glass', id: 'constants-footer', hidden: true }, [
    el('p', { class: 'eyebrow', text: 'Constants and provenance of this response' }),
    el('div', { id: 'constants-body' }),
    el('div', { id: 'provenance-body' }),
  ]);
}

function horizonCell(row) {
  const label = row.horizon_label;
  const badge = el('span', {
    class: `badge badge-${String(label).toLowerCase()}`,
    'data-horizon': label,
    text: label,
  });
  const issue =
    row.forecast_issue_time === null || row.forecast_issue_time === undefined
      ? 'no forecast issue time'
      : `issued ${formatUtcShort(row.forecast_issue_time)}`;
  return el('td', {}, [badge, el('span', { class: 'secondary', text: issue })]);
}

function constraintCell(row) {
  const screens = row.screens === null || row.screens === undefined ? {} : row.screens;
  const notes = [];
  if (screens.hazard === 'pass') {
    notes.push('hazard clear');
  } else if (screens.hazard === 'fail') {
    notes.push('hazard fail');
  }
  if (screens.conjunction === 'clear') {
    notes.push('conjunction clear');
  } else if (screens.conjunction === 'flagged') {
    notes.push('conjunction flagged');
  }
  if (screens.notam === 'active') {
    notes.push('NOTAM active');
  }
  const children = [];
  if (typeof row.constraint_fired === 'string') {
    children.push(el('span', { class: 'badge badge-constraint', text: row.constraint_fired }));
  }
  children.push(el('span', { text: notes.join(', ') }));
  return el('td', {}, children);
}

function windowRow(row, index) {
  const rejected = isHazardRejected(row);
  return el(
    'tr',
    {
      'data-liftoff-utc': row.t_liftoff_utc,
      'data-index': String(index),
      'data-hazard-rejected': String(rejected),
      class: rejected ? 'row-rejected' : 'row',
    },
    [
      el('td', {}, [
        el('span', { text: formatUtc(row.t_liftoff_utc) }),
        el('span', { class: 'secondary', text: formatAtlantic(row.t_liftoff_utc) }),
      ]),
      el('td', {}, [
        el('span', { text: formatUtc(row.t_injection_utc) }),
        el('span', { class: 'secondary', text: formatAtlantic(row.t_injection_utc) }),
      ]),
      el('td', { class: 'num', text: seconds(row.window_width_s) }),
      el('td', { class: 'num', text: degrees(row.azimuth_deg) }),
      el('td', { class: 'num', text: degrees(row.reached_inclination_deg) }),
      el('td', { class: 'num', text: percent(row.p_success) }),
      horizonCell(row),
      constraintCell(row),
    ],
  );
}

function emptyRow(message, columnCount = WINDOW_TABLE_COLUMNS.length) {
  return el('tr', { class: 'row-empty' }, [el('td', { colspan: String(columnCount), text: message })]);
}

function renderTable(state, tbody) {
  const response = state.engineResponse;
  const rows = windowRows(response);
  if (response === null) {
    replaceChildren(tbody, emptyRow('No response fetched yet.'));
    return;
  }
  if (rows.length === 0) {
    replaceChildren(tbody, emptyRow('No windows returned for this request.'));
    return;
  }
  replaceChildren(tbody, rows.map((row, index) => windowRow(row, index)));
}

function renderHonesty(state, panel) {
  const response = state.engineResponse;
  if (response === null || response.reachable !== false) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  const site = siteNameOf(response, state.request === null ? DEFAULT_SITE : state.request.site);
  panel.querySelector('#honesty-headline').textContent = `Target not reachable from ${site} by direct ascent`;
  panel.querySelector('#honesty-explanation').textContent =
    'An unreachable target is a domain answer, not a request failure (spec IV.7). The engine priced the plane change a dogleg turn would cost; the window list is empty because no direct ascent satisfies the plane condition.';
  panel.querySelector('#honesty-plane-change-dv-ms').textContent = planeChangeText(response);
  panel.querySelector('#honesty-hint').textContent =
    'Constants used for this verdict are printed below with their sources.';
}

function renderVehicle(state, controls) {
  const response = state.engineResponse;
  const flag = vehicleTToInjFlag(response);
  const vehicleId = controls.vehicle.value;
  const selected = controls.vehicle.selectedOptions[0];
  if (selected !== undefined) {
    selected.textContent = flag === null ? vehicleId : `${vehicleId}: T_to_inj ${flag}`;
  }
  controls.vehicleFlag.textContent =
    flag === null
      ? `T_to_inj and its VERIFIED or ASSUMPTION flag for ${vehicleId} belong to ENGINE at ${VEHICLE_PROFILE_OWNER}. The engine echoes them in provenance_block.row_flags; this response declares none, so no flag is shown.`
      : `T_to_inj flag for ${vehicleId} reported by the engine in provenance_block.row_flags: ${flag}.`;
}

function renderInputError(state, inputError) {
  inputError.hidden = state.inputError === null;
  inputError.textContent = state.inputError === null ? '' : state.inputError;
}

function renderProvenance(state, footer) {
  const response = state.engineResponse;
  const constants = constantsOf(response);
  if (constants === null) {
    footer.hidden = true;
    return;
  }
  footer.hidden = false;
  const entries = [
    ['J2', String(constants.J2)],
    ['GM (m^3/s^2)', String(constants.GM)],
    ['R_e (m)', String(constants.R_e)],
    ['omega_sid_rad_s', String(constants.omega_sid_rad_s)],
    ['gmst_model', String(constants.gmst_model)],
    ['citation_id', String(constants.citation_id)],
  ];
  for (const [name, source] of Object.entries(constants.source ?? {})) {
    entries.push([`source of ${name}`, String(source)]);
  }
  replaceChildren(
    footer.querySelector('#constants-body'),
    el(
      'dl',
      { class: 'definitions' },
      entries.flatMap(([term, value]) => [el('dt', { text: term }), el('dd', { text: value })]),
    ),
  );

  const provenance = response.provenance_block ?? {};
  const flags = rowFlags(response);
  const provenanceEntries = [
    ['site', JSON.stringify(provenance.site ?? {})],
    ['corridor', JSON.stringify(provenance.corridor ?? {})],
    ['criteria_version', String(provenance.criteria_version)],
    ['vehicle_profile_id', String(provenance.vehicle_profile_id)],
    ['row_flags', JSON.stringify(flags)],
    ['source_files', (provenance.source_files ?? []).join(', ')],
    ['engine_version', String(response.engine_version)],
    ['computation_ms', String(response.computation_ms)],
  ];
  replaceChildren(
    footer.querySelector('#provenance-body'),
    el(
      'dl',
      { class: 'definitions' },
      provenanceEntries.flatMap(([term, value]) => [el('dt', { text: term }), el('dd', { text: value })]),
    ),
  );
}

export function createWindowEngineScreen({ root, store, onInputsChanged }) {
  const { form, controls } = buildForm(onInputsChanged);
  const countdownHost = buildCountdownHost();
  const honestyPanel = buildHonestyPanel();
  const tbody = el('tbody', { id: 'window-rows' });
  const footer = buildProvenance();
  const tablePanel = el('section', { class: 'panel glass', id: 'window-table-panel' }, [
    el('div', { class: 'panel-head' }, [
      el('h2', { text: 'Windows' }),
      el('p', { class: 'hint', id: 'window-table-sub' }),
    ]),
    buildTable(tbody),
  ]);
  root.replaceChildren(
    el('header', { class: 'masthead' }, [
      el('h1', { text: 'Canso Launch Windows' }),
      el('p', {
        class: 'hint',
        text: 'Spaceport Nova Scotia. Every number below is rendered from one POST /v1/windows response.',
      }),
    ]),
    form,
    countdownHost,
    honestyPanel,
    tablePanel,
    footer,
  );
  applyPreset('SSO', controls);

  function render(state) {
    renderInputError(state, controls.inputError);
    renderVehicle(state, controls);
    renderHonesty(state, honestyPanel);
    renderTable(state, tbody);
    renderProvenance(state, footer);
    const rows = windowRows(state.engineResponse);
    const usable = rows.filter((row) => !isHazardRejected(row));
    tablePanel.querySelector('#window-table-sub').textContent =
      state.engineResponse === null
        ? ''
        : `${rows.length} windows returned, ${usable.length} not rejected by the hazard screen`;
  }

  function readInputs() {
    return {
      target_type: controls.targetSelect.value,
      i_t_deg: controls.inclination.value,
      h_t_km: controls.altitude.value,
      plane_mode: controls.planeMode.value,
      ltan_hours: controls.ltan.value,
      raan_deg: controls.raan.value,
      site: controls.site.value,
      date_start: controls.dateStart.value,
      date_end: controls.dateEnd.value,
      vehicle_profile_id: controls.vehicle.value,
      corridor_a_min_deg: controls.corridorMin.value,
      corridor_a_max_deg: controls.corridorMax.value,
      include_weather: controls.includeWeather.checked,
    };
  }

  return {
    element: root,
    form,
    countdownHost,
    honestyPanel,
    tbody,
    footer,
    controls,
    render,
    readInputs,
    destroy() {
      root.replaceChildren();
    },
  };
}
