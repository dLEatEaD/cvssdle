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

# Shown when the player ran out of guesses but landed within 0.5 of the answer.
# Deliberately not a win - but being half a point out is genuinely good CVSS
# work and deserves to be told apart from a wild miss.
NEAR = ("So close \U0001F91E", [
    "Within half a point. That is a correct severity call by any practical measure.",
    "Close enough that a real triage would have reached the same decision.",
    "Half a point out. The rubric split hairs with you.",
    "You had the shape of it exactly right.",
    "That is the right answer with a rounding dispute attached.",
    "Near miss. Your instincts were sound, the arithmetic was unlucky.",
    "So close the difference would not change a single remediation priority.",
    "A fraction out. Nobody would argue with your triage.",
    "You read the vector correctly and landed a whisker away.",
    "That margin is smaller than most vendors' own disagreements.",
    "Close enough to be right in every way that matters operationally.",
    "Half a point. Somewhere a CVSS calculator is being smug.",
    "You were in the right neighbourhood and knocked on the wrong door.",
    "Correct severity band, wrong decimal. Take the moral victory.",
    "That is a miss on paper and a hit in practice.",
    "Painfully close. The kind of miss that stings more than a bad guess.",
    "You bracketed it perfectly and still could not land it.",
    "A near miss at this range is skill, not luck.",
    "So close the scoring guide would call it a judgement call.",
    "That is within the margin most analysts argue over anyway.",
    "Nearly. The vector was telling you the truth and you nearly heard it.",
    "Half a point adrift, and a perfectly defensible answer.",
    "You would pass peer review with that, just not this game.",
    "Close. Genuinely, respectably close.",
    "That one was decided by a single metric value.",
    "A hair out. Your reasoning was right.",
    "So near. The base score was being needlessly precise.",
    "Within half a point and out of guesses. Brutal combination.",
    "You found the right answer and then walked past it.",
    "That is the best kind of loss. Still a loss, mind.",
])


# Vector mode has four tries and is scored on metrics, not a number, so it
# needs its own pools: a score-mode line like "six attempts" is simply wrong
# here, and "you brute-forced it" is the one thing vector mode makes impossible.
VECTOR_TIERS = {
    1: ("Vector nailed \U0001F9E9", [
        "Eight metrics, first attempt, no reveals. That is the whole rubric from memory.",
        "One submission. You did not guess that, you derived it.",
        "First try on 2,592 combinations. There is no lucky version of that.",
        "Straight to the vector. The advisory never stood a chance.",
        "You read it once and scored it exactly. That is the job, done properly.",
        "No feedback, no hints, eight for eight. Genuinely elite.",
        "Perfect vector, first pass. Somewhere a CVSS working group member nods.",
        "That is not scoring, that is fluency.",
        "You built the answer before the game could tell you anything.",
        "One attempt. Every metric. Nothing to correct.",
        "Clean sheet on the first submission. No notes.",
        "You skipped the iteration entirely and just knew it.",
        "Eight correct metrics with zero information. Show-off.",
        "First-pass exact vector. This is the hardest thing the game asks for.",
        "You did not need the feedback loop. You are the feedback loop.",
        "Flawless. The kind of result that makes people check the code for bugs.",
        "Called every metric blind. The advisory was an open book.",
        "That is a vector built from understanding, not elimination.",
        "One shot, eight metrics, full marks. Absurd.",
        "You scored it the way NVD scored it, on the first go.",
        "No trial, no error, just the answer.",
        "Perfect first vector. Your triage queue must be a peaceful place.",
        "Eight out of eight, cold. That is the ceiling of this game.",
        "You read the words and produced the exact vector. Remarkable.",
        "First attempt. The search space did not get a say.",
        "That is the rubric internalised, not memorised.",
        "Immaculate. One submission and the whole vector fell out correct.",
        "You have clearly done this for a living.",
        "Eight metrics, one try, no help. Take the rest of the day.",
        "A first-attempt vector is the real high score. You just set it.",
    ]),
    2: ("Vector solved \U0001F9E9", [
        "Two attempts. One probe, one correction, done.",
        "You found the shape immediately and fixed the rest.",
        "Second try. That is efficient reading, not luck.",
        "One miss to calibrate, then the full vector. Textbook.",
        "Quick convergence. You knew which metric was wrong before the game said so.",
        "Two submissions for eight metrics. Comfortable.",
        "You corrected the right thing first time. That is the skill.",
        "A single adjustment and the whole vector locked in.",
        "Two tries, no flailing. You were reasoning, not sampling.",
        "That is how someone who actually reads advisories plays it.",
        "Second attempt exact. The first one was basically right anyway.",
        "You spent one guess learning and one guess winning.",
        "Clean. Two passes and the vector was yours.",
        "Minimal correction, maximum result.",
        "You identified your own error faster than the feedback did.",
        "Two attempts on 2,592 combinations is genuinely strong.",
        "Nearly first-try. The near-first-try is underrated.",
        "One nudge was all it needed. Confident work.",
        "Second submission, perfect vector. No wasted motion.",
        "You read the description properly. It shows.",
        "That is a tight loop. One hypothesis, one fix.",
        "Two tries. The rubric put up almost no resistance.",
        "Solid. You were never actually lost.",
        "A single wrong metric, then a flawless vector.",
        "Fast and deliberate. The good combination.",
        "You did not brute-force anything. There is nothing to brute-force.",
        "Two attempts and done. Quietly impressive.",
        "Efficient. You treated the first attempt as information, not a gamble.",
        "Second-try vector. Comfortably above the curve.",
        "You narrowed eight unknowns in one move. That is real CVSS work.",
    ]),
    3: ("Vector solved \U0001F9E9", [
        "Three attempts. You worked it out, metric by metric.",
        "Methodical. Every pass got you closer and you finished it.",
        "That is proper iterative scoring. Nothing wrong with earning it.",
        "Three tries, full vector. The process worked.",
        "You kept the metrics that landed and fixed the ones that did not.",
        "Patient work. The vector came apart under pressure.",
        "Three passes to eight correct metrics. Respectable.",
        "You used the feedback exactly the way it is meant to be used.",
        "Not flashy, but completely correct. That counts.",
        "Steady convergence. No panic, no scattergun.",
        "Three attempts and a perfect vector. Earned.",
        "You narrowed it properly instead of guessing wildly.",
        "That is what reading the advisory twice gets you.",
        "Solved with one try to spare. Comfortable enough.",
        "Three rounds of honest reasoning. Good result.",
        "You held your nerve on the metrics you had right.",
        "The long way round, but the vector is exact.",
        "Three tries. The rubric made you work and you did.",
        "Incremental and correct. Nothing to apologise for.",
        "You debugged your own vector. That is the exercise.",
        "Three attempts, eight metrics, zero errors at the end.",
        "A real solve. You reasoned your way there.",
        "Took some doing. You did it.",
        "Three passes and the advisory gave it up.",
        "You converged. That is all the game asks.",
        "Good discipline. You changed one thing at a time.",
        "Three tries on 2,592 combinations is still a strong result.",
        "The vector resisted, briefly.",
        "Worked for it, got it. The best kind of win.",
        "Three attempts. Solid, unglamorous, correct.",
    ]),
    4: ("Vector solved \U0001F9E9", [
        "Last attempt. That was uncomfortably close to a loss.",
        "Four tries, final submission, exact vector. Clutch.",
        "You got there on the last possible move. Take it.",
        "Right at the buzzer. The vector nearly got away.",
        "Final attempt, full marks. Nerve held.",
        "That is the narrowest possible win and it counts the same.",
        "Four tries. You spent every one of them and earned it.",
        "Down to the last submission and you landed it.",
        "Hard-fought. Eight metrics do not always come quietly.",
        "You were one wrong metric from nothing. You found it.",
        "Final-try vector. Genuinely tense.",
        "That advisory did not want to be scored. You scored it anyway.",
        "No tries left and no errors left. Perfect timing.",
        "You used the whole budget. That is what it is for.",
        "Four attempts, exact vector, zero margin.",
        "Scraped it. A win is a win and this one was work.",
        "The last submission was the right one. Barely.",
        "You fixed the final metric with nothing in reserve.",
        "Four tries. The rubric made you suffer for that.",
        "Clutch solve. Those stay with you longer than the easy ones.",
        "Right on the edge. Exactly where the good ones happen.",
        "You held it together when it mattered.",
        "Final attempt exact. That is a real comeback.",
        "Four passes to prise eight metrics loose. Well done.",
        "No room left at all. Still correct.",
        "You earned that one the hard way.",
        "Last try, full vector. The best kind of relief.",
        "That was going badly right up until it was not.",
        "Four attempts and a perfect finish. Hard-won.",
        "The vector held out as long as it could.",
    ]),
}

VECTOR_LOSS = ("Vector unsolved", [
    "Four attempts and the vector kept at least one secret.",
    "Eight metrics is a lot to be right about all at once.",
    "Close on most of them is still wrong on the whole.",
    "The vector wins this round. It usually does.",
    "You had most of it. The rubric only accepts all of it.",
    "One stubborn metric, and that is the whole game.",
    "This is the hard mode, and it just demonstrated why.",
    "No shortcuts here. That is the point, and it bit.",
    "The advisory was vaguer than the vector it produced.",
    "Scope and impact are where these usually come apart.",
    "You were reasoning correctly about the wrong metric.",
    "Four tries, 2,592 combinations. The odds were always rude.",
    "The answer was in the description. It just was not obvious.",
    "Some vectors only make sense after you see them.",
    "Even NVD analysts argue about a few of these.",
    "Not today. The metrics held the line.",
    "You will recognise this pattern next time.",
    "That one rewarded a reading nobody would call natural.",
    "Out of attempts, not out of understanding.",
    "The vector was more pedantic than the vulnerability deserved.",
    "Partial credit is not a thing here. Harsh, but honest.",
    "Eight simultaneous judgement calls. One of them went.",
    "The exploit was clear. Its scoring was not.",
    "You lost to a single metric value. Infuriating.",
    "Tomorrow's vector will be more reasonable. Probably not.",
    "This is why vector mode exists. It is genuinely hard.",
    "The rubric is unmoved by how close you were.",
    "Four passes and it still would not resolve.",
    "Some advisories are written to defeat exactly this.",
    "Beaten by the vector. There is no shame in that one.",
])


def js_array(items: list[str], indent: str) -> str:
    return "\n".join(f"{indent}{json.dumps(s, ensure_ascii=False)}," for s in items)


def main() -> None:
    for n, (_, quips) in TIERS.items():
        assert len(quips) >= REQUIRED, f"tier {n} has {len(quips)}"
        assert len(set(quips)) == len(quips), f"tier {n} has duplicates"
    assert len(LOSS[1]) >= REQUIRED, f"loss has {len(LOSS[1])}"
    assert len(set(LOSS[1])) == len(LOSS[1]), "loss has duplicates"
    assert len(NEAR[1]) >= REQUIRED, f"near has {len(NEAR[1])}"
    assert len(set(NEAR[1])) == len(NEAR[1]), "near has duplicates"
    for n, (_, quips) in VECTOR_TIERS.items():
        assert len(quips) >= REQUIRED, f"vector tier {n} has {len(quips)}"
        assert len(set(quips)) == len(quips), f"vector tier {n} has duplicates"
    assert len(VECTOR_LOSS[1]) >= REQUIRED, f"vector loss has {len(VECTOR_LOSS[1])}"
    assert len(set(VECTOR_LOSS[1])) == len(VECTOR_LOSS[1]), "vector loss has duplicates"
    # The vector pools are indexed by attempt count, so they must cover every
    # try the game actually allows.
    assert set(VECTOR_TIERS) == {1, 2, 3, 4}, "vector tiers must cover 1-4 tries"

    blocks = []
    for n, (title, quips) in TIERS.items():
        blocks.append(
            f"  {n}: {{\n"
            f"    title: {json.dumps(title, ensure_ascii=False)},\n"
            f"    quips: [\n{js_array(quips, '      ')}\n    ],\n"
            f"  }},"
        )
    vblocks = []
    for n, (title, quips) in VECTOR_TIERS.items():
        vblocks.append(
            f"  {n}: {{\n"
            f"    title: {json.dumps(title, ensure_ascii=False)},\n"
            f"    quips: [\n{js_array(quips, '      ')}\n    ],\n"
            f"  }},"
        )
    verdicts = (
        "const VERDICTS = {\n" + "\n".join(blocks) + "\n};\n\n"
        "const LOSS_QUIPS = [\n" + js_array(LOSS[1], "  ") + "\n];\n\n"
        "const NEAR_QUIPS = [\n" + js_array(NEAR[1], "  ") + "\n];\n\n"
        "const VECTOR_VERDICTS = {\n" + "\n".join(vblocks) + "\n};\n\n"
        "const VECTOR_LOSS_QUIPS = [\n" + js_array(VECTOR_LOSS[1], "  ") + "\n];\n\n"
        "const VECTOR_LOSS_HEADING = " +
        json.dumps(VECTOR_LOSS[0], ensure_ascii=False) + ";"
    )

    text = TARGET.read_text()
    pattern = re.compile(
        r"const VERDICTS = \{.*?\n\};\n\nconst LOSS_QUIPS = \[.*?\n\];"
        r"(?:\n\nconst NEAR_QUIPS = \[.*?\n\];)?"
        r"(?:\n\nconst VECTOR_VERDICTS = \{.*?\n\};\n\n"
        r"const VECTOR_LOSS_QUIPS = \[.*?\n\];\n\n"
        r"const VECTOR_LOSS_HEADING = .*?;)?", re.S
    )
    if not pattern.search(text):
        raise SystemExit("could not locate the VERDICTS / LOSS_QUIPS block")
    TARGET.write_text(pattern.sub(lambda _: verdicts, text, count=1))

    total = (sum(len(q) for _, q in TIERS.values()) + len(LOSS[1]) + len(NEAR[1])
             + sum(len(q) for _, q in VECTOR_TIERS.values()) + len(VECTOR_LOSS[1]))
    print("Quips per tier:", {n: len(q) for n, (_, q) in TIERS.items()},
          "loss:", len(LOSS[1]), "near:", len(NEAR[1]))
    print("Vector quips per tier:", {n: len(q) for n, (_, q) in VECTOR_TIERS.items()},
          "vector loss:", len(VECTOR_LOSS[1]))
    print(f"Wrote {total} quips into {TARGET.name}")


if __name__ == "__main__":
    main()
