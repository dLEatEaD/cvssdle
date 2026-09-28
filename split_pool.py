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
import json
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

HERE = Path(__file__).parent
SOURCE = HERE / "puzzles.json"
PRACTICE_OUT = HERE / "puzzles.practice.json"
DAILY_OUT = HERE / "puzzles.daily.enc"


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


def partition(puzzles: list, practice_n: int) -> tuple[list, list]:
    """Split into practice and daily pools, keeping related CVEs together.

    Vendors often file several CVEs from one advisory with near-identical
    descriptions (e.g. CVE-2021-20022 and -20023). If such a pair straddles the
    two pools, playing the practice one telegraphs the daily. So group by
    description prefix first and assign whole groups.

    puzzles.json is already interleaved across score bands by build_puzzles.py,
    so walking groups in order preserves that spread in both halves.
    """
    if practice_n >= len(puzzles):
        sys.exit("practice pool must be smaller than the full pool")

    groups: dict[str, list] = {}
    for p in puzzles:
        groups.setdefault(p["desc"][:60], []).append(p)

    practice, daily = [], []
    # Take every Nth group for practice so the score spread survives grouping.
    stride = max(1, round(len(groups) / practice_n))
    for i, members in enumerate(groups.values()):
        if i % stride == 0 and len(practice) + len(members) <= practice_n:
            practice.extend(members)
        else:
            daily.extend(members)

    if not practice or not daily:
        sys.exit("partition produced an empty pool - adjust --practice")
    return practice, daily


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--practice", type=int, default=100,
                    help="how many puzzles to reserve for practice mode")
    ap.add_argument("--new-key", action="store_true",
                    help="print a fresh base64 key and exit")
    args = ap.parse_args()

    if args.new_key:
        print(base64.b64encode(os.urandom(32)).decode())
        return

    key = load_key()
    puzzles = json.loads(SOURCE.read_text())
    practice, daily = partition(puzzles, args.practice)

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

    print(f"practice pool : {len(practice):>3} puzzles -> {PRACTICE_OUT.name}")
    print(f"daily pool    : {len(daily):>3} puzzles -> {DAILY_OUT.name} "
          f"({len(blob) / 1024:.0f} KB encrypted)")
    print(f"daily pool lasts ~{len(daily) / 365:.1f} years")


if __name__ == "__main__":
    main()
