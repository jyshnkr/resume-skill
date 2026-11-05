# Rules, part 1

Generated from assets/rules/registry.json by tools/make_rules.py. Do not edit by hand.
Tag = when the rule applies, then who enforces it (checker = scripts/check.py, build = a script, read = you).

## Building a bullet

**1** [preflight · checker] Build each bullet in this order: strong verb, the result with its number, the word 'by', then how you did it. A count of services or a product number is not the result number (rule 10).
**2** [preflight · checker] Use 'by' exactly once, right before the method. Not 'by 40%': put the number in the result ('load time 40%' or 'from A to B').
**3** [preflight · checker] Start with a strong past-tense verb; no two bullets in one resume start with the same verb. Skip Helped, Responsible for, Worked on, Ensured, Assisted, Participated, plain Built or Designed.
**4** [preflight · checker] Keep each bullet inside the limits in settings (default 20 to 30 words, 215 characters, about two lines). Never pad with invented detail.
**5** [preflight · checker] Write numbers as digits ('zero' and 'single' may stay words). Mark estimates with '~' and floors with '+'. Write a unit once: 'from 480 to 140 ms'.
**6** [preflight · checker] Do not repeat a word inside one bullet, product names included. Small words and numbers do not count. A repeat approved in the bank (allowed_repeats) stays.
**7** [tailoring · read] No keyword soup: name the few tools that mattered to the result, usually 2 to 5. Never add a tool only to place a posting word (rule 41).
**8** [preflight · checker] The first AWS service in a bullet carries 'AWS' or 'Amazon' (AWS Lambda, Amazon DynamoDB); later ones can be bare. Use the real brand: Amazon SQS, not 'AWS SQS'.
**9** [preflight · checker] Name the product, not a class, method or API name (the jargon list in settings). Heavy jargon gets a note (rule 38), never a failure.
**10** [preflight · checker] A count of services, customers, teams or records is scope, not a result; a version or product number (HTML5, JDK 17) is not a number. A project bullet may skip the number but must say what the project does.
**11** [posting · read] Platform brackets: read brackets.md before adding one.
**35** [posting · read] Inside each role put first the bullet that best matches the posting, so the strongest proof is never buried.
**36** [tailoring · read] Name the business domain in at least one bullet per role (payments, retail, logistics) so the reader sees industry experience.
**37** [preflight · checker] Punctuate every bullet the same way (all end with a period, or none do) and keep every lead verb in past tense; clauses inside may be present tense.
**67** [tailoring · checker] Name the language or runtime when a bullet is about code you wrote or changed ('Node.js AWS Lambda'). It counts toward rule 7's 2 to 5 tools. Skip it when the work was not code. If length is the problem, trim other words first.

## Words and style

**18** [preflight · checker] Warn on the robot words and phrases in assets/phrases/robot-phrases.json (extend or mute them in settings). Weak verbs (Helped, Assisted, Participated, Ensured, Responsible for, Worked on) count only at the start of a bullet or summary sentence, not inside a compound such as 'AI-assisted'. Warn only.
**19** [preflight · checker] Warn on tired patterns the checker can see: a last clause that opens with a vague '-ing' outcome ('improving customer experience'), passive voice, em dashes. Other patterns (it's not X, it's Y; lists of three) are for your read-aloud pass (rule 22).
**20** [preflight · checker] No first-person words (I, we, my, our, us, me) anywhere in a resume line.
**21** [final · read] Keep it sounding like you: drafts follow your voice notes in profile.md, and each new or reworded bullet answers your voice questions before you see it.
**22** [final · read] Before you send, read the bullets and summary aloud once and fix any typo.
**38** [tailoring · read] Use the short form for AWS service names and common abbreviations (JWT, TLS, CI/CD, SQL). Spell out only a niche in-house abbreviation, and only if the bullet stays inside the limits; otherwise use plain words.
