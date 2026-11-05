#!/usr/bin/env python3
"""One-time tool: copy the old repo's data (jd-fit-check layout) into a new resume-skill data folder. Not part of the installed skill.

    python3 import_old.py --old OLD_REPO --data NEW_DATA_FOLDER [--dry-run] [--fixes FIXES.json] [--apply ID ...]

Old layout (read only, never changed): data/{bank.json, summaries.json, retired.json, bank-notes.md, profile.md, drive.json,
versions/*.json, private/*, tailorings/<slug>.json, jds/*.md}, changelog/, CHANGELOG.md, resumes/.

Mapping: bank, summaries, profile and versions are copied (version names and marks keys unchanged). bank.json gains a top-level
"roles" (the distinct bullet roles) and every row gains "tech": []. Versions gain "certifications": []. private/* is copied.
tailorings/<slug>.json becomes jobs/<slug>/tailoring.json; its jd_files are copied to jobs/<slug>/posting.md (posting-2.md, ...)
and "posting" is set (jd_files is dropped: those paths no longer exist); status and bank_commit are kept, sent_on is null.
retired.json, bank-notes.md and drive.json go to archive/, changelog/ to archive/history/, CHANGELOG.md to archive/,
resumes/ to archive/resumes/. settings.json is the shipped defaults: the user-specific values the old check.py held are NOT
carried; set them in settings.json by hand.

Fixes file: a JSON list of {id, description, op, ...}. Ops (file paths are relative to the NEW data folder):
  replace          {file, find, replace}              the exact text must occur once, else "not applicable: text not found"
  append_line      {file, after_heading, line}        added as the last line of that heading's section
  set_bank_field   {ids, field, value}                sets bank.json rows' field
  offer            {...}                              listed only, never applied automatically
Fixes run only for ids given to --apply, after the copy and before the check, and each prints before/after.

--dry-run lists the mapping and every fix with applicable yes/no, and writes nothing anywhere (not even the data folder).
A real run needs a missing or empty data folder, copies, runs validate.py, then preflight.py --quiet when it exists and prints
"N of M bullets need attention" from out/preflight.json.
Exit 0 done, 1 refused or the new folder has validate errors.
"""
import argparse, json, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "skills", "resume-skill", "scripts")
sys.path.insert(0, SCRIPTS)
import setup as su  # noqa: E402  (the new-folder layout: DIRS, FILES)
import resume_data as rd  # noqa: E402


def refuse(msg):
    raise SystemExit(f"error: {msg}")


def jtext(obj):
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def files_under(folder):
    for dirpath, dirs, files in os.walk(folder):
        dirs.sort()
        for f in sorted(files):
            yield os.path.relpath(os.path.join(dirpath, f), folder)


def build_plan(old):
    """{dest path relative to the new folder: ("copy", source file) | ("text", text)}, plus notes to print."""
    d = os.path.join(old, "data")
    plan, notes = {}, []
    if not os.path.isfile(os.path.join(d, "bank.json")):
        refuse(f"{old} does not look like the old repo: data/bank.json not found")

    def copy(src_rel, dest):
        if os.path.isfile(os.path.join(old, src_rel)):
            plan[dest] = ("copy", os.path.join(old, src_rel))
            return True
        return False

    bank = read_json(os.path.join(d, "bank.json"))
    roles = []
    for b in bank["bullets"]:
        if b.get("role") not in roles:
            roles.append(b.get("role"))
        b.setdefault("tech", [])
    plan["bank.json"] = ("text", jtext({"roles": roles, **bank}))
    for name in ("summaries.json", "profile.md"):
        if not copy(f"data/{name}", name):
            notes.append(f"data/{name} not found in the old repo; the new folder keeps its empty starter")
    vdir = os.path.join(d, "versions")
    for f in sorted(os.listdir(vdir)) if os.path.isdir(vdir) else []:
        if f.endswith(".json"):
            v = read_json(os.path.join(vdir, f))
            v.setdefault("certifications", [])
            plan[f"versions/{f}"] = ("text", jtext(v))
    pdir = os.path.join(d, "private")
    for rel in files_under(pdir) if os.path.isdir(pdir) else []:
        plan[f"private/{rel}"] = ("copy", os.path.join(pdir, rel))
    tdir = os.path.join(d, "tailorings")
    for f in sorted(os.listdir(tdir)) if os.path.isdir(tdir) else []:
        if not f.endswith(".json"):
            continue
        t = read_json(os.path.join(tdir, f))
        slug = t.get("slug") or os.path.splitext(f)[0]
        postings = []
        for src in t.pop("jd_files", []) or []:
            name = "posting.md" if not postings else f"posting-{len(postings) + 1}.md"
            if copy(src, f"jobs/{slug}/{name}"):
                postings.append(name)
            else:
                notes.append(f"tailoring {slug}: jd file {src} not found, skipped")
        head = {"slug": slug, "base": t.pop("base", None), "status": t.pop("status", "draft"), "posting": postings[0] if postings else None,
                "sent_on": None}
        t.pop("slug", None)
        for part in (t.get("roles") or []) + (t.get("projects") or []):
            for b in part.get("bullets", []):
                if b.get("override") and not b.get("why"):  # the new layout asks for a one-line why on every reworded bullet (rule 48)
                    b["why"] = "Carried over from the old repo; the reason is in archive/history."
        plan[f"jobs/{slug}/tailoring.json"] = ("text", jtext({**head, **t}))
    for src, dest in (("data/retired.json", "archive/retired.json"), ("data/bank-notes.md", "archive/bank-notes.md"),
                      ("data/drive.json", "archive/drive.json"), ("CHANGELOG.md", "archive/CHANGELOG.md")):
        copy(src, dest)
    for folder, dest in (("changelog", "archive/history"), ("resumes", "archive/resumes")):
        for rel in files_under(os.path.join(old, folder)) if os.path.isdir(os.path.join(old, folder)) else []:
            plan[f"{dest}/{rel}"] = ("copy", os.path.join(old, folder, rel))
    plan["settings.json"] = ("copy", rd.DEFAULT_SETTINGS)
    for name, text in su.FILES.items():  # starters for anything the old repo did not have (recruiters.md, ...)
        plan.setdefault(name, ("text", text))
    return plan, notes


def get_text(plan, dest):
    kind, val = plan[dest]
    if kind == "text":
        return val
    try:
        with open(val, encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        return None


def section_end(lines, start):
    """Index after the last non-blank line of the section that starts at lines[start] (a heading)."""
    end = start + 1
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("#"):
            break
        if lines[i].strip():
            end = i + 1
    return end


def run_fix(fix, plan, do):
    """(applicable, [message lines]). When do is true the plan is changed."""
    op, file = fix.get("op"), fix.get("file")
    if op == "offer":
        return False, ["offer: listed only, never applied automatically"]
    if op == "set_bank_field":
        text = get_text(plan, "bank.json")
        bank = json.loads(text)
        rows = {b["id"]: b for b in bank["bullets"]}
        missing = [i for i in fix.get("ids", []) if i not in rows]
        if missing:
            return False, [f"not applicable: unknown bullet {', '.join(missing)}"]
        changed = [i for i in fix["ids"] if rows[i].get(fix["field"]) != fix["value"] or fix["field"] not in rows[i]]
        if not changed:
            return False, [f"not applicable: {fix['field']} already has that value"]
        msgs = [f"  {i}.{fix['field']}: {json.dumps(rows[i].get(fix['field']), ensure_ascii=False)} -> {json.dumps(fix['value'], ensure_ascii=False)}"
                for i in changed]
        if do:
            for i in changed:
                rows[i][fix["field"]] = fix["value"]
            plan["bank.json"] = ("text", jtext(bank))
        return True, msgs
    if op not in ("replace", "append_line"):
        return False, [f"not applicable: unknown op {op!r}"]
    if file not in plan:
        return False, [f"not applicable: file {file!r} not found in the new folder"]
    text = get_text(plan, file)
    if text is None:
        return False, [f"not applicable: {file} is not a text file"]
    if op == "replace":
        n = text.count(fix["find"]) if fix.get("find") else 0
        if n != 1:
            return False, ["not applicable: text not found" if n == 0 else f"not applicable: text found {n} times (it must occur once)"]
        if do:
            plan[file] = ("text", text.replace(fix["find"], fix["replace"]))
        return True, [f"  before: {fix['find']}", f"  after:  {fix['replace']}"]
    lines = text.split("\n")
    want = fix["after_heading"].lstrip("#").strip()
    start = next((i for i, l in enumerate(lines) if l.startswith("#") and l.lstrip("#").strip() == want), None)
    if start is None:
        return False, [f"not applicable: heading {fix['after_heading']!r} not found"]
    end = section_end(lines, start)
    if any(l.strip() == fix["line"].strip() for l in lines[start + 1:end]):
        return False, ["not applicable: line already present"]
    if do:
        plan[file] = ("text", "\n".join(lines[:end] + [fix["line"]] + lines[end:]))
    return True, [f"  before: (the {fix['after_heading']!r} section does not have this line)", f"  after:  {fix['line']}  (added to the end of that section)"]


def load_fixes(path):
    if not path:
        return []
    try:
        fixes = read_json(path)
    except (OSError, ValueError) as e:
        refuse(f"cannot read the fixes file {path} ({e})")
    if not isinstance(fixes, list) or not all(isinstance(f, dict) and f.get("id") and f.get("op") for f in fixes):
        refuse("the fixes file must be a JSON list of {id, description, op, ...}")
    if len({f["id"] for f in fixes}) != len(fixes):
        refuse("the fixes file has a repeated id")
    keys = {"replace": ("file", "find", "replace"), "append_line": ("file", "after_heading", "line"),
            "set_bank_field": ("ids", "field", "value"), "offer": ()}
    for f in fixes:
        if f["op"] not in keys:
            refuse(f"fix {f['id']}: unknown op {f['op']!r} (use {', '.join(keys)})")
        lacking = [k for k in keys[f["op"]] if k not in f]
        if lacking:
            refuse(f"fix {f['id']}: op {f['op']} needs {', '.join(lacking)}")
    return fixes


def attention(doc):
    """(N, M) from out/preflight.json, or None when its shape is not recognised."""
    if isinstance(doc, dict) and isinstance(doc.get("summary"), str):  # the real preflight.py: "N of M bullets need attention"
        m = re.match(r"(\d+) of (\d+) bullets need attention", doc["summary"])
        if m:
            return int(m.group(1)), int(m.group(2))
    if isinstance(doc, dict) and isinstance(doc.get("summary"), dict) and {"needs_attention", "bullets"} <= set(doc["summary"]):
        return doc["summary"]["needs_attention"], doc["summary"]["bullets"]
    items = doc.get("bullets") if isinstance(doc, dict) else None
    if isinstance(items, dict):
        items = list(items.values())
    if not isinstance(items, list):
        return None
    flagged = [x for x in items if isinstance(x, dict) and (x.get("needs_attention") is True or x.get("findings") or x.get("results")
                                                              or x.get("level") in ("FAIL", "WARN"))]
    return len(flagged), len(items)


def child(script, path, *extra):
    env = dict(os.environ, RESUME_SKILL_DATA=path)
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *extra], capture_output=True, text=True, env=env,
                          stdin=subprocess.DEVNULL, timeout=600)


def write_plan(plan, new):
    os.makedirs(new, exist_ok=True)
    for d in su.DIRS:
        os.makedirs(os.path.join(new, d), exist_ok=True)
    for dest, (kind, val) in sorted(plan.items()):
        full = os.path.join(new, dest)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        if kind == "copy":
            shutil.copyfile(val, full)
        else:
            with open(full, "w", encoding="utf-8") as f:
                f.write(val)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--old", required=True, help="the old repo folder (read only)")
    ap.add_argument("--data", required=True, help="the new data folder (must not exist or be empty)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fixes", help="JSON list of fixes")
    ap.add_argument("--apply", nargs="+", action="extend", default=[], metavar="ID", help="fix ids to apply")
    a = ap.parse_args(argv)
    old, new = os.path.abspath(os.path.expanduser(a.old)), os.path.abspath(os.path.expanduser(a.data))
    if not os.path.isdir(old):
        refuse(f"{old} is not a folder")
    if su.inside(new, su.SKILL_DIR):
        refuse(f"{new} is inside the skill folder; pick a folder outside it")
    if os.path.isfile(new) or (os.path.isdir(new) and os.listdir(new)):
        refuse(f"{new} already exists and is not empty; the import needs a new or empty folder")
    plan, notes = build_plan(old)
    fixes = load_fixes(a.fixes)
    unknown = [i for i in a.apply if i not in {f["id"] for f in fixes}]
    if unknown:
        refuse(f"no fix with id {', '.join(unknown)} in the fixes file")
    n_files = len(plan)
    print(f"import {old} -> {new}: {n_files} files mapped" + (" (dry run, nothing is written)" if a.dry_run else ""))
    for n in notes:
        print("note:", n)
    if a.dry_run:
        for f in fixes:
            if f["op"] == "offer":
                state = "offer"
            else:
                ok, msgs = run_fix(f, plan, False)
                state = "yes" if ok else "no"
            line = f"  [{f['id']}] applicable: {state:<5} {f.get('description', '')}"
            if state == "no":
                line += f"  -- {msgs[0]}"
            if state == "offer":
                line += "  -- listed only, never applied automatically"
            print(line + ("  (selected by --apply)" if f["id"] in a.apply else ""))
        print(f"fixes: {len(fixes)} listed. dry run: nothing was written.")
        return 0
    applied = skipped = 0
    for f in fixes:
        if f["id"] not in a.apply:
            continue
        ok, msgs = run_fix(f, plan, True)
        print(f"fix [{f['id']}] {f.get('description', '')}: {'applied' if ok else msgs[0]}")
        if ok:
            print("\n".join(msgs))
        applied, skipped = applied + ok, skipped + (not ok)
    write_plan(plan, new)
    print(f"copied {n_files} files; fixes: {applied} applied, {skipped} not applied.")
    print("settings.json is the shipped defaults. Values the old check.py held (limits, banned words, internal names, "
          "and anything else user-specific) are not carried: set them in settings.json by hand.")
    r = child("validate.py", new)
    print(r.stdout.rstrip())
    if r.stderr.strip():
        print(r.stderr.rstrip(), file=sys.stderr)
    if os.path.exists(os.path.join(SCRIPTS, "preflight.py")):
        child("preflight.py", new, "--quiet")
        pf = os.path.join(new, "out", "preflight.json")
        if os.path.isfile(pf):
            try:
                n = attention(read_json(pf))
            except ValueError:
                n = None
            print(f"{n[0]} of {n[1]} bullets need attention" if n else "preflight ran, but out/preflight.json has a shape this tool does not read")
    return 0 if r.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
