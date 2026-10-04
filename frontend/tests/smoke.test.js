import { readFileSync } from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { afterEach, describe, expect, it } from 'vitest';
import { boot, flush, installWindowsApi, jsonResponse, loadExample, textOf } from './helpers.js';

const INDEX_URL = new URL('index.html', pathToFileURL(`${process.cwd()}${path.sep}`));

describe('F0 smoke test', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('declares the module entry point and the screen host', () => {
    const html = readFileSync(INDEX_URL, 'utf8');
    expect(html).toMatch(/<script type="module" src="src\/main\.js"><\/script>/);
    expect(html).toContain('id="screen-window-engine"');
    expect(html).toContain('id="mode-banner"');
  });

  it('renders the page and the window table element exists', async () => {
    installWindowsApi(() => jsonResponse(loadExample('windows_response_good_stub.json')));
    const { app } = boot();

    app.start();
    await flush();

    expect(document.querySelector('main#screen-window-engine')).not.toBeNull();
    expect(document.querySelector('#window-table')).not.toBeNull();
    expect(document.querySelectorAll('#window-table thead th')).toHaveLength(8);
    expect(document.querySelectorAll('#window-rows tr[data-liftoff-utc]')).toHaveLength(1);
    expect(textOf('#countdown-value')).toMatch(/^(\d+d )?\d{2}:\d{2}:\d{2}$/);

    app.stop();
  });
});
