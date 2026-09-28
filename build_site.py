#!/usr/bin/env python3
"""Inline puzzles.json into game.template.html to produce a standalone index.html.

Usage:  python3 build_site.py
"""

import json
from pathlib import Path

HERE = Path(__file__).parent
template = (HERE / "game.template.html").read_text()
puzzles = json.loads((HERE / "puzzles.json").read_text())


def js_safe(data: str) -> str:
    """Make a JSON string safe to embed inside an HTML <script> block.

    json.dumps produces valid JSON, not a safe script-block literal. The HTML
    parser ends a <script> element at the byte sequence "</script" regardless
    of JS string quoting, so an unescaped "<" in puzzle text (which comes from
    third-party NVD and CISA KEV records) could terminate the data block and
    inject markup into the published page.

    These are valid JS string escapes and decode back to the original
    characters at runtime, so the game sees identical data.
    """
    return (
        data.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


# Compact JSON keeps the single-file build small enough to load instantly.
# ensure_ascii=True (the default) is load-bearing: it keeps U+2028/U+2029,
# which are JS line terminators, out of the output.
data = js_safe(json.dumps(puzzles, separators=(",", ":")))

if "__PUZZLE_DATA__" not in template:
    raise SystemExit("template is missing the __PUZZLE_DATA__ placeholder")
if "</" in data or "<script" in data.lower():
    raise SystemExit("refusing to build: puzzle data can escape the script block")

out = HERE / "index.html"
out.write_text(template.replace("__PUZZLE_DATA__", data))

# The built page must contain only the two script tags the template defines.
built = out.read_text()
if built.count("</script>") != 2:
    raise SystemExit(
        f"refusing to ship: expected 2 script blocks, found {built.count('</script>')}"
    )

kb = out.stat().st_size / 1024
print(f"Wrote {out.name} ({kb:.0f} KB) with {len(puzzles)} puzzles.")
