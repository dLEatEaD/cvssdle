#!/usr/bin/env python3
"""CI gate: the stele must be a true, safe, self-contained artifact.

The stele is the one thing the game produces that leaves the page and outlives
the session - it gets pasted into chats, saved, and read by people who have
never seen CVSSdle. That makes it the worst possible place for a wrong number
or an injected tag, and it cannot be fixed after the fact the way a web page
can: once an image is minted it is out there.

So it is held to the same standard as the on-screen breakdown, independently.
Every figure is re-derived from a separate CVSS v3.1 implementation (shared
with check_explain.py) and matched against what the plaque actually draws:

  - the filled-cell count is round(score * 10), so the self-defining scale
    tells the truth and agrees with the printed decimal
  - each dimension draws exactly as many slots as that metric has values, with
    the filled one at the real index - the structural layer a reader with no
    CVSS knowledge is meant to be able to recover
  - every "would be X as Y" figure is the real score of that variant
  - the plaque carries the vector, the CVE id and the severity band

and the things that make it safe to hand to a stranger:

  - it is well-formed XML and parses
  - no script, no foreignObject, no external reference of any kind, so it
    rasterises to a canvas without tainting it and carries everything it needs
  - puzzle text is escaped, not spliced: a malicious vendor or product string
    in the pool cannot add elements to the artifact
  - it actually rasterises to a PNG through the shipped code path
  - it is never mintable before the round is decided
"""

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from check_explain import METRICS, ORDER, expected_rows, load_puzzles, parse, score

HERE = Path(__file__).parent
BUILT = HERE / "index.html"

SVG_NS = "{http://www.w3.org/2000/svg}"
XLINK = "{http://www.w3.org/1999/xlink}"
# Anything that would make the artifact depend on the outside world, or run.
BANNED_TAGS = {"script", "foreignObject", "image", "use", "iframe", "a",
               "animate", "set", "feImage"}
URL_VALUE = re.compile(r"https?://|url\s*\(", re.I)


def external_refs(root) -> list:
    """Attributes that would fetch something or run something.

    Deliberately structural rather than a regex over the raw string: escaped
    puzzle text legitimately contains things like `href=` as *characters*, and
    treating that as an injection would be a false alarm that trains people to
    ignore the gate. What matters is whether it parsed into an attribute.
    """
    bad = []
    for el in root.iter():
        for name, value in el.attrib.items():
            short = name.replace(XLINK, "xlink:")
            if short in ("href", "xlink:href") or short.startswith("on"):
                bad.append(f"{el.tag.replace(SVG_NS, '')}/@{short}")
            elif URL_VALUE.search(value or ""):
                bad.append(f"{el.tag.replace(SVG_NS, '')}/@{short}={value!r}")
    return sorted(set(bad))


def texts(root) -> list:
    return [(e.text or "") for e in root.iter(SVG_NS + "text")]


def rects(root) -> list:
    return list(root.iter(SVG_NS + "rect"))


def main() -> None:
    if not BUILT.exists():
        sys.exit("index.html not built yet - run build_site.py first")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP: playwright not installed")
        return

    puzzles, origin = load_puzzles(BUILT.read_text())
    failures = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(BUILT.resolve().as_uri())

        if not page.evaluate("() => typeof buildStele === 'function'"):
            browser.close()
            sys.exit("FAIL: the page has no buildStele() - there is no stele "
                     "to mint")

        # Build a plaque for every puzzle in the pool by pointing the page's
        # own state at it, so this tests the shipped function and not a copy.
        # The records are passed in rather than looked up: locally the pool is
        # far larger than the 136 puzzles the built page carries, and the whole
        # point is to cover all of it.
        svgs = {}
        fields = ("id", "vendor", "product", "published", "vector", "score",
                  "severity", "url", "name", "desc")
        batch = [{k: p.get(k, "") for k in fields} for p in puzzles]
        for i in range(0, len(batch), 150):
            svgs.update(page.evaluate(
                """(items) => {
                  const d = document.getElementById('dlg-help');
                  if (d && d.open) d.close();
                  localStorage.clear();
                  startDaily();
                  const keep = puzzle;
                  const out = {};
                  for (const p of items) {
                    puzzle = p;
                    out[p.id] = buildStele();
                  }
                  puzzle = keep;
                  return out;
                }""",
                batch[i:i + 150],
            ))

        # --- never mintable mid-round ---------------------------------
        live = page.evaluate(
            """() => {
              localStorage.clear();
              startDaily();
              document.getElementById('guess').value = '1.0';
              document.getElementById('btn-guess').click();
              return {
                finished,
                resultHidden: document.getElementById('result').hidden,
                button: !!document.getElementById('btn-stele'),
              };
            }"""
        )
        if live["finished"] or not live["resultHidden"] or live["button"]:
            failures.append(
                "the Mint button exists before the round is decided - the "
                "stele carries the answer")

        # --- and present, and rasterising, once it is -----------------
        minted = page.evaluate(
            """async () => {
              localStorage.clear();
              startDaily();
              document.getElementById('guess').value =
                DAILY.puzzle.score.toFixed(1);
              document.getElementById('btn-guess').click();
              if (!document.getElementById('btn-stele')) {
                return { button: false };
              }
              let bytes = 0, png = false, err = null;
              try {
                const blob = await steleToPng();
                bytes = blob.size;
                png = blob.type === 'image/png';
              } catch (e) { err = String(e); }
              return { button: true, bytes, png, err, name: steleName() };
            }"""
        )
        if errors:
            failures.append(f"uncaught page errors: {errors[:3]}")
        browser.close()

    if not minted.get("button"):
        failures.append("no Mint button on the result card after a win")
    else:
        if minted.get("err"):
            failures.append(f"the stele does not rasterise: {minted['err']}")
        if not minted.get("png"):
            failures.append("steleToPng() did not produce an image/png blob")
        if minted.get("bytes", 0) < 5000:
            failures.append(
                f"the minted PNG is {minted.get('bytes')} bytes - too small to "
                "be a drawn plaque")
        if not str(minted.get("name", "")).endswith(".png"):
            failures.append(f"odd download name {minted.get('name')!r}")

    # --- every plaque, checked against the independent calculator -----
    checked = 0
    for p in puzzles:
        svg = svgs.get(p["id"])
        pid = p["id"]
        if not svg:
            failures.append(f"{pid}: no stele produced")
            continue

        # Well-formed, and carrying nothing it cannot carry on its own.
        try:
            root = ET.fromstring(svg)
        except ET.ParseError as e:
            failures.append(f"{pid}: the stele is not well-formed XML ({e})")
            continue
        found = {e.tag.replace(SVG_NS, "") for e in root.iter()}
        banned = sorted(found & BANNED_TAGS)
        if banned:
            failures.append(
                f"{pid}: the stele contains {banned} - it must be inert and "
                "self-contained")
        ext = external_refs(root)
        if ext:
            failures.append(f"{pid}: the stele references something external: {ext}")
        checked += 1
        base, rows = expected_rows(p["vector"])
        body = "".join(texts(root))

        # Layer one: the scale must define itself honestly.
        want_marks = round(p["score"] * 10)
        boxes = [r for r in rects(root)
                 if r.get("width") == r.get("height") == "20"]
        filled = [r for r in boxes if r.get("fill") not in (None, "none")]
        if len(boxes) != 100:
            failures.append(
                f"{pid}: magnitude grid has {len(boxes)} cells, not 100 - it no "
                "longer defines its own scale")
        elif len(filled) != want_marks:
            failures.append(
                f"{pid}: {len(filled)} of 100 cells filled, score {p['score']} "
                f"needs {want_marks}")
        if f"{want_marks} of 100" not in body:
            failures.append(f"{pid}: plaque does not state '{want_marks} of 100'")
        if f"{p['score']:.1f}" not in body:
            failures.append(f"{pid}: plaque does not print the score "
                            f"{p['score']:.1f}")

        # Layer two: the slot rows must describe the real rubric.
        pips = [r for r in rects(root)
                if r.get("width") == r.get("height") == "16"]
        want_pips = sum(len(METRICS[k][1]) for k in ORDER)
        if len(pips) != want_pips:
            failures.append(
                f"{pid}: {len(pips)} slots drawn, the eight metrics have "
                f"{want_pips} values between them")
        else:
            at = 0
            for k in ORDER:
                codes = list(METRICS[k][1])
                group = pips[at:at + len(codes)]
                at += len(codes)
                on = [i for i, r in enumerate(group)
                      if r.get("fill") not in (None, "none")]
                want_idx = codes.index(parse(p["vector"])[k])
                if on != [want_idx]:
                    failures.append(
                        f"{pid} {k}: slot {on} filled, the vector says "
                        f"{want_idx} ({codes[want_idx]})")

        # Layer three: the consequences must be the real ones.
        for r in rows:
            if r["altValue"] is None:
                continue
            claim = f"\u2192 {r['altScore']:.1f} as {r['altValue']}"
            if claim not in body:
                failures.append(f"{pid} {r['key']}: plaque is missing {claim!r}")
            if r["label"] not in body or r["value"] not in body:
                failures.append(
                    f"{pid} {r['key']}: plaque does not name "
                    f"{r['label']}/{r['value']}")

        # Provenance.
        for must in (p["vector"], pid):
            if must not in body:
                failures.append(f"{pid}: plaque does not carry {must!r}")

    # --- escaping, against a deliberately hostile record --------------
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(BUILT.resolve().as_uri())
        hostile = page.evaluate(
            """() => {
              const d = document.getElementById('dlg-help');
              if (d && d.open) d.close();
              localStorage.clear();
              startDaily();
              puzzle = { ...DAILY.puzzle,
                vendor: '<script>x</script>',
                product: ']]><image href="http://evil/x"/>',
                id: 'CVE-0000-0000"><script/>' };
              return buildStele();
            }"""
        )
        browser.close()
    try:
        root = ET.fromstring(hostile)
    except ET.ParseError as e:
        failures.append(f"hostile puzzle text breaks the stele's XML ({e})")
    else:
        bad = sorted({e.tag.replace(SVG_NS, "") for e in root.iter()}
                     & BANNED_TAGS)
        if bad:
            failures.append(
                f"hostile puzzle text injected {bad} into the stele - it must "
                "be escaped, never spliced")
        ext = external_refs(root)
        if ext:
            failures.append(
                f"hostile puzzle text injected an external reference: {ext}")

    if failures:
        for f in failures[:12]:
            print("FAIL:", f)
        if len(failures) > 12:
            print(f"... and {len(failures) - 12} more")
        sys.exit(f"{len(failures)} stele failures")

    print(f"OK: the stele is inert, self-contained, escapes hostile text, and "
          f"tells the truth on all {origin}")


if __name__ == "__main__":
    main()
