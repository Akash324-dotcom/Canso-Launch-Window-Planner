# Vendored scripts and fonts for `Canso Launch Prototype.html`

These files are copied unchanged from npm so the page renders with the network off
(issue #27, the offline acceptance). The page used to load all of them from CDNs.

| File | Package | Version | Licence |
|---|---|---|---|
| `three.min.js` | `three` build/three.min.js | 0.128.0 | MIT |
| `OrbitControls.js`, `LineSegmentsGeometry.js`, `LineGeometry.js`, `LineMaterial.js`, `LineSegments2.js`, `Line2.js` | `three` examples/js | 0.128.0 | MIT |
| `gsap.min.js` | `gsap` dist/gsap.min.js | 3.12.5 | GSAP Standard "no charge" licence, https://gsap.com/standard-license |
| `fonts/saira-semi-condensed-latin-*.woff2` | `@fontsource/saira-semi-condensed` | 5.3.0 | SIL OFL 1.1 |
| `fonts/ibm-plex-sans-latin-*.woff2` | `@fontsource/ibm-plex-sans` | 5.3.0 | SIL OFL 1.1 |
| `fonts/ibm-plex-mono-latin-*.woff2` | `@fontsource/ibm-plex-mono` | 5.3.0 | SIL OFL 1.1 |

`fonts.css` is written by hand and points at the local `fonts/` files (latin subset only).

To refresh: `npm pack three@0.128.0 gsap@3.12.5`, unpack, copy the same paths.
