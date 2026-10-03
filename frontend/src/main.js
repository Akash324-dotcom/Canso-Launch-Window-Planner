import { createApp } from './app.js';

const root = document.getElementById('screen-window-engine');
const bannerHost = document.getElementById('mode-banner');
const app = createApp({
  root,
  bannerHost,
  trajectoryHost: document.getElementById('screen-trajectory'),
  weatherHost: document.getElementById('screen-weather'),
  viewingHost: document.getElementById('screen-viewing'),
  analysisHost: document.getElementById('screen-analysis'),
  autoMountMaps: true,
});

app.start();