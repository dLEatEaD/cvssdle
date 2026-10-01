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
              const inp = document.getElementById('guess');
              const gb = document.getElementById('btn-guess');

              // A deliberate low guess must report "higher".
              inp.value = '0.5'; gb.click();
              out.lowFeedback = document.querySelector('.row:not(.empty) .feedback').textContent;
              out.hintsAfterOne = document.querySelectorAll('.hint.revealed').length;

              // A duplicate must be rejected without consuming a turn.
              inp.value = '0.5'; gb.click();
              out.rowsAfterDuplicate = document.querySelectorAll('.row:not(.empty)').length;

              // Out of range must also be rejected.
              inp.value = '99'; gb.click();
              out.rowsAfterOutOfRange = document.querySelectorAll('.row:not(.empty)').length;

              // The correct answer must win.
              inp.value = DAILY.puzzle.score.toFixed(1); gb.click();
              out.finished = !document.getElementById('result').hidden;
              out.heading = document.querySelector('#result h2').textContent;
              out.quip = (document.querySelector('.quip') || {}).textContent || '';
              out.allHints = document.querySelectorAll('.hint.revealed').length;
              out.link = document.getElementById('answer-link').href;

              // Practice must reset the board.
              startPractice();
              out.practiceRows = document.querySelectorAll('.row:not(.empty)').length;
              out.practiceHints = document.querySelectorAll('.hint.revealed').length;
              out.practiceInput = document.getElementById('guess').value;
              return out;
            }"""
        )

        checks = [
            ("low guess reports higher", "HIGHER" in probe["lowFeedback"].upper()),
            ("one hint after one guess", probe["hintsAfterOne"] == 1),
            ("duplicate guess rejected", probe["rowsAfterDuplicate"] == 1),
            ("out-of-range guess rejected", probe["rowsAfterOutOfRange"] == 1),
            ("correct answer finishes the round", probe["finished"]),
            ("a verdict heading is shown", bool(probe["heading"].strip())),
            ("a quip is shown", bool(probe["quip"].strip())),
            ("all 8 metrics revealed at the end", probe["allHints"] == 8),
            ("answer links to NVD", probe["link"].startswith("https://nvd.nist.gov/")),
            ("practice clears the rows", probe["practiceRows"] == 0),
            ("practice clears the hints", probe["practiceHints"] == 0),
            ("practice clears the input", probe["practiceInput"] == ""),
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
