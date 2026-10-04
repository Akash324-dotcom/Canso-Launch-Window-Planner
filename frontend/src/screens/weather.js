import { WEATHER_BAND_LABELS, WEATHER_THRESHOLDS } from '../config.js';
import { el, replaceChildren } from '../dom.js';
import { flagCounts } from '../researcher.js';
import { renderSkillCurve } from '../svgChart.js';
import { formatIssueTime, percent } from '../time.js';
import { thresholdsText, weatherBand } from '../weatherBands.js';

function indicatorBlock(id, title, probability, extra) {
  const band = weatherBand(probability);
  return {
    band,
    element: el('div', { class: 'indicator', id, 'data-band': band.band }, [
      el('p', { class: 'eyebrow', text: title }),
      el('p', { class: 'indicator-row' }, [
        el('span', { class: `swatch swatch-${band.band.toLowerCase()}`, 'aria-hidden': 'true' }),
        el('span', { class: 'indicator-band', 'data-band': band.band, text: band.band }),
        el('span', {
          class: 'indicator-probability',
          'data-probability': probability === null || probability === undefined ? '' : String(probability),
          text: band.label,
        }),
        el('span', {
          class: 'indicator-value',
          'data-value': probability === null || probability === undefined ? '' : String(probability),
          text:
            probability === null || probability === undefined
              ? 'no probability in the response'
              : percent(Number(probability)),
        }),
      ]),
      extra,
    ]),
  };
}

function horizonBadge(label, issueTime, id) {
  const text = label === null || label === undefined ? 'no horizon label' : String(label);
  const style = label === 'FORECAST' ? 'forecast' : label === 'CLIMATOLOGY' ? 'climatology' : 'unknown';
  return el('span', { class: 'badge-row' }, [
    el('span', {
      class: `badge badge-${style}`,
      id,
      'data-horizon': text,
      'data-horizon-style': style,
      text,
    }),
    el('span', { class: 'secondary issue-time', text: formatIssueTime(issueTime) }),
  ]);
}

function criteriaList(components) {
  const rows = Array.isArray(components) ? components : [];
  const body = el(
    'tbody',
    { id: 'weather-criteria-rows' },
    rows.length === 0
      ? [el('tr', {}, [el('td', { colspan: '3', text: 'The weather response carries no per-criterion breakdown.' })])]
      : rows.map((component) =>
          el('tr', { 'data-criterion-id': String(component.criterion_id) }, [
            el('td', { text: String(component.criterion_id) }),
            el('td', { class: 'num', 'data-p-violation': String(component.p_violation), text: percent(Number(component.p_violation)) }),
            el('td', {}, [
              el('span', {
                class: `badge badge-${String(component.flag).toLowerCase()}`,
                'data-flag': String(component.flag),
                text: String(component.flag),
              }),
            ]),
          ]),
        ),
  );
  return el('details', { class: 'criteria', id: 'weather-criteria' }, [
    el('summary', { text: `Per-criterion breakdown, ${rows.length} criteria, each with its VERIFIED or PROXY flag` }),
    el('div', { class: 'table-wrap' }, [
      el('table', { class: 'window-table' }, [
        el('thead', {}, el('tr', {}, [
          el('th', { scope: 'col', text: 'criterion_id' }),
          el('th', { scope: 'col', text: 'p_violation' }),
          el('th', { scope: 'col', text: 'flag' }),
        ])),
        body,
      ]),
    ]),
  ]);
}

export function createWeatherScreen({ root, store, thresholds = WEATHER_THRESHOLDS }) {
  const sub = el('p', { class: 'hint', id: 'weather-sub' });
  const rowIndicatorHost = el('div', { id: 'weather-row-indicator' });
  const launchIndicatorHost = el('div', { id: 'weather-launch-indicator' });
  const thresholdsNote = el('p', { class: 'hint', id: 'weather-thresholds' });
  const criteriaHost = el('div', { id: 'weather-criteria-host' });
  const rowUncertainty = el('p', { class: 'hint', id: 'weather-row-uncertainty' });
  const criteriaSummary = el('p', { class: 'hint', id: 'weather-criteria-summary' });
  const criteriaUncertainty = el('p', { class: 'hint', id: 'weather-criteria-uncertainty' });
  const versionSelect = el('select', { class: 'inp', id: 'criteria-version-select', disabled: true }, [
    el('option', { value: '', text: 'no weather answer loaded' }),
  ]);
  const versionNote = el('p', { class: 'hint', id: 'criteria-version-note' });
  const versionControl = el('div', { class: 'field', id: 'criteria-version-control' }, [
    el('label', { for: 'criteria-version-select', text: 'Criteria version' }),
    versionSelect,
    versionNote,
  ]);
  const skillHost = el('div', { class: 'chart-host', id: 'weather-skill-curve-host' });
  const skillNote = el('p', { class: 'hint', id: 'weather-skill-note' });
  const honesty = el('p', { class: 'hint', id: 'weather-honesty' });

  root.replaceChildren(
    el('header', { class: 'panel-head' }, [
      el('h2', { text: 'Screen 3, weather panel with its evidence' }),
      sub,
    ]),
    thresholdsNote,
    rowIndicatorHost,
    rowUncertainty,
    launchIndicatorHost,
    criteriaSummary,
    criteriaHost,
    criteriaUncertainty,
    versionControl,
    el('h3', { text: 'Hindcast skill behind the label' }),
    skillHost,
    skillNote,
    honesty,
  );

  function selectedRow(state) {
    const rows = state.engineResponse === null ? [] : state.engineResponse.windows ?? [];
    const index = state.selectedRowIndex;
    if (!Number.isInteger(index) || index < 0 || index >= rows.length) {
      return null;
    }
    return rows[index];
  }

  function renderRowIndicator(state, row) {
    if (row === null) {
      sub.textContent = 'Select a window row in the table to read the weather for its date.';
      const block = indicatorBlock(
        'weather-row-indicator-block',
        'p_success_components.weather of the selected row',
        null,
        null,
      );
      replaceChildren(rowIndicatorHost, [block.element]);
      return;
    }
    const component = row.p_success_components?.weather ?? null;
    const block = indicatorBlock(
      'weather-row-indicator-block',
      'p_success_components.weather of the selected row',
      component,
      horizonBadge(row.horizon_label, row.forecast_issue_time, 'weather-row-horizon-badge'),
    );
    replaceChildren(rowIndicatorHost, [block.element]);
    sub.textContent =
      `Selected row liftoff ${row.t_liftoff_utc}, weather component ${component === null ? 'absent' : component} ` +
      `inside p_success ${row.p_success}.`;
  }

  function renderLaunchIndicator(state, row) {
    const response = state.weatherResponse;
    if (response === null || response === undefined) {
      const reason =
        state.weatherError === null
          ? 'no probability fetched for this date'
          : `GET /v1/weather/probability failed: ${state.weatherError}`;
      replaceChildren(launchIndicatorHost, [
        indicatorBlock(
          'weather-launch-indicator-block',
          'p_launch from GET /v1/weather/probability',
          null,
          el('p', { class: 'hint', id: 'weather-launch-reason', text: reason }),
        ).element,
      ]);
      return;
    }
    const block = indicatorBlock(
      'weather-launch-indicator-block',
      `p_launch from GET /v1/weather/probability for ${response.date} at ${response.site}`,
      response.p_launch,
      el('span', { class: 'meta-line' }, [
        horizonBadge(response.horizon_label, response.forecast_issue_time, 'weather-launch-horizon-badge'),
        el('span', { class: 'secondary', text: `source ${response.source}` }),
        el('span', {
          class: 'secondary',
          text: `criteria ${response.criteria_version}, ensemble size ${
            response.ensemble_size === null ? 'null in CLIMATOLOGY mode' : response.ensemble_size
          }`,
        }),
        row === null
          ? null
          : el('span', {
              class: 'secondary',
              text: `row horizon label ${row.horizon_label}, row issue time ${
                row.forecast_issue_time === null ? 'absent' : formatIssueTime(row.forecast_issue_time)
              }`,
            }),
      ]),
    );
    replaceChildren(launchIndicatorHost, [block.element]);
  }

  function renderCriteria(state) {
    const response = state.weatherResponse;
    replaceChildren(criteriaHost, [criteriaList(response === null ? null : response.components)]);
  }

  /**
   * Criteria transparency and the uncertainty behind each probability of this screen
   * (issue 26). Every value is a field of the weather answer or of the selected window row.
   */
  function renderResearcher(state, row) {
    const response = state.weatherResponse;
    const present = response !== null && response !== undefined;

    if (!present) {
      criteriaSummary.textContent = 'No weather answer loaded, so no criteria are listed.';
      criteriaSummary.removeAttribute('data-criteria-version');
      criteriaSummary.setAttribute('data-verified', '');
      criteriaSummary.setAttribute('data-proxy', '');
      criteriaUncertainty.textContent = 'No weather answer loaded, so there is nothing to qualify.';
    } else {
      const counts = flagCounts(response.components);
      const others = Object.entries(counts.counts)
        .filter(([flag]) => flag !== 'VERIFIED' && flag !== 'PROXY')
        .map(([flag, count]) => `, ${count} ${flag}`)
        .join('');
      criteriaSummary.setAttribute('data-criteria-version', String(response.criteria_version));
      criteriaSummary.setAttribute('data-verified', String(counts.verified));
      criteriaSummary.setAttribute('data-proxy', String(counts.proxy));
      criteriaSummary.textContent =
        `GET /v1/weather/probability for ${response.date}: criteria version ${response.criteria_version}, ` +
        `${counts.total} criteria: ${counts.verified} VERIFIED, ${counts.proxy} PROXY${others}.`;
      criteriaUncertainty.textContent =
        `The p_launch and p_violation values of this answer: horizon_label ${response.horizon_label}, ` +
        `forecast_issue_time ${response.forecast_issue_time ?? 'null'}, ensemble size N ${response.ensemble_size ?? 'null'}, ` +
        `source ${response.source}.`;
    }

    const version = present ? String(response.criteria_version) : '';
    replaceChildren(versionSelect, [
      el('option', { value: version, text: present ? version : 'no weather answer loaded' }),
    ]);
    versionSelect.value = version;
    versionNote.textContent =
      'The API offers no list of criteria versions: no endpoint returns one and no field of any response names the ' +
      'versions that exist. The version therefore cannot be chosen here; the selector shows the one the weather answer used.';

    if (row === null) {
      rowUncertainty.setAttribute('data-ensemble-size', '');
      rowUncertainty.textContent = 'Select a window row to read what stands behind its probability.';
      return;
    }
    const liftoffDate = String(row.t_liftoff_utc).slice(0, 10);
    const behind =
      `p_success_components.weather of the selected row: horizon_label ${row.horizon_label}, ` +
      `forecast_issue_time ${row.forecast_issue_time ?? 'null'}`;
    if (present && response.date === liftoffDate) {
      rowUncertainty.setAttribute('data-ensemble-size', response.ensemble_size === null ? '' : String(response.ensemble_size));
      rowUncertainty.textContent =
        `${behind}; ensemble size N ${response.ensemble_size ?? 'null'}, from GET /v1/weather/probability for ` +
        `${response.date}, the liftoff date of the row.`;
    } else {
      rowUncertainty.setAttribute('data-ensemble-size', '');
      rowUncertainty.textContent =
        `${behind}; ensemble size N not available for this row: the window response has no such field, and the weather ` +
        `answer on the page is ${present ? `for ${response.date}` : 'absent'}, not for the liftoff date ${liftoffDate}.`;
    }
  }

  function renderSkill(state) {
    const response = state.skillResponse;
    if (response === null || response === undefined) {
      const reason =
        state.skillError === null
          ? 'no skill series fetched'
          : `GET /v1/validation/skill failed: ${state.skillError}`;
      replaceChildren(skillHost, [
        el('p', { class: 'chart-empty', id: 'weather-skill-empty', text: reason }),
      ]);
      skillNote.textContent =
        'The curve below the indicator is what spec V.3 asks for, so the public screen shows the evidence behind the horizon label.';
      return;
    }
    const { element, geometry } = renderSkillCurve(response);
    element.setAttribute('id', 'weather-skill-curve');
    replaceChildren(skillHost, [element]);
    const period = response.period ?? {};
    skillNote.textContent =
      `Brier skill score against lead time, ${geometry.points.length} points, hindcast ${period.start} to ${period.end}, ` +
      `verification ${response.verification_source}, reference ${response.reference_forecast}, base rate ${response.base_rate}. ` +
      (response.skill_horizon_measured_days === null
        ? 'The measured skill horizon is null in this response, so no horizon line is drawn.'
        : `The measured skill horizon is ${response.skill_horizon_measured_days} days. Positive Brier skill at short lead time is a CONJECTURE in spec II.9, measured here by the hindcast.`);
  }

  function render(state) {
    const row = selectedRow(state);
    thresholdsNote.textContent = thresholdsText(thresholds);
    renderRowIndicator(state, row);
    renderLaunchIndicator(state, row);
    renderCriteria(state);
    renderResearcher(state, row);
    renderSkill(state);
    const bands = [
      weatherBand(row?.p_success_components?.weather ?? null).band,
      weatherBand(state.weatherResponse?.p_launch ?? null).band,
    ];
    honesty.textContent =
      `Honesty boundary: the colour is a threshold on a probability, ${WEATHER_BAND_LABELS.GREY} means the response ` +
      'carries no probability at all. The panel does not predict brightness, contrail lighting or obscuration: ' +
      'that is the geometric visibility of Screen 4 and the probability above, kept separate.';
    root.setAttribute('data-bands', bands.join(','));
  }

  function destroy() {
    root.replaceChildren();
  }

  return {
    element: root,
    render,
    destroy,
    openCriteria() {
      const node = document.getElementById('weather-criteria');
      if (node !== null) {
        node.open = true;
      }
    },
  };
}