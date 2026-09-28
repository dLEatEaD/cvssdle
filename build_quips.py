#!/usr/bin/env python3
"""Regenerate the VERDICTS / LOSS_QUIPS block in game.template.html.

Keeping the quip lists here rather than hand-editing the HTML makes it easy
to add more later: edit the lists, re-run, then run build_site.py.
"""

import json
import re
from pathlib import Path

HERE = Path(__file__).parent
TARGET = HERE / "game.template.html"
REQUIRED = 30

TIERS = {
    1: ("Nailed it \U0001F389", [
        "First guess. Either you know CVSS cold or you wrote this advisory.",
        "One shot. The scoring rubric fears you.",
        "Straight to the number. Nothing left to calculate.",
        "Called it blind. The whole game, beaten in one move.",
        "No hints, no hedging, no second attempt. Filthy.",
        "That is not scoring, that is recall.",
        "You skipped triage entirely and went straight to the verdict.",
        "Zero wrong guesses. Your MTTR is theoretical at this point.",
        "Perfect. Suspiciously perfect.",
        "Either brilliant or you have this CVE bookmarked.",
        "One guess. Somewhere a vulnerability analyst felt a chill.",
        "You did not need the vector. You are the vector.",
        "Instant. No deliberation. Slightly unsettling.",
        "First try. Please do not tell the rest of the team, they will feel bad.",
        "That was less a guess and more a diagnosis.",
        "Clean kill. No collateral guesses.",
        "You closed this ticket before it was assigned.",
        "Flawless. Put it on the performance review.",
        "One attempt. Even the CVSS calculator is impressed.",
        "Textbook. Genuinely, that is what the textbook says.",
        "You read eight words of description and produced the exact base score.",
        "No warm-up guess. Just the answer. Cold.",
        "That is the kind of precision that gets you volunteered for on-call.",
        "Straight through. Not even a bracketing guess for show.",
        "Immaculate. The severity never stood a chance.",
        "You have clearly scored a few of these before. Or several hundred.",
        "Called on the first pitch. No notes.",
        "Direct hit. The rest of us need six tries and a coffee.",
        "One and done. The advisory should have just asked you.",
        "That is base-score clairvoyance and we are all a bit concerned.",
    ]),
    2: ("Two guesses \U0001F3AF", [
        "One bracket, then the kill. Efficient.",
        "Bisected it like a pro. Barely needed the hints.",
        "Two moves. Most people are still reading the description.",
        "Quick triage, correct severity. Ship it.",
        "Ranged it, then nailed it. Textbook method.",
        "One probe, one answer. That is how it is supposed to work.",
        "Two guesses is basically one guess with a safety net.",
        "You bracketed and closed. Very tidy.",
        "Barely a hint used. Respectable.",
        "That is a sub-hour response time in ticket terms.",
        "Fast. The vector had one metric showing and that was plenty.",
        "Found the range, then the number. No wasted motion.",
        "Two tries. Practically a first guess with extra steps.",
        "Sharp. You clearly know where the network-vector scores land.",
        "Minimal guessing, maximum result. Good instincts.",
        "You calibrated once and converged. Solid method.",
        "Efficient enough that nobody will ask follow-up questions.",
        "One warm-up, then straight to the answer.",
        "Two. That is the polite number of guesses.",
        "Quick work. Whoever wrote this advisory was not subtle.",
        "You narrowed and struck. The way the game intends.",
        "Barely broke stride. That is the good stuff.",
        "Two guesses and a confident click. Very SOC-analyst of you.",
        "Almost perfect, and honestly close enough to brag about.",
        "Dialled in fast. The scoring gods approve.",
        "One miss to calibrate, then done. That is skill, not luck.",
        "Clean. You would pass an audit on that methodology.",
        "Short and decisive. The rest of us are still squinting at the vector.",
        "Two tries. Statistically, you are showing off.",
        "You treated it like a bisect and it worked perfectly.",
    ]),
    3: ("Three guesses \U0001F44D", [
        "Solid. That is a respectable mean time to resolution.",
        "Three tries, well within SLA.",
        "Converged nicely. The vector hints did their job.",
        "Comfortably inside the window. No escalation needed.",
        "Textbook convergence. Nothing to flag in the post-mortem.",
        "Three guesses is the honest answer most days.",
        "Good process. Bracket, narrow, close.",
        "That is a perfectly defensible number of attempts.",
        "Right down the middle. Nobody is filing a complaint.",
        "Three. The number of a person who reads the vector properly.",
        "Nicely triaged. You used the hints like they were intended.",
        "That is the median analyst experience and there is no shame in it.",
        "Efficient without being smug about it.",
        "Three attempts, correct result, zero drama.",
        "You worked the problem instead of guessing wildly. It shows.",
        "Squarely competent. We will take it.",
        "Good instincts on the scope change, that is what got you there.",
        "Three tries. Well inside the acceptable risk threshold.",
        "Methodical. Slightly slow. Entirely correct.",
        "That is what a calm Tuesday looks like.",
        "You converged without panicking. Underrated skill.",
        "Three guesses and a correct score. Case closed.",
        "Reliable work. The kind that never makes the incident report.",
        "Not flashy, but nobody is going to second-guess it.",
        "Halfway through the hints and you had it. Good pace.",
        "That is a solid, employable score.",
        "Three. Respectable, repeatable, no notes.",
        "You did the actual arithmetic and it paid off.",
        "Competent throughout. The advisory put up a mild fight.",
        "Good enough that we will not review the tape.",
    ]),
    4: ("Four guesses \U0001F605", [
        "Got there. We are not going to audit the methodology.",
        "Four tries is still a pass. Barely.",
        "You brute-forced the base score. Effective, if inelegant.",
        "Found it eventually. Let us call that thorough analysis.",
        "Half the vector was showing, but a win is a win.",
        "That is more of a negotiation than a calculation.",
        "Four attempts. The SLA is technically still green.",
        "You got there the long way round. Scenic, even.",
        "Correct, eventually. We will put that in the summary.",
        "Four guesses. Nobody needs to know the exact number.",
        "The hints carried you a bit there, but you closed it out.",
        "That is well within tolerance, if slightly sweaty.",
        "You circled it a few times before landing. Fine. Acceptable.",
        "Four. The number of someone who second-guessed a correct instinct.",
        "Persistence over precision. Still counts.",
        "You needed half the vector, but you did use it well.",
        "Correct answer, moderate detour.",
        "Four tries. The score was always going to lose eventually.",
        "A bit of flailing, then a clean finish.",
        "Not your finest work, but the ticket is closed.",
        "You got the scope change wrong the first time. Everyone does.",
        "Four guesses. We will call it due diligence.",
        "The long way, but the right way. Sort of.",
        "Solid effort. Slightly extended timeline.",
        "You wore it down. That is a legitimate strategy.",
        "Four attempts and a correct result. Rounding up to good.",
        "A little wobble in the middle there, but you recovered.",
        "That is a passing grade with a note in the margin.",
        "You found it. The method remains a mystery.",
        "Correct. Eventually. Emphatically eventually.",
    ]),
    5: ("Five guesses \U0001F62C", [
        "Cutting it fine. One more and this was an incident.",
        "Five. At this point the vector was basically the answer key.",
        "You had seven of eight metrics. But you got there.",
        "That is less scoring and more negotiating.",
        "Five guesses. We are counting this as a near miss.",
        "The hints did most of the work and we both know it.",
        "One guess from disaster. Great recovery, questionable route.",
        "Five attempts. That is an escalation waiting to happen.",
        "You were running out of runway there.",
        "Technically a win. Spiritually a warning.",
        "Five. The vector had practically spelled it out.",
        "That was uncomfortably close to a loss.",
        "You got there with one guess in reserve. One.",
        "A win, but the post-mortem will have action items.",
        "Five tries. The SLA clock was flashing amber.",
        "You brute-forced it with the answer key open. Still counts.",
        "That is a correct result and a concerning process.",
        "Nearly went to six. Let us not discuss it further.",
        "Five guesses. The CVSS calculator would have been faster.",
        "You squeaked it. Genuinely squeaked it.",
        "Correct, but the margin was thin enough to see through.",
        "The last two hints were doing heavy lifting.",
        "Five. Somewhere between perseverance and stubbornness.",
        "A win with an asterisk the size of the scoreboard.",
        "You survived. The methodology did not.",
        "Five attempts. File under lessons learned.",
        "That is the kind of win you do not post in the channel.",
        "Close call. The vulnerability nearly won.",
        "Five tries and the full vector. But your name is on the win.",
        "Barely. Genuinely, barely.",
    ]),
    6: ("Six guesses \U0001F613", [
        "The entire vector was showing. We both know what happened.",
        "Last possible guess. Technically a win. Technically.",
        "Six of six. Add it to the risk register.",
        "Scraped in on the final attempt. No notes. Actually, several.",
        "You had every metric revealed. Every single one.",
        "That is not a win, that is a hostage negotiation.",
        "Six guesses. The answer key was fully open on the last one.",
        "Final attempt. The margin was zero.",
        "You got there with nothing left in the tank.",
        "Six. We are calling that a controlled landing.",
        "Correct on the buzzer. Deeply stressful to watch.",
        "The whole vector was visible and it still took the last guess.",
        "A win, in the way that surviving a car crash is a win.",
        "Six attempts. The incident report writes itself.",
        "You exhausted every hint and every try. But you did it.",
        "That was a full-vector, full-guess, full-panic finish.",
        "Last guess, correct answer, no dignity.",
        "Six. The CVSS calculator is laughing somewhere.",
        "Technically successful. Procedurally alarming.",
        "You took it to the wire and the wire nearly won.",
        "Every metric shown, every guess used. Peak effort.",
        "That is a win the way a 4am page is a learning opportunity.",
        "Final try. Somewhere a manager is asking about process improvements.",
        "Six guesses to score one CVE. Do not put that in the metrics deck.",
        "You got there. The journey was harrowing.",
        "Last attempt. We will take the result and ignore the path.",
        "Maximum guesses, minimum elegance, correct answer.",
        "That is the definition of scraping through.",
        "Six. Let us just be glad it is over.",
        "A win is a win. This one just needed a lot of scaffolding.",
    ]),
}

LOSS = ("Out of guesses", [
    "The vector was right there the whole time.",
    "Mark it risk-accepted and move on.",
    "Some vulnerabilities just refuse to be scored.",
    "This one goes in the backlog. Permanently.",
    "Six guesses, no match. CVSS remains undefeated.",
    "Every metric revealed and still no luck. Brutal.",
    "File an exception request and pretend this never happened.",
    "That one is going straight to the compensating controls pile.",
    "Not today. The base score wins this round.",
    "Six attempts, zero hits. We have all been there.",
    "The vulnerability survives. Patch it out of spite.",
    "No match. Blame the scoring rubric, everyone does.",
    "This is why we have a CVSS calculator.",
    "Swing and a miss. Six times.",
    "The scope metric got you, did it not. It always does.",
    "Unresolved. Escalating to tomorrow.",
    "You had the full vector and it still slipped away.",
    "Zero for six. Statistically, that takes effort.",
    "The CVE wins. Better luck with tomorrow's.",
    "Sometimes the impact metrics just do not add up the way you expect.",
    "No result. Log it and try again tomorrow.",
    "That one was genuinely nasty. Take the loss with dignity.",
    "Six guesses gone, severity unresolved. Classic.",
    "Defeated by arithmetic. It happens to the best of us.",
    "The answer was never where you were looking.",
    "Out of tries. The vulnerability remains gloriously unscored.",
    "Not a great day for your remediation stats.",
    "Consider this one accepted risk and move along.",
    "Six attempts. The base score did not blink once.",
    "Tomorrow is another CVE. This one belongs to the void.",
])


def js_array(items: list[str], indent: str) -> str:
    return "\n".join(f"{indent}{json.dumps(s, ensure_ascii=False)}," for s in items)


def main() -> None:
    for n, (_, quips) in TIERS.items():
        assert len(quips) >= REQUIRED, f"tier {n} has {len(quips)}"
        assert len(set(quips)) == len(quips), f"tier {n} has duplicates"
    assert len(LOSS[1]) >= REQUIRED, f"loss has {len(LOSS[1])}"
    assert len(set(LOSS[1])) == len(LOSS[1]), "loss has duplicates"

    blocks = []
    for n, (title, quips) in TIERS.items():
        blocks.append(
            f"  {n}: {{\n"
            f"    title: {json.dumps(title, ensure_ascii=False)},\n"
            f"    quips: [\n{js_array(quips, '      ')}\n    ],\n"
            f"  }},"
        )
    verdicts = (
        "const VERDICTS = {\n" + "\n".join(blocks) + "\n};\n\n"
        "const LOSS_QUIPS = [\n" + js_array(LOSS[1], "  ") + "\n];"
    )

    text = TARGET.read_text()
    pattern = re.compile(
        r"const VERDICTS = \{.*?\n\};\n\nconst LOSS_QUIPS = \[.*?\n\];", re.S
    )
    if not pattern.search(text):
        raise SystemExit("could not locate the VERDICTS / LOSS_QUIPS block")
    TARGET.write_text(pattern.sub(lambda _: verdicts, text, count=1))

    total = sum(len(q) for _, q in TIERS.values()) + len(LOSS[1])
    print("Quips per tier:", {n: len(q) for n, (_, q) in TIERS.items()},
          "loss:", len(LOSS[1]))
    print(f"Wrote {total} quips into {TARGET.name}")


if __name__ == "__main__":
    main()
