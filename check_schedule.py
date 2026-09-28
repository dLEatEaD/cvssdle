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


def main() -> None:
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
