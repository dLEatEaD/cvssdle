#!/usr/bin/env python3
"""CI gate: one game, and honest stats.

Guessing the score outright has been retired - it was solvable by binary search
without knowing any CVSS - so building the vector is now the whole game. Two
things have to hold for that to be a clean change rather than a destructive one.

First, nobody loses a game they were in the middle of. A score board already in
progress for today is adopted and can be finished; the lock is keyed to today's
puzzle, so it lapses by itself at the next rollover and that player joins the
vector game tomorrow.

Second, a *finished* score board for today must also stay put. That player has
already seen the full answer vector printed on their result card, so dropping
them into today's vector game would hand them an eight-of-eight win for free -
the exact laundering route the mode lock was built to close.

Checks:
  - a fresh player gets the vector game, with no toggle and no switchMode
  - a score game in flight for today survives and can still be finished
  - a finished score game for today is not reopened as a free vector win
  - a score board for another puzzle is ignored
  - stats record under the right distribution and never a negative index
  - the help text describes one game and does not advertise a toggle
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
    if "build its cvss v3.1 vector" not in help_text:
        bad.append("the help does not say the game is building the vector")
    if "how many" not in help_text:
        bad.append("the help does not explain that feedback is a count")
    # The retired mode must not be advertised, or players will hunt for a
    # toggle that is not there.
    for stale in ("guess the score", "two ways to play", "toggle at the top",
                  "one mode per puzzle"):
        if stale in help_text:
            bad.append(f"the help still advertises the retired mode: {stale!r}")
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
            "in the vector game")
    if ".mode-toggle" in text or 'id="mode-vector"' in text:
        failures.append("the mode toggle is still in the built page")

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

        # --- a fresh player gets the vector game ----------------------
        fresh = page.evaluate(
            """() => {
              localStorage.clear(); startDaily();
              return { vector: vectorMode(),
                       vectorArea: !document.getElementById('vector-area').hidden,
                       scoreArea: !document.getElementById('play-area').hidden,
                       toggle: !!document.querySelector('.mode-toggle'),
                       switcher: typeof switchMode,
                       setter: typeof setVectorMode,
                       note: document.getElementById('mode-note').textContent };
            }"""
        )
        if not fresh["vector"] or not fresh["vectorArea"] or fresh["scoreArea"]:
            failures.append("a fresh player does not land in the vector game")
        if fresh["toggle"]:
            failures.append("the mode toggle is still rendered")
        if fresh["switcher"] != "undefined" or fresh["setter"] != "undefined":
            failures.append(
                "switchMode/setVectorMode still exist; score mode is retired")
        if "eight metrics" not in fresh["note"].lower():
            failures.append(f"the mode note is wrong: {fresh['note']!r}")

        # --- a score game in flight for today survives ----------------
        # Nobody loses a board they were part-way through. The adopted lock is
        # keyed to today's puzzle, so it lapses at the next rollover.
        inflight = page.evaluate(
            """() => {
              localStorage.clear();
              save(KEY_STATE, {
                day: DAILY.number, id: DAILY.puzzle.id, mode: 'score',
                guesses: [5.0, 7.0], vectorTries: [],
                finished: false, won: false,
              });
              startDaily();
              const rows = document.querySelectorAll('.row:not(.empty)').length;
              const before = { vector: vectorMode(), lock: modeLock(), rows,
                               playable: !document.getElementById('play-area').hidden,
                               note: document.getElementById('mode-note').textContent };
              // And it must be finishable.
              const i = document.getElementById('guess');
              i.value = DAILY.puzzle.score.toFixed(1);
              document.getElementById('btn-guess').click();
              const s = normaliseStats(load(KEY_STATS, blankStats()));
              return { before,
                       finished, won,
                       dist: s.dist, vdist: s.vdist, wins: s.wins };
            }"""
        )
        b = inflight["before"]
        if b["vector"] or b["lock"] != "score":
            failures.append(
                "a score game in flight for today was not adopted - that player "
                "loses the board they were part-way through")
        if b["rows"] != 2 or not b["playable"]:
            failures.append(
                f"the in-flight score board did not restore ({b['rows']} rows, "
                f"playable={b['playable']})")
        if "score game" not in b["note"].lower():
            failures.append(f"the in-flight note is unclear: {b['note']!r}")
        if not inflight["finished"] or not inflight["won"]:
            failures.append("the adopted score game could not be finished")
        # A score win belongs in the score histogram, not the vector one.
        if inflight["dist"] != [0, 0, 1, 0, 0, 0]:
            failures.append(
                f"a 3-guess score win should sit in dist[2], got {inflight['dist']}")
        if sum(inflight["vdist"]) != 0:
            failures.append("a score win leaked into the vector distribution")

        # --- a finished score game is not reopened --------------------
        # That player has seen the full answer vector on their result card.
        # Dropping them into today's vector game is a free 8/8.
        done = page.evaluate(
            """() => {
              localStorage.clear();
              save(KEY_STATE, {
                day: DAILY.number, id: DAILY.puzzle.id, mode: 'score',
                guesses: [5.0, DAILY.puzzle.score], vectorTries: [],
                finished: true, won: true,
              });
              startDaily();
              return { vector: vectorMode(), lock: modeLock(),
                       finished,
                       resultShown: !document.getElementById('result').hidden,
                       vectorPlayable: !document.getElementById('vector-area').hidden };
            }"""
        )
        if done["vector"] or done["lock"] != "score":
            failures.append(
                "a finished score game for today was reopened as the vector game - "
                "that player already saw the answer vector, so this is a free win")
        if not done["finished"] or not done["resultShown"]:
            failures.append("the finished score board did not show its result")
        if done["vectorPlayable"]:
            failures.append("the vector picker is playable over a finished board")

        # --- a score board for another puzzle is ignored --------------
        stale = page.evaluate(
            """() => {
              localStorage.clear();
              save(KEY_STATE, {
                day: DAILY.number - 2, id: 'CVE-1999-0001', mode: 'score',
                guesses: [1.1, 2.2], vectorTries: [],
                finished: false, won: false,
              });
              startDaily();
              return { vector: vectorMode(), lock: modeLock(),
                       rows: document.querySelectorAll('.row:not(.empty)').length,
                       vectorPlayable: !document.getElementById('vector-area').hidden };
            }"""
        )
        if not stale["vector"] or stale["lock"] is not None:
            failures.append(
                "a score board from another puzzle was adopted for today")
        if stale["rows"] != 0 or not stale["vectorPlayable"]:
            failures.append("a stale score board interfered with the vector game")

        # --- vector wins land in their own distribution ---------------
        dist = page.evaluate(
            """() => {
              localStorage.clear(); startDaily();
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
            })"""
        )
        if quips["pools"] != 4:
            failures.append("VECTOR_VERDICTS must cover all four attempt counts")
        if not quips["loss"] or quips["loss"] < 30:
            failures.append("VECTOR_LOSS_QUIPS is missing or too small")

        if errors:
            failures.append(f"page errors: {errors[:3]}")
        browser.close()

    if failures:
        for f in failures:
            print("FAIL:", f)
        sys.exit(f"{len(failures)} mode failures")
    print("OK: the vector game is the only game, boards in flight from the "
          "retired mode still finish, and each keeps its own honest distribution")


if __name__ == "__main__":
    main()
