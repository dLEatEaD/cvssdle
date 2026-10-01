#!/usr/bin/env python3
"""CI gate: every workflow step must pass the env vars its script requires.

A script that reads PUZZLE_SEED from a workflow that only passes PUZZLE_KEY
fails at runtime, days later, in a job nobody is watching. That happened to the
monthly refresh. This matches the secrets each script needs against the ones
each step actually provides.
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
WORKFLOWS = HERE / ".github" / "workflows"

# Environment variables each script requires in order to run at all.
REQUIRES = {
    "split_pool.py": {"PUZZLE_KEY", "PUZZLE_SEED"},
    "pick_daily.py": {"PUZZLE_KEY", "PUZZLE_SEED"},
    "verify_build.py": {"PUZZLE_KEY"},
    "build_site.py": set(),
    "build_puzzles.py": set(),
    "check_schedule.py": set(),
    "check_compat.py": set(),
    "check_playable.py": set(),
    "check_workflows.py": set(),
}

STEP_SPLIT = re.compile(r"\n      - ")
# Walk the env: block line by line rather than regex-matching it whole, so a
# comment or blank line inside the block does not truncate the match.
ENV_NAME = re.compile(r"^\s+([A-Z][A-Z0-9_]*):")


def env_names(step: str) -> set:
    """Names declared under this step's `env:` key."""
    names, inside, indent = set(), False, None
    for line in step.splitlines():
        stripped = line.strip()
        if not inside:
            if stripped == "env:":
                inside = True
                indent = len(line) - len(line.lstrip())
            continue
        if not stripped or stripped.startswith("#"):
            continue
        depth = len(line) - len(line.lstrip())
        if depth <= indent:          # dedent: the env block has ended
            break
        m = ENV_NAME.match(line)
        if m:
            names.add(m.group(1))
    return names


def main() -> None:
    problems = []
    checked = 0

    for wf in sorted(WORKFLOWS.glob("*.yml")):
        text = wf.read_text()
        for step in STEP_SPLIT.split(text):
            scripts = {
                s for s in REQUIRES
                if re.search(rf"python3?\s+{re.escape(s)}", step)
            }
            if not scripts:
                continue
            # --new-key needs no secrets; it only prints one.
            if "--new-key" in step:
                continue
            provided = env_names(step)
            for script in sorted(scripts):
                checked += 1
                missing = REQUIRES[script] - provided
                if missing:
                    label = re.search(r"name:\s*(.+)", step)
                    where = label.group(1).strip() if label else step.strip()[:40]
                    problems.append(
                        f"{wf.name}: step '{where}' runs {script} "
                        f"without {', '.join(sorted(missing))}"
                    )

    if problems:
        for p in problems:
            print("FAIL:", p)
        sys.exit(f"{len(problems)} workflow steps are missing required secrets")

    print(f"OK: {checked} workflow script invocations have the secrets they need")


if __name__ == "__main__":
    main()
