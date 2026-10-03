export const API_BASE = 'http://localhost:8000/v1';

export const REQUEST_TIMEOUT_MS = 8000;

export const COUNTDOWN_INTERVAL_MS = 1000;

export const MODE_LIVE = 'live_engine';
export const MODE_OFFLINE = 'offline_precomputed';

export const ATLANTIC_TIME_ZONE = 'America/Halifax';

export const DEFAULT_SITE = 'canso';

export const DEFAULT_RANGE_DAYS = 4;

export const FIXTURE_BASE = '../backend/fixtures/';

export const FIXTURES = {
  windows: 'windows.json',
  weather: 'weather.json',
  skill: 'skill.json',
  site: 'site.json',
  ephemeris: 'ephemeris.json',
};

export const SITES = [
  { id: 'canso', label: 'Canso, Spaceport Nova Scotia (45.3 N, 61.0 W)' },
];

export const ORBIT_PRESETS = [
  {
    id: 'LEO',
    label: 'LEO, inclination 45.1 deg',
    inclination_deg: 45.1,
    plane_mode: 'raan',
    slide_clause: 'LEO: calculate windows for inclinations about 45.1 deg',
  },
  {
    id: 'POLAR',
    label: 'Polar, inclination 87.9 deg (to 90 deg)',
    inclination_deg: 87.9,
    plane_mode: 'raan',
    slide_clause: 'Polar: calculate windows for inclinations 87.9 to 90 deg',
  },
  {
    id: 'SSO',
    label: 'SSO, inclination 98.1 deg',
    inclination_deg: 98.1,
    plane_mode: 'ltan',
    ltan_hours: '10:30',
    slide_clause: 'SSO: calculate windows for inclinations about 98.1 deg',
  },
  {
    id: 'CUSTOM',
    label: 'Custom, h_t and i_t with RAAN or LTAN',
    inclination_deg: null,
    plane_mode: 'raan',
    slide_clause: null,
  },
];

export const VEHICLE_PROFILE_IDS = ['cyclone4m'];

export const VEHICLE_PROFILE_OWNER = 'backend/engine/data/vehicles/cyclone4m.json';

export const T_TO_INJ_FLAG_PATTERN = /^T_to_inj/i;

export const WINDOW_TABLE_COLUMNS = [
  { key: 't_liftoff_utc', label: 't_liftoff_utc' },
  { key: 't_injection_utc', label: 't_injection_utc' },
  { key: 'window_width_s', label: 'window_width_s' },
  { key: 'azimuth_deg', label: 'azimuth_deg' },
  { key: 'reached_inclination_deg', label: 'reached_inclination_deg' },
  { key: 'p_success', label: 'p_success' },
  { key: 'horizon_label', label: 'horizon_label' },
  { key: 'constraint_fired', label: 'constraint status' },
];
