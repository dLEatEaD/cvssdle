#!/usr/bin/env python3
"""CI gate: one mode per puzzle, and honest per-mode stats.

The two modes share one answer, and finishing either one puts the whole answer
on screen - score mode reveals a metric per miss and prints the full vector at
the end, vector mode prints the derived score. So an unguarded mode switch is
not a mode switch, it is a lookup:

  - play score mode, read the vector off the result card, switch, solve 1/4
  - lose vector mode on purpose, read the score, switch, type it for 1/6
  - abandon score mode at five guesses so recordStats never fires, switch,
    and the laundered vector win records as genuine

The fix is a per-day lock committed on the first move. This gate holds it down,
and holds down the stats bug that made the third route profitable: vector wins
used to index the six-slot score histogram at guesses.length - 1, which is -1.

Checks:
  - a first score guess locks out vector mode, and vice versa
  - the lock survives a reload and is scoped to the day and the CVE
  - practice mode stays switchable
  - only one mode can record stats for a given day
  - a vector win lands in its own distribution, never at a negative index
  - the help text documents both modes and the lock
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
BUILT = HERE / "index.html"


def check_help(text: str) -> list[str]:
    """The in-game help is the only explanation most players will ever read."""
    bad = []
    m = re.search(r"<h2>How to play</h2>(.*?)</dialog>", text, re.S)
    if not m:
        return ["could not find the How to play dialog"]
    help_text = m.group(1).lower()
    for phrase, why in (
        ("guess the score", "score mode is not named in the help"),
        ("build the vector", "vector mode is not named in the help"),
        ("locks the mode", "the help does not explain the per-day mode lock"),
        ("practice", "the help does not mention the practice exemption"),
    ):
        if phrase not in help_text:
            bad.append(why)
    # The old copy promised one game in six tries. Saying so now is just wrong.
    if "guess its <b>cvss v3.1 base score</b> in 6 tries" in help_text:
        bad.append("the help still describes score mode as the only mode")
    return bad


def main() -> None:
    if not BUILT.exists():
        sys.exit("index.html not built yet - run build_site.py first")

    text = BUILT.read_text()
    failures = check_help(text)

    # A vector win must never index the score histogram. This is a source-level
    # check because the bug was invisible at runtime: JS happily accepts
    # arr[-1] = 1 as a named property and drops it from every later read.
    if re.search(r"s\.dist\[\s*guesses\.length\s*-\s*1\s*\]", text):
        failures.append(
            "recordStats still indexes s.dist by guesses.length, which is -1 "
            "in vector mode")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        if failures:
            for f in failures:
                print("FAIL:", f)
            sys.exit(f"{len(failures)} mode failures")
        print("SKIP: playwright not installed (static checks passed)")
        return

    url = BUILT.resolve().as_uri()

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url)
        page.evaluate(
            "() => { const h = document.getElementById('dlg-help');"
            " if (h && h.open) h.close(); }"
        )

        # --- a score guess locks out vector mode ----------------------
        lock = page.evaluate(
            """() => {
              localStorage.clear(); setVectorMode(false);
              startDaily();
              const before = document.getElementById('mode-vector').disabled;
              const i = document.getElementById('guess');
              i.value = '5.0';
              document.getElementById('btn-guess').click();
              const after = document.getElementById('mode-vector').disabled;
              // Clicking it anyway must not switch, even if the UI were bypassed.
              switchMode(true);
              return { before, after, nowVector: vectorMode(),
                       lock: modeLock(),
                       note: document.getElementById('mode-note').textContent };
            }"""
        )
        if lock["before"]:
            failures.append("vector mode was disabled before any move was made")
        if not lock["after"]:
            failures.append("a score guess did not disable the vector button")
        if lock["nowVector"]:
            failures.append(
                "switchMode let a player move to vector mode after guessing in "
                "score mode - this is the answer-laundering route")
        if lock["lock"] != "score":
            failures.append(f"expected a score lock, got {lock['lock']!r}")
        if "locked" not in lock["note"].lower():
            failures.append("the mode note does not tell the player they are locked")

        # --- and the reverse direction --------------------------------
        rev = page.evaluate(
            """() => {
              localStorage.clear(); setVectorMode(true);
              startDaily();
              // One deliberately wrong attempt is enough to commit.
              const ans = parseVector();
              for (const k of HINT_ORDER) {
                const opts = Object.keys(METRIC_NAMES[k][1]);
                vectorPick[k] = opts.find(o => o !== ans[k]) || opts[0];
              }
              renderVectorPreview();
              document.getElementById('btn-submit-vector').click();
              const disabled = document.getElementById('mode-score').disabled;
              switchMode(false);
              return { disabled, nowVector: vectorMode(), lock: modeLock() };
            }"""
        )
        if not rev["disabled"]:
            failures.append("a vector attempt did not disable the score button")
        if not rev["nowVector"] or rev["lock"] != "vector":
            failures.append(
                "a player could drop back to score mode after a vector attempt")

        # --- the lock survives a reload -------------------------------
        page.reload()
        after_reload = page.evaluate(
            """() => {
              const h = document.getElementById('dlg-help');
              if (h && h.open) h.close();
              return { lock: modeLock(), vector: vectorMode(),
                       scoreDisabled: document.getElementById('mode-score').disabled };
            }"""
        )
        if after_reload["lock"] != "vector" or not after_reload["vector"]:
            failures.append("the mode lock did not survive a reload")
        if not after_reload["scoreDisabled"]:
            failures.append("the lock survived but the button was re-enabled")

        # --- the lock is scoped to the day and the CVE ----------------
        scoped = page.evaluate(
            """() => {
              // A lock written for another day, or for a different CVE on the
              // same day number, must not bind today's puzzle. Pool refreshes
              // remap day numbers to different CVEs.
              localStorage.clear();
              save(KEY_LOCK, { day: DAILY.number - 1, id: DAILY.puzzle.id,
                               mode: 'vector' });
              const otherDay = modeLock();
              save(KEY_LOCK, { day: DAILY.number, id: 'CVE-0000-0000',
                               mode: 'vector' });
              const otherId = modeLock();
              return { otherDay, otherId };
            }"""
        )
        if scoped["otherDay"] is not None:
            failures.append("a lock from another day still bound today's puzzle")
        if scoped["otherId"] is not None:
            failures.append("a lock for a different CVE still bound today's puzzle")

        # --- practice stays switchable --------------------------------
        prac = page.evaluate(
            """() => {
              localStorage.clear(); setVectorMode(false);
              startDaily();
              const i = document.getElementById('guess');
              i.value = '5.0';
              document.getElementById('btn-guess').click();   // locks the day
              startPractice();
              const before = vectorMode();
              switchMode(true);
              return { before, after: vectorMode(), practice: practiceMode };
            }"""
        )
        if prac["before"]:
            failures.append("practice started in the wrong mode")
        if not prac["after"] or not prac["practice"]:
            failures.append(
                "practice mode is not switchable - it draws a different puzzle "
                "and records nothing, so there is nothing to launder")

        # --- only one mode can record a day ---------------------------
        once = page.evaluate(
            """() => {
              localStorage.clear(); setVectorMode(false);
              startDaily();
              const i = document.getElementById('guess');
              const b = document.getElementById('btn-guess');
              // Five misses: the old bug was abandoning here, since recordStats
              // never fired and the next mode's win counted as the day's result.
              for (let k = 0; k < 5; k++) {
                let g = (k + 1) * 1.1;
                if (g === DAILY.puzzle.score) g = 0.2;
                i.value = g.toFixed(1); b.click();
              }
              const played = normaliseStats(load(KEY_STATS, blankStats())).played;
              switchMode(true);
              return { played, stillScore: !vectorMode(),
                       vectorBlocked: document.getElementById('mode-vector').disabled };
            }"""
        )
        if once["played"] != 0:
            failures.append("an unfinished score game recorded a result")
        if not once["stillScore"] or not once["vectorBlocked"]:
            failures.append(
                "abandoning score mode at five guesses still allowed a switch to "
                "vector - the laundered win would record as the day's result")

        # --- vector wins land in their own distribution ---------------
        dist = page.evaluate(
            """() => {
              localStorage.clear(); setVectorMode(true);
              startDaily();
              Object.assign(vectorPick, parseVector());
              renderMetricPicker(); renderVectorPreview();
              document.getElementById('btn-submit-vector').click();
              const s = normaliseStats(load(KEY_STATS, blankStats()));
              const raw = load(KEY_STATS, {});
              return { dist: s.dist, vdist: s.vdist, wins: s.wins,
                       played: s.played,
                       negative: Object.prototype.hasOwnProperty.call(raw.dist || {}, '-1'),
                       history: s.history[s.history.length - 1] };
            }"""
        )
        if dist["negative"]:
            failures.append("a vector win wrote s.dist[-1]")
        if dist["vdist"] != [1, 0, 0, 0]:
            failures.append(
                f"a one-attempt vector win should sit in vdist[0], got {dist['vdist']}")
        if sum(dist["dist"]) != 0:
            failures.append("a vector win leaked into the score distribution")
        if dist["wins"] != 1 or dist["played"] != 1:
            failures.append("a vector win was not counted as a win")
        h = dist["history"] or {}
        if h.get("n") != 1:
            failures.append(f"vector history recorded n={h.get('n')}, expected 1")
        if not isinstance(h.get("m"), (int, float)):
            failures.append("vector history recorded no accuracy value")
        if h.get("v") is not True:
            failures.append("vector history is not flagged as a vector game")

        # --- the result card uses the vector quip pools ---------------
        quips = page.evaluate(
            """() => ({
              pools: typeof VECTOR_VERDICTS === 'object'
                && Object.keys(VECTOR_VERDICTS).length,
              loss: Array.isArray(VECTOR_LOSS_QUIPS) && VECTOR_LOSS_QUIPS.length,
              quip: document.querySelector('#result .quip').textContent,
            })"""
        )
        if quips["pools"] != 4:
            failures.append("VECTOR_VERDICTS must cover all four attempt counts")
        if not quips["loss"] or quips["loss"] < 30:
            failures.append("VECTOR_LOSS_QUIPS is missing or too small")
        if "That is the rubric, not a lucky number" in quips["quip"]:
            failures.append("the result card still uses the hardcoded vector line")

        if errors:
            failures.append(f"page errors: {errors[:3]}")
        browser.close()

    if failures:
        for f in failures:
            print("FAIL:", f)
        sys.exit(f"{len(failures)} mode failures")
    print("OK: one mode per puzzle, the lock survives reloads, practice stays "
          "free, and each mode keeps its own honest distribution")


if __name__ == "__main__":
    main()
