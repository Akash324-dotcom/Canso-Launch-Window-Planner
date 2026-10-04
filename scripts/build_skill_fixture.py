"""Generate backend/fixtures/skill.json from the hindcast. The fixture is never typed by hand (issue #7 V7).

    python scripts/build_skill_fixture.py [site]

Runs the hindcast over the longest period the committed data supports and writes the GET /v1/validation/skill
response (spec IV.4). Needs no network. Running it twice for the same data gives byte-identical output.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.weather import config, hindcast  # noqa: E402

FIXTURE = REPO / "backend" / "fixtures" / "skill.json"


def build(site: str = "canso") -> str:
    """Return the text of the fixture file."""
    start, end = hindcast.longest_period(site)
    lead_max = config.load_sources()["hindcast"]["lead_max_days"]
    return json.dumps(hindcast.response(hindcast.compute(start, end, lead_max, site)), indent=1,
                      ensure_ascii=False) + "\n"


def main(site: str = "canso") -> None:
    text = build(site)
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(text, encoding="utf-8")
    print(f"wrote {FIXTURE.relative_to(REPO)} ({len(text)} bytes)")


if __name__ == "__main__":
    main(*sys.argv[1:2])
