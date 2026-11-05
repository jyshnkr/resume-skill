# resume-skill

A local agent skill that answers one job posting. It fit-checks the posting against your saved resume data and builds a tailored `.docx` from bullets you have already approved. It never invents a fact, and it saves nothing until you say OK.

It runs through agents that read a skills folder and can run Python on your computer (Claude Code, Codex, other `AGENTS.md` readers). Chat apps are not supported yet. The scripts use only the Python standard library and make no network calls (a test checks this).

## What you get per posting
- A fit score from 1 to 5, the requirement counts behind it (for example "3 of 4 required met"), a soft apply or skip lean, and at most three flags. A script does the arithmetic, not the model.
- The real gaps, up to five questions, and checked edits shown as `was:` and `now:` lines with a reason.
- A `.docx` resume (Times New Roman 11 pt, US Letter, 0.5 inch margins), plus a one-page fit card.
- A save step with a backup, a dated note and an undo. A resume you mark as sent becomes read-only.

## How a run goes
1. Find your data folder. It is never inside this repo.
2. Pre-flight: every approved bullet is checked once; a bullet that fails is held back from swaps.
3. Read the posting and pick the version (for example full-time or contract).
4. Score the fit, then choose edits only from approved bullets.
5. Check each bullet against a registry of 67 resume-writing rules (digits, one "by", 20 to 30 words, no repeated words, and more) and write a three-sentence summary whose claims all trace to bullets on the page.
6. Build the `.docx` and count pages.
7. Save only after you say OK.

## Install
1. Clone this repo.
2. Link the skill folder into your agent's skills folder: `ln -s "$PWD/skills/resume-skill" ~/.agents/skills/resume-skill` (Claude Code also reads `~/.claude/skills/`).
3. Ask your agent about a job posting. On the first run it asks where your data should live and runs `scripts/setup.py` for you. Your data stays outside this repo, by default in `~/.config/resume-skill/data/` (override with `RESUME_SKILL_DATA`).

Needs Python 3.9 or newer. Pillow (line-fit checks) and LibreOffice (page counts) are optional. Without them those checks say "not checked" and never pass silently.

## Try it with made-up data
`examples/data/` holds a made-up backend engineer. Point the skill at it:

```
RESUME_SKILL_DATA="$PWD/examples/data" python3 skills/resume-skill/scripts/where.py
RESUME_SKILL_DATA="$PWD/examples/data" python3 skills/resume-skill/scripts/check.py --all
```

## How well does it work?
- `python3 -m unittest discover -s tests` (from the repo root) runs the test suite; CI runs it on Python 3.9 and 3.13, and a few tests skip without Pillow or LibreOffice.
- `evals/` holds 15 agent cases and a trigger set of 20 queries (10 that should fire the skill, 10 that should not), each run 3 times. They run through Claude Code only when you ask (`tools/run_evals.py`). In the pre-registered run recorded in `evals/frozen-run-2.json`, the default model passed 14 of 15 cases and a smaller model 14 of 15; the skill fired in 26 of 30 runs that should fire it and in 0 of 30 that should not. A no-skill baseline (`evals/baseline.json`, 1 run per case) passed 6 of 15. One case's check was faulty; the same file records it (`check_defect_found_after_the_run`).
- These evals are small and use phrase matching, so read them as a smoke test, not a benchmark.

## Limits
- v0.1 builds `.docx` only (no PDF) and runs only in agents that can run Python.
- Page counts need LibreOffice; line fit needs Pillow.
- It tailors from bullets you wrote; writing new bullets and interview prep are out of scope.

## Built with
Built with Claude Code. Builder and reviewer agents wrote and checked the code against tests that run each script as a separate process. See `AGENTS.md` for the working rules.

## Contributing
Issues and pull requests are welcome. Tests come first, scripts stay standard-library only, and no personal facts go in this repo (`python3 tools/leak_scan.py --from YOUR_DATA_FOLDER` checks that).

## License
MIT. See `LICENSE`.

## Layout
- `skills/resume-skill/`: the installable skill (`SKILL.md`, `references/`, `scripts/`, `assets/`).
- `tools/`: rule generator, one-time importer, leak scan, eval runner, CI gates.
- `tests/`, `evals/`, `examples/`: tests, agent evals, made-up sample data.
