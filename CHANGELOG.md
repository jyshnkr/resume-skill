# Changelog

## 0.1.0 (unreleased)

First local build.

- Fit check with a 1-5 score, requirement counts, a soft apply or skip lean and a fit card.
- Tailoring from a bank of approved bullets, checked by `check.py` (67 rules, Wave 1 checks, stack coverage note).
- Pre-flight check of the whole bank, with failing bullets held back from swap offers.
- `.docx` build (Times New Roman 11 pt, US Letter, 0.5 in margins). No PDF: page counts read "not checked" without LibreOffice.
- User data lives outside the skill folder (`RESUME_SKILL_DATA`, a saved location, or `~/.config/resume-skill/data/`).
- Saving with a backup, a dated note and `--undo`; sent copies are frozen.
