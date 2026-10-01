#!/usr/bin/env python3
"""CI gate: vector mode.

Score mode is solvable without knowing any CVSS - a plain binary search wins
every time - so vector mode exists to make domain knowledge the only route.
That only holds if the mode genuinely never leaks the answer, and if switching
between modes cannot corrupt either board.

Checks the things that would quietly ruin it:
  - score mode stays the default, so nobody is opted in by surprise
  - no metric is pre-selected, and an incomplete vector cannot be submitted
  - feedback is a count, never a per-metric map
  - the metric hints stay locked, since in vector mode they are the answer
  - the derived score tracks the player's selection
  - a solved vector wins, four wrong attempts lose
  - the two modes keep separate saved boards
  - vector challenge fragments round-trip and reject nonsense
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

        # --- score mode is the default --------------------------------
        d = page.evaluate(
            """() => {
              const h = document.getElementById('dlg-help');
              if (h && h.open) h.close();
              localStorage.clear(); startDaily();
              return { vector: vectorMode(),
                       score: !document.getElementById('play-area').hidden,
                       vec: !document.getElementById('vector-area').hidden };
            }"""
        )
        if d["vector"] or not d["score"] or d["vec"]:
            failures.append("vector mode is not opt-in; score mode must be the default")

        # --- nothing is pre-selected ----------------------------------
        # An earlier build defaulted every metric to its worst value, which is
        # AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H - CVSS 9.8, and the most common
        # vector in the KEV catalog. Opening vector mode and pressing Submit
        # won outright on 36.5% of the pool. There is no safe default.
        blank = page.evaluate(
            """() => {
              localStorage.clear(); setVectorMode(true); startDaily();
              const btn = document.getElementById('btn-submit-vector');
              const picked = HINT_ORDER.filter(k => vectorPick[k]).length;
              // Try to submit anyway, as a bypass of the disabled button would.
              submitVector();
              return { picked,
                       disabled: btn.disabled,
                       label: btn.textContent,
                       preview: document.getElementById('vector-preview').textContent,
                       score: document.getElementById('vector-score').textContent,
                       tries: vectorTries.length,
                       finished, won };
            }"""
        )
        if blank["picked"] != 0:
            failures.append(
                f"{blank['picked']} metrics are pre-selected - a default vector "
                "hands the answer to every puzzle that happens to match it")
        if not blank["disabled"]:
            failures.append("the submit button is enabled with no metrics chosen")
        if blank["tries"] or blank["finished"] or blank["won"]:
            failures.append(
                "an untouched vector could be submitted - this is the 36.5% "
                "free-win bug")
        if "?" not in blank["preview"]:
            failures.append(f"the preview should mark unset metrics, got {blank['preview']!r}")
        if blank["score"] not in ("\u2014", "-"):
            failures.append(
                f"a partial vector showed a score of {blank['score']!r}; it has none")

        # --- the live readout is a band, never the exact score ---------
        # Of the 84 distinct scores a vector can take, exactly one - 9.8 - is
        # produced by a single vector out of all 2,592, and that vector is
        # 36.5% of the pool. An exact live readout therefore let anyone dial
        # the picker until it said 9.8 and submit the most likely answer in the
        # catalogue with no CVSS knowledge whatsoever.
        oracle = page.evaluate(
            """() => {
              localStorage.clear(); setVectorMode(true); startDaily();
              // The unique 9.8 vector.
              const nine8 = { AV:'N', AC:'L', PR:'N', UI:'N', S:'U',
                              C:'H', I:'H', A:'H' };
              for (const k of HINT_ORDER) vectorPick[k] = nine8[k];
              renderMetricPicker(); renderVectorPreview();
              return { readout: document.getElementById('vector-score').textContent,
                       derived: scoreVector(vectorPick).toFixed(1) };
            }"""
        )
        if oracle["derived"] != "9.8":
            failures.append(
                f"the calculator no longer scores the canonical vector 9.8: "
                f"{oracle['derived']}")
        if "9.8" in oracle["readout"] or "9." in oracle["readout"]:
            failures.append(
                f"the live readout shows the exact score ({oracle['readout']!r}) - "
                "9.8 pins a unique vector, so this hands over the single most "
                "common answer in the pool")
        if oracle["readout"] != "Critical":
            failures.append(
                f"expected a severity band in the live readout, got {oracle['readout']!r}")

        # --- the answer is revealed once a vector game ends ------------
        reveal = page.evaluate(
            """() => {
              localStorage.clear(); setVectorMode(true); startDaily();
              const masked = document.querySelectorAll('.hint.revealed').length;
              for (const k of HINT_ORDER) vectorPick[k] = parseVector()[k];
              renderMetricPicker(); renderVectorPreview();
              document.getElementById('btn-submit-vector').click();
              return { masked,
                       after: document.querySelectorAll('.hint.revealed').length,
                       label: document.getElementById('hints-label').textContent };
            }"""
        )
        if reveal["masked"] != 0:
            failures.append("metrics were revealed during a vector game")
        if reveal["after"] != 8:
            failures.append(
                f"only {reveal['after']}/8 metrics revealed after the vector game "
                "ended - the grid stays masked behind question marks")

        # Still refused when only seven of eight are chosen.
        partial = page.evaluate(
            """() => {
              localStorage.clear(); setVectorMode(true); startDaily();
              const ans = parseVector();
              for (const k of HINT_ORDER.slice(0, 7)) vectorPick[k] = ans[k];
              renderVectorPreview();
              submitVector();
              return { disabled: document.getElementById('btn-submit-vector').disabled,
                       tries: vectorTries.length };
            }"""
        )
        if not partial["disabled"] or partial["tries"]:
            failures.append("a seven-of-eight vector was accepted")

        # --- feedback is a count, never a per-metric map ---------------
        # Marking each metric right or wrong let a player lock the correct ones
        # and cycle the rest: that solves 100% of the pool in three attempts
        # with no CVSS knowledge, and it is how this mode was first beaten.
        # The player learns how many landed, never which.
        fbk = page.evaluate(
            """() => {
              localStorage.clear(); setVectorMode(true); startDaily();
              const ans = parseVector();
              // Get exactly seven of eight right - the state that used to give
              // the answer away completely.
              for (const k of HINT_ORDER) vectorPick[k] = ans[k];
              const opts = Object.keys(METRIC_NAMES.AV[1]);
              vectorPick.AV = opts.find(o => o !== ans.AV);
              renderMetricPicker(); renderVectorPreview();
              document.getElementById('btn-submit-vector').click();
              const row = document.querySelector('.vtry');
              const cells = [...row.querySelectorAll('.vcell')];
              return {
                hitCells: cells.filter(c => c.className.includes('hit')).length,
                missCells: cells.filter(c => c.className.includes('miss')).length,
                distinctClasses: [...new Set(cells.map(c => c.className.trim()))],
                rowText: row.textContent,
                grid: shareGrid(),
                finished,
              };
            }"""
        )
        if fbk["hitCells"] or fbk["missCells"]:
            failures.append(
                "attempt rows still mark individual metrics right or wrong - "
                "lock-the-greens solves the whole pool in three tries")
        if len(fbk["distinctClasses"]) != 1:
            failures.append(
                f"metric cells are styled differently from each other: "
                f"{fbk['distinctClasses']} - that is per-metric feedback")
        if "7" not in fbk["rowText"]:
            failures.append(f"the attempt row does not report the count: {fbk['rowText']!r}")
        if fbk["finished"]:
            failures.append("a seven-of-eight attempt should not end the game")
        # The share grid must convey the count only - a positional grid hands a
        # recipient exactly the feedback the game withholds.
        first = fbk["grid"].split("\n")[0]
        if first != "\U0001F7E9" * 7 + "\u2B1C":
            failures.append(
                f"the share grid leaks metric positions: {first!r}")
        # --- hints stay locked, and the score is derived --------------
        v = page.evaluate(
            """() => {
              localStorage.clear(); setVectorMode(true); startDaily();
              // Fill the vector so a score exists to compare against.
              const ans = parseVector();
              for (const k of HINT_ORDER) vectorPick[k] = ans[k];
              renderMetricPicker(); renderVectorPreview();
              const before = scoreVector(vectorPick).toFixed(1);
              const rows = [...document.querySelectorAll('.metric-row')];
              const opts = [...rows[0].querySelectorAll('.metric-opt')];
              // Pick an Attack Vector that differs from the answer's, so the
              // derived score is guaranteed to move.
              const codes = Object.keys(METRIC_NAMES.AV[1]);
              const idx = codes.findIndex(c => c !== ans.AV);
              opts[idx].click();
              return { revealed: document.querySelectorAll('.hint.revealed').length,
                       metrics: rows.length,
                       before, after: scoreVector(vectorPick).toFixed(1),
                       readout: document.getElementById('vector-score').textContent,
                       scoreAreaHidden: document.getElementById('play-area').hidden };
            }"""
        )
        if v["revealed"] != 0:
            failures.append(
                f"{v['revealed']} metrics revealed in vector mode - they are the answer")
        if v["metrics"] != 8:
            failures.append(f"expected 8 metric rows, found {v['metrics']}")
        if v["before"] == v["after"]:
            failures.append("the derived score did not change when a metric changed")
        # The derivation must track the selection, but the player only ever
        # sees the band it falls in.
        if any(ch.isdigit() for ch in v["readout"]):
            failures.append(
                f"the live readout leaked a number: {v['readout']!r}")
        if not v["scoreAreaHidden"]:
            failures.append("score-mode input is still visible in vector mode")

        # --- a correct vector wins ------------------------------------
        win = page.evaluate(
            """() => {
              localStorage.clear(); startDaily();
              document.getElementById('mode-vector').click();
              Object.assign(vectorPick, parseVector());
              renderMetricPicker(); renderVectorPreview();
              document.getElementById('btn-submit-vector').click();
              return { finished: !document.getElementById('result').hidden,
                       heading: document.querySelector('#result h2').textContent,
                       frag: encodeChallenge(),
                       grid: shareGrid() };
            }"""
        )
        # A one-attempt win earns its own heading ("nailed"), so match the
        # outcome rather than one specific word.
        if not win["finished"] or win["heading"].lower().startswith("vector unsolved"):
            failures.append(f"a correct vector did not win: {win['heading']!r}")
        if win["grid"].count("\U0001F7E9") != 8:
            failures.append("a winning vector grid should be eight greens")
        if not win["frag"].endswith(".v1"):
            failures.append(f"vector win fragment is {win['frag']!r}, expected .v1")

        # --- four wrong attempts lose ---------------------------------
        lose = page.evaluate(
            """() => {
              localStorage.clear(); startDaily();
              document.getElementById('mode-vector').click();
              const ans = parseVector();
              for (let i = 0; i < 4; i++) {
                for (const k of HINT_ORDER) {
                  const opts = Object.keys(METRIC_NAMES[k][1]);
                  vectorPick[k] = opts.find(o => o !== ans[k]) || opts[0];
                }
                renderVectorPreview();
                document.getElementById('btn-submit-vector').click();
              }
              return { finished: !document.getElementById('result').hidden,
                       heading: document.querySelector('#result h2').textContent,
                       frag: encodeChallenge(),
                       rows: document.querySelectorAll('.vtry').length };
            }"""
        )
        if not lose["finished"]:
            failures.append("four wrong vectors did not end the game")
        if lose["rows"] != 4:
            failures.append(f"expected 4 attempt rows, found {lose['rows']}")
        if not lose["frag"].endswith(".vx"):
            failures.append(f"vector loss fragment is {lose['frag']!r}, expected .vx")

        # --- the two modes keep separate boards -----------------------
        # Switching mid-puzzle is now refused outright (see check_modes.py), so
        # the invariant that still matters is in restore(): a board saved in one
        # mode must never be loaded as the other. That is what protects a player
        # whose lock is absent - an upgrade from a pre-lock build, or a cleared
        # lock - from being shown a finished result they never played.
        sep = page.evaluate(
            """() => {
              localStorage.clear();
              document.getElementById('mode-score').click();
              startDaily();
              const i = document.getElementById('guess');
              const g = document.getElementById('btn-guess');
              i.value = '5.0'; g.click();
              i.value = DAILY.puzzle.score.toFixed(1); g.click();   // finish it
              const scoreRows = document.querySelectorAll('.row:not(.empty)').length;
              const scoreFinished = !document.getElementById('result').hidden;
              const saved = load(KEY_STATE, null);

              // Drop the lock and flip the preference, simulating a player who
              // arrives in vector mode with a score board already on disk.
              localStorage.removeItem(KEY_LOCK);
              setVectorMode(true);
              startDaily();
              const vec = {
                restored: restore(),
                rows: document.querySelectorAll('.vtry').length,
                finished: !document.getElementById('result').hidden,
                playable: !document.getElementById('vector-area').hidden,
              };

              // The score board itself must still be on disk, untouched.
              const after = load(KEY_STATE, null);
              return { scoreRows, scoreFinished, vec,
                       savedMode: saved && saved.mode,
                       keptMode: after && after.mode };
            }"""
        )
        if sep["scoreRows"] != 2 or not sep["scoreFinished"]:
            failures.append("the score game did not complete as expected")
        if sep["savedMode"] != "score":
            failures.append("the finished score board was not saved as a score board")
        if sep["vec"]["restored"]:
            failures.append("a score board was restored as a vector board")
        if sep["vec"]["rows"] != 0:
            failures.append("switching to vector mode carried the score board across")
        if sep["vec"]["finished"]:
            failures.append(
                "vector mode showed a finished result inherited from score mode")
        if not sep["vec"]["playable"]:
            failures.append("vector mode was not playable after switching")

        # Vector progress must likewise not bleed into score mode.
        sep2 = page.evaluate(
            """() => {
              localStorage.clear();
              setVectorMode(true);
              startDaily();
              Object.assign(vectorPick, parseVector());
              renderMetricPicker(); renderVectorPreview();
              document.getElementById('btn-submit-vector').click();   // solved
              const vectorFinished = !document.getElementById('result').hidden;
              localStorage.removeItem(KEY_LOCK);
              setVectorMode(false);
              startDaily();
              return { vectorFinished,
                       restored: restore(),
                       scoreRows: document.querySelectorAll('.row:not(.empty)').length,
                       scoreFinished: !document.getElementById('result').hidden };
            }"""
        )
        if not sep2["vectorFinished"]:
            failures.append("the vector game did not complete as expected")
        if sep2["restored"]:
            failures.append("a vector board was restored as a score board")
        if sep2["scoreRows"] != 0 or sep2["scoreFinished"]:
            failures.append("a solved vector leaked a finished board into score mode")

        # --- vector challenge fragments -------------------------------
        n = page.evaluate("() => DAILY.number")
        page.goto(url + f"#c{n}.v2")
        ok = page.evaluate(
            """() => ({ shown: !document.getElementById('challenge').hidden,
                        text: document.getElementById('challenge').textContent })"""
        )
        if not ok["shown"] or "vector" not in ok["text"].lower():
            failures.append("a valid vector challenge fragment was not shown correctly")

        for frag in (f"c{n}.v5", f"c{n}.v6", f"c{n}.vn", f"c{n}.v9", f"c{n}.v0"):
            page.goto(url)
            page.evaluate("f => { location.hash = f; }", frag)
            page.wait_for_timeout(120)
            if page.evaluate("() => !document.getElementById('challenge').hidden"):
                failures.append(f"invalid vector fragment {frag!r} was accepted")

        if errors:
            failures.append(f"page errors: {errors[:3]}")
        browser.close()

    if failures:
        for f in failures:
            print("FAIL:", f)
        sys.exit(f"{len(failures)} vector-mode failures")
    print("OK: vector mode is opt-in, never reveals the answer, and keeps a "
          "separate board from score mode")


if __name__ == "__main__":
    main()
