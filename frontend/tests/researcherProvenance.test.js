/** Issue 26, control 2: provenance of the run that produced the visible rows, and its citation. */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { API_BASE, MODE_OFFLINE } from '../src/config.js';
import { boot, installContractApi, loadExample, textOf } from './helpers.js';
import { STUB, citationRecord, settle, start } from './researcherHelpers.js';

afterEach(() => {
  document.body.innerHTML = '';
  vi.unstubAllGlobals();
});

describe('researcher layer, provenance per run', () => {
  it('renders the constants and the source files of the response that produced the visible rows', async () => {
    const response = loadExample(STUB);
    const { app, posts } = await start({ windows: () => response });

    expect(posts()).toHaveLength(1);
    const constants = textOf('#constants-body');
    for (const key of ['J2', 'GM', 'R_e', 'omega_sid_rad_s', 'gmst_model']) {
      expect(constants).toContain(String(response.constants_block[key]));
    }
    expect(constants).toContain(response.constants_block.source.J2);
    const files = [...document.querySelectorAll('#analysis-source-files li[data-source-file]')].map((node) =>
      node.getAttribute('data-source-file'),
    );
    expect(files).toEqual(response.provenance_block.source_files);
    expect(textOf('#citation-id')).toBe(response.constants_block.citation_id);
    app.stop();
  });

  it('offers a link that fetches the citation of the run from /v1/citation', async () => {
    const response = loadExample(STUB);
    const { app } = await start({ windows: () => response, citation: () => citationRecord(response) });
    const link = document.getElementById('citation-link');

    expect(link.getAttribute('href')).toBe(`${API_BASE}/citation?id=${response.constants_block.citation_id}`);
    expect(link.getAttribute('target')).toBe('_blank');
    expect(link.getAttribute('aria-disabled')).toBe('false');
    app.stop();
  });

  it('fetches the record again on request and renders what GET /v1/citation returned', async () => {
    const response = loadExample(STUB);
    let generated = '2026-10-04T11:25:22Z';
    const { app, calls } = await start({
      windows: () => response,
      citation: () => citationRecord(response, { generated_at: generated }),
    });
    const before = calls.filter((call) => call.url.includes('/citation')).length;
    expect(textOf('#citation-status')).toContain('generated_at 2026-10-04T11:25:22Z');

    generated = '2026-10-04T12:00:00Z';
    document.getElementById('citation-fetch').click();
    await settle();

    const citationCalls = calls.filter((call) => call.url.includes('/citation'));
    expect(citationCalls).toHaveLength(before + 1);
    expect(citationCalls.at(-1).url).toBe(`${API_BASE}/citation?id=${response.constants_block.citation_id}`);
    const status = textOf('#citation-status');
    expect(status).toContain('generated_at 2026-10-04T12:00:00Z');
    expect(status).toContain('config_hash ce4fb5178ec2b5ea272a736ec630505cd0f00e919aa5d2046378d5d0c10d4a3a');
    expect(status).toContain('2 source files');
    app.stop();
  });

  it('copies the citation id and says so, and says when the browser refuses', async () => {
    const response = loadExample(STUB);
    const writeText = vi.fn(async () => undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });
    const { app } = await start({ windows: () => response, citation: () => citationRecord(response) });

    document.getElementById('citation-copy').click();
    await settle();
    expect(writeText).toHaveBeenCalledWith(response.constants_block.citation_id);
    expect(textOf('#citation-copy-status')).toBe(`Copied ${response.constants_block.citation_id}.`);

    writeText.mockImplementation(async () => {
      throw new Error('denied');
    });
    document.getElementById('citation-copy').click();
    await settle();
    expect(textOf('#citation-copy-status')).toContain('The browser refused clipboard access');
    app.stop();
  });

  it('states the failure of GET /v1/citation and shows no record', async () => {
    const response = loadExample(STUB);
    const { app } = await start({ windows: () => response });

    expect(textOf('#citation-status')).toContain('GET /v1/citation did not answer for this run (HTTP 404)');
    expect(textOf('#citation-status')).not.toContain('config_hash');
    app.stop();
  });

  it('offers no citation link in offline mode, where no service stored the run', async () => {
    installContractApi(() => {
      throw new TypeError('Failed to fetch');
    });
    const { app } = boot();
    app.start();
    await settle();

    expect(app.store.getState().mode).toBe(MODE_OFFLINE);
    const link = document.getElementById('citation-link');
    expect(link.getAttribute('aria-disabled')).toBe('true');
    expect(link.hasAttribute('href')).toBe(false);
    expect(document.getElementById('citation-fetch').disabled).toBe(true);
    expect(textOf('#citation-status')).toContain('offline fixture');
    app.stop();
  });
});
