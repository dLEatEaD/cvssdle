#!/usr/bin/env python3
"""CI gate: a saved game from the live site must still load after a change.

Players keep progress, stats and streaks in localStorage. A change that renames
a field, tightens validation, or assumes a key that older saves lack will
silently wipe someone's streak or - worse - replay their guesses against a
different answer. That has happened once already.

This loads the built page in a headless browser, plants saved state in the
shapes the live site has actually written, and asserts each one either resumes
correctly or is discarded cleanly. Never a crash, never a wrong board.

Falls back to a static check if Playwright is unavailable, so the gate degrades
to something useful rather than failing the build for the wrong reason.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
BUILT = HERE / "index.html"

# Saved-state shapes this project has shipped, oldest first, each with the
# behaviour the game must exhibit. Add to this list whenever the state format
# changes; never remove an entry.
#
# "resume" - the save provably belongs to today's puzzle and must be restored.
# "discard" - it cannot be proven to match, so it must be dropped and the board
#             left playable. Replaying guesses against a different answer is the
#             failure this gate exists to prevent.
LEGACY_STATES = [
    # Pre-2026-09-28 saves carry no puzzle id. A day number alone does not
    # identify a puzzle once the pool has been re-split, so these are dropped.
    ("v1 no id", "discard", {"day": None, "guesses": [5.0, 8.0],
                             "finished": False, "won": False}),
    ("v1 finished, no id", "discard",
     {"day": None, "guesses": [5.0, 8.0, 9.9, 1.2, 3.4, 5.6],
      "finished": True, "won": False}),
    ("v2 with id, in progress", "resume",
     {"day": None, "id": None, "guesses": [5.0], "finished": False, "won": False}),
    ("v2 with id, finished", "resume",
     {"day": None, "id": None, "guesses": [5.0], "finished": True, "won": False}),
    ("stale id from a different puzzle", "discard",
     {"day": None, "id": "CVE-1999-0001", "guesses": [1.1, 2.2],
      "finished": True, "won": False}),
    ("corrupt guesses", "discard",
     {"day": None, "id": None, "guesses": ["x", None], "finished": False, "won": False}),
    ("out-of-range guesses", "discard",
     {"day": None, "id": None, "guesses": [99.0], "finished": False, "won": False}),
    ("too many guesses", "discard",
     {"day": None, "id": None, "guesses": [1, 2, 3, 4, 5, 6, 7], "finished": True,
      "won": False}),
]

LEGACY_STATS = [
    ("v1 stats, no lastId", {"played": 3, "wins": 2, "streak": 2, "max": 2,
                             "dist": [0, 1, 1, 0, 0, 0], "lastDay": 1}),
    ("stats with missing dist", {"played": 1, "wins": 1, "streak": 1, "max": 1,
                                 "lastDay": 1}),
    ("stats with short dist", {"played": 1, "wins": 1, "streak": 1, "max": 1,
                               "dist": [1], "lastDay": 1}),
]


def built_daily() -> dict:
    """Pull the daily puzzle straight out of the built page."""
    text = BUILT.read_text()
    m = re.search(r"const DAILY = (\{.*?\});", text, re.S)
    if not m:
        sys.exit("could not find DAILY in index.html")
    raw = (m.group(1).replace("\\u003c", "<").replace("\\u003e", ">")
           .replace("\\u0026", "&"))
    return json.loads(raw)


def static_checks(daily: dict) -> None:
    """Minimum viable gate when a browser isn't available."""
    text = BUILT.read_text()
    required = [
        ("state is keyed on the puzzle id", "DAILY.puzzle.id"),
        ("stats survive a missing dist", "s.dist"),
        ("saved guesses are validated", "Number.isFinite"),
    ]
    missing = [name for name, needle in required if needle not in text]
    if missing:
        sys.exit("FAIL: built page is missing compatibility guards: " + ", ".join(missing))
    print("OK (static): compatibility guards present in the built page")


def browser_checks(daily: dict) -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False

    number = daily["number"]
    real_id = daily["puzzle"]["id"]
    url = BUILT.resolve().as_uri()
    failures = []

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Exception:
            return False
        page = browser.new_page()

        for label, expect, template in LEGACY_STATES:
            state = dict(template)
            if state.get("day") is None:
                state["day"] = number
            if "id" in state and state["id"] is None:
                state["id"] = real_id
            page.goto(url)
            page.evaluate(
                "s => { localStorage.clear();"
                "localStorage.setItem('cvssdle.state.v1', JSON.stringify(s)); }",
                state,
            )
            page.reload()
            res = page.evaluate(
                "() => ({"
                " rows: document.querySelectorAll('.row:not(.empty)').length,"
                " playable: !document.getElementById('play-area').hidden,"
                " finished: !document.getElementById('result').hidden })"
            )
            if expect == "resume":
                expected = len(state["guesses"])
                if res["rows"] != expected:
                    failures.append(
                        f"{label}: expected {expected} rows restored, got {res['rows']}")
            else:
                if res["rows"] != 0:
                    failures.append(
                        f"{label}: should have been discarded but restored "
                        f"{res['rows']} rows")
                if not res["playable"]:
                    failures.append(f"{label}: discarded save left the board unplayable")
            # A board is either in play or finished, never both and never neither.
            if res["finished"] == res["playable"]:
                failures.append(f"{label}: board is both finished and playable")

        for label, stats in LEGACY_STATS:
            page.goto(url)
            page.evaluate(
                "s => { localStorage.clear();"
                "localStorage.setItem('cvssdle.stats.v1', JSON.stringify(s)); }",
                stats,
            )
            page.reload()
            res = page.evaluate(
                "() => { try {"
                " document.getElementById('btn-stats').click();"
                " const t = document.getElementById('dlg-stats').innerText;"
                " document.getElementById('dlg-stats').close();"
                " return { ok: true, text: t }; }"
                " catch (e) { return { ok: false, err: String(e) }; } }"
            )
            if not res["ok"]:
                failures.append(f"{label}: stats panel threw {res['err']}")

        browser.close()

    if failures:
        for f in failures:
            print("FAIL:", f)
        sys.exit(f"{len(failures)} compatibility failures")

    print(f"OK: {len(LEGACY_STATES)} saved-game shapes and "
          f"{len(LEGACY_STATS)} stats shapes all load correctly")
    return True


def main() -> None:
    if not BUILT.exists():
        sys.exit("index.html not built yet - run build_site.py first")
    daily = built_daily()
    if not browser_checks(daily):
        static_checks(daily)


if __name__ == "__main__":
    main()
