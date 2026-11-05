# resume-skill

A local agent skill that answers one job posting: it fit-checks the posting against your saved resume data and builds a tailored `.docx` from bullets you have already approved. It never invents a fact, and it saves nothing until you say OK.

It runs through agents that read a skills folder and can run Python on your computer (Claude Code, Codex, other `AGENTS.md` readers). Chat apps are not supported yet.

## What you get per posting
- A fit score from 1 to 5, the requirement counts behind it (for example "3 of 4 required met"), a soft apply or skip lean, and at most three flags.
- The real gaps, up to five questions, and checked edits with before and after.
- A `.docx` resume, plus a one-page fit card.
- A save step with a backup, a dated note and an undo.

## Install
1. Clone this repo.
2. Link the skill folder into your agent's skills folder: `ln -s "$PWD/skills/resume-skill" ~/.agents/skills/resume-skill` (Claude Code also reads `~/.claude/skills/`).
3. Ask your agent about a job posting. On the first run it asks where your data should live and runs `scripts/setup.py` for you. Your data stays outside this repo, by default in `~/.config/resume-skill/data/` (override with `RESUME_SKILL_DATA`).

Needs Python 3.9 or newer. Pillow (line-fit checks) and LibreOffice (page counts) are optional.

## Try it with made-up data
`examples/data/` holds a made-up backend engineer. Point the skill at it:

```
RESUME_SKILL_DATA="$PWD/examples/data" python3 skills/resume-skill/scripts/where.py
RESUME_SKILL_DATA="$PWD/examples/data" python3 skills/resume-skill/scripts/check.py --all
```

## Tests
`python3 -m unittest discover -s tests` (run from the repo root). Evals and the trigger set live in `evals/` and run only on request (`tools/run_evals.py`).

## Layout
- `skills/resume-skill/`: the installable skill (`SKILL.md`, `references/`, `scripts/`, `assets/`).
- `tools/`: rule generator, one-time importer, leak scan, eval runner, CI gates.
- `tests/`, `evals/`, `examples/`: tests, agent evals, made-up sample data.
