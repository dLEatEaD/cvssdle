#!/usr/bin/env python3
"""Select today's puzzle from the encrypted daily pool.

Run in CI, where PUZZLE_KEY and PUZZLE_SEED are available as secrets. Writes
today.json containing exactly one puzzle, which build_site.py inlines.

Selection is HMAC-SHA256(seed, date), so knowing the pool is not enough to
work out tomorrow's puzzle without the seed.

Usage:
    python3 pick_daily.py [--date YYYY-MM-DD]
"""

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

HERE = Path(__file__).parent
DAILY_ENC = HERE / "puzzles.daily.enc"
OUT = HERE / "today.json"

# Day zero for the puzzle counter shown in the UI and in shared results.
EPOCH = date(2026, 1, 1)


def secret(name: str) -> bytes:
    raw = os.environ.get(name, "").strip()
    if not raw:
        sys.exit(f"{name} is not set")
    return raw.encode()


def load_key() -> bytes:
    key = base64.b64decode(os.environ.get("PUZZLE_KEY", "").strip() or "")
    if len(key) != 32:
        sys.exit("PUZZLE_KEY must decode to 32 bytes")
    return key


def _rand_stream(seed: bytes, label: str):
    """Deterministic byte stream from HMAC-SHA256 in counter mode."""
    counter = 0
    while True:
        block = hmac.new(seed, f"{label}:{counter}".encode(), hashlib.sha256).digest()
        for i in range(0, 32, 4):
            yield int.from_bytes(block[i:i + 4], "big")
        counter += 1


def cycle_order(n: int, seed: bytes, cycle: int) -> list[int]:
    """Seeded Fisher-Yates shuffle of pool indices for one cycle.

    Every puzzle is used exactly once before any repeats, and each cycle gets a
    fresh order. Without the seed the order is not predictable, so publishing
    today's puzzle reveals nothing about tomorrow's.
    """
    rand = _rand_stream(seed, f"cycle{cycle}")
    order = list(range(n))
    for i in range(n - 1, 0, -1):
        j = next(rand) % (i + 1)
        order[i], order[j] = order[j], order[i]
    return order


def pick(pool: list, day: date, seed: bytes) -> dict:
    n = len(pool)
    offset_days = (day - EPOCH).days
    cycle, offset = divmod(offset_days, n)
    return pool[cycle_order(n, seed, cycle)[offset]]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="override the date (YYYY-MM-DD), for testing")
    args = ap.parse_args()

    day = (
        datetime.strptime(args.date, "%Y-%m-%d").date()
        if args.date
        else datetime.now(timezone.utc).date()
    )

    key = load_key()
    seed = secret("PUZZLE_SEED")
    blob = DAILY_ENC.read_bytes()
    pool = json.loads(AESGCM(key).decrypt(blob[:12], blob[12:], None))

    puzzle = pick(pool, day, seed)
    number = (day - EPOCH).days + 1

    OUT.write_text(json.dumps({"number": number, "date": day.isoformat(),
                               "puzzle": puzzle}, separators=(",", ":")))
    # Deliberately not printing the score - CI logs are public on a public repo.
    print(f"puzzle #{number} for {day}: {puzzle['vendor']} {puzzle['product']}")


if __name__ == "__main__":
    main()
