#!/usr/bin/env python3
"""Split puzzles.json into a public practice pool and an encrypted daily pool.

The daily answers must not be readable from the public repository, so they are
committed only as AES-GCM ciphertext. The key lives in GitHub Actions secrets
and never touches the tree.

The two pools are disjoint: a daily answer can never leak by being served as a
practice puzzle.

Usage:
    export PUZZLE_KEY=$(python3 split_pool.py --new-key)
    python3 split_pool.py --practice 100
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
SOURCE = HERE / "puzzles.json"
PRACTICE_OUT = HERE / "puzzles.practice.json"
DAILY_OUT = HERE / "puzzles.daily.enc"

# Day zero of the schedule. Must match EPOCH in pick_daily.py.
EPOCH = date(2026, 1, 1)


def load_key() -> bytes:
    raw = os.environ.get("PUZZLE_KEY", "").strip()
    if not raw:
        sys.exit(
            "PUZZLE_KEY is not set.\n"
            "Generate one with:  python3 split_pool.py --new-key"
        )
    try:
        key = base64.b64decode(raw)
    except Exception:
        sys.exit("PUZZLE_KEY is not valid base64")
    if len(key) != 32:
        sys.exit(f"PUZZLE_KEY must decode to 32 bytes, got {len(key)}")
    return key


def encrypt(payload: bytes, key: bytes) -> bytes:
    """AES-256-GCM. The 12-byte nonce is prepended to the ciphertext."""
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, payload, None)


def decrypt(blob: bytes, key: bytes) -> bytes:
    return AESGCM(key).decrypt(blob[:12], blob[12:], None)


def partition(puzzles: list, practice_n: int, reserved: set | None = None,
              prior_practice: set | None = None, prior_daily: set | None = None
              ) -> tuple[list, list]:
    """Split into practice and daily pools, keeping related CVEs together.

    Vendors often file several CVEs from one advisory with near-identical
    descriptions (e.g. CVE-2021-20022 and -20023). If such a pair straddles the
    two pools, playing the practice one telegraphs the daily. So group by
    description prefix first and assign whole groups.

    Assignment is sticky. A group that already has a side keeps it, and only
    brand-new groups are assigned fresh. Without this the split depends on
    position in puzzles.json, which shifts every time the source is refreshed,
    which in turn churns the daily pool and re-dates the whole schedule.

    `reserved` holds CVE ids whose schedule positions are already spent; their
    groups are forced to the daily side regardless of anything else.
    """
    if practice_n >= len(puzzles):
        sys.exit("practice pool must be smaller than the full pool")
    reserved = reserved or set()
    prior_practice = prior_practice or set()
    prior_daily = prior_daily or set()

    groups: dict[str, list] = {}
    for p in puzzles:
        groups.setdefault(p["desc"][:60], []).append(p)

    practice, daily, unassigned = [], [], []
    for members in groups.values():
        ids = {p["id"] for p in members}
        if ids & reserved or ids & prior_daily:
            daily.extend(members)
        elif ids & prior_practice:
            practice.extend(members)
        else:
            unassigned.append(members)

    # Top practice up towards the target with new groups; the rest are dailies.
    stride = max(1, round(len(unassigned) / max(1, practice_n - len(practice)))) \
        if len(practice) < practice_n else 0
    for i, members in enumerate(unassigned):
        if stride and i % stride == 0 and len(practice) + len(members) <= practice_n:
            practice.extend(members)
        else:
            daily.extend(members)

    if not practice or not daily:
        sys.exit("partition produced an empty pool - adjust --practice")
    return practice, daily


def _rand_stream(seed: bytes, label: str):
    """Deterministic byte stream from HMAC-SHA256 in counter mode."""
    counter = 0
    while True:
        block = hmac.new(seed, f"{label}:{counter}".encode(), hashlib.sha256).digest()
        for i in range(0, 32, 4):
            yield int.from_bytes(block[i:i + 4], "big")
        counter += 1


def shuffled(items: list, seed: bytes, label: str) -> list:
    """Seeded Fisher-Yates. Same seed and label always give the same order."""
    rand = _rand_stream(seed, label)
    out = list(items)
    for i in range(len(out) - 1, 0, -1):
        j = next(rand) % (i + 1)
        out[i], out[j] = out[j], out[i]
    return out


def existing_pool(key: bytes) -> list:
    """The current daily pool, in play order. Empty if there isn't one."""
    if not DAILY_OUT.exists():
        return []
    try:
        return json.loads(decrypt(DAILY_OUT.read_bytes(), key))
    except Exception:
        return []


def elapsed_positions(today: date) -> int:
    """How many schedule positions are already spoken for, including today."""
    return max(0, (today - EPOCH).days + 1)


def daily_order(daily: list, key: bytes, seed: bytes, rebuild: bool,
                today: date) -> list:
    """Put the daily pool into play order, stable across refreshes.

    pick_daily.py reads this pool positionally, so the order has to be treated
    as a schedule rather than a list. Two rules keep it stable:

    1. Positions up to and including today are frozen verbatim. They are spent
       - already played, or in play right now - and their content no longer
       matters, but their *count* does: dropping one shifts every later day by
       a position. Entries that have since been filtered out of the source are
       therefore kept here anyway, tagged "retired" so later cycles skip them.

    2. Future positions keep their prior relative order, minus anything the
       filters now exclude, with new arrivals appended.

    Without rule 1, excluding a vendor mid-schedule silently re-dates every
    remaining puzzle and anyone mid-game has their guesses replayed against a
    different answer.

    Pass rebuild=True to discard the schedule and reshuffle from scratch.
    """
    if rebuild:
        return shuffled(daily, seed, "daily")

    prior = existing_pool(key)
    if not prior:
        return shuffled(daily, seed, "daily")

    current = {p["id"]: p for p in daily}
    freeze_n = min(len(prior), elapsed_positions(today))

    frozen = []
    for p in prior[:freeze_n]:
        if p["id"] in current:
            frozen.append(current[p["id"]])      # refresh the record in place
        else:
            frozen.append({**p, "retired": True})  # keep the slot, retire it

    # Rebuild the future from what is still eligible.
    frozen_ids = {p["id"] for p in frozen}
    remaining = {p["id"]: p for p in daily if p["id"] not in frozen_ids}
    tail = [remaining.pop(p["id"]) for p in prior[freeze_n:] if p["id"] in remaining]
    fresh = shuffled(list(remaining.values()), seed, f"append{len(frozen) + len(tail)}")

    retired = sum(1 for p in frozen if p.get("retired"))
    removed = len(prior) - freeze_n - len(tail)
    print(f"schedule: {freeze_n} positions frozen through {today}"
          + (f" ({retired} retired)" if retired else ""))
    print(f"          {len(tail)} future positions preserved, "
          f"{removed} removed, {len(fresh)} appended")
    return frozen + tail + fresh


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--practice", type=int, default=150,
                    help="how many puzzles to reserve for practice mode")
    ap.add_argument("--rebuild", action="store_true",
                    help="discard the existing schedule and reshuffle from scratch")
    ap.add_argument("--new-key", action="store_true",
                    help="print a fresh base64 key and exit")
    ap.add_argument("--date", help="override today's date (YYYY-MM-DD), for testing")
    args = ap.parse_args()

    if args.new_key:
        print(base64.b64encode(os.urandom(32)).decode())
        return

    key = load_key()
    seed = os.environ.get("PUZZLE_SEED", "").strip().encode()
    if not seed:
        sys.exit("PUZZLE_SEED is not set")

    today = (
        datetime.strptime(args.date, "%Y-%m-%d").date()
        if args.date
        else datetime.now(timezone.utc).date()
    )

    puzzles = json.loads(SOURCE.read_text())

    # Positions already spent are locked to the daily side: moving one into
    # practice would shift the schedule and hand out a past answer as practice.
    # Pool membership is otherwise sticky, so a refresh only places new CVEs.
    reserved, prior_practice, prior_daily = set(), set(), set()
    if not args.rebuild:
        prior = existing_pool(key)
        reserved = {p["id"] for p in prior[:elapsed_positions(today)]}
        prior_daily = {p["id"] for p in prior}
        if PRACTICE_OUT.exists():
            prior_practice = {p["id"] for p in json.loads(PRACTICE_OUT.read_text())}

    practice, daily = partition(puzzles, args.practice, reserved,
                                prior_practice, prior_daily)
    daily = daily_order(daily, key, seed, args.rebuild, today)

    overlap = {p["id"] for p in practice} & {p["id"] for p in daily}
    assert not overlap, f"pools overlap: {overlap}"

    # A shared description prefix across pools would let a practice puzzle
    # telegraph a future daily, so the grouping above must have prevented it.
    shared = {p["desc"][:60] for p in practice} & {p["desc"][:60] for p in daily}
    assert not shared, f"{len(shared)} description groups straddle both pools"

    PRACTICE_OUT.write_text(json.dumps(practice, separators=(",", ":")))
    blob = encrypt(json.dumps(daily, separators=(",", ":")).encode(), key)
    DAILY_OUT.write_bytes(blob)

    # Fail loudly rather than shipping a pool that cannot be opened in CI.
    assert json.loads(decrypt(blob, key)) == daily, "round-trip failed"

    print(f"practice pool : {len(practice):>4} puzzles -> {PRACTICE_OUT.name}")
    print(f"daily pool    : {len(daily):>4} puzzles -> {DAILY_OUT.name} "
          f"({len(blob) / 1024:.0f} KB encrypted)")
    print(f"daily pool lasts ~{len(daily) / 365:.1f} years")


if __name__ == "__main__":
    main()
