# Rules, part 3

Generated from assets/rules/registry.json by tools/make_rules.py. Do not edit by hand.
Tag = when the rule applies, then who enforces it (checker = scripts/check.py, build = a script, read = you).

## Layout and length

**29** [final · build] One fixed layout: Times New Roman 11 pt, US Letter, 0.5-inch margins, bold uppercase headings, dates right-aligned with an en dash, round-dot bullets; a title or sub-line never stands alone at a page bottom.
**30** [final · build] Page caps come from each version's page_cap in the data folder. A resume over its cap is not final.
**31** [final · build] One column, plain section names (Summary, Professional Experience, Education, Technical Skills, Projects), no tables, text boxes or pictures for anything that matters, nothing important in the header or footer area.
**32** [final · build] Deliver the .docx; check the page count on a real render. If no renderer is available, say 'pages not checked' and never call the count checked.
**51** [final · build] Leave off a photo, home address, age, gender, marital status, nationality and 'references available'; never start a line with a date.
**52** [final · build] Put email, phone, LinkedIn and GitHub in the header as full visible text with a professional email address; never only an icon or the word 'LinkedIn'.
**53** [final · build] Set your name in bold at 16 pt at most, with the contact line below it in the body font size.
**54** [final · build] Name the file with your full name and a label: the client or job for a tailoring, the version name for a version.
**55** [final · build] Put a line under each section heading.
**56** [final · build] Keep the job title and the degree bold; the company name stays in the same bold run as the title; location and school in italic.
**57** [final · build] Delete an empty optional section together with its heading.
**58** [tailoring · read] List jobs newest first, and never move a better-fitting older role to the top.
**59** [final · read] Fill the last page at least halfway. If it is less, trim to the page before, or add an approved bank bullet; a full version adds one only by cutting one (rule 33).
**60** [preflight · checker] A bullet's last line should not be a near-orphan: the checker notes a bullet whose second line is under half the text width (note only, needs Pillow). Fix it by rewording within rule 4, never by adding words.
**61** [final · read] Before sending, extract the file's text and check every section is there, readable and in order, not only the page count.

## Tailoring for a posting

**33** [tailoring · read] Start from a version and change only what the posting needs. Use an approved bank bullet; a rewrite that keeps less than half of a bank bullet's words is a new bank row and needs your OK. Adding a bullet to a full version means cutting one of the same length.
**34** [tailoring · build] A resume that has been sent is frozen: no edit, and no later bank change flows into it. A new mix of postings gets a new copy. The one exception is a correction of a claim found untrue, with your explicit yes and a 'Correction' note.
**40** [posting · read] Where you really did the work, use the posting's exact term (in a bullet or a skills-line label) instead of your synonym; never for work you did not do.
**41** [posting · read] Each important posting word that is true for you appears in the skills lines and in at least one bullet or the summary. Never add a word to a bullet only to place it (rule 7).
**42** [tailoring · read] When cutting for space, keep each role's headline result, then cut the line the posting cares about least; cut by age only after relevance cuts run out. Never cut a line whose absence would mislead. (Rule 64 merged here.)
**43** [posting · read] For each posting, list what a recruiter may doubt about you (for example seniority) and make sure a real bullet near the top answers each doubt.

## Other

**62** [tailoring · read] List each degree with its school and dates; leave out high school; add coursework only when you have little work experience.
**63** [tailoring · build] If you hold a certification or award the posting values, list it near Education (the version's certifications list). An empty list prints nothing.
**64** merged into rule 42.
**65** merged into rule 25.
**66** [tailoring · read] For a bullet with no result, ask what problem it solved and what time or money it saved.
