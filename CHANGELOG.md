# Changelog

## 0.1.1 (2026-11-05)

- The line-fit check measures with the system's own Times New Roman (macOS, Windows) and falls back to Liberation Serif, so no font install is needed on a Mac.
- Missing numbers are asked for with a placeholder ([N]), never a digit, in any draft.
- Eval runner can switch a competing skill off for a fair measure; eval results are recorded in `evals/results-*.json`.

## 0.1.0 (2026-11-05)

First local build.

- Fit check with a 1-5 score, requirement counts, a soft apply or skip lean and a fit card.
- Tailoring from a bank of approved bullets, checked by `check.py` (the 65 live rules of the 67 numbered, Wave 1 checks, stack coverage note).
- Pre-flight check of the whole bank, with failing bullets held back from swap offers.
- `.docx` build (Times New Roman 11 pt, US Letter, 0.5 in margins). No PDF: page counts read "not checked" without LibreOffice.
- User data lives outside the skill folder (`RESUME_SKILL_DATA`, a saved location, or `~/.config/resume-skill/data/`).
- MIT license.
- Sent tailorings are read-only files (`save.py --lock`), and the data folder carries a CLAUDE.md / AGENTS.md note, so a hand edit by an agent that never loaded the skill is blocked.
- Saving with a backup, a dated note and `--undo`; sent copies are frozen.
