// Local runs talk to the local API; the deployed site talks to the Render service.
// Any page can still override this with ?api=<url>.
const LOCAL_HOSTS = ['localhost', '127.0.0.1', ''];
const isLocal = typeof location === 'undefined' || LOCAL_HOSTS.includes(location.hostname);
export const API_BASE = isLocal ? 'http://localhost:8000/v1' : 'https://canso-launch-api.onrender.com/v1';

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
  { id: 'canso', label: 'Canso, Spaceport Nova Scotia' },
];

export const ORBIT_PRESETS = [
  {
    id: 'LEO',
    label: 'LEO, inclination 45.1 deg',
    inclination_deg: 45.1,
    plane_mode: 'raan',
    orbit_id: 'leo45',
    slide_clause: 'LEO: calculate windows for inclinations about 45.1 deg',
  },
  {
    id: 'POLAR',
    label: 'Polar, inclination 87.9 deg (to 90 deg)',
    inclination_deg: 87.9,
    plane_mode: 'raan',
    orbit_id: 'polar879',
    slide_clause: 'Polar: calculate windows for inclinations 87.9 to 90 deg',
  },
  {
    id: 'SSO',
    label: 'SSO, inclination 98.1 deg',
    inclination_deg: 98.1,
    plane_mode: 'ltan',
    ltan_hours: '10:30',
    orbit_id: 'sso981',
    slide_clause: 'SSO: calculate windows for inclinations about 98.1 deg',
  },
  {
    id: 'CUSTOM',
    label: 'Custom, h_t and i_t with RAAN or LTAN',
    inclination_deg: null,
    plane_mode: 'raan',
    orbit_id: null,
    slide_clause: null,
  },
];

export const ORBIT_IDS_BY_TYPE = ORBIT_PRESETS.reduce((accumulator, preset) => {
  accumulator[preset.id] = preset.orbit_id;
  return accumulator;
}, {});

export const EPHEMERIS_STEP_S = 300;

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

export const WEATHER_THRESHOLDS = {
  green_min: 0.7,
  yellow_min: 0.4,
  flag: 'ASSUMPTION',
  source:
    'src/config.js WEATHER_THRESHOLDS, the defaults spec V.3 states; the backend serves no weather thresholds, so they are kept in this file',
};

export const WEATHER_BAND_LABELS = {
  GREEN: 'Green',
  YELLOW: 'Yellow',
  RED: 'Red',
  GREY: 'no probability available',
};

// Spec III.4 pass criterion 2: at least 5 populated reliability bins and a mean absolute
// difference between observed and predicted of at most 0.15. The numbers are the spec's.
export const CALIBRATION_GAP_BOUND = 0.15;

export const CALIBRATION_MIN_BINS = 5;

export const ELEVATION_MASK_DEG = 10;

export const ELEVATION_MASK_FLAG = 'ASSUMPTION';

export const ELEVATION_MASK_SOURCE = 'src/config.js ELEVATION_MASK_DEG, the default of spec V.4';

export const VEHICLE_FOOTPRINTS = {
  cyclone4m: {
    hazard_half_width_km: null,
    source: 'backend/engine/data/vehicles/cyclone4m.json',
    flag: 'ASSUMPTION',
  },
};

export const CORRIDOR_ARC_SAMPLES = 24;

export const CORRIDOR_FALLBACK_ARC_KM = 1200;

export const CORRIDOR_BEARING_TOLERANCE_DEG = 0;

// How far from the site the ephemeris sample at the liftoff instant may be and still count as
// "on the pad". The site coordinate variants of GET /v1/site differ by about 1.5 km, so the
// bound has to be wider than that. The value is a choice of this page, not vehicle or range data.
export const TRACK_START_TOLERANCE_KM = 5;

export const TRACK_START_TOLERANCE_FLAG = 'ASSUMPTION';

export const DATA_BASE = './src/data/';

export const CENTRES_FILE = 'centres.json';

export const LEAFLET_ESM = '../node_modules/leaflet/dist/leaflet-src.esm.js';

export const LEAFLET_STYLESHEET = 'node_modules/leaflet/dist/leaflet.css';

export const EARTH_RADIUS_M = 6378137.0;

export const EARTH_RADIUS_SOURCE =
  'constants_block.R_e of the ephemeris response, with the spec II.10 value 6378137.0 m as the fallback';

// Sidereal rotation rate of the Earth. The corridor guard turns the Earth back by this rate
// to read a ground track sample in the frame fixed at liftoff, the frame the corridor azimuth
// is stated in.
export const OMEGA_SID_RAD_S = 7.292115e-5;

export const OMEGA_SID_SOURCE =
  'constants_block.omega_sid_rad_s of the ephemeris response, with the spec II.10 value 7.292115e-5 rad/s as the fallback';

export const J2000_MS = Date.UTC(2000, 0, 1, 12, 0, 0);

export const DAY_MS = 86400000;

export const SOLAR_FORMULA_SOURCE = [
  'Low precision solar coordinates: mean longitude, mean anomaly, ecliptic longitude and obliquity',
  'as published under Solar Coordinates in the Astronomical Almanac of the US Naval Observatory and',
  'reproduced by the NOAA Solar Calculator. The same Greenwich mean sidereal time polynomial is the',
  'IAU 1982 expression that constants_block.gmst_model names. Neither citation was resolved online',
  'on this branch, so the expression is carried as ASSUMPTION pending verification.',
].join(' ');
