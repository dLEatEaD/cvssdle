#!/usr/bin/env python3
"""CI gate: streaks must survive the weekend.

This is played at work, Monday to Friday. Measuring streak gaps in calendar
days means Friday to Monday is a three-day gap, so every streak resets every
Monday and nobody can exceed five. Gaps are therefore measured in missed
*weekdays*.

This drives the shipped helpers against real dates rather than restating the
rule, so a regression in dateForDay/missedWeekdays is caught rather than
mirrored.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
BUILT = HERE / "index.html"
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def missed_weekdays(a: date, b: date) -> int:
    """Weekdays strictly between a and b."""
    n, d = 0, a + timedelta(days=1)
    while d < b:
        if d.weekday() < 5:
            n += 1
        d += timedelta(days=1)
    return n


def main() -> None:
    if not BUILT.exists():
        sys.exit("index.html not built yet - run build_site.py first")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP: playwright not installed")
        return

    url = BUILT.resolve().as_uri()
    failures = []

    # Anchor on a fixed Monday rather than the real today. Run on a Thursday,
    # no backward offset spans a weekend, so calendar-day and weekday gaps
    # agree and the test silently loses all its discriminating power. Pinning
    # the anchor makes the Friday-to-Monday case reachable every day.
    ANCHOR = date(2026, 10, 5)          # a Monday
    assert ANCHOR.weekday() == 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url)

        for offset in range(-9, 0):
            prev = ANCHOR + timedelta(days=offset)
            want = missed_weekdays(prev, ANCHOR)
            res = page.evaluate(
                """([offset, anchorIso]) => {
                  const d = document.getElementById('dlg-help');
                  if (d && d.open) d.close();
                  localStorage.clear();
                  // Pin the anchor so the weekday maths is deterministic.
                  DAILY.date = anchorIso;
                  const lastDay = DAILY.number + offset;
                  localStorage.setItem('cvssdle.stats.v1', JSON.stringify({
                    played: 9, wins: 9, streak: 9, max: 9,
                    dist: [0,0,9,0,0,0], lastDay, lastId: 'CVE-OLD',
                    history: [], freezeUsedOn: null }));
                  startDaily();
                  const i = document.getElementById('guess');
                  const g = document.getElementById('btn-guess');
                  i.value = DAILY.puzzle.score.toFixed(1); g.click();
                  const s = JSON.parse(localStorage.getItem('cvssdle.stats.v1'));
                  return { missed: missedWeekdays(lastDay, DAILY.number),
                           streak: s.streak, froze: s.freezeUsedOn !== null };
                }""",
                [offset, ANCHOR.isoformat()],
            )
            label = (f"{DAYS[prev.weekday()]} {prev} -> "
                     f"{DAYS[ANCHOR.weekday()]} {ANCHOR}")
            if res["missed"] != want:
                failures.append(f"{label}: missed {res['missed']}, expected {want}")
                continue
            # 0 missed weekdays continues; exactly 1 is bridged by the freeze;
            # more than that resets.
            want_streak = 10 if want <= 1 else 1
            if res["streak"] != want_streak:
                failures.append(
                    f"{label}: streak {res['streak']}, expected {want_streak}")
            if res["froze"] != (want == 1):
                failures.append(
                    f"{label}: freeze used={res['froze']}, expected {want == 1}")

        # The decisive case: Friday to Monday must continue a streak, because
        # it is the gap every player hits every single week.
        fri_mon = page.evaluate(
            """([anchorIso]) => {
              localStorage.clear();
              DAILY.date = anchorIso;
              const lastDay = DAILY.number - 3;       // the preceding Friday
              localStorage.setItem('cvssdle.stats.v1', JSON.stringify({
                played: 9, wins: 9, streak: 9, max: 9,
                dist: [0,0,9,0,0,0], lastDay, lastId: 'CVE-OLD',
                history: [], freezeUsedOn: null }));
              startDaily();
              const i = document.getElementById('guess');
              const g = document.getElementById('btn-guess');
              i.value = DAILY.puzzle.score.toFixed(1); g.click();
              const s = JSON.parse(localStorage.getItem('cvssdle.stats.v1'));
              return { streak: s.streak, froze: s.freezeUsedOn !== null };
            }""",
            [ANCHOR.isoformat()],
        )
        if fri_mon["streak"] != 10:
            failures.append(
                f"Friday to Monday reset the streak to {fri_mon['streak']} "
                "- weekends must not break a streak")
        if fri_mon["froze"]:
            failures.append(
                "Friday to Monday consumed a streak freeze - a weekend is not "
                "a missed day")

        # A full working month must accumulate rather than reset every Monday.
        streak, last = 0, None
        for i in range(21):
            d = ANCHOR + timedelta(days=i)
            if d.weekday() >= 5:
                continue
            streak = streak + 1 if last is None or missed_weekdays(last, d) == 0 else 1
            last = d
        if streak < 10:
            failures.append(f"three work weeks only reached a streak of {streak}")

        if errors:
            failures.append(f"page errors: {errors[:3]}")
        browser.close()

    if failures:
        for f in failures:
            print("FAIL:", f)
        sys.exit(f"{len(failures)} weekend-streak failures")
    print("OK: streaks survive weekends; Friday-to-Monday continues, "
          "9 gap cases and a 3-week run all correct")


if __name__ == "__main__":
    main()
