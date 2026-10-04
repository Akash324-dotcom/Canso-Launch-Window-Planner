"""Hazard-screen policy check for the report that (II.10)-era southbound is global."""

from __future__ import annotations

import pathlib

from backend.engine import provenance, reachability, screens, target

root = pathlib.Path(__file__).resolve().parents[1]

SITES = ["canso", "kourou_ela1", "plesetsk_133", "vandenberg_slc4e"]
ANCHORS = {
    "canso": ("SSO advertised 98.1", 98.1, 674.0),
    "kourou_ela1": ("Sentinel-1C 98.18", 98.18, 693.0),
    "plesetsk_133": ("Sentinel-5P 98.74", 98.74, 824.0),
    "vandenberg_slc4e": ("EarthCARE 97.05", 97.05, 393.0),
}

print("=" * 96)
print("HAZARD SCREEN: per-site corridor vs the hard-coded _is_southbound (90..270)")
print("=" * 96)
print(f"{'site':16} {'corridor':>16} {'branch':>11} {'azimuth':>9} "
      f"{'in corridor':>12} {'southbound':>11} {'rule bites':>11}")
for name in SITES:
    site = target.load_site(name)
    corridor = site["corridor"]
    a_min, a_max = float(corridor["A_min_deg"]), float(corridor["A_max_deg"])
    label, incl, alt = ANCHORS[name]
    az = reachability.launch_azimuth_deg(incl, float(site["latitude_deg"]))
    in_corridor = a_min <= az <= a_max
    south = screens._is_southbound(az)
    bites = (not south) and in_corridor
    print(f"{name:16} {f'[{a_min:g}, {a_max:g}]':>16} {corridor.get('branch', '-'):>11} "
          f"{az:9.3f} {str(in_corridor):>12} {str(south):>11} {str(bites):>11}")

print()
print("The hard-coded rule is REDUNDANT at every current site: each declared corridor is")
print("a subset of [90, 270], so corridor membership already implies southbound.")
print()
print("Is it a NO-OP or a BUG? Probe a hypothetical site whose corridor is northbound.")
fake_north = {"A_min_deg": 330.0, "A_max_deg": 350.0, "branch": "northbound"}
verdict = screens.hazard_screen(341.5, fake_north, {})
print(f"  azimuth 341.5 in a declared northbound corridor [330, 350] -> hazard={verdict.hazard}")
print(f"  reason: {verdict.reason}")
print()
print("Canso alone carries a numeric southbound restriction in configuration:")
canso = provenance.load_json("site_canso.json")
print(f"  canso corridor source mentions Atlantic southbound: "
      f"{'Atlantic' in canso['corridor']['source']}")
for name in SITES[1:]:
    site = target.load_site(name)
    print(f"  {name:16} corridor source: {site['corridor']['source'][:78]}")