# CVSSdle

A daily guessing game for security teams. You get one real, actively-exploited
vulnerability from the [CISA KEV catalog](https://www.cisa.gov/known-exploited-vulnerabilities-catalog)
and six tries to guess its CVSS v3.1 base score.

Every wrong guess reveals one metric from the real CVSS vector — attack vector,
attack complexity, privileges required, and so on — so by guess four you can
stop guessing and start actually calculating. That's the hook: it's a game that
quietly drills CVSS fluency.

**Play:** https://dleatead.github.io/cvssdle/

## How it works

- One puzzle per day, identical for every player.
- ~765 puzzles in the daily pool — every one is used before any repeats,
  so the sequence runs about two years before it can come round again.
- Desktop, mobile and server OS bugs are excluded. They dominate KEV and the
  records are repetitive. Network and security appliance firmware that happens
  to be named an OS (Cisco IOS, PAN-OS, FortiOS, Junos) is deliberately kept.
- Microsoft is excluded entirely. Even after dropping Windows it was the
  largest single vendor, and the rest skewed heavily to long-dead Internet
  Explorer and Office bugs. Third-party products that merely run on Windows
  (e.g. Citrix Workspace for Windows) still qualify — those aren't Microsoft
  vulnerabilities.
- Feedback per guess: higher/lower plus a proximity band (exact / hot ≤0.5 /
  warm ≤1.5 / cold).
- Streaks, win rate, and guess distribution are kept in `localStorage`.
- Streaks are measured in missed **weekdays**, not calendar days, because
  this is played at work: Friday to Monday is a three-day gap but zero
  missed weekdays, so it continues the streak. Weekend play counts and
  never hurts, it just isn't required.
- Shareable emoji result grid, Wordle-style.
- **Partial credit**: running out of guesses while within half a point is
  reported as a near miss rather than a flat loss. It is deliberately *not* a
  win — win rate and streaks keep meaning exactly what they say — but landing
  that close is real CVSS skill and is worth telling apart from a wild miss.
- **Challenge links**: your result is encoded in the URL hash, so sending it to
  a colleague shows them how you did and invites them to try the same puzzle.
  No backend, nothing stored, and the answer is never in the link.
- 210 end-of-game quips: only a first-guess win earns "Nailed it", and each
  of the other outcomes has 30 of its own.
- Practice mode for unlimited extra puzzles.

- Dark SOC-console theme by default (near-black navy `#030711`, sky-blue
  `#0da2e7`), with a light mode toggle.

No backend, no accounts, no tracking. `index.html` is a single self-contained
file — no external requests at runtime.

## How the answers stay hidden

A static site has to hand the browser today's score to give higher/lower
feedback, so **today's answer is readable from view-source**. That much is
unavoidable without a server, and the game is built on the honour system.

What *is* avoidable is leaking every *future* answer, which the original build
did by shipping all 400 puzzles and selecting one client-side. Instead:

- The daily pool is committed only as AES-256-GCM ciphertext. The key lives in
  Actions secrets, never in the tree.
- A scheduled workflow decrypts it, picks one puzzle, and publishes a build
  containing **that one answer**. Tomorrow's is simply not in the artifact.
- Selection is `HMAC-SHA256(seed, date)` over a per-cycle shuffle, so every
  puzzle is used once before any repeat and the order is unguessable without
  the seed.
- The practice pool ships in the clear but is disjoint from the daily pool, and
  same-advisory CVEs are kept in one pool so a practice puzzle can't telegraph
  a daily.
- `verify_build.py` fails the build if any future answer appears.

## Project layout

| File | Purpose |
| --- | --- |
| `game.template.html` | Game source. **Edit this** — `index.html` is generated. |
| `puzzles.practice.json` | Practice pool, in the clear. Spoilable by design. |
| `puzzles.daily.enc` | Daily pool, AES-256-GCM. Opened only in CI. |
| `build_puzzles.py` | Pulls fresh CVE data from NVD + CISA KEV into `puzzles.json`. |
| `split_pool.py` | Splits `puzzles.json` into the practice and encrypted daily pools. |
| `pick_daily.py` | Selects today's puzzle from the daily pool. Runs in CI. |
| `build_site.py` | Builds `index.html` from the template, today's puzzle, and the practice pool. |
| `verify_build.py` | CI gate: proves no future answers reached the build. |
| `check_compat.py` | CI gate: saved games from the live site must still load. |
| `check_playable.py` | CI gate: plays a round and asserts the core loop works. |
| `check_streaks.py` | CI gate: streaks must survive weekends. |
| `check_social.py` | CI gate: partial credit and challenge links. |
| `check_workflows.py` | CI gate: workflow steps must pass the secrets their scripts need. |
| `check_schedule.py` | CI gate: cron, countdown and EPOCH must agree. |
| `build_quips.py` | Source of the 210 end-of-game quips. |
| `play.sh` | Serve locally and open a browser. |

`index.html`, `puzzles.json` and `today.json` are generated and gitignored.

## Environments

| | URL | Built from |
| --- | --- | --- |
| Production | `https://dleatead.github.io/cvssdle/` | `main` |
| Staging | `https://dleatead.github.io/cvssdle/preview/` | `preview` branch |

Pages allows one deployment source, so both are published from a single
artifact. The preview build is isolated and non-fatal: if it fails, the
workflow warns and production ships anyway. Production is always built from
`main` regardless of which branch triggered the run, so pushing to `preview`
cannot publish preview code to the live URL.

The `github-pages` environment is restricted to `main`, so a push to `preview`
runs the tests but cannot deploy. The preview site is rebuilt from the
`preview` branch on every publish run, so it refreshes on the next push to
`main`, the next scheduled run, or an on-demand run from the Actions tab
(Actions → Publish daily puzzle → Run workflow).

Work lands on `preview` first:

```bash
git switch -c preview        # first time only
git push -u origin preview
```

Then merge to `main` once it has been played.

The daily publish deliberately runs only the light checks - it is the job
players depend on, so it carries no browser dependency. The heavier gates
(`check_compat.py`, `check_playable.py`) run in `ci.yml` on every push, where a
failure blocks a bad change rather than blocking today's puzzle.

## Deploying to GitHub Pages

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin github-personal:dLEatEaD/cvssdle.git
git push -u origin main
```

Then:

1. **Settings → Pages → Source: GitHub Actions** (not "Deploy from a branch").
2. **Settings → Secrets and variables → Actions** and add:
   - `PUZZLE_KEY` — from `python3 split_pool.py --new-key`
   - `PUZZLE_SEED` — any long random string
   - `NVD_API_KEY` — optional, speeds up the monthly refresh

The daily workflow publishes at 05:05 UTC (midnight Central). Change the cron
in `.github/workflows/daily.yml` and `ROLLOVER_UTC` in `build_site.py` together
if you want a different time. Run it by hand from the Actions tab any time.

## Refreshing the puzzle pool

The KEV catalog grows constantly, so regenerate whenever you want new content:

The `Refresh puzzle pool` workflow does this monthly and opens a PR. By hand:

```bash
export PUZZLE_KEY=...                  # same value as the repo secret
python3 build_puzzles.py               # re-pull from NVD + CISA
python3 split_pool.py --practice 150   # re-split and re-encrypt
```

Re-splitting reshuffles which puzzles are dailies, so the sequence changes from
the next publish onwards.

To change the end-of-game messages, edit the lists in `build_quips.py`, then:

```bash
python3 build_quips.py   # rewrites the block in game.template.html
python3 build_site.py    # rebuild index.html
```

No API key is required. NVD rate-limits anonymous callers to 5 requests per 30
seconds, which makes a full pull take a couple of minutes. A
[free NVD API key](https://nvd.nist.gov/developers/request-an-api-key) raises
that to 50 per 30 seconds:

```bash
python3 build_puzzles.py --api-key YOUR_KEY
```

Don't commit the key — pass it on the command line or via an environment
variable in CI.

### Tuning the content

`build_puzzles.py` has two filters: `KNOWN_VENDORS`, which keeps the pool to
vendors a security team will recognise, and `is_operating_system()`, which
drops desktop/mobile/server OS entries. Adjust either to taste. The script
also interleaves the pool across score bands so the answer isn't a 9.8 four
days out of five.

By default it keeps everything eligible; pass `--limit N` to cap the pool.

## Local development

```bash
python3 build_site.py   # without PUZZLE_KEY this stands in a practice puzzle
./play.sh               # serves on :8777 and opens your browser
```

With `PUZZLE_KEY` and `PUZZLE_SEED` set you can build the real daily locally:

```bash
python3 pick_daily.py --date 2026-10-01
python3 build_site.py
```

`index.html` also works when opened directly from disk, since the data is
inlined rather than fetched.

## Data sources & licence

Vulnerability data comes from the [NVD](https://nvd.nist.gov/) and
[CISA KEV](https://www.cisa.gov/known-exploited-vulnerabilities-catalog), both
US government public-domain sources. The game code is MIT licensed.

CVSS is a standard from [FIRST](https://www.first.org/cvss/). This project isn't
affiliated with FIRST, NIST, or CISA.
