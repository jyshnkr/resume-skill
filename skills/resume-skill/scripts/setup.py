#!/usr/bin/env python3
"""Create the user's data folder (or top up its settings), then check it. Flags only: it never prompts.

    python3 setup.py --data PATH [--yes] [--dry-run] [--save-location] [--add-missing-settings] [--json]

  --data PATH               where the data folder lives (created if missing; an empty existing folder is fine)
  --yes                     apply the plan. Without --yes (and without --dry-run) the plan is printed and nothing is written.
  --dry-run                 print the plan, write nothing. Wins over --yes.
  --save-location           write PATH to <config>/location so the other scripts find it (config = RESUME_SKILL_CONFIG_DIR
                            or ~/.config/resume-skill). Only done when asked.
  --add-missing-settings    add options that the shipped assets/defaults/settings.json has and the folder's settings.json
                            lacks (nested keys too). Never changes a value that is already there. With --dry-run only lists them.
  --json                    print one JSON document instead of text lines

Plan -> validate -> confirm -> apply -> verify. A new folder gets: settings.json, profile.md (headings only), bank.json,
summaries.json, versions/, private/{contact.json,terms.json,bank-notes.md,recruiters.md}, jobs/, changes/, backups/, out/,
archive/. It never overwrites a file: running it again on a data folder (one that holds settings.json) changes nothing and
says "already set up". It refuses a PATH inside the skill folder, and a non-empty folder that is not a data folder.
After a real run it verifies the folder with validate.py (a fresh folder has warnings, not errors) and, if preflight.py
exists, ends with `preflight.py --if-stale --quiet`.

Exit 0: done, already set up, or a dry run. Exit 1: refused, or the check of the new folder found errors.
Exit 2: the plan was printed and needs --yes.
"""
import json, os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resume_data as rd  # noqa: E402
import where  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
DIRS = ["versions", "private", "jobs", "changes", "backups", "out", "archive"]
PROFILE = "# Profile\n\n## Claim boundaries\n\n## Do not claim\n\n## Preferences\n"


GUARD = """# This folder is the data of the resume-skill skill

Never edit these files by hand. They hold the user's approved bullets, resumes and saved job folders.

- Change them only through the resume-skill skill: it checks the change, keeps a backup and can undo it.
- A tailoring with status "submitted" or "archived" is a resume that was sent. Its file is read-only on purpose.
  Never change its permissions to edit it. Make a new tailoring instead.
- If the skill is not loaded, stop and tell the user to say "use resume-skill".
"""


def jtext(obj):
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


FILES = {
    "CLAUDE.md": GUARD,
    "AGENTS.md": GUARD,
    "profile.md": PROFILE,
    "bank.json": jtext({"roles": [], "bullets": []}),
    "summaries.json": jtext({"summaries": []}),
    "private/contact.json": jtext({"name": "", "phone": "", "links": []}),
    "private/terms.json": jtext({"people": [], "internal_codenames": [], "patterns": [], "stage_words": []}),
    "private/bank-notes.md": "# Bank notes\n",
    "private/recruiters.md": "# Recruiters\n",
}


def refuse(msg):
    raise SystemExit(f"error: {msg}")


def inside(path, folder):
    path, folder = os.path.realpath(path), os.path.realpath(folder)
    return os.path.commonpath([path, folder]) == folder


def missing_settings(default, user, prefix=""):
    """[(dotted path, default value)] for options the defaults have and the user's settings lack. Dicts only, never lists."""
    out = []
    for k, v in default.items():
        if k not in user:
            out.append((prefix + k, v))
        elif isinstance(v, dict) and isinstance(user[k], dict):
            out += missing_settings(v, user[k], f"{prefix}{k}.")
    return out


def put(doc, dotted, value):
    keys = dotted.split(".")
    for k in keys[:-1]:
        doc = doc[k]
    doc[keys[-1]] = value


def plan_for(path, state, args):
    """The list of actions: dicts with kind (folder|file|setting|location), name, detail."""
    acts = []
    if state == "new":
        acts.append({"kind": "folder", "name": ".", "detail": "the data folder itself"} if not os.path.isdir(path) else None)
        acts += [{"kind": "folder", "name": d + "/"} for d in DIRS]
        acts.append({"kind": "file", "name": "settings.json", "detail": "copy of the shipped defaults"})
        acts += [{"kind": "file", "name": n} for n in FILES]
        acts = [a for a in acts if a]
    if "--add-missing-settings" in args and state == "ready":
        sp = os.path.join(path, "settings.json")
        try:
            with open(sp, encoding="utf-8") as f:
                mine = json.load(f)
        except (OSError, ValueError) as e:
            refuse(f"cannot read {sp} as JSON ({e}); fix it before adding missing settings")
        if not isinstance(mine, dict):
            refuse(f"{sp} should hold a JSON object")
        acts += [{"kind": "setting", "name": k, "value": v} for k, v in missing_settings(rd.default_settings(), mine)]
    if "--save-location" in args and where.saved_location() != path:
        acts.append({"kind": "location", "name": os.path.join(where.config_dir(), "location"), "detail": path})
    return acts


def apply(path, acts):
    for a in acts:
        if a["kind"] == "folder":
            os.makedirs(os.path.join(path, a["name"]), exist_ok=True)
    os.makedirs(path, exist_ok=True)
    for a in acts:
        if a["kind"] == "file":
            full = os.path.join(path, a["name"])
            if os.path.exists(full):  # never overwrite
                continue
            if a["name"] == "settings.json":
                with open(rd.DEFAULT_SETTINGS, "rb") as src, open(full, "xb") as dst:
                    dst.write(src.read())
            else:
                with open(full, "x", encoding="utf-8") as f:
                    f.write(FILES[a["name"]])
    adds = [a for a in acts if a["kind"] == "setting"]
    if adds:
        sp = os.path.join(path, "settings.json")
        with open(sp, encoding="utf-8") as f:
            mine = json.load(f)
        for a in adds:
            put(mine, a["name"], a["value"])
        with open(sp, "w", encoding="utf-8") as f:
            f.write(jtext(mine))
    for a in acts:
        if a["kind"] == "location":
            os.makedirs(os.path.dirname(a["name"]), exist_ok=True)
            with open(a["name"], "w", encoding="utf-8") as f:
                f.write(path + "\n")


def child(script, path, *extra):
    env = dict(os.environ, RESUME_SKILL_DATA=path)
    return subprocess.run([sys.executable, os.path.join(HERE, script), *extra], capture_output=True, text=True, env=env,
                          stdin=subprocess.DEVNULL, timeout=300)


def describe(a):
    if a["kind"] == "setting":
        return f"add setting   {a['name']} = {json.dumps(a['value'], ensure_ascii=False)}"
    if a["kind"] == "location":
        return f"save location {a['name']} -> {a['detail']}"
    return f"create {a['kind']:<6} {a['name']}" + (f"  ({a['detail']})" if a.get("detail") else "")


def main(a):
    if {"-h", "--help"} & set(a):
        print(__doc__)
        return 0
    known = {"--data", "--yes", "--dry-run", "--save-location", "--add-missing-settings", "--json"}
    bad = [x for i, x in enumerate(a) if x.startswith("-") and x not in known]
    if bad:
        refuse(f"unknown option {bad[0]!r}; see --help")
    if "--data" not in a or a.index("--data") + 1 >= len(a) or a[a.index("--data") + 1].startswith("--"):
        refuse("--data PATH is required (where the data folder should live); see --help")
    path = os.path.abspath(os.path.expanduser(a[a.index("--data") + 1]))
    as_json = "--json" in a
    if inside(path, SKILL_DIR):
        refuse(f"{path} is inside the skill folder ({SKILL_DIR}); a skill update would erase it. Pick a folder outside it.")
    if os.path.isfile(path):
        refuse(f"{path} is a file, not a folder")
    if os.path.isdir(path) and os.path.isfile(os.path.join(path, where.MARKER)):
        state = "ready"
    elif os.path.isdir(path) and os.listdir(path):
        refuse(f"{path} is not empty and is not a resume-skill data folder (no {where.MARKER}); pick an empty or new folder")
    else:
        state = "new"
    acts = plan_for(path, state, a)
    dry = "--dry-run" in a
    doc = {"path": path, "state": state, "actions": [dict(x) for x in acts], "applied": False, "dry_run": dry}

    def emit(lines, code):
        if as_json:
            print(json.dumps(doc, ensure_ascii=False))
        else:
            print("\n".join(lines))
        return code
    if not acts:
        doc["status"] = "already set up"
        return emit([f"already set up: {path} (nothing changed)"], 0)
    head = f"plan for {path} ({'new data folder' if state == 'new' else 'existing data folder'}):"
    lines = [head] + ["  " + describe(x) for x in acts]
    if dry:
        doc["status"] = "dry run"
        return emit(lines + ["dry run: nothing was written."], 0)
    if "--yes" not in a:
        doc["status"] = "needs --yes"
        return emit(lines + ["nothing written. Check the plan, then re-run with --yes to apply it."], 2)
    apply(path, acts)
    doc["applied"] = True
    r = child("validate.py", path, "--json")
    try:
        v = json.loads(r.stdout)
    except ValueError:
        v = {"errors": [f"validate.py gave no result: {(r.stderr or r.stdout).strip()[:200]}"], "warnings": [], "counts": {}}
    doc["validate"] = v
    doc["status"] = "done" if r.returncode == 0 and not v["errors"] else "check failed"
    lines += ["applied.", f"verify: validate.py found {len(v['errors'])} errors, {len(v['warnings'])} warnings"]
    lines += ["  ERROR " + e for e in v["errors"]] + ["  WARN " + w for w in v["warnings"]]
    if os.path.exists(os.path.join(HERE, "preflight.py")):
        try:
            child("preflight.py", path, "--if-stale", "--quiet")
        except (OSError, subprocess.SubprocessError):
            pass
    return emit(lines, 0 if doc["status"] == "done" else 1)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
