# Working on resume-skill

- The skill is `skills/resume-skill/`. Everything the skill needs is inside that folder; tests, evals, tools and sample data stay at the repo root.
- No personal facts anywhere in this repo: sample data is made up (Jordan Ellis). Real data lives in the user's data folder, never here. Run `python3 tools/leak_scan.py --from PATH` before pushing.
- Test first. Tests run the scripts as separate processes (`tests/helpers.py`). `python3 -m unittest discover -s tests` must pass on Python 3.9 and a current Python.
- Scripts use only the standard library, take flags (no prompts), print `--help`, and make no network calls.
- `assets/rules/registry.json` is the source of the rules; regenerate the three rules files with `python3 tools/make_rules.py`.
- Version: `.claude-plugin/plugin.json` is the one source; `SKILL.md` metadata must match.
