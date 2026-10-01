#!/usr/bin/env python3
"""CI gate: the in-game CVSS calculator must agree with NVD.

Vector mode derives the base score from the eight metrics the player picks, so
the formula in the page has to produce exactly the score NVD published - for
every puzzle, not just the common ones. A rounding or scope-branch error here
makes the game quietly wrong, which is worse than useless for a tool whose
whole point is teaching the scoring rubric.

Runs the shipped JS against every puzzle in the pool.
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
BUILT = HERE / "index.html"
SOURCE = HERE / "puzzles.json"


def main() -> None:
    if not BUILT.exists():
        sys.exit("index.html not built yet - run build_site.py first")
    if not SOURCE.exists():
        print("SKIP: puzzles.json not present (it is gitignored); "
              "the built page's own pools will be used instead")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP: playwright not installed")
        return

    # Prefer the full pool when it is available locally; fall back to whatever
    # the built page carries, so this still means something in CI.
    if SOURCE.exists():
        puzzles = json.loads(SOURCE.read_text())
        origin = f"{len(puzzles)} puzzles from puzzles.json"
    else:
        text = BUILT.read_text()
        def grab(pattern):
            m = re.search(pattern, text, re.S)
            raw = (m.group(1).replace("\\u003c", "<").replace("\\u003e", ">")
                   .replace("\\u0026", "&"))
            return json.loads(raw)
        puzzles = grab(r"const PRACTICE = (\[.*?\]);")
        puzzles.append(grab(r"const DAILY = (\{.*?\});")["puzzle"])
        origin = f"{len(puzzles)} puzzles from the built page"

    url = BUILT.resolve().as_uri()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url)

        has_calc = page.evaluate("() => typeof scoreVector === 'function'")
        if not has_calc:
            browser.close()
            sys.exit("FAIL: the page has no scoreVector() function")

        bad = page.evaluate(
            """(items) => {
              const out = [];
              for (const p of items) {
                let got;
                try { got = scoreVector(parseVectorString(p.vector)); }
                catch (e) { out.push({id: p.id, err: String(e), vector: p.vector}); continue; }
                if (got !== p.score) {
                  out.push({id: p.id, vector: p.vector, want: p.score, got});
                }
              }
              return out;
            }""",
            [{"id": p["id"], "vector": p["vector"], "score": p["score"]} for p in puzzles],
        )

        if errors:
            bad.append({"id": "-", "err": f"page errors: {errors[:2]}"})
        browser.close()

    if bad:
        for b in bad[:12]:
            if "err" in b:
                print(f"FAIL: {b['id']}: {b['err']}")
            else:
                print(f"FAIL: {b['id']} {b['vector']} -> {b['got']}, NVD says {b['want']}")
        if len(bad) > 12:
            print(f"... and {len(bad) - 12} more")
        sys.exit(f"{len(bad)} vectors scored incorrectly")

    print(f"OK: the in-game CVSS calculator matches NVD on all {origin}")


if __name__ == "__main__":
    main()
