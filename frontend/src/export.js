import { windowRows } from './selectors.js';

const CSV_MIME = 'text/csv';
const JSON_MIME = 'application/json';

/**
 * Client-side exports of what the screens already show, spec V.6.
 *
 * The window table CSV is read from the rendered table rather than from the response
 * object, so the file is the table the planner saw, formatted the way the table
 * formats it, with one column per rendered cell and the rendered headers as the header
 * row. The JSON download is the untouched response object, so a researcher who needs
 * the exact values has them without parsing a formatted string.
 */

export function csvCell(value) {
  if (value === null || value === undefined) {
    return '';
  }
  const text = String(value);
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function csvRow(cells) {
  return cells.map(csvCell).join(',');
}

/**
 * The text of one rendered cell, with the boundary between two child elements kept as
 * a single space, so a cell made of a badge and a note exports as the two strings the
 * reader sees rather than as their concatenation.
 */
export function cellText(cell) {
  return [...cell.childNodes]
    .map((node) => (node.nodeType === 3 ? node.nodeValue : node.textContent))
    .join(' ')
    .replace(/\s+/g, ' ')
    .trim();
}

export function renderedTableCsv(table) {
  const header = [...table.querySelectorAll('thead th')].map(cellText);
  const rows = [...table.querySelectorAll('tbody tr')].map((row) => [...row.children].map(cellText));
  return `${[csvRow(header), ...rows.map(csvRow)].join('\n')}\n`;
}

export function skillSeriesCsv(skillResponse) {
  const series = Array.isArray(skillResponse?.skill_series) ? skillResponse.skill_series : [];
  const lines = [
    csvRow(['lead_time_days', 'bs', 'bs_ref', 'bss', 'n_cases']),
    ...series.map((entry) => csvRow([entry.lead_time_days, entry.bs, entry.bs_ref, entry.bss, entry.n_cases])),
  ];
  return `${lines.join('\n')}\n`;
}

export function reliabilityCsv(skillResponse) {
  const bins = Array.isArray(skillResponse?.reliability_bins) ? skillResponse.reliability_bins : [];
  const lines = [
    csvRow(['p_center', 'observed_freq', 'n']),
    ...bins.map((bin) => csvRow([bin.p_center, bin.observed_freq, bin.n])),
  ];
  return `${lines.join('\n')}\n`;
}

export function responseJson(response) {
  return `${JSON.stringify(response, null, 2)}\n`;
}

/** The rows of the window table as the response holds them, one object per displayed row. */
export function windowRowsJson(response) {
  return `${JSON.stringify(windowRows(response), null, 2)}\n`;
}

export function windowRowCount(response) {
  return windowRows(response).length;
}

/**
 * Hand a finished string to the browser as a file. The Blob becomes an object URL
 * where the environment provides one and a data URL otherwise, so the export path is
 * the same under jsdom and in a browser.
 */
export function downloadText(descriptor, target = document) {
  const { filename, mimeType, text } = descriptor;
  const blob = new Blob([text], { type: mimeType });
  const createObjectURL = globalThis.URL?.createObjectURL;
  const href =
    typeof createObjectURL === 'function'
      ? createObjectURL.call(globalThis.URL, blob)
      : `data:${mimeType};charset=utf-8,${encodeURIComponent(text)}`;
  const anchor = target.createElement('a');
  anchor.href = href;
  anchor.download = filename;
  anchor.rel = 'noopener';
  anchor.style.display = 'none';
  target.body.appendChild(anchor);
  anchor.click();
  target.body.removeChild(anchor);
  if (typeof createObjectURL === 'function') {
    // The revoke is deferred by one turn: revoking the object URL in the same turn as
    // the click can cancel the download in some browsers.
    setTimeout(() => {
      globalThis.URL.revokeObjectURL(href);
    }, 0);
  }
  return { filename, mimeType, href, size: text.length, blob };
}

export function csvDescriptor(filename, table) {
  return { filename, mimeType: CSV_MIME, text: renderedTableCsv(table) };
}

export function jsonDescriptor(filename, response) {
  return { filename, mimeType: JSON_MIME, text: responseJson(response) };
}