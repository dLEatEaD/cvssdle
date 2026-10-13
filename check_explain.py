#!/usr/bin/env python3
"""CI gate: the end-of-round vector breakdown must be true.

The result card does not just print the vector any more - it says, metric by
metric, what the score would have been at the alternative that moves it
furthest. That is the part of the game that actually teaches, which means a
wrong claim there is worse than no claim at all: it would confidently teach the
wrong rubric to someone using the game to learn one.

The page computes those counterfactuals with its own scoreVector(). Checking
them against that same function would only prove it is self-consistent, so this
re-derives every claim from an independent CVSS v3.1 implementation written
here from the specification (FIRST CVSS v3.1, section 7.1) and compares.

For every puzzle in the pool it asserts:
  - the headline score the breakdown opens with is the published score
  - every "would have been X as Y" figure is the real score of that variant
  - the alternative named for each metric really is the furthest-moving one
  - the swing shown equals the distance between the two, to one decimal
  - the metric called out in the heading is the one with the largest swing
  - the breakdown appears on the result card, after the raw vector string
  - puzzle text reaches the DOM as text, never as markup
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
BUILT = HERE / "index.html"
SOURCE = HERE / "puzzles.json"

# Independent CVSS v3.1 base score, from the specification. Deliberately a
# separate implementation from the one in the page - that is the entire point
# of this gate.
AV_W = {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2}
AC_W = {"L": 0.77, "H": 0.44}
PR_W = {"U": {"N": 0.85, "L": 0.62, "H": 0.27},
        "C": {"N": 0.85, "L": 0.68, "H": 0.5}}
UI_W = {"N": 0.85, "R": 0.62}
CIA_W = {"H": 0.56, "L": 0.22, "N": 0.0}

METRICS = {
    "AV": ("Attack Vector",
           {"N": "Network", "A": "Adjacent", "L": "Local", "P": "Physical"}),
    "AC": ("Attack Complexity", {"L": "Low", "H": "High"}),
    "PR": ("Privileges Required", {"N": "None", "L": "Low", "H": "High"}),
    "UI": ("User Interaction", {"N": "None", "R": "Required"}),
    "S": ("Scope", {"U": "Unchanged", "C": "Changed"}),
    "C": ("Confidentiality", {"H": "High", "L": "Low", "N": "None"}),
    "I": ("Integrity", {"H": "High", "L": "Low", "N": "None"}),
    "A": ("Availability", {"H": "High", "L": "Low", "N": "None"}),
}
ORDER = ["AV", "AC", "PR", "UI", "S", "C", "I", "A"]


def round_up(x: float) -> float:
    """The spec's Roundup, guarded against float noise at exact values."""
    i = int(round(x * 100_000))
    if i % 10_000 == 0:
        return i / 100_000
    return (i // 10_000 + 1) / 10


def score(v: dict) -> float:
    scope = "C" if v["S"] == "C" else "U"
    iss = 1 - (1 - CIA_W[v["C"]]) * (1 - CIA_W[v["I"]]) * (1 - CIA_W[v["A"]])
    if scope == "U":
        impact = 6.42 * iss
    else:
        impact = 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15
    if impact <= 0:
        return 0.0
    expl = 8.22 * AV_W[v["AV"]] * AC_W[v["AC"]] * PR_W[scope][v["PR"]] * UI_W[v["UI"]]
    raw = min(impact + expl, 10) if scope == "U" else min(1.08 * (impact + expl), 10)
    return round_up(raw)


def parse(vector: str) -> dict:
    out = {}
    for part in vector.split("/"):
        k, _, val = part.partition(":")
        if k in METRICS:
            out[k] = val
    return out


def expected_rows(vector: str) -> list:
    """What the breakdown must say, derived here rather than in the page."""
    v = parse(vector)
    base = score(v)
    rows = []
    for k in ORDER:
        label, names = METRICS[k]
        codes = list(names)
        cur = codes.index(v[k])
        best_code, best_score, best_swing, best_dist = None, base, -1.0, -1
        for code in codes:
            if code == v[k]:
                continue
            s = score({**v, k: code})
            swing, dist = abs(s - base), abs(codes.index(code) - cur)
            # Matches the page's tie-break: the biggest swing wins, and ties go
            # to the alternative furthest from the real value in the metric's
            # own ordering.
            if swing > best_swing + 1e-9 or (
                    swing > best_swing - 1e-9 and dist > best_dist):
                best_code, best_score, best_swing, best_dist = code, s, swing, dist
        rows.append({
            "key": k,
            "label": label,
            "value": names[v[k]],
            "altValue": names[best_code] if best_code else None,
            "altScore": best_score,
            "swing": round(abs(best_score - base), 1),
        })
    return base, rows


def load_puzzles(text: str) -> tuple:
    if SOURCE.exists():
        puzzles = json.loads(SOURCE.read_text())
        return puzzles, f"{len(puzzles)} puzzles from puzzles.json"

    def grab(pattern):
        m = re.search(pattern, text, re.S)
        raw = (m.group(1).replace("\\u003c", "<").replace("\\u003e", ">")
               .replace("\\u0026", "&"))
        return json.loads(raw)

    puzzles = grab(r"const PRACTICE = (\[.*?\]);")
    puzzles.append(grab(r"const DAILY = (\{.*?\});")["puzzle"])
    return puzzles, f"{len(puzzles)} puzzles from the built page"


def main() -> None:
    if not BUILT.exists():
        sys.exit("index.html not built yet - run build_site.py first")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP: playwright not installed")
        return

    text = BUILT.read_text()
    puzzles, origin = load_puzzles(text)
    failures = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(BUILT.resolve().as_uri())

        if not page.evaluate("() => typeof explainVector === 'function'"):
            browser.close()
            sys.exit("FAIL: the page has no explainVector() function - the "
                     "result card is no longer explaining the vector")

        got = page.evaluate(
            """(vectors) => vectors.map((vec) => {
                 const e = explainVector(parseVectorString(vec));
                 return {
                   base: e.base,
                   widest: e.widest.key,
                   widestSwing: e.widest.swing,
                   rows: e.rows.map((r) => ({
                     key: r.key, label: r.label, value: r.value,
                     altValue: r.altValue, altScore: r.altScore, swing: r.swing,
                   })),
                 };
               })""",
            [p["vector"] for p in puzzles],
        )

        # --- every claim must match the independent calculator ------------
        for p, g in zip(puzzles, got):
            base, rows = expected_rows(p["vector"])
            pid = p["id"]
            if g["base"] != p["score"]:
                failures.append(
                    f"{pid}: breakdown opens with {g['base']}, "
                    f"NVD published {p['score']}")
            if [r["key"] for r in g["rows"]] != ORDER:
                failures.append(f"{pid}: breakdown skips or reorders metrics")
                continue
            for want, have in zip(rows, g["rows"]):
                where = f"{pid} {want['key']}"
                if have["label"] != want["label"] or have["value"] != want["value"]:
                    failures.append(
                        f"{where}: described as "
                        f"{have['label']}/{have['value']}, vector says "
                        f"{want['label']}/{want['value']}")
                if have["altValue"] != want["altValue"]:
                    failures.append(
                        f"{where}: names {have['altValue']} as the biggest "
                        f"mover, but {want['altValue']} moves it further")
                if round(have["altScore"], 1) != round(want["altScore"], 1):
                    failures.append(
                        f"{where}: claims {have['altValue']} would score "
                        f"{have['altScore']}, really {want['altScore']}")
                if round(have["swing"], 1) != want["swing"]:
                    failures.append(
                        f"{where}: claims a swing of {have['swing']}, "
                        f"really {want['swing']}")
            widest = max(rows, key=lambda r: r["swing"])
            if round(g["widestSwing"], 1) != widest["swing"]:
                failures.append(
                    f"{pid}: headline swing {g['widestSwing']} is not the "
                    f"largest ({widest['swing']} on {widest['key']})")

        # --- and it must actually reach the result card -------------------
        dom = page.evaluate(
            """() => {
              const d = document.getElementById('dlg-help');
              if (d && d.open) d.close();
              localStorage.clear();
              startDaily();
              document.getElementById('guess').value =
                DAILY.puzzle.score.toFixed(1);
              document.getElementById('btn-guess').click();
              const why = document.getElementById('why');
              if (!why) return { present: false };
              // Re-rendering the result must not stack duplicate breakdowns.
              renderResult(); renderResult();
              return {
                present: true,
                copies: document.querySelectorAll('#result .why').length,
                afterVector:
                  document.getElementById('why').previousElementSibling.id,
                rows: document.querySelectorAll('#why .why-row').length,
                head: document.querySelector('#why .why-head').textContent,
                // Puzzle-derived strings must arrive as text, not markup.
                injected: document.querySelectorAll(
                  '#why script, #why img, #why iframe, #why a').length,
                score: DAILY.puzzle.score,
              };
            }"""
        )
        if errors:
            failures.append(f"uncaught page errors: {errors[:3]}")
        browser.close()

    if not dom.get("present"):
        failures.append("no breakdown on the result card after a win")
    else:
        if dom["afterVector"] != "answer-vector":
            failures.append(
                "the breakdown does not follow the raw vector string "
                f"(follows #{dom['afterVector']})")
        if dom["copies"] != 1:
            failures.append(
                f"re-rendering the result leaves {dom['copies']} breakdowns")
        if dom["rows"] != len(ORDER):
            failures.append(
                f"breakdown shows {dom['rows']} metrics, expected {len(ORDER)}")
        if f"{dom['score']:.1f}" not in dom["head"]:
            failures.append(
                f"breakdown heading {dom['head']!r} does not open with the "
                f"answer {dom['score']:.1f}")
        if dom["injected"]:
            failures.append(
                f"{dom['injected']} elements rendered from puzzle text - "
                "it must be inserted as text, never as markup")

    if failures:
        for f in failures[:12]:
            print("FAIL:", f)
        if len(failures) > 12:
            print(f"... and {len(failures) - 12} more")
        sys.exit(f"{len(failures)} breakdown failures")

    print(f"OK: the vector breakdown matches an independent CVSS v3.1 "
          f"calculator on all {origin}")


if __name__ == "__main__":
    main()
