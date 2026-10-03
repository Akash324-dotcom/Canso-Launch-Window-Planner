import { createApp } from './app.js';

const root = document.getElementById('screen-window-engine');
const bannerHost = document.getElementById('mode-banner');
const app = createApp({ root, bannerHost });

app.start();
