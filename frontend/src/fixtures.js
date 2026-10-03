import { FIXTURE_BASE, FIXTURES } from './config.js';
import { requestJson } from './api.js';

export function fixtureUrl(name) {
  const file = FIXTURES[name];
  if (file === undefined) {
    throw new Error(`unknown offline fixture: ${name}`);
  }
  return `${FIXTURE_BASE}${file}`;
}

export async function loadFixture(name, options = {}) {
  return requestJson(fixtureUrl(name), options);
}

export async function loadFixtures(names = Object.keys(FIXTURES), options = {}) {
  const results = await Promise.allSettled(names.map((name) => loadFixture(name, options)));
  const loaded = {};
  const failures = [];
  results.forEach((result, index) => {
    const name = names[index];
    if (result.status === 'fulfilled') {
      loaded[name] = result.value;
    } else {
      failures.push({ name, reason: result.reason instanceof Error ? result.reason.message : String(result.reason) });
    }
  });
  return { loaded, failures };
}
