#!/usr/bin/env python3
"""Build index.html from the template, today's puzzle, and the practice pool.

Only ONE daily answer is inlined. Future daily answers are never present in the
published artifact - they stay in puzzles.daily.enc, which needs a key held in
Actions secrets.

Usage:
    python3 pick_daily.py      # writes today.json (needs PUZZLE_KEY/SEED)
    python3 build_site.py
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
TEMPLATE = HERE / "game.template.html"
PRACTICE = HERE / "puzzles.practice.json"
TODAY = HERE / "today.json"
OUT = HERE / "index.html"

# UTC time the daily workflow publishes. Must match the cron in daily.yml.
ROLLOVER_UTC = "05:05"


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


def dump(obj) -> str:
    # ensure_ascii=True (the default) is load-bearing: it keeps U+2028/U+2029,
    # which are JS line terminators, out of the output.
    return js_safe(json.dumps(obj, separators=(",", ":")))


def main() -> None:
    template = TEMPLATE.read_text()
    practice = json.loads(PRACTICE.read_text())

    if TODAY.exists():
        daily = json.loads(TODAY.read_text())
    else:
        # Local preview without the decryption key: stand in a practice puzzle
        # so the page is playable. CI always has today.json.
        print("today.json missing - using a practice puzzle for local preview",
              file=sys.stderr)
        daily = {"number": 0, "date": "preview", "puzzle": practice[0],
                 "next": practice[1]["vendor"] if len(practice) > 1 else ""}

    # The teaser must be a bare vendor name and nothing else. Guard it here so
    # a future change cannot quietly start leaking tomorrow's product or score.
    teaser = daily.get("next", "")
    if not isinstance(teaser, str):
        sys.exit("refusing to build: teaser must be a string")
    if len(teaser) > 40 or any(c in teaser for c in "0123456789"):
        sys.exit(f"refusing to build: teaser looks like more than a vendor: {teaser!r}")

    if daily["puzzle"]["id"] in {p["id"] for p in practice} and daily["number"]:
        sys.exit("refusing to build: today's puzzle is also in the practice pool")

    out = template
    for token, value in (
        ("__DAILY_DATA__", dump(daily)),
        ("__PRACTICE_DATA__", dump(practice)),
        ("__ROLLOVER_UTC__", json.dumps(ROLLOVER_UTC)),
    ):
        if token not in out:
            sys.exit(f"template is missing the {token} placeholder")
        out = out.replace(token, value)

    if "</" in dump(daily) or "</" in dump(practice):
        sys.exit("refusing to build: puzzle data can escape the script block")

    OUT.write_text(out)

    built = OUT.read_text()
    if built.count("</script>") != 2:
        sys.exit(
            f"refusing to ship: expected 2 script blocks, found {built.count('</script>')}"
        )

    # The whole point of this pipeline: exactly one daily answer in the artifact.
    answers = built.count('"score"')
    expected = len(practice) + 1
    if answers != expected:
        sys.exit(f"refusing to ship: expected {expected} scores, found {answers}")

    kb = OUT.stat().st_size / 1024
    print(f"Wrote {OUT.name} ({kb:.0f} KB): "
          f"daily #{daily['number']} + {len(practice)} practice puzzles")


if __name__ == "__main__":
    main()
