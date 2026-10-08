#!/usr/bin/env python3
"""CI gate: play the built page and assert the core loop still works.

verify_build.py checks what is in the file. This checks that the file is a
working game: that a round can be played, feedback is correct, hints reveal on
schedule, practice resets cleanly, and nothing throws.

Skips with a clear message if Playwright is unavailable, so local runs without
a browser do not fail for the wrong reason.
"""

import sys
from pathlib import Path

HERE = Path(__file__).parent
BUILT = HERE / "index.html"


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

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url)

        probe = page.evaluate(
            """() => {
              const d = document.getElementById('dlg-help');
              if (d && d.open) d.close();
              localStorage.clear();
              startDaily();
              const out = { answer: DAILY.puzzle.score, practice: PRACTICE.length };
              const sb = document.getElementById('btn-submit-vector');
              const pick = (k, code) => {
                const row = [...document.querySelectorAll('.metric-row')]
                              [HINT_ORDER.indexOf(k)];
                const label = METRIC_NAMES[k][1][code];
                [...row.querySelectorAll('.metric-opt')]
                  .find(o => o.textContent === label).click();
              };

              // Nothing is pre-selected, and an incomplete vector is refused.
              out.freshPicked = HINT_ORDER.filter(k => vectorPick[k]).length;
              out.freshDisabled = sb.disabled;
              sb.click();
              out.rowsAfterEmptySubmit = document.querySelectorAll('.vtry').length;

              // A deliberately wrong vector: right everywhere but Attack Vector.
              const ans = parseVector();
              for (const k of HINT_ORDER) pick(k, ans[k]);
              const wrongAV = Object.keys(METRIC_NAMES.AV[1])
                                .find(c => c !== ans.AV);
              pick('AV', wrongAV);
              out.readout = document.getElementById('vector-score').textContent;
              sb.click();
              out.rowsAfterOne = document.querySelectorAll('.vtry').length;
              out.countText = document.querySelector('.vtry .vtry-count').textContent;
              out.hintsDuringPlay = document.querySelectorAll('.hint.revealed').length;
              out.markedDuringPlay = [...document.querySelectorAll('.vcell')]
                .filter(c => /hit|miss/.test(c.className)).length;
              out.finishedEarly = !document.getElementById('result').hidden;

              // The correct vector must win.
              pick('AV', ans.AV);
              sb.click();
              out.finished = !document.getElementById('result').hidden;
              out.heading = document.querySelector('#result h2').textContent;
              out.quip = (document.querySelector('.quip') || {}).textContent || '';
              out.allHints = document.querySelectorAll('.hint.revealed').length;
              out.link = document.getElementById('answer-link').href;
              out.markedAfterEnd = [...document.querySelectorAll('.vcell')]
                .filter(c => /hit|miss/.test(c.className)).length;

              // Practice must reset the board.
              startPractice();
              out.practiceTries = document.querySelectorAll('.vtry').length;
              out.practiceHints = document.querySelectorAll('.hint.revealed').length;
              out.practicePicked = HINT_ORDER.filter(k => vectorPick[k]).length;
              return out;
            }"""
        )

        checks = [
            ("nothing is pre-selected", probe["freshPicked"] == 0),
            ("submit is disabled until all eight are picked", probe["freshDisabled"]),
            ("an empty vector cannot be submitted",
             probe["rowsAfterEmptySubmit"] == 0),
            ("the live readout is a band, not a score",
             not any(c.isdigit() for c in probe["readout"])),
            ("a wrong vector records an attempt", probe["rowsAfterOne"] == 1),
            ("the attempt reports a count", "7" in probe["countText"]),
            ("a 7-of-8 attempt does not end the game", not probe["finishedEarly"]),
            ("metrics stay hidden during play", probe["hintsDuringPlay"] == 0),
            ("attempts are not marked up during play",
             probe["markedDuringPlay"] == 0),
            ("the correct vector finishes the round", probe["finished"]),
            ("a verdict heading is shown", bool(probe["heading"].strip())),
            ("a quip is shown", bool(probe["quip"].strip())),
            ("all 8 metrics revealed at the end", probe["allHints"] == 8),
            ("attempts are marked up once the game ends",
             probe["markedAfterEnd"] > 0),
            ("answer links to NVD", probe["link"].startswith("https://nvd.nist.gov/")),
            ("practice clears the attempts", probe["practiceTries"] == 0),
            ("practice clears the hints", probe["practiceHints"] == 0),
            ("practice clears the selection", probe["practicePicked"] == 0),
            ("practice pool is non-empty", probe["practice"] > 0),
        ]
        failures = [name for name, ok in checks if not ok]
        if errors:
            failures.append(f"uncaught page errors: {errors[:3]}")
        browser.close()

    if failures:
        for f in failures:
            print("FAIL:", f)
        sys.exit(f"{len(failures)} playability failures")
    print(f"OK: {len(checks)} playability checks passed")


if __name__ == "__main__":
    main()
