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

    # No daily answer other than today's may appear. Match on CVE id and on the
    # full description; a shared prefix is not a leak, since split_pool.py keeps
    # same-advisory CVEs in one pool.
    leaked = [
        p["id"] for p in pool
        if p["id"] != today["id"] and (p["id"] in built or p["desc"] in built)
    ]
    if leaked:
        sys.exit(f"FAIL: {len(leaked)} future answers leaked, e.g. {leaked[:5]}")

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

    scores = built.count('"score"')
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
