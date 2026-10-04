/** Issue 26, control 1: CSV and JSON download of the window table, rows in the file equal rows displayed. */
import { afterEach, describe, expect, it } from 'vitest';
import { clone, loadExample, textOf } from './helpers.js';
import { STUB, captureDownloads, displayedRows, start } from './researcherHelpers.js';

afterEach(() => {
  document.body.innerHTML = '';
});

function fiveRows() {
  const response = clone(loadExample(STUB));
  const base = response.windows[0];
  response.windows = [0, 1, 2, 3, 4].map((day) => ({
    ...clone(base),
    t_liftoff_utc: `2026-10-0${5 + day}T13:42:11Z`,
    t_injection_utc: `2026-10-0${5 + day}T13:47:26Z`,
    window_width_s: 600 + day,
  }));
  return response;
}

describe('researcher layer, downloads of the window table', () => {
  it('writes a CSV whose data rows are the rows displayed, from the response of POST /v1/windows', async () => {
    const response = fiveRows();
    const { app, posts } = await start({ windows: () => response });
    const downloads = captureDownloads();

    document.getElementById('download-window-csv').click();
    const lines = (await downloads.text(0)).split('\n').filter((line) => line.length > 0);

    expect(posts()).toHaveLength(1);
    expect(displayedRows()).toHaveLength(5);
    expect(lines.length - 1).toBe(displayedRows().length);
    expect(lines[1]).toContain('600.0 s');
    expect(lines[5]).toContain('604.0 s');
    downloads.release();
    app.stop();
  });

  it('writes a JSON file of the window rows, as many as are displayed and equal to the response', async () => {
    const response = fiveRows();
    const { app } = await start({ windows: () => response });
    const downloads = captureDownloads();

    document.getElementById('download-window-json').click();
    const rows = JSON.parse(await downloads.text(0));

    expect(downloads.files[0].filename).toBe(`canso-windows-${response.constants_block.citation_id}.json`);
    expect(Array.isArray(rows)).toBe(true);
    expect(rows).toHaveLength(displayedRows().length);
    expect(rows).toEqual(response.windows);
    expect(rows.map((row) => row.t_liftoff_utc)).toEqual(displayedRows().map((row) => row.getAttribute('data-liftoff-utc')));
    downloads.release();
    app.stop();
  });

  it('states the row count the two files will hold and follows a new response', async () => {
    let response = fiveRows();
    const { app } = await start({ windows: () => response });
    expect(textOf('#analysis-window-download-count')).toBe(
      '5 rows are displayed in the window table; the CSV and the JSON file of the window table hold the same 5 rows.',
    );

    response = clone(loadExample(STUB));
    await app.dispatch();
    const shown = displayedRows().length;

    expect(shown).toBe(response.windows.length);
    expect(textOf('#analysis-window-download-count')).toContain(`${shown} row`);
    app.stop();
  });

  it('says there is nothing to download when the response has no rows', async () => {
    const response = { ...clone(loadExample(STUB)), windows: [] };
    const { app } = await start({ windows: () => response });
    const downloads = captureDownloads();

    document.getElementById('download-window-json').click();

    expect(downloads.files).toHaveLength(1);
    expect(JSON.parse(await downloads.text(0))).toEqual([]);
    expect(textOf('#analysis-window-download-count')).toContain('0 rows are displayed');
    downloads.release();
    app.stop();
  });
});
