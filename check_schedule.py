#!/usr/bin/env python3
"""Check that the publish schedule and the client countdown agree.

build_site.py bakes ROLLOVER_UTC into the page so the countdown can target the
next publish. If it drifts from the cron in daily.yml, the countdown silently
lies and the page reloads at the wrong moment. Cheap to check, annoying to
notice by hand.
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
WORKFLOW = HERE / ".github" / "workflows" / "daily.yml"
BUILD = HERE / "build_site.py"
PICK = HERE / "pick_daily.py"
SPLIT = HERE / "split_pool.py"


def check_epoch() -> None:
    """EPOCH is declared in both scheduling scripts and must agree.

    split_pool.py uses it to work out which positions are already spent and
    must be frozen; pick_daily.py uses it to map a date to a position. If they
    drift, split_pool.py freezes the wrong range and the schedule shifts under
    anyone mid-game.
    """
    pat = re.compile(r"EPOCH\s*=\s*date\((\d+),\s*(\d+),\s*(\d+)\)")
    found = {}
    for path in (PICK, SPLIT):
        m = pat.search(path.read_text())
        if not m:
            sys.exit(f"could not find EPOCH in {path.name}")
        found[path.name] = m.groups()
    if len(set(found.values())) != 1:
        sys.exit(f"EPOCH mismatch: {found}")
    y, mo, d = next(iter(found.values()))
    print(f"OK: EPOCH is {y}-{int(mo):02d}-{int(d):02d} in both scripts")


def main() -> None:
    check_epoch()
    cron = re.search(r'-\s*cron:\s*"([^"]+)"', WORKFLOW.read_text())
    if not cron:
        sys.exit("could not find a cron expression in daily.yml")
    minute, hour = cron.group(1).split()[:2]

    declared = re.search(r'ROLLOVER_UTC\s*=\s*"(\d{2}):(\d{2})"', BUILD.read_text())
    if not declared:
        sys.exit("could not find ROLLOVER_UTC in build_site.py")
    d_hour, d_minute = declared.groups()

    if (int(hour), int(minute)) != (int(d_hour), int(d_minute)):
        sys.exit(
            f"schedule mismatch: cron publishes at {int(hour):02d}:{int(minute):02d} UTC "
            f"but ROLLOVER_UTC says {d_hour}:{d_minute}"
        )

    print(f"OK: cron and ROLLOVER_UTC both say {d_hour}:{d_minute} UTC")


if __name__ == "__main__":
    main()
