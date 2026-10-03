import { ELEVATION_MASK_DEG } from './config.js';
import { svgEl } from './dom.js';

const DEFAULT_SIZE = { width: 620, height: 240, margin: { top: 18, right: 18, bottom: 38, left: 56 } };

function scale(domainMin, domainMax, rangeMin, rangeMax) {
  const span = domainMax - domainMin;
  if (span === 0) {
    return () => (rangeMin + rangeMax) / 2;
  }
  return (value) => rangeMin + ((value - domainMin) / span) * (rangeMax - rangeMin);
}

function plotArea(size) {
  return {
    x0: size.margin.left,
    x1: size.width - size.margin.right,
    y0: size.margin.top,
    y1: size.height - size.margin.bottom,
  };
}

function axisTicks(min, max, count) {
  const ticks = [];
  for (let index = 0; index <= count; index += 1) {
    ticks.push(min + ((max - min) * index) / count);
  }
  return ticks;
}

function niceBounds(values, padding = 0.1) {
  if (values.length === 0) {
    return [0, 1];
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min === 0 ? 1 : max - min;
  return [min - span * padding, max + span * padding];
}

/**
 * The hindcast skill curve of spec V.3, drawn as inline SVG from the skill_series of the
 * GET /v1/validation/skill response. No chart library is used: the geometry is computed
 * here and the nodes are built by src/dom.js.
 */
export function skillCurveGeometry(skillResponse, options = {}) {
  const size = { ...DEFAULT_SIZE, ...options.size, margin: { ...DEFAULT_SIZE.margin, ...(options.size?.margin ?? {}) } };
  const plot = plotArea(size);
  const series = Array.isArray(skillResponse?.skill_series) ? skillResponse.skill_series : [];
  const bssValues = series.map((entry) => Number(entry.bss)).filter(Number.isFinite);
  const yDomain = options.yDomain ?? niceBounds([0, ...bssValues]);
  const xMin = series.length === 0 ? 0 : Math.min(...series.map((entry) => Number(entry.lead_time_days)));
  const xMax = series.length === 0 ? 1 : Math.max(...series.map((entry) => Number(entry.lead_time_days)));
  const x = scale(xMin, xMax, plot.x0, plot.x1);
  const y = scale(yDomain[0], yDomain[1], plot.y1, plot.y0);
  const points = series.map((entry) => ({
    lead_time_days: Number(entry.lead_time_days),
    bss: Number(entry.bss),
    bs: Number(entry.bs),
    bs_ref: Number(entry.bs_ref),
    n_cases: Number(entry.n_cases),
    x: x(Number(entry.lead_time_days)),
    y: y(Number(entry.bss)),
  }));
  const measured = skillResponse?.skill_horizon_measured_days;
  return {
    size,
    plot,
    series,
    points,
    xDomain: [xMin, xMax],
    yDomain,
    xScale: x,
    yScale: y,
    measuredSkillHorizonDays: Number.isFinite(Number(measured)) ? Number(measured) : null,
  };
}

export function renderSkillCurve(skillResponse, options = {}) {
  const geometry = skillCurveGeometry(skillResponse, options);
  const { size, plot, points, measuredSkillHorizonDays } = geometry;
  const children = [];
  const yTicks = axisTicks(geometry.yDomain[0], geometry.yDomain[1], 4).map((value) =>
    Number(value.toFixed(4)),
  );
  for (const tick of yTicks) {
    children.push(
      svgEl('line', {
        class: 'chart-grid',
        x1: plot.x0,
        x2: plot.x1,
        y1: geometry.yScale(tick),
        y2: geometry.yScale(tick),
      }),
      svgEl('text', {
        class: 'chart-tick',
        x: plot.x0 - 8,
        y: geometry.yScale(tick) + 4,
        'text-anchor': 'end',
      }, [tick.toFixed(2)]),
    );
  }
  children.push(
    svgEl('line', {
      class: 'chart-axis',
      x1: plot.x0,
      x2: plot.x1,
      y1: plot.y1,
      y2: plot.y1,
    }),
    svgEl('line', {
      class: 'chart-axis',
      x1: plot.x0,
      x2: plot.x0,
      y1: plot.y0,
      y2: plot.y1,
    }),
  );
  if (geometry.yDomain[0] < 0 && geometry.yDomain[1] > 0) {
    children.push(
      svgEl('line', {
        class: 'chart-zero',
        x1: plot.x0,
        x2: plot.x1,
        y1: geometry.yScale(0),
        y2: geometry.yScale(0),
      }),
      svgEl('text', { class: 'chart-note', x: plot.x1, y: geometry.yScale(0) - 5, 'text-anchor': 'end' }, [
        'no skill',
      ]),
    );
  }
  if (measuredSkillHorizonDays !== null && geometry.xDomain[0] !== geometry.xDomain[1]) {
    const xValue = geometry.xScale(measuredSkillHorizonDays);
    children.push(
      svgEl('line', {
        class: 'chart-horizon',
        x1: xValue,
        x2: xValue,
        y1: plot.y0,
        y2: plot.y1,
        'data-measured-skill-horizon-days': measuredSkillHorizonDays,
      }),
      svgEl('text', { class: 'chart-note', x: xValue + 4, y: plot.y0 + 10 }, [
        `measured skill horizon ${measuredSkillHorizonDays} d`,
      ]),
    );
  }
  if (points.length > 0) {
    children.push(
      svgEl('polyline', {
        class: 'chart-line',
        points: points.map((point) => `${point.x},${point.y}`).join(' '),
        'data-point-count': points.length,
      }),
    );
    for (const point of points) {
      children.push(
        svgEl('circle', {
          class: 'chart-point',
          cx: point.x,
          cy: point.y,
          r: 4,
          'data-lead-time-days': point.lead_time_days,
          'data-bss': point.bss,
          'data-bs': point.bs,
          'data-bs-ref': point.bs_ref,
          'data-n-cases': point.n_cases,
        }),
        svgEl('text', {
          class: 'chart-tick',
          x: point.x,
          y: plot.y1 + 16,
          'text-anchor': 'middle',
        }, [`${point.lead_time_days} d`]),
      );
    }
  }
  children.push(
    svgEl('text', { class: 'chart-axis-label', x: (plot.x0 + plot.x1) / 2, y: size.height - 6, 'text-anchor': 'middle' }, [
      'lead time (days)',
    ]),
    svgEl('text', {
      class: 'chart-axis-label',
      x: 12,
      y: (plot.y0 + plot.y1) / 2,
      'text-anchor': 'middle',
      transform: `rotate(-90 12 ${(plot.y0 + plot.y1) / 2})`,
    }, ['Brier skill score']),
  );
  const svg = svgEl(
    'svg',
    {
      class: 'chart',
      viewBox: `0 0 ${size.width} ${size.height}`,
      role: 'img',
      'aria-label': 'Hindcast Brier skill score against lead time',
      'data-point-count': points.length,
      'data-series': 'bss',
    },
    children,
  );
  return { element: svg, geometry };
}

/**
 * The elevation against time chart of spec V.4 for the best viewing centre.
 */
export function renderElevationCurve(centre, options = {}) {
  const maskDeg = options.elevationMaskDeg ?? ELEVATION_MASK_DEG;
  const size = { ...DEFAULT_SIZE, ...options.size, margin: { ...DEFAULT_SIZE.margin, ...(options.size?.margin ?? {}) } };
  const plot = plotArea(size);
  const samples = Array.isArray(centre?.samples) ? centre.samples : [];
  const startMs = samples.length === 0 ? 0 : Date.parse(samples[0].t_utc);
  const offsetsMin = samples.map((sample) => (Date.parse(sample.t_utc) - startMs) / 60000);
  const elevations = samples.map((sample) => sample.elevation_deg).filter(Number.isFinite);
  const yDomain = options.yDomain ?? niceBounds([...elevations, maskDeg]);
  const xDomain = offsetsMin.length === 0 ? [0, 1] : [Math.min(...offsetsMin), Math.max(...offsetsMin)];
  const x = scale(xDomain[0], xDomain[1], plot.x0, plot.x1);
  const y = scale(yDomain[0], yDomain[1], plot.y1, plot.y0);
  const points = samples.map((sample, index) => ({
    t_utc: sample.t_utc,
    offset_min: offsetsMin[index],
    elevation_deg: sample.elevation_deg,
    azimuth_deg: sample.azimuth_deg,
    sunlit_in_darkness: sample.sunlit_in_darkness,
    x: x(offsetsMin[index]),
    y: y(sample.elevation_deg),
  }));
  const children = [];
  if (yDomain[0] < maskDeg && yDomain[1] > maskDeg) {
    children.push(
      svgEl('line', {
        class: 'chart-mask',
        x1: plot.x0,
        x2: plot.x1,
        y1: y(maskDeg),
        y2: y(maskDeg),
        'data-elevation-mask-deg': maskDeg,
      }),
      svgEl('text', { class: 'chart-note', x: plot.x0 + 4, y: y(maskDeg) - 5 }, [
        `elevation mask ${maskDeg} deg, ASSUMPTION`,
      ]),
    );
  }
  children.push(
    svgEl('line', { class: 'chart-axis', x1: plot.x0, x2: plot.x1, y1: plot.y1, y2: plot.y1 }),
    svgEl('line', { class: 'chart-axis', x1: plot.x0, x2: plot.x0, y1: plot.y0, y2: plot.y1 }),
  );
  if (points.length > 0) {
    children.push(
      svgEl('polyline', {
        class: 'chart-line',
        points: points.map((point) => `${point.x},${point.y}`).join(' '),
        'data-point-count': points.length,
      }),
    );
    for (const point of points) {
      children.push(
        svgEl('circle', {
          class: 'chart-point',
          cx: point.x,
          cy: point.y,
          r: 4,
          'data-t-utc': point.t_utc,
          'data-elevation-deg': point.elevation_deg === null ? '' : Number(point.elevation_deg.toFixed(4)),
          'data-azimuth-deg': point.azimuth_deg === null ? '' : Number(point.azimuth_deg.toFixed(4)),
          'data-sunlit-in-darkness': String(point.sunlit_in_darkness === true),
        }),
        svgEl('text', { class: 'chart-tick', x: point.x, y: plot.y1 + 16, 'text-anchor': 'middle' }, [
          `T+${Math.round(point.offset_min)} min`,
        ]),
      );
    }
  }
  children.push(
    svgEl('text', { class: 'chart-axis-label', x: (plot.x0 + plot.x1) / 2, y: size.height - 6, 'text-anchor': 'middle' }, [
      'minutes after the first sample',
    ]),
    svgEl('text', {
      class: 'chart-axis-label',
      x: 12,
      y: (plot.y0 + plot.y1) / 2,
      'text-anchor': 'middle',
      transform: `rotate(-90 12 ${(plot.y0 + plot.y1) / 2})`,
    }, ['elevation (deg)']),
  );
  const svg = svgEl(
    'svg',
    {
      class: 'chart',
      viewBox: `0 0 ${size.width} ${size.height}`,
      role: 'img',
      'aria-label': `Elevation of the ascent from ${centre?.name ?? 'the best centre'} against time`,
      'data-centre-id': centre?.id ?? '',
      'data-point-count': points.length,
      'data-series': 'elevation_deg',
    },
    children,
  );
  return { element: svg, points, yDomain, xDomain };
}