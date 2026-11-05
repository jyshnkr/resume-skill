#!/usr/bin/env python3
"""Save an approved change to the data folder safely, with a backup and an undo. Never prompts.

    python3 save.py PLAN.json [--dry-run] [--yes] [--json]
    python3 save.py --undo [ID] [--yes] [--unfreeze]
    python3 save.py --lock        make every sent tailoring read-only (a save and an undo do this by themselves)

PLAN.json:
    {"id": "2026-11-04-acme-backend", "reason": "one line", "note": "text of the dated note",
     "writes": [{"path": "jobs/acme-backend/tailoring.json", "content": {...json...}},
                {"path": "jobs/acme-backend/notes.txt", "text": "..."},
                {"path": "jobs/old/posting.md", "delete": true}],
     "correction": false}
Paths are relative to the data folder. The data folder comes from where.py.

Flow (plan -> validate -> confirm -> apply -> verify):
  1. Check the plan: paths relative, inside the data folder, no "..", not under backups/ or changes/; the id is new.
  2. Stage: copy the data folder to a temp folder, apply the writes there and run validate.py on the copy.
     Any ERROR refuses the save; nothing in the real folder changes.
  3. Without --yes the plan is printed and the script stops (exit 2). --dry-run prints it and stops (exit 0).
  4. With --yes: files that will change or go are copied to backups/<id>/ (same relative paths, plus manifest.json),
     each file is written through a temp file and renamed, changes/<id>.md (the dated note) is written, preflight.py
     --quiet runs if it exists (failure ignored), and settings output.backup_copy_to (if set) gets a copy of the backup.
  5. Verify: every file is read back. A failed write puts the old files back.
A tailoring whose status is submitted or archived is frozen. A plan touching it is refused unless the plan has
"correction": true and its note starts with "Correction".

--undo restores the newest backup (or the ID given) exactly, removes the files that save created, and writes
changes/<id>-undo.md. It refuses when those files changed since the save, unless --yes. A backup whose manifest.json
is unreadable or incomplete is unusable: --undo ID names it and stops; a bare --undo skips it and says so.
--undo also refuses when a file it would overwrite or delete is currently a submitted or archived tailoring (an undo
could turn a sent resume back into a draft). Add --unfreeze together with --yes to undo anyway; the reply says which
sent files were unfrozen.

Paths are judged on the real file, not the spelling: a different letter case, a hard link or a folder symlink cannot
reach backups/, changes/ or a sent tailoring. A path that goes through a symlink is refused. Two plan paths that differ
only in letter case count as the same path.

Exit 0: done (or a dry run). Exit 2: the plan was printed and waits for --yes. Exit 1: refused or an error (one line each).
Writes only inside the data folder (and the optional backup_copy_to folder).
"""
import datetime, glob, hashlib, json, os, re, shutil, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resume_data as rd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
FROZEN = ("submitted", "archived")
RESERVED_DIRS = ("backups", "changes")


def fail(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def write_atomic(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = os.path.join(os.path.dirname(path), "." + os.path.basename(path) + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def inside(root, path):
    r = os.path.realpath(root)
    return os.path.realpath(path) == r or os.path.realpath(path).startswith(r + os.sep)


# ---------- 1. the plan ----------

def load_plan(path):
    try:
        with open(path, encoding="utf-8") as f:
            plan = json.load(f)
    except OSError as e:
        fail(f"cannot read {path}: {e.strerror or e}")
    except ValueError as e:
        fail(f"{path} is not valid JSON: {e}")
    if not isinstance(plan, dict):
        fail("the plan must be a JSON object")
    for key in ("id", "reason", "note"):
        if not isinstance(plan.get(key), str) or not plan[key].strip():
            fail(f"the plan needs a non-empty \"{key}\"")
    if not ID_RE.fullmatch(plan["id"]) or plan["id"].endswith("-undo"):
        fail(f"id {plan['id']!r} must be letters, digits, dot, dash or underscore, and not end in -undo")
    if not isinstance(plan.get("writes"), list) or not plan["writes"]:
        fail("the plan needs a non-empty \"writes\" list")
    return plan


def same_file(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def reserved_reason(root, rel):
    """Why a plan may not write rel (judged on the real file and folders, and on letter case), or None."""
    first = rel.split("/")[0]
    if first.casefold() in RESERVED_DIRS:
        return f"under {first.casefold()}/, which save.py manages itself"
    if rel.casefold() == "manifest.json":
        return "manifest.json at the top of the data folder is reserved"
    target = os.path.join(root, *rel.split("/"))
    d = os.path.dirname(target)
    while len(d) > len(root):  # a folder that is the real backups/ or changes/ under another spelling
        if os.path.isdir(d) and any(same_file(d, os.path.join(root, r)) for r in RESERVED_DIRS):
            return "inside backups/ or changes/, which save.py manages itself"
        d = os.path.dirname(d)
    if os.path.exists(target) and same_file(target, os.path.join(root, "manifest.json")):
        return "manifest.json at the top of the data folder is reserved"
    return None


def check_plan(plan, root):
    """Returns [(relative path, action, bytes or None)] in plan order, or exits with one line."""
    pid = plan["id"]
    if os.path.exists(os.path.join(root, "changes", pid + ".md")) or os.path.exists(os.path.join(root, "backups", pid)):
        fail(f"id {pid!r} is already used; pick a new id (see changes/ and backups/)")
    base = os.path.realpath(root)
    items, seen, seen_files = [], set(), []
    for w in plan["writes"]:
        if not isinstance(w, dict) or not isinstance(w.get("path"), str) or not w["path"]:
            fail("every write needs a \"path\"")
        p = w["path"]
        parts = p.replace("\\", "/").split("/")
        if os.path.isabs(p) or p.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", p):
            fail(f"path {p!r} must be relative to the data folder")
        if ".." in parts:
            fail(f"path {p!r} must stay inside the data folder (no \"..\")")
        rel = "/".join(x for x in parts if x not in ("", "."))
        if not rel:
            fail(f"path {p!r} is empty")
        if rel.casefold() in seen:
            fail(f"path {rel!r} appears twice in the plan (paths that differ only in letter case count as the same)")
        seen.add(rel.casefold())
        target = os.path.join(base, *rel.split("/"))
        if not inside(base, target):
            fail(f"path {p!r} must stay inside the data folder")
        if os.path.realpath(target) != target:
            fail(f"path {p!r} goes through a symlink; write to the real path instead")
        why = reserved_reason(base, rel)
        if why:
            fail(f"path {p!r}: {why}")
        if os.path.exists(target):
            if any(same_file(target, f) for f in seen_files):
                fail(f"path {rel!r} is the same file as another path in the plan")
            seen_files.append(target)
        kinds = [k for k in ("content", "text", "delete") if k in w and not (k == "delete" and not w[k])]
        if len(kinds) != 1:
            fail(f"write {p!r} needs exactly one of content, text or delete")
        exists = os.path.exists(target)
        if kinds[0] == "delete":
            if not os.path.isfile(target):
                fail(f"cannot delete {rel!r}: it does not exist")
            items.append((rel, "delete", None))
        else:
            if exists and not os.path.isfile(target):
                fail(f"{rel!r} is not a file")
            if kinds[0] == "content":
                if isinstance(w["content"], str) or not rel.endswith(".json"):
                    fail(f"write {p!r}: content is JSON data for a .json file; use text for any other file")
                data = (json.dumps(w["content"], indent=2, ensure_ascii=False) + "\n").encode("utf-8")
            elif isinstance(w["text"], str):
                data = w["text"].encode("utf-8")
            else:
                fail(f"text for {rel!r} must be a string")
            items.append((rel, "change" if exists else "create", data))
    check_frozen(plan, base, items)
    return items


def frozen_tailoring(root, rel):
    """(real tailoring path relative to root, status, sent_on) when rel is, on disk, a submitted or archived tailoring."""
    target = os.path.join(root, *rel.split("/"))
    if not os.path.isfile(target):
        return None
    for f in sorted(glob.glob(os.path.join(root, "jobs", "*", "tailoring.json"))):
        if same_file(target, f):
            try:
                t = json.loads(read_bytes(f).decode("utf-8"))
            except ValueError:
                return None
            status = t.get("status") if isinstance(t, dict) else None
            if status in FROZEN:
                return os.path.relpath(f, root).replace(os.sep, "/"), status, t.get("sent_on")
    return None


def check_frozen(plan, root, items):
    ok_correction = plan.get("correction") is True and plan["note"].startswith("Correction")
    for rel, _, _ in items:
        hit = frozen_tailoring(root, rel)
        if hit and not ok_correction:
            name, status, sent_on = hit
            sent = f" (sent {sent_on})" if sent_on else ""
            fail(f"{name} is {status}{sent} and frozen. To fix a mistake in a sent resume, set \"correction\": true "
                 f"in the plan and start the note with \"Correction\".")


# ---------- 2. the stage ----------

def apply_items(root, items):
    for rel, action, data in items:
        target = os.path.join(root, *rel.split("/"))
        if action == "delete":
            os.remove(target)
        else:
            write_atomic(target, data)


def validate_stage(root, items):
    stage = tempfile.mkdtemp(prefix="resume-skill-stage-")
    try:
        data = os.path.join(stage, "data")
        shutil.copytree(root, data, symlinks=True,
                        ignore=lambda d, names: ["backups"] if os.path.realpath(d) == os.path.realpath(root) else [])
        apply_items(data, items)
        script = os.path.join(HERE, "validate.py")
        if not os.path.exists(script):
            print("warning: validate.py not found; the checked-copy step was skipped", file=sys.stderr)
            return
        env = dict(os.environ, RESUME_SKILL_DATA=data)
        r = subprocess.run([sys.executable, script], capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL, timeout=300)
        if r.returncode == 1:
            lines = [l for l in (r.stdout + r.stderr).splitlines() if "ERROR" in l] or (r.stdout + r.stderr).splitlines()[-10:]
            print("error: validate.py found errors in the changed copy; nothing was saved", file=sys.stderr)
            for l in lines:
                print(l, file=sys.stderr)
            sys.exit(1)
    finally:
        shutil.rmtree(stage, ignore_errors=True)


# ---------- 3-5. confirm, apply, verify ----------

def describe(plan, items):
    lines = [f"Plan {plan['id']}: {plan['reason']}"]
    lines += [f"  {action:<6} {rel}" for rel, action, _ in items]
    lines.append("Note: " + plan["note"])
    return lines


def now():
    return datetime.datetime.now()


def save(plan, items, root, as_json):
    pid = plan["id"]
    bdir = os.path.join(root, "backups", pid)
    changed = [r for r, a, _ in items if a == "change"]
    deleted = [r for r, a, _ in items if a == "delete"]
    created = [r for r, a, _ in items if a == "create"]
    for rel in changed + deleted:
        write_atomic(os.path.join(bdir, *rel.split("/")), read_bytes(os.path.join(root, *rel.split("/"))))
    created_dirs = []
    for rel in created:
        d = os.path.dirname(os.path.join(root, *rel.split("/")))
        missing = []
        while not os.path.isdir(d):
            missing.append(os.path.relpath(d, root).replace(os.sep, "/"))
            d = os.path.dirname(d)
        created_dirs += [m for m in missing if m not in created_dirs]
    manifest = {"id": pid, "saved_at": now().isoformat(), "reason": plan["reason"], "changed": changed, "deleted": deleted,
                "created": created, "created_dirs": created_dirs,
                "after": {rel: (sha(data) if data is not None else None) for rel, _, data in items}, "undone": False}
    write_atomic(os.path.join(bdir, "manifest.json"), (json.dumps(manifest, indent=2) + "\n").encode("utf-8"))
    try:
        apply_items(root, items)
        note = [f"# {pid}", "", f"Date: {now().date().isoformat()}", f"Reason: {plan['reason']}", "", "Files changed:"]
        note += [f"- {rel} ({action}d)" for rel, action, _ in items]
        note += ["", "Note:", plan["note"], ""]
        write_atomic(os.path.join(root, "changes", pid + ".md"), "\n".join(note).encode("utf-8"))
        verify(items, root, pid)
    except (OSError, RuntimeError) as e:
        restore(root, manifest)
        fail(f"the save failed ({e}); the old files were put back")
    mirror(root, bdir, pid)
    rd.lock_frozen(root)  # a tailoring that is now sent becomes read-only on disk
    preflight(root)
    result = {"id": pid, "status": "saved", "files": [{"path": r, "action": a} for r, a, _ in items],
              "undo": f"save.py --undo {pid}"}
    if as_json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Saved {pid}: {len(items)} file(s). Backup in backups/{pid}/. Undo with: save.py --undo {pid}")


def verify(items, root, pid):
    for rel, action, data in items:
        p = os.path.join(root, *rel.split("/"))
        if action == "delete":
            if os.path.exists(p):
                raise RuntimeError(f"{rel} is still there")
        elif not os.path.isfile(p) or read_bytes(p) != data:
            raise RuntimeError(f"{rel} does not read back as written")
    if not os.path.isfile(os.path.join(root, "changes", pid + ".md")):
        raise RuntimeError("the dated note was not written")


def mirror(root, bdir, pid):
    dest = rd.settings(root).get("output", {}).get("backup_copy_to")
    if not dest:
        return
    try:
        shutil.copytree(bdir, os.path.join(os.path.expanduser(dest), pid), dirs_exist_ok=True)
    except OSError as e:
        print(f"warning: could not copy the backup to {dest}: {e.strerror or e}", file=sys.stderr)


def preflight(root):
    script = os.path.join(HERE, "preflight.py")
    if os.path.exists(script):
        try:
            subprocess.run([sys.executable, script, "--quiet"], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                           env=dict(os.environ, RESUME_SKILL_DATA=root), timeout=120)
        except (OSError, subprocess.SubprocessError):
            pass


# ---------- undo ----------

def restore(root, manifest):
    """Put back the backed-up files, remove the created ones and the folders save made if they are empty."""
    bdir = os.path.join(root, "backups", manifest["id"])
    for rel in manifest["changed"] + manifest["deleted"]:
        write_atomic(os.path.join(root, *rel.split("/")), read_bytes(os.path.join(bdir, *rel.split("/"))))
    for rel in manifest["created"]:
        p = os.path.join(root, *rel.split("/"))
        if os.path.isfile(p):
            os.remove(p)
    for rel in sorted(manifest["created_dirs"], key=len, reverse=True):
        try:
            os.rmdir(os.path.join(root, *rel.split("/")))
        except OSError:
            pass


def safe_rel(rel):
    return (isinstance(rel, str) and rel and not os.path.isabs(rel) and not rel.startswith(("/", "~", "\\"))
            and ".." not in rel.replace("\\", "/").split("/") and not re.match(r"^[A-Za-z]:", rel))


def load_manifest(root, name):
    """(manifest, None) for a usable backup folder, else (None, reason). Checks the keys, the paths and the backed-up files."""
    bdir = os.path.join(root, "backups", name)
    try:
        m = json.loads(read_bytes(os.path.join(bdir, "manifest.json")).decode("utf-8"))
    except OSError:
        return None, "manifest.json is missing or unreadable"
    except ValueError:
        return None, "manifest.json is not valid JSON"
    if not isinstance(m, dict):
        return None, "manifest.json is not an object"
    for key in ("id", "saved_at"):
        if not isinstance(m.get(key), str):
            return None, f"manifest.json has no \"{key}\""
    if m["id"] != name:
        return None, f"manifest.json says id {m['id']!r}"
    for key in ("changed", "deleted", "created", "created_dirs"):
        if not isinstance(m.get(key), list) or not all(safe_rel(x) for x in m[key]):
            return None, f"manifest.json has a bad \"{key}\" list"
    if not isinstance(m.get("after"), dict) or not all(safe_rel(k) and (v is None or isinstance(v, str)) for k, v in m["after"].items()):
        return None, "manifest.json has a bad \"after\" entry"
    if set(m["after"]) != set(m["changed"] + m["deleted"] + m["created"]):
        return None, "manifest.json file lists do not match"
    m.setdefault("reason", "")
    m["undone"] = bool(m.get("undone", False))
    for rel in m["changed"] + m["deleted"]:
        if not os.path.isfile(os.path.join(bdir, *rel.split("/"))):
            return None, f"the backed-up copy of {rel} is missing"
    return m, None


def manifests(root):
    """(usable manifests, [(folder, reason)] for the unusable ones)."""
    out, bad = [], []
    b = os.path.join(root, "backups")
    for name in sorted(os.listdir(b)) if os.path.isdir(b) else []:
        if not os.path.isdir(os.path.join(b, name)):
            continue
        m, why = load_manifest(root, name)
        if m:
            out.append(m)
        else:
            bad.append((name, why))
    return out, bad


def undo(root, pid, yes, unfreeze):
    if pid:
        if not ID_RE.fullmatch(pid):
            fail(f"id {pid!r} is not a valid id")
        if not os.path.isdir(os.path.join(root, "backups", pid)):
            fail(f"no backup named {pid!r} in backups/")
        m, why = load_manifest(root, pid)
        if m is None:
            fail(f"backups/{pid} is unusable: {why}")
        if m["undone"]:
            fail(f"{pid} was already undone")
    else:
        ms, bad = manifests(root)
        for name, why in bad:
            print(f"warning: skipped unusable backup backups/{name}: {why}", file=sys.stderr)
        live = [x for x in ms if not x["undone"]]
        if not live:
            fail("nothing to undo: no usable saved backup in backups/")
        m = max(live, key=lambda x: x["saved_at"])
    moved = []
    for rel, digest in m["after"].items():
        p = os.path.join(root, *rel.split("/"))
        now_sha = sha(read_bytes(p)) if os.path.isfile(p) else None
        if now_sha != digest:
            moved.append(rel)
    if moved and not yes:
        print(f"error: {', '.join(moved)} changed since {m['id']} was saved; undoing would overwrite that. "
              f"Run again with --yes to undo anyway.", file=sys.stderr)
        sys.exit(1)
    sent = [(rel, hit) for rel in m["after"] for hit in [frozen_tailoring(root, rel)] if hit]
    if sent and not (unfreeze and yes):
        names = ", ".join(f"{h[0]} ({h[1]})" for _, h in sent)
        fail(f"undoing {m['id']} would change {names}, a sent tailoring. Add --unfreeze together with --yes to undo "
             f"anyway; that puts the sent file back to the older saved content or removes it.")
    restore(root, m)
    bdir = os.path.join(root, "backups", m["id"])
    for rel in m["changed"] + m["deleted"]:
        if read_bytes(os.path.join(root, *rel.split("/"))) != read_bytes(os.path.join(bdir, *rel.split("/"))):
            fail(f"{rel} did not read back as the backup after the undo")
    m["undone"], m["undone_on"] = True, now().isoformat()
    write_atomic(os.path.join(bdir, "manifest.json"), (json.dumps(m, indent=2) + "\n").encode("utf-8"))
    note = [f"# {m['id']}-undo", "", f"Date: {now().date().isoformat()}", f"Undid: {m['id']} ({m['reason']})", "", "Files restored:"]
    note += [f"- {r} (restored from backup)" for r in m["changed"] + m["deleted"]]
    note += [f"- {r} (removed, it was created by the save)" for r in m["created"]]
    if moved:
        note += ["", "Changed since the save and overwritten by this undo: " + ", ".join(moved)]
    if sent:
        note += ["", "Unfroze (--unfreeze): " + ", ".join(f"{h[0]} was {h[1]}" for _, h in sent)]
    write_atomic(os.path.join(root, "changes", m["id"] + "-undo.md"), ("\n".join(note) + "\n").encode("utf-8"))
    rd.lock_frozen(root)  # a tailoring that is now sent becomes read-only on disk
    preflight(root)
    print(f"Undid {m['id']}: {len(m['changed']) + len(m['deleted'])} file(s) restored, {len(m['created'])} removed.")
    if sent:
        print("Unfroze " + ", ".join(f"{h[0]} (it was {h[1]})" for _, h in sent) + ": --unfreeze changed a sent tailoring.")


def main(argv):
    if {"-h", "--help"} & set(argv):
        print(__doc__)
        return 0
    yes, dry, as_json, unfreeze = "--yes" in argv, "--dry-run" in argv, "--json" in argv, "--unfreeze" in argv
    rest = [a for a in argv if a not in ("--yes", "--dry-run", "--json", "--unfreeze", "--lock")]
    if "--lock" in argv:
        if rest:
            fail("usage: save.py --lock")
        locked = rd.lock_frozen(rd.data_root())
        print("\n".join(f"locked (read-only): {p}" for p in locked) if locked else "nothing to lock: every sent tailoring is already read-only")
        return 0
    if unfreeze and "--undo" not in rest:
        fail("--unfreeze only applies to --undo")
    if unfreeze and not yes:
        fail("--unfreeze needs --yes")
    root = rd.data_root()
    if "--undo" in rest:
        rest.remove("--undo")
        if len(rest) > 1 or any(a.startswith("--") for a in rest):
            fail("usage: save.py --undo [ID] [--yes]")
        undo(root, rest[0] if rest else None, yes, unfreeze)
        return 0
    if len(rest) != 1 or rest[0].startswith("--"):
        fail("usage: save.py PLAN.json [--dry-run] [--yes] [--json]")
    plan = load_plan(rest[0])
    items = check_plan(plan, root)
    validate_stage(root, items)
    if dry or not yes:
        if as_json:
            print(json.dumps({"id": plan["id"], "status": "dry-run" if dry else "needs-yes", "reason": plan["reason"],
                              "files": [{"path": r, "action": a} for r, a, _ in items], "note": plan["note"]}, indent=2))
        else:
            print("\n".join(describe(plan, items)))
            print("Dry run: nothing was changed." if dry else "Nothing was changed. Run again with --yes to save.")
        return 0 if dry else 2
    try:
        save(plan, items, root, as_json)
    except OSError as e:
        fail(f"could not write the backup or files: {e.strerror or e}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
