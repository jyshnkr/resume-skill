# Rules, part 2

Generated from assets/rules/registry.json by tools/make_rules.py. Do not edit by hand.
Tag = when the rule applies, then who enforces it (checker = scripts/check.py, build = a script, read = you).

## Numbers and honesty

**12** [preflight · checker] Use real numbers only; never invent a number or a fact. A size word with no numeral ('millions', 'dozens of') is not a number: get the figure or leave it out. An estimate as a numeral with '~' is fine.
**13** [tailoring · read] A bullet with no measured result (rule 10) stays a capability bullet marked needs_metric in the bank, or the tool stays in the skills line only. Never swap in an estimate you cannot back.
**14** [tailoring · read] Never replace a bullet that has a number with one that does not, unless the posting needs that skill and nothing else on the resume shows it.
**15** [preflight · checker] Say it accurately: 'implemented' if someone else designed it; 'designed', 'co-designed' or 'architected' only for work you designed end to end. Say 'passed the review', never 'cleared' it.
**16** [preflight · checker] Keep private things out: no internal names, internal config, decision-record numbers or colleague names in resume text or any public data file.
**17** [posting · read] Never write anything on your do-not-claim list as experience, and never add a posting keyword you have not used. Close real gaps in interview prep with a bridge from what you did.
**39** [tailoring · read] When an amount is confidential, give the real percentage change instead ('cut spend 30%'), never a vague or made-up figure.
**44** [posting · read] A posting term you have used may replace your synonym only when it means the same thing at the same scope. Count school projects as projects, not as a job.
**45** [final · read] Test every reworded bullet: could you explain it in an interview without backtracking? If not, tone it down or drop it.
**46** [final · read] Label unfinished work as it is: a degree 'in progress' or 'expected <month year>', other work 'under review' or 'internal', never as finished or published.
**47** [tailoring · read] Keep each job title exactly as on your version; never upgrade it for a posting.
**48** [tailoring · read] For every reworded bullet, show before and after and one line on why it stays accurate.
**49** [final · build] Never hide keywords or instructions in white, tiny or invisible text; every word must be visible to a person.

## The summary

**23** [tailoring · checker] Write exactly 3 sentences (about 4 lines). Sentence 1 opens with your title, 'with X+ years of experience in ...' (the pattern is in settings); the years run from your first listed start to your last listed end, degrees included, rounded down.
**24** [tailoring · checker] Sentence 2 gives one headline result for each of your three most recent roles. Sentence 3 covers your strengths (tools, quality, leadership) in past tense, never as an instruction.
**25** [tailoring · checker] Every claim in the summary traces to a bullet in the same resume; build it from the bank's numbered bullets. No platform brackets and no retired wording in a summary.
**50** [final · build] Do not write an objective statement; open with the three-sentence summary.

## Skills and posting words

**26** [tailoring · read] Put the skills section after Education. List tools, technologies and engineering practices only; soft skills go in bullets. A new skills item needs your OK and a source in a version or profile.md.
**27** [posting · read] For each job, reorder the skills lines so the lines with the most posting mentions come first, and trim items the posting never needs. Add an item only from another version's skills lines or what profile.md allows (rules 17, 26).
**28** [posting · read] For each posting, list every skill word it names twice or more and mark each: in the resume; true for you but not written; not yours (do-not-claim); unknown (ask). Warn when a repeated word that is true for you is missing.
