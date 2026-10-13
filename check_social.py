#!/usr/bin/env python3
"""CI gate: partial credit and challenge links.

Two things worth protecting here.

A near miss - out of guesses but within half a point - must be reported as its
own outcome and must never count as a win. Win rate and streaks are the numbers
people compare, so quietly inflating them would make the whole record
meaningless.

A challenge link encodes a result in the URL hash. It must survive being opened
cold or clicked while the site is already open (a same-document navigation,
which does not reload the page and so needs an explicit hashchange handler), it
must reject anything malformed without throwing, and it must never carry the
answer.
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

        # --- a near miss is its own outcome, and is not a win -------------
        page.goto(url)
        near = page.evaluate(
            """() => {
              const d = document.getElementById('dlg-help');
              if (d && d.open) d.close();
              localStorage.clear(); startDaily();
              const a = DAILY.puzzle.score;
              const i = document.getElementById('guess');
              const g = document.getElementById('btn-guess');
              const close = Math.max(0.1, Math.round((a - 0.3) * 10) / 10);
              [0.1, 0.2, 0.3, 0.4, 0.5, close].forEach(v => {
                i.value = v.toFixed(1); g.click();
              });
              const s = JSON.parse(localStorage.getItem('cvssdle.stats.v1'));
              return { heading: document.querySelector('#result h2').textContent,
                       wins: s.wins, near: s.near, streak: s.streak,
                       winRateUnaffected: s.wins === 0 };
            }"""
        )
        if "close" not in near["heading"].lower():
            failures.append(f"near miss headed {near['heading']!r}, expected a near-miss verdict")
        if not near["winRateUnaffected"]:
            failures.append("a near miss counted as a win")
        if near["near"] != 1:
            failures.append(f"near-miss counter is {near['near']}, expected 1")
        if near["streak"] != 0:
            failures.append("a near miss kept the streak alive; it is still a loss")

        # --- a far miss stays an ordinary loss ---------------------------
        page.goto(url)
        far = page.evaluate(
            """() => {
              localStorage.clear(); startDaily();
              const i = document.getElementById('guess');
              const g = document.getElementById('btn-guess');
              [0.1,0.2,0.3,0.4,0.5,0.6].forEach(v => { i.value = v.toFixed(1); g.click(); });
              const s = JSON.parse(localStorage.getItem('cvssdle.stats.v1'));
              return { heading: document.querySelector('#result h2').textContent, near: s.near };
            }"""
        )
        if far["near"] != 0:
            failures.append("a far miss was counted as a near miss")
        if "close" in far["heading"].lower():
            failures.append("a far miss was given the near-miss verdict")

        # --- the challenge link must not carry the answer ----------------
        page.goto(url)
        link = page.evaluate(
            """() => {
              localStorage.clear(); startDaily();
              const i = document.getElementById('guess');
              const g = document.getElementById('btn-guess');
              i.value = '5.0'; g.click();
              i.value = DAILY.puzzle.score.toFixed(1); g.click();
              return { frag: encodeChallenge(), url: challengeUrl(),
                       answer: String(DAILY.puzzle.score),
                       vector: DAILY.puzzle.vector, id: DAILY.puzzle.id };
            }"""
        )
        for field in ("answer", "vector", "id"):
            if link[field] and link[field] in link["url"]:
                failures.append(f"challenge URL leaks the {field}")

        # --- opened cold, and clicked while already open -----------------
        for label, nav in (("cold open", "goto"), ("same-document", "hash")):
            if nav == "goto":
                page.goto(url + "#" + link["frag"])
            else:
                page.goto(url)
                page.evaluate("f => { location.hash = f; }", link["frag"])
                page.wait_for_timeout(250)
            res = page.evaluate(
                """() => ({ shown: !document.getElementById('challenge').hidden,
                            cleared: location.hash === '',
                            playable: !document.getElementById('play-area').hidden })"""
            )
            if not res["shown"]:
                failures.append(f"{label}: challenge banner did not appear")
            if not res["cleared"]:
                failures.append(f"{label}: hash was not cleared after being read")

        # --- malformed and stale links are ignored, not rendered ---------
        # Build the cases from the page's own puzzle number rather than
        # hardcoding it: a fixed number silently stops testing anything the
        # day it goes stale.
        today_n = page.evaluate("() => DAILY.number")
        cases = [
            (f"c{today_n + 500}.3", "a puzzle number that is not today's"),
            (f"c{today_n}.9", "an outcome above the guess limit"),
            (f"c{today_n}.0", "a zero guess count"),
            (f"c{today_n}.z", "an unknown outcome letter"),
            (f"c{today_n}.1.1", "a malformed fragment"),
            ("cXYZ", "a non-numeric puzzle"),
            ("<img src=x onerror=alert(1)>", "an injection attempt"),
            ("", "an empty hash"),
        ]
        for frag, why in cases:
            page.goto(url)
            page.evaluate("f => { location.hash = f; }", frag)
            page.wait_for_timeout(150)
            res = page.evaluate(
                """() => ({ shown: !document.getElementById('challenge').hidden,
                            text: document.getElementById('challenge').textContent,
                            injected: document.querySelectorAll('img[src="x"]').length })"""
            )
            if res["injected"]:
                failures.append(f"hash {frag!r} injected markup")
            if res["shown"]:
                failures.append(f"hash {frag!r} rendered a challenge despite {why}")

        # A well-formed fragment for today must still work, so the rejections
        # above are not simply rejecting everything.
        page.goto(url)
        page.evaluate("n => { location.hash = 'c' + n + '.3'; }", today_n)
        page.wait_for_timeout(200)
        if page.evaluate("() => document.getElementById('challenge').hidden"):
            failures.append("a valid challenge fragment for today was rejected")

        if errors:
            failures.append(f"page errors: {errors[:3]}")
        browser.close()

    if failures:
        for f in failures:
            print("FAIL:", f)
        sys.exit(f"{len(failures)} social-feature failures")
    print("OK: near misses stay losses, challenge links round-trip and leak nothing")


if __name__ == "__main__":
    main()
