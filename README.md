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

No backend, no accounts, no API keys, no tracking. `index.html` is a single
self-contained file with the puzzle data baked in.

## Project layout

| File | Purpose |
| --- | --- |
| `index.html` | The built game. This is the only file that needs to be served. |
| `game.template.html` | Game source, with a `__PUZZLE_DATA__` placeholder. **Edit this, not `index.html`.** |
| `puzzles.json` | Generated puzzle data (CVE, description, score, vector). |
| `build_puzzles.py` | Pulls fresh CVE data from NVD + CISA KEV. |
| `build_site.py` | Inlines `puzzles.json` into the template to produce `index.html`. |
| `build_quips.py` | Source of the 210 end-of-game quips; regenerates the block in the template. |
| `play.sh` | Serve locally and open a browser. |

## Deploying to GitHub Pages

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin github-personal:dLEatEaD/cvssdle.git
git push -u origin main
```

Then in the repo: **Settings → Pages → Source: Deploy from a branch →
`main` / `(root)`**. It'll be live at
`https://dleatead.github.io/cvssdle/` within a minute.

Update the play URL at the top of this README once it's live.

## Refreshing the puzzle pool

The KEV catalog grows constantly, so regenerate whenever you want new content:

```bash
python3 build_puzzles.py --limit 400   # re-pull from NVD + CISA
python3 build_site.py                  # rebuild index.html
```

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
./play.sh          # serves on :8777 and opens your browser
./play.sh 9000     # or pick a port
```

Or rebuild and serve manually:

```bash
python3 build_site.py
python3 -m http.server 8777
# open http://localhost:8777
```

`index.html` also works when opened directly from disk, since the data is
inlined rather than fetched.

## Data sources & licence

Vulnerability data comes from the [NVD](https://nvd.nist.gov/) and
[CISA KEV](https://www.cisa.gov/known-exploited-vulnerabilities-catalog), both
US government public-domain sources. The game code is MIT licensed.

CVSS is a standard from [FIRST](https://www.first.org/cvss/). This project isn't
affiliated with FIRST, NIST, or CISA.
