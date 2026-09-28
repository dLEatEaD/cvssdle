#!/usr/bin/env python3
"""Inline puzzles.json into game.template.html to produce a standalone index.html.

Usage:  python3 build_site.py
"""

import json
from pathlib import Path

HERE = Path(__file__).parent
template = (HERE / "game.template.html").read_text()
puzzles = json.loads((HERE / "puzzles.json").read_text())

# Compact JSON keeps the single-file build small enough to load instantly.
data = json.dumps(puzzles, separators=(",", ":"))
if "__PUZZLE_DATA__" not in template:
    raise SystemExit("template is missing the __PUZZLE_DATA__ placeholder")

out = HERE / "index.html"
out.write_text(template.replace("__PUZZLE_DATA__", data))

kb = out.stat().st_size / 1024
print(f"Wrote {out.name} ({kb:.0f} KB) with {len(puzzles)} puzzles.")
