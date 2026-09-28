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

- One puzzle per day, identical for every player, rolls over at local midnight.
- 400 puzzles in the pool — every one is used before any repeats.
- Feedback per guess: higher/lower plus a proximity band (exact / hot ≤0.5 /
  warm ≤1.5 / cold).
- Streaks, win rate, and guess distribution are kept in `localStorage`.
- Shareable emoji result grid, Wordle-style.
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
| `build_quips.py` | Source of the 210 end-of-game quips. |
| `play.sh` | Serve locally and open a browser. |

`index.html`, `puzzles.json` and `today.json` are generated and gitignored.

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
python3 build_puzzles.py --limit 400   # re-pull from NVD + CISA
python3 split_pool.py --practice 100   # re-split and re-encrypt
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

`build_puzzles.py` has a `KNOWN_VENDORS` set that filters the pool down to
vendors a security team will actually recognise. Add or remove entries there to
taste. The script also balances the pool across score bands so the answer isn't
a 9.8 four days out of five.

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
