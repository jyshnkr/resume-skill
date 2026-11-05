# Saving an approved change

Save only after the user says OK, and only through `scripts/save.py`.

## Plan file
`PLAN.json`: `{"id": "acme-backend-save-1", "reason": "one line", "note": "text for the dated note", "writes": [{"path": "jobs/acme-backend/tailoring.json", "content": {...}}, {"path": "jobs/acme-backend/posting.md", "text": "..."}, {"path": "jobs/old/x.json", "delete": true}], "correction": false}`.
Paths are relative to the data folder. Include the posting, `fit.json`, `fit.html` and the tailoring (copy them from `out/SLUG/`). To mark a copy as sent, rewrite its tailoring with `"status": "submitted"` and `"sent_on": "YYYY-MM-DD"`.

## Steps
1. `python3 scripts/save.py PLAN.json --dry-run`: it stages the result, runs `validate.py` on it and prints what would change. Any validation error stops the save and nothing changes.
2. Show the user the printed plan.
3. After the OK: `python3 scripts/save.py PLAN.json --yes`. It copies the old files to `backups/ID/`, writes the new ones, adds a dated note `changes/ID.md` and refreshes the pre-flight.
4. `python3 scripts/save.py --undo ID --yes` puts everything back from the backup (it refuses if the files changed since, unless `--yes`).

## Sent copies
A plan that touches a submitted or archived tailoring is refused. The one exception is a correction of a claim found untrue: the user says yes explicitly, the plan has `"correction": true`, and its note starts with "Correction".

## Sent copies are read-only on disk
A submitted or archived tailoring file is made read-only, so a hand edit by an agent that never loaded the skill fails. A save, an undo and the importer do this by themselves; `python3 scripts/save.py --lock` does it for every sent copy at once, and `validate.py` warns about one that is still writable. A correction still goes through `save.py`. Never change the permissions to get past the lock.

## What save.py will not do
- It judges every path on the real file: a different letter case, a hard link or a folder symlink cannot reach `backups/`, `changes/` or a sent tailoring, and a path through a symlink is refused.
- A backup with a damaged `manifest.json` is unusable: `--undo ID` names it and stops; a bare `--undo` skips it and says so.
- `--undo` will not touch a submitted or archived tailoring. To undo anyway (for example a copy marked sent by mistake), run `save.py --undo ID --unfreeze --yes`; the reply names every sent file it unfroze. Only do this on the user's explicit yes.

## Optional settings
`output.backup_copy_to` copies each backup to a second folder. `output.copy_resumes_to` copies each built `.docx` to a folder you choose. Both are off by default.
