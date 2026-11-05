# Changelog

## 0.1.7 (2026-11-05)

- Ready for a public repository: a fuller README (how a run goes, install, evidence and limits, contributing), and the MIT licence now names the author. The leak scan skips only that one copyright line; every other file is still scanned. All 38 earlier commits were scanned against the author's private data with 0 hits.

## 0.1.6 (2026-11-05)

- Draft bullet options can be kept in the bank with `"status": "candidate"`. A candidate is never offered in a swap, never placed in a version or tailoring (validate.py reports it as an error if it is), and not counted in "N of M need attention". Pre-flight checks candidates and reports them on a separate line (`out/preflight.json` keys `candidates` and `candidates_summary`); `check.py --all` skips them.

## 0.1.5 (2026-11-05)

- Fixed a settings-reader regression from 0.1.3: single-quoted text containing a doubled quote ('it''s, ok'), which is how the writer saves a value with an apostrophe, no longer breaks when a comma, colon or # follows. 20,000 random write-and-read round trips pass, and a smaller seeded version is part of the tests.
- SKILL.md step 6 and the output contract agree on `was:`/`now:` edit lines; the Scripts list names `--convert-settings`.

## 0.1.4 (2026-11-05)

- Edits in a reply are always shown as a `was:` line and a `now:` line with a reason, so the old and new text are easy to compare (the output contract named before/after but not the layout).

## 0.1.3 (2026-11-05)

- The settings reader treats an apostrophe inside a word (Austin's) as text, not a quote, so a comment after it is no longer kept in the value.
- `setup.py --add-missing-settings` on a folder that still has only the old `settings.json` now converts it fully (settings.yaml written, the old file moved to `archive/`), so two settings files never sit side by side.

## 0.1.2 (2026-11-05)

- Settings are now `settings.yaml`, a commented file with hints and a `preferences` block at the top (work type, location, remote, minimum rate and its unit, domains). An old `settings.json` is still read; `setup.py --convert-settings --yes` converts it, `--add-missing-settings` adds new options. The YAML reader is built in (`scripts/miniyaml.py`), so nothing needs installing.
- When a posting or message contains an instruction aimed at the AI, the reply names it and says it was ignored.
- Eval runner: `--workers N` runs calls in parallel and `--strict-mcp` skips the machine's connectors.

## 0.1.1 (2026-11-05)

- The line-fit check measures with the system's own Times New Roman (macOS, Windows) and falls back to Liberation Serif, so no font install is needed on a Mac. Line fit still needs Pillow; without it the check reads "not checked".

## 0.1.0 (2026-11-05)

First local build.

- Fit check with a 1-5 score, requirement counts, a soft apply or skip lean and a fit card.
- Tailoring from a bank of approved bullets, checked by `check.py` (the 65 live rules of the 67 numbered, Wave 1 checks, stack coverage note).
- Pre-flight check of the whole bank, with failing bullets held back from swap offers.
- `.docx` build (Times New Roman 11 pt, US Letter, 0.5 in margins). No PDF: page counts read "not checked" without LibreOffice.
- User data lives outside the skill folder (`RESUME_SKILL_DATA`, a saved location, or `~/.config/resume-skill/data/`).
- MIT license.
- Missing numbers are asked for with a placeholder ([N]), never a digit, in any draft.
- The eval runner (`tools/run_evals.py`) can switch a competing skill off for a fair measure; results are recorded in `evals/results-*.json`.
- Sent tailorings are read-only files (`save.py --lock`), and the data folder carries a CLAUDE.md / AGENTS.md note, so a hand edit by an agent that never loaded the skill is blocked.
- Saving with a backup, a dated note and `--undo`; sent copies are frozen.
