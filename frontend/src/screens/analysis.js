import { FIXTURES, T_TO_INJ_FLAG_PATTERN } from '../config.js';
import { el, replaceChildren } from '../dom.js';
import { downloadText, jsonDescriptor, reliabilityCsv, renderedTableCsv, skillSeriesCsv } from '../export.js';
import { constantsOf, rowFlags, siteNameOf } from '../selectors.js';
import { renderReliabilityDiagram, renderSkillCurve } from '../svgChart.js';
import { percent } from '../time.js';

/**
 * Screen 5 of spec V.6, the view a researcher reads instead of a colour: the Brier
 * skill table and chart, the reliability diagram, the ROC points, the constants block
 * with its sources, the criteria version, the config hash and the provenance table,
 * plus the downloads. Every number is read from the same response objects the other
 * screens read, so nothing here is computed in the browser.
 */

const CONSTANT_ROWS = [
  ['J2', 'the second zonal harmonic'],
  ['GM', 'the Earth gravitational parameter in m^3/s^2'],
  ['R_e', 'the Earth equatorial radius in m'],
  ['omega_sid_rad_s', 'the sidereal rotation rate in rad/s'],
  ['gmst_model', 'the sidereal time model'],
  ['citation_id', 'the config hash and run identifier of this response'],
];

const SKILL_HEADERS = ['lead_time_days', 'bs', 'bs_ref', 'bss', 'n_cases'];
const RELIABILITY_HEADERS = ['p_center', 'observed_freq', 'n'];
const ROC_HEADERS = ['threshold', 'pod', 'far'];
const DURATION_HEADERS = [
  't_liftoff_utc',
  't_injection_utc',
  'window_center_shift_s',
  'liftoff_instant_error_min',
  'ascent_s',
];

/**
 * The Vehicle Duration of the slide, read row by row: the ascent is the interval from
 * the liftoff instant to the injection instant, the window centre shift is the fixed
 * point term of spec II.18 and the liftoff instant error is term 2 of spec II.5. The
 * window table shows the two instants; this table shows the numbers behind them.
 */
function durationRows(response) {
  const rows = Array.isArray(response?.windows) ? response.windows : [];
  return rows.map((row) => ({
    t_liftoff_utc: row.t_liftoff_utc,
    t_injection_utc: row.t_injection_utc,
    window_center_shift_s: row.window_center_shift_s,
    liftoff_instant_error_min: row.liftoff_instant_error_min,
    ascent_s: ((Date.parse(row.t_injection_utc) - Date.parse(row.t_liftoff_utc)) / 1000).toFixed(1),
  }));
}

function tableBlock(headers) {
  const body = el('tbody', {});
  return {
    body,
    element: el('div', { class: 'table-wrap' }, [
      el('table', { class: 'window-table' }, [
        el('thead', {}, el('tr', {}, headers.map((header) => el('th', { scope: 'col', text: header })))),
        body,
      ]),
    ]),
  };
}

function fillTable(body, headers, rows, rowAttributes, emptyMessage) {
  replaceChildren(
    body,
    rows.length === 0
      ? [el('tr', {}, [el('td', { colspan: String(headers.length), text: emptyMessage })])]
      : rows.map((row) =>
          el(
            'tr',
            rowAttributes(row),
            headers.map((header) => el('td', { class: 'num', 'data-field': header, text: String(row[header]) })),
          ),
        ),
  );
}

function definitionList(entries) {
  return el(
    'dl',
    { class: 'definitions' },
    entries.flatMap(([term, value]) => [el('dt', { text: term }), el('dd', { text: value })]),
  );
}

export function createAnalysisScreen({ root, store, table = () => document.querySelector('#window-table') }) {
  const sub = el('p', { class: 'hint', id: 'analysis-sub' });
  const claims = el('p', { class: 'hint', id: 'analysis-claims' });
  const downloadNote = el('p', { class: 'hint', id: 'analysis-download-note' });
  const skillNote = el('p', { class: 'hint', id: 'analysis-skill-note' });
  const reliabilityNote = el('p', { class: 'hint', id: 'analysis-reliability-note' });
  const durationNote = el('p', { class: 'hint', id: 'analysis-duration-note' });
  const provenanceHost = el('div', { id: 'analysis-provenance-body' });
  const sourceFileList = el('ol', { class: 'source-files', id: 'analysis-source-files' });
  const criteriaLine = el('p', { class: 'hint', id: 'analysis-criteria-version' });
  const configHashLine = el('p', { class: 'hint', id: 'analysis-config-hash' });
  const skillHost = el('div', { class: 'chart-host', id: 'analysis-skill-curve-host' });
  const reliabilityHost = el('div', { class: 'chart-host', id: 'analysis-reliability-host' });
  const fixtureLinks = el('ul', { class: 'chip-list', id: 'analysis-fixture-links' });

  const skillTable = tableBlock(SKILL_HEADERS);
  skillTable.body.id = 'analysis-skill-rows';
  const reliabilityTable = tableBlock(RELIABILITY_HEADERS);
  reliabilityTable.body.id = 'analysis-reliability-rows';
  const rocTable = tableBlock(ROC_HEADERS);
  rocTable.body.id = 'analysis-roc-rows';
  const durationTable = tableBlock(DURATION_HEADERS);
  durationTable.body.id = 'analysis-duration-rows';

  const buttons = [
    { id: 'download-window-csv', label: 'Download the window table as CSV' },
    { id: 'download-skill-csv', label: 'Download the Brier skill series as CSV' },
    { id: 'download-reliability-csv', label: 'Download the reliability bins as CSV' },
    { id: 'download-response-json', label: 'Download the full JSON response' },
  ].map((definition) => el('button', { class: 'btn', type: 'button', id: definition.id, text: definition.label }));

  const provenancePanel = el('section', { class: 'panel', id: 'analysis-provenance' }, [
    el('p', { class: 'eyebrow', text: 'Constants, criteria version, config hash and provenance' }),
    criteriaLine,
    configHashLine,
    provenanceHost,
    el('h3', { text: 'Source files the run declared' }),
    sourceFileList,
  ]);
  const skillPanel = el('section', { class: 'panel', id: 'analysis-skill' }, [
    el('p', { class: 'eyebrow', text: 'Brier skill series against lead time' }),
    skillNote,
    skillTable.element,
    skillHost,
  ]);
  const reliabilityPanel = el('section', { class: 'panel', id: 'analysis-reliability' }, [
    el('p', { class: 'eyebrow', text: 'Reliability diagram and ROC points' }),
    reliabilityNote,
    reliabilityHost,
    el('h3', { text: 'Reliability bins' }),
    reliabilityTable.element,
    el('h3', { text: 'ROC points' }),
    rocTable.element,
  ]);
  const durationPanel = el('section', { class: 'panel', id: 'analysis-duration' }, [
    el('p', { class: 'eyebrow', text: 'Vehicle duration of every window row' }),
    durationNote,
    durationTable.element,
  ]);
  const downloadPanel = el('section', { class: 'panel', id: 'analysis-downloads' }, [
    el('p', { class: 'eyebrow', text: 'Downloadable results' }),
    el('div', { class: 'button-row' }, buttons),
    downloadNote,
    el('h3', { text: 'Offline fixture files of this run' }),
    fixtureLinks,
  ]);

  root.replaceChildren(
    el('header', { class: 'panel-head' }, [el('h2', { text: 'Screen 5, scientific analysis' }), sub]),
    claims,
    provenancePanel,
    durationPanel,
    skillPanel,
    reliabilityPanel,
    downloadPanel,
  );

  function runIdOf(state) {
    return constantsOf(state.engineResponse)?.citation_id ?? constantsOf(state.skillResponse)?.citation_id ?? null;
  }

  const produced = [];

  function renderProvenance(state) {
    const response = state.engineResponse;
    const constants = constantsOf(response);
    if (constants === null) {
      criteriaLine.textContent = 'No window response loaded, so no criteria version and no config hash yet.';
      configHashLine.textContent = '';
      provenanceHost.removeAttribute('data-criteria-version');
      provenanceHost.removeAttribute('data-citation-id');
      replaceChildren(provenanceHost, [
        el('p', { class: 'chart-empty', id: 'analysis-provenance-empty', text: 'No response fetched yet.' }),
      ]);
      replaceChildren(sourceFileList, [
        el('li', { class: 'vertex-empty', text: 'No source files declared by a run yet.' }),
      ]);
      return;
    }
    const provenance = response.provenance_block ?? {};
    const skill = state.skillResponse;
    // The constants of a live run are read from GET /v1/citation, the record the service
    // stored for the run, which also holds the config hash. When that record is not available
    // the constants_block echoed by POST /v1/windows is shown and the line below says so.
    const citation = state.citationOrigin === 'api' ? state.citationResponse : null;
    const values = citation === null ? constants : { ...(citation.constants ?? {}), citation_id: citation.citation_id };
    const sources = citation === null ? (constants.source ?? {}) : (citation.constants_sources ?? {});
    provenanceHost.setAttribute('data-constants-origin', citation === null ? 'windows_response' : 'citation');
    const entries = CONSTANT_ROWS.map(([key, description]) => [
      `${key}, ${description}`,
      values[key] === undefined ? 'absent from this response' : String(values[key]),
    ]).concat(
      Object.entries(sources).map(([key, value]) => [`source of ${key}`, String(value)]),
      [
        ['site', JSON.stringify(provenance.site ?? {})],
        ['corridor', JSON.stringify(provenance.corridor ?? {})],
        ['row_flags', JSON.stringify(rowFlags(response))],
        ['vehicle_profile_id', String(provenance.vehicle_profile_id)],
        ['engine_version', String(response.engine_version)],
        ['computation_ms', String(response.computation_ms)],
        ['criteria_version', String(provenance.criteria_version)],
        ['base_rate', skill === null ? 'absent, no skill response loaded' : percent(Number(skill.base_rate))],
        [
          'verification_source',
          skill === null ? 'absent, no skill response loaded' : String(skill.verification_source),
        ],
        [
          'reference_forecast',
          skill === null ? 'absent, no skill response loaded' : String(skill.reference_forecast),
        ],
      ],
    );
    replaceChildren(provenanceHost, [definitionList(entries)]);
    provenanceHost.setAttribute('data-site', siteNameOf(response, 'canso'));
    provenanceHost.setAttribute('data-criteria-version', String(provenance.criteria_version));
    provenanceHost.setAttribute('data-citation-id', String(constants.citation_id));

    criteriaLine.textContent =
      `Criteria version ${provenance.criteria_version}, vehicle profile ${provenance.vehicle_profile_id}. ` +
      'The criteria version is WEATHER data at backend/weather/data/criteria_v1.json and is echoed here so that a ' +
      'probability is always read together with the criteria that produced it.';
    const runLine = `Run identifier constants_block.citation_id ${constants.citation_id}, gmst model ${constants.gmst_model}.`;
    if (citation !== null) {
      configHashLine.textContent =
        `${runLine} Config hash ${citation.config_hash}, read from GET /v1/citation?id=${citation.citation_id}; ` +
        'the constants and their sources below are those of that record.';
    } else if (state.engineResponseOrigin === 'fixture') {
      configHashLine.textContent =
        `${runLine} This run is the offline fixture ${FIXTURES.windows}. GET /v1/citation is not asked in offline ` +
        'mode: no running service stored this run, so no config hash is shown and the constants below are the ' +
        'constants_block of the fixture.';
    } else if (state.citationError !== null && state.citationError !== undefined) {
      configHashLine.textContent =
        `${runLine} GET /v1/citation did not answer for this run (${state.citationError}), so no config hash is shown ` +
        'and the constants below are the constants_block echoed by POST /v1/windows.';
    } else {
      configHashLine.textContent =
        `${runLine} GET /v1/citation has not answered for this run yet; the constants below are the constants_block ` +
        'echoed by POST /v1/windows.';
    }
    const sourceFiles = Array.isArray(provenance.source_files) ? provenance.source_files : [];
    replaceChildren(
      sourceFileList,
      sourceFiles.length === 0
        ? [el('li', { class: 'vertex-empty', text: 'This response declares no source_files array.' })]
        : sourceFiles.map((file) => el('li', { 'data-source-file': file }, [el('span', { text: file })])),
    );
  }

  /**
   * T_to_inj and its flag are ENGINE data. The window response does not carry them; the
   * citation record of the run lists every vehicle row with its flag and source.
   */
  function tToInjText(state) {
    const citation = state.citationOrigin === 'api' ? state.citationResponse : null;
    const rows = citation !== null && Array.isArray(citation.vehicle_rows) ? citation.vehicle_rows : [];
    const row = rows.find((entry) => T_TO_INJ_FLAG_PATTERN.test(String(entry.key))) ?? null;
    if (row !== null) {
      return (
        `${row.key} is flagged ${row.flag}, source: ${row.source} ` +
        `(vehicle_rows of GET /v1/citation for vehicle profile ${citation.vehicle_profile_id}).`
      );
    }
    if (citation !== null) {
      return 'The citation record of this run lists no T_to_inj vehicle row, so no flag is shown here.';
    }
    return (
      'T_to_inj and its VERIFIED or ASSUMPTION flag are ENGINE data, listed under vehicle_rows of GET /v1/citation; ' +
      'no citation record is available for this run, so no flag is shown here.'
    );
  }

  function renderDuration(state) {
    const response = state.engineResponse;
    const rows = response === null || response === undefined ? [] : durationRows(response);
    fillTable(durationTable.body, DURATION_HEADERS, rows, (row) => ({
      'data-liftoff-utc': row.t_liftoff_utc,
    }), 'No window response loaded, so no vehicle duration to show.');
    const ascents = rows.map((row) => Number(row.ascent_s));
    durationNote.textContent =
      rows.length === 0
        ? 'The ascent interval comes from t_injection_utc minus t_liftoff_utc of the loaded response.'
        : `The window accounts for the time the vehicle needs to reach the injection point, not only the liftoff ` +
          `moment: ${rows.length} rows, ascent ${Math.min(...ascents).toFixed(1)} to ${Math.max(...ascents).toFixed(1)} s, ` +
          `window centre shift ${rows[0].window_center_shift_s} s, liftoff instant error ` +
          `${rows[0].liftoff_instant_error_min} min on the first row. ${tToInjText(state)}`;
  }

  function skillSourceText(state) {
    const asked = state.skillRequest;
    const query =
      asked === null || asked === undefined
        ? 'GET /v1/validation/skill'
        : `GET /v1/validation/skill?period_start=${asked.period_start}&period_end=${asked.period_end}`;
    if (state.skillOrigin === 'api') {
      return `Source: ${query}, a live response.`;
    }
    if (state.skillOrigin === 'fixture') {
      return `Source: the offline fixture ${FIXTURES.skill}, because ${query} failed (${state.skillError}).`;
    }
    return '';
  }

  function renderSkill(state) {
    const response = state.skillResponse;
    if (response === null || response === undefined) {
      fillTable(skillTable.body, SKILL_HEADERS, [], () => ({}), 'No skill series in this response.');
      replaceChildren(skillHost, [
        el('p', { class: 'chart-empty', id: 'analysis-skill-empty', text: 'No skill series fetched.' }),
      ]);
      skillNote.textContent =
        'The skill series comes from GET /v1/validation/skill and falls back to the offline skill fixture.';
      return;
    }
    const series = Array.isArray(response.skill_series) ? response.skill_series : [];
    fillTable(skillTable.body, SKILL_HEADERS, series, (entry) => ({
      'data-lead-time-days': String(entry.lead_time_days),
    }), 'No skill series in this response.');
    const { element, geometry } = renderSkillCurve(response);
    element.setAttribute('id', 'analysis-skill-curve');
    replaceChildren(skillHost, [element]);
    const period = response.period ?? {};
    skillNote.textContent =
      `Hindcast ${period.start} to ${period.end}, verification ${response.verification_source}, reference ` +
      `${response.reference_forecast}, base rate ${percent(Number(response.base_rate))}, measured skill horizon ` +
      `${response.skill_horizon_measured_days === null ? 'null in this response' : `${response.skill_horizon_measured_days} days`}, ` +
      `${geometry.points.length} lead times. ${skillSourceText(state)}`;
  }

  function renderReliability(state) {
    const response = state.skillResponse;
    if (response === null || response === undefined) {
      fillTable(reliabilityTable.body, RELIABILITY_HEADERS, [], () => ({}), 'No reliability bins in this response.');
      fillTable(rocTable.body, ROC_HEADERS, [], () => ({}), 'No ROC points in this response.');
      replaceChildren(reliabilityHost, [
        el('p', { class: 'chart-empty', id: 'analysis-reliability-empty', text: 'No reliability bins fetched.' }),
      ]);
      reliabilityNote.textContent = 'The reliability diagram comes from GET /v1/validation/skill.';
      return;
    }
    const bins = Array.isArray(response.reliability_bins) ? response.reliability_bins : [];
    const roc = Array.isArray(response.roc_points) ? response.roc_points : [];
    fillTable(reliabilityTable.body, RELIABILITY_HEADERS, bins, (bin) => ({
      'data-p-center': String(bin.p_center),
    }), 'No reliability bins in this response.');
    fillTable(rocTable.body, ROC_HEADERS, roc, (point) => ({
      'data-threshold': String(point.threshold),
    }), 'No ROC points in this response.');
    const { element, points } = renderReliabilityDiagram(response);
    element.setAttribute('id', 'analysis-reliability-diagram');
    replaceChildren(reliabilityHost, [element]);
    reliabilityNote.textContent =
      `Observed frequency against forecast probability for ${points.length} bins, with the perfect reliability ` +
      `diagonal and the climatological base rate ${response.base_rate} marked on the horizontal axis. ` +
      `The ${roc.length} ROC points are the hit rate pod against the false alarm rate far of the same verification.`;
  }

  replaceChildren(
    fixtureLinks,
    Object.entries(FIXTURES).map(([name, file]) =>
      el('li', { class: 'chip', 'data-fixture-name': name }, [
        el('a', { href: `../backend/fixtures/${file}`, 'data-fixture-file': file, text: file }),
      ]),
    ),
  );

  function reportDownload(result) {
    if (result === null) {
      return result;
    }
    produced.push(result);
    downloadNote.textContent = produced
      .map((entry) => `${entry.filename}, ${entry.size} characters, ${entry.mimeType}`)
      .join('; then ');
    return result;
  }

  function windowTableCsvResult() {
    const node = table();
    if (node === null) {
      downloadNote.textContent = 'The window table is not rendered, so there is no CSV to download.';
      return null;
    }
    const filename = `canso-windows-${runIdOf(store.getState()) ?? 'no-run-id'}.csv`;
    return reportDownload(downloadText({ filename, mimeType: 'text/csv', text: renderedTableCsv(node) }));
  }

  function textDownload(kind) {
    const state = store.getState();
    const text = kind === 'skill' ? skillSeriesCsv(state.skillResponse) : reliabilityCsv(state.skillResponse);
    const filename = `canso-${kind}-${runIdOf(state) ?? 'no-run-id'}.csv`;
    return reportDownload(downloadText({ filename, mimeType: 'text/csv', text }));
  }

  function jsonResult() {
    const state = store.getState();
    const response = state.engineResponse ?? state.skillResponse;
    if (response === null || response === undefined) {
      downloadNote.textContent = 'No response is loaded, so there is no JSON to download.';
      return null;
    }
    const filename = `canso-response-${runIdOf(state) ?? 'no-run-id'}.json`;
    return reportDownload(downloadText(jsonDescriptor(filename, response)));
  }

  const handlers = {
    'download-window-csv': windowTableCsvResult,
    'download-skill-csv': () => textDownload('skill'),
    'download-reliability-csv': () => textDownload('reliability'),
    'download-response-json': jsonResult,
  };

  for (const button of buttons) {
    button.addEventListener('click', () => {
      handlers[button.id]();
    });
  }

  function render(state) {
    sub.textContent =
      state.engineResponse === null && state.skillResponse === null
        ? 'Nothing loaded yet. This view renders the same response objects as Screens 1 to 4.'
        : 'Every number below is read from the loaded POST /v1/windows and GET /v1/validation/skill responses.';
    claims.textContent =
      'Claim status, spec II.9: the injection-consistent fixed point and the reachability predicate are PROVED; the ' +
      'chance-constrained window and the decision layer are SKETCHED; positive Brier skill, the skill horizon and the ' +
      'proxy-criteria consistency are CONJECTURE, and the series below is the hindcast measurement of the first of those.';
    renderProvenance(state);
    renderDuration(state);
    renderSkill(state);
    renderReliability(state);
  }

  return {
    element: root,
    buttons,
    render,
    download: (id) => handlers[id](),
    destroy() {
      root.replaceChildren();
    },
  };
}