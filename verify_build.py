#!/usr/bin/env python3
"""CI gate: prove the built page leaks no future daily answers.

build_site.py already counts scores, but that only checks the shape of what we
meant to publish. This decrypts the real daily pool and asserts that none of
the other answers appear anywhere in index.html - the actual property we care
about.

Run after build_site.py, with PUZZLE_KEY available.
"""

import base64
import json
import re
import os
import sys
from datetime import date
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

HERE = Path(__file__).parent

# Imported rather than restated, so the gate cannot drift from the filter.
from build_puzzles import EXCLUDED_VENDORS  # noqa: E402
from pick_daily import EPOCH  # noqa: E402


def main() -> None:
    key = base64.b64decode(os.environ.get("PUZZLE_KEY", "").strip() or "")
    if len(key) != 32:
        sys.exit("PUZZLE_KEY must decode to 32 bytes")

    built = (HERE / "index.html").read_text()
    today = json.loads((HERE / "today.json").read_text())["puzzle"]
    practice = json.loads((HERE / "puzzles.practice.json").read_text())

    blob = (HERE / "puzzles.daily.enc").read_bytes()
    pool = json.loads(AESGCM(key).decrypt(blob[:12], blob[12:], None))

    # No daily answer other than today's may appear. The id check is absolute:
    # a future CVE id in the page is a leak however it got there.
    #
    # The description check has to allow one case. Vendors file several CVEs
    # from a single advisory with byte-identical descriptions - Oracle WebLogic
    # and Cisco IOS do it routinely - and split_pool.py deliberately keeps such
    # a group together in one pool. When one of them is today's puzzle, its
    # twins' descriptions are necessarily in the page, because they are the same
    # string as today's. That reveals nothing: the player sees one description
    # and cannot tell it maps to more than one CVE. Treating it as a leak took
    # the daily publish down for a day, so the comparison is now against
    # descriptions that actually differ from today's.
    leaked = [
        p["id"] for p in pool
        if p["id"] != today["id"]
        and (p["id"] in built
             or (p["desc"] != today["desc"] and p["desc"] in built))
    ]
    if leaked:
        sys.exit(f"FAIL: {len(leaked)} future answers leaked, e.g. {leaked[:5]}")

    # Report the twins rather than silently tolerating them. They are not a
    # leak, but a group that also shares a score is the same puzzle served on
    # two different days, which is a content problem worth seeing in the log.
    twins = [p["id"] for p in pool
             if p["id"] != today["id"] and p["desc"] == today["desc"]]
    if twins:
        same_score = [p["id"] for p in pool
                      if p["id"] in twins and p.get("score") == today.get("score")]
        print(f"NOTE: today's description is shared with {len(twins)} other pool "
              f"entries ({', '.join(twins[:4])})"
              + (f"; {len(same_score)} also share its score" if same_score else ""))

    # A practice puzzle sharing an advisory with a daily would telegraph it.
    straddle = {p["desc"][:60] for p in pool} & {p["desc"][:60] for p in practice}
    if straddle:
        sys.exit(f"FAIL: {len(straddle)} description groups straddle both pools")

    # The pools must stay disjoint, or a daily answer leaks through practice.
    overlap = {p["id"] for p in pool} & {p["id"] for p in practice}
    if overlap:
        sys.exit(f"FAIL: pools overlap: {sorted(overlap)[:5]}")

    if today["id"] not in built:
        sys.exit("FAIL: today's puzzle is missing from the build")

    # Count score fields inside the inlined data blocks, not anywhere in the
    # file: the game's own source legitimately contains the word "score".
    blocks = re.findall(r"const (?:DAILY|PRACTICE) = (.+?);\n", built, re.S)
    if len(blocks) != 2:
        sys.exit(f"FAIL: expected 2 data blocks in the page, found {len(blocks)}")
    scores = sum(b.count('"score":') for b in blocks)
    if scores != len(practice) + 1:
        sys.exit(f"FAIL: expected {len(practice) + 1} scores, found {scores}")

    # Excluded vendors must not reach the published page by any route - not as
    # today's puzzle, not in the practice pool, and not via a stale pool file.
    offenders = sorted(
        {p["vendor"] for p in practice + [today] if p["vendor"] in EXCLUDED_VENDORS}
    )
    if offenders:
        sys.exit(f"FAIL: excluded vendors published: {offenders}")

    # Retired slots hold the schedule open for days already played; they must
    # never sit in the future, where they would be served as a live puzzle.
    spent = (date.today() - EPOCH).days + 1
    future_retired = [
        p["id"] for p in pool[spent:] if p.get("retired")
    ]
    if future_retired:
        sys.exit(f"FAIL: {len(future_retired)} retired puzzles are scheduled ahead")

    retired = sum(1 for p in pool if p.get("retired"))
    print(f"OK: 1 daily answer + {len(practice)} practice puzzles published; "
          f"{len(pool) - 1} future answers withheld"
          + (f"; {retired} retired slots, all in the past" if retired else ""))


if __name__ == "__main__":
    main()
