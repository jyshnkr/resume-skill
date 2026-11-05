# Workflow details

## Read the posting
- Note title, company, job ID, location, work type, rate. Look in `jobs/` for the same ID or the same title and company; if found, say so and ask whether to reuse it.
- One requirement row per line the posting treats as required ("must", "required") or preferred ("nice to have", "preferred"). Skills first, then level, then location.
- Look first for flags: sponsorship excluded, on-site where the preferences in `settings.json` say remote, contract versus full-time, a rate under the minimum, a level far above or below, a clearance, years asked. State what the posting says; do not guess the user's work authorization, read `profile.md` or ask.

## Pick the version
The posting says contract or full-time and a version of that kind exists: use it and say so. Otherwise ask which version and stop. If two fit, recommend one with the reason.

## A recruiter introduction
A message that introduces someone but describes no role is not a posting: no fit score, no invented requirements. Say what it is and ask for the posting. Do not read remarks addressed to someone else as facts about the user.

## Several postings
Reply with one short table (posting, lean, main gap, version) and ask which to tailor. Build no files until the user picks.

## Ask and stop
Ask one question and stop when the version is undecided, the posting is missing, a needed number is missing, a required skill is in neither the bank nor the profile and a bullet would lean on it, or work authorization matters. Put at most five numbered questions in the reply; the rest wait.

## Reading order for a run
`profile.md`, `settings.json`, the version files, the bank (skip ids in `hold_back` when offering swaps), then `rules-1.md` to `rules-3.md`.

## Where files go
Drafts and derived files (`fit.json`, `fit.html`, a draft `tailoring.json`, the `.docx`) go to `out/SLUG/`. Nothing goes into `jobs/` until the user says OK; `save.py` moves it (`references/save.md`).
