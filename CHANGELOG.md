# Changelog

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

- The line-fit check measures with the system's own Times New Roman (macOS, Windows) and falls back to Liberation Serif, so no font install is needed on a Mac.

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
