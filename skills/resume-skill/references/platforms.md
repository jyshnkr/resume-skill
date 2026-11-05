# Platforms

This skill runs through agents that read a skills folder and can run Python on the user's own computer (Claude Code, Codex, other agents that read `AGENTS.md`). Chat apps without a folder are not supported.

## Install (link, do not copy)
Link the skill folder so an update to the repo reaches every agent:

`ln -s /path/to/resume-skill/skills/resume-skill ~/.agents/skills/resume-skill`

Claude Code reads `~/.claude/skills/` (or the repo as a plugin through `.claude-plugin/plugin.json`); Codex and other agents read the folder they document. Linking changes the user's global setup: ask first.

## Run
Commands in `SKILL.md` are written `python3 scripts/NAME.py`; run them from the skill folder or give the full path. Check `python3 --version` (3.9 or newer).

## Where the data lives
`python3 scripts/where.py` prints the data folder. To pick a place other than `~/.config/resume-skill/data/`, set `RESUME_SKILL_DATA`. A terminal reads it from the shell profile; Claude Code reads it from the `env` block in `settings.json`; desktop apps started from the Dock do not read the shell profile.

## Optional tools
- Pillow (line-fit checks): install it in a folder of its own, not the system Python.
- LibreOffice (page counts): without it every page count reads "not checked" and exit code 2.
- Liberation Serif (a metric match for Times New Roman) is needed for line-fit checks.
Each install is the user's call; ask before running one.

## Updating
Update by pulling the repo. The data folder is outside the skill folder and is never touched by an update or a re-install.
