#!/usr/bin/env python3
"""Validate the data folder: schema, unique IDs, references, private terms kept out of public fields, override lint.

Stdlib only. Exit 0 clean (warnings print but do not fail), 1 on any error.

    python3 validate.py            # the data folder from where.py (RESUME_SKILL_DATA, saved location, default)
    python3 validate.py --json     # {"errors": [...], "warnings": [...], "counts": {...}} instead of text lines

Checks: bank rows (ids, role is in bank.json "roles", status approved or candidate, marks for every version, lead word, tech list;
a candidate row is never marked in, placed in a version or used in a tailoring), summaries,
every versions/*.json, every jobs/<slug>/tailoring.json (base is a version, posting file exists, status, submitted
tailorings carry sent_on or bank_commit, override lint), private terms from private/terms.json, and the settings file
(settings.yaml; the older settings.json is still read) against assets/defaults/settings.yaml: new options are warnings,
unknown options are warnings, a file that does not parse is an error naming the line, and a hand edit of the wrong kind
(a text where a list belongs, a rate that is not a number, minimum_rate_unit other than hour or year) is an error naming the key.
A folder that still holds settings.json gets a warning to run setup.py --convert-settings --yes.
"""
import glob, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resume_data as rd  # noqa: E402

STATUS = {"draft", "submitted", "archived"}
BANK_STATUS = {"approved", "candidate"}  # a bank row without "status" is approved
errors, warnings = [], []


def err(m): errors.append(m)
def warn(m): warnings.append(m)


def need(obj, keys, where):
    for k, t in keys.items():
        if k not in obj:
            err(f"{where}: missing '{k}'")
        elif t is not None and not isinstance(obj[k], t):
            err(f"{where}: '{k}' should be {t.__name__ if isinstance(t, type) else '/'.join(x.__name__ for x in t)}")


def unique(items, pattern, where):
    seen = set()
    for i in items:
        if not re.fullmatch(pattern, i.get("id", "")):
            err(f"{where}: bad id {i.get('id')!r} (want {pattern})")
        if i.get("id") in seen:
            err(f"{where}: duplicate id {i['id']}")
        seen.add(i.get("id"))


def load(name, root, required=True):
    """The JSON file, or None with an error (a broken file is reported, never a traceback)."""
    try:
        return rd.load(name, root)
    except FileNotFoundError:
        if required:
            err(f"{name}: file is missing")
    except (OSError, ValueError) as e:
        err(f"{name}: cannot read as JSON ({e})")
    return None


def private_matcher(root):
    """Colleague names, ADR numbers and internal codenames from private/terms.json."""
    p = os.path.join(root, "private", "terms.json")
    if not os.path.exists(p):
        warn("private/terms.json missing: private-term scan skipped")
        return None
    t = rd.private_terms(root)
    people = {p for n in t["people"] for p in [n] + n.split()}  # full names, first names and surnames
    parts = [r"\b" + re.escape(n) + r"\b" for n in sorted(people, key=len, reverse=True) if n] + [p for p in t["patterns"] if p]
    parts += [r"\b" + re.escape(n) + r"\b" for n in t["internal_codenames"] if n]
    stage = "|".join(map(re.escape, [w for w in t["stage_words"] if w]))
    if stage:  # stage words only count next to stage/canary/environment wording, as in check.py
        parts.append(r"(?i:\b(?:%s)\b(?=(?:\s+and\s+(?:%s))?[-\s]+(?:stages?|canar(?:y|ies)|environments?|accounts?|fleet)\b))" % (stage, stage))
    if not parts:  # an empty pattern would match everywhere
        return None
    try:
        return re.compile("|".join(parts))
    except re.error as e:
        err(f"private/terms.json: a pattern is not a valid regular expression ({e})")
        return None


def scan(rx, text, where):
    if rx and text:
        m = rx.search(text)
        if m:
            err(f"{where}: private term {m.group(0)!r} in a public field (move it to private_note or mark the row private)")


def is_text(v): return isinstance(v, str)
def is_number(v): return isinstance(v, (int, float)) and not isinstance(v, bool)
def is_text_list(v): return isinstance(v, list) and all(isinstance(x, str) for x in v)


# key path -> (check, what it should be). Run on the user's values laid over the defaults, so a missing key is never a type error.
SETTING_TYPES = {
    ("preferences", "work_type"): (is_text_list, "a list of text, for example [full-time, contract]"),
    ("preferences", "location"): (is_text, "text"),
    ("preferences", "remote"): (is_text, "text"),
    ("preferences", "minimum_rate"): (lambda v: v is None or is_number(v), "a number or null"),
    ("preferences", "minimum_rate_unit"): (lambda v: v in ("hour", "year"), "exactly hour or year"),
    ("preferences", "domains"): (is_text_list, "a list of text"),
    ("output", "copy_resumes_to"): (lambda v: v is None or is_text(v), "text (a folder) or null"),
    ("output", "backup_copy_to"): (lambda v: v is None or is_text(v), "text (a folder) or null"),
}


def settings_diff(root):
    """New options (in the shipped defaults, not in the user's file) and unknown options (the reverse), then the type checks.
    Dicts only, never lists."""
    path = rd.settings_path(root)
    if path is None:
        err("settings: no settings.yaml in the data folder")
        return
    name = os.path.basename(path)
    if os.path.isfile(os.path.join(root, "settings.json")):
        warn("settings: settings.json is the old format; run setup.py --convert-settings --yes for settings.yaml with hints")
    try:
        mine = rd.user_settings(root)
    except (OSError, ValueError) as e:
        err(str(e) if str(e).startswith(name) else f"{name}: {e}")
        return

    def walk(default, user, path):
        for k, v in default.items():
            if k not in user:
                warn(f"settings: new option '{path}{k}' (run setup.py --add-missing-settings)")
            elif isinstance(v, dict) and isinstance(user[k], dict):
                walk(v, user[k], f"{path}{k}.")
        for k, v in user.items():
            if k not in default:
                warn(f"settings: unknown option '{path}{k}'")
    walk(rd.default_settings(), mine, "")
    merged = rd.settings(root)
    for keys, (ok, want) in SETTING_TYPES.items():
        v = merged.get(keys[0], {}).get(keys[1]) if isinstance(merged.get(keys[0]), dict) else None
        if not ok(v):
            err(f"{name}: {'.'.join(keys)} should be {want}, not {v!r}")
    weights = merged.get("fit", {}).get("weights") if isinstance(merged.get("fit"), dict) else None
    if not isinstance(weights, dict):
        err(f"{name}: fit.weights should be a list of 'name: number' entries (required and preferred), not {weights!r}")
    else:
        for k, v in weights.items():
            if not is_number(v):
                err(f"{name}: fit.weights.{k} should be a number, not {v!r}")


def main(as_json=False):
    root = rd.data_root()
    rx = private_matcher(root)
    bank_doc = load("bank.json", root) or {}
    bank = bank_doc.get("bullets", []) if isinstance(bank_doc, dict) else []
    roles = bank_doc.get("roles") if isinstance(bank_doc, dict) else None
    if not isinstance(roles, list):
        err("bank.json: 'roles' should be a list of role keys")
        roles = []
    if not isinstance(bank, list):
        err("bank.json: 'bullets' should be a list")
        bank = []
    versions = rd.version_names(root)
    if not versions:
        warn("versions: none yet (add one under versions/ before building a resume)")
    unique(bank, r"b\d{3}", "bank")
    idx = {b["id"]: b for b in bank}
    for b in bank:
        w = f"bank {b.get('id')}"
        need(b, {"role": str, "project": (str, type(None)), "lead": str, "text": str, "marks": dict, "held_back": bool,
                 "needs_metric": bool, "allowed_repeats": list, "note": str, "private_note": str}, w)
        if b.get("role") not in roles:
            err(f"{w}: role {b.get('role')!r} not in {sorted(roles)}")
        if (b.get("role") == "project") != bool(b.get("project")):
            err(f"{w}: project bullets need a project name, others must not have one")
        if not (isinstance(b.get("status", "approved"), str) and b.get("status", "approved") in BANK_STATUS):
            err(f"{w}: status {b.get('status')!r} should be approved or candidate")
        cand = b.get("status") == "candidate"
        for v in versions:
            m = b.get("marks", {}).get(v) if isinstance(b.get("marks"), dict) else None
            if not isinstance(m, dict) or not isinstance(m.get("in"), bool):
                err(f"{w}: marks.{v} needs {{raw, in}}")
            elif cand and m["in"]:
                err(f"{w}: candidate bullet is marked in version {v!r}")
        if "tech" not in b:
            if not cand:
                warn(f"{w}: no 'tech' list (the tools this bullet used; add [] if none)")
        elif not isinstance(b["tech"], list) or not all(isinstance(x, str) for x in b["tech"]):
            err(f"{w}: 'tech' should be a list of strings")
        if str(b.get("text", "")).split(" ", 1)[0] != b.get("lead"):
            err(f"{w}: lead {b.get('lead')!r} is not the first word of the text")
        for f in ("lead", "text", "note"):
            scan(rx, b.get(f), f"{w}.{f}")
    sums_doc = load("summaries.json", root) or {}
    sums = sums_doc.get("summaries", []) if isinstance(sums_doc, dict) else []
    unique(sums, r"s\d{2}", "summaries")
    for s in sums:
        need(s, {"version": str, "text": str, "status": str, "traces_to": str}, f"summary {s.get('id')}")
        for f in ("version", "text", "traces_to"):
            scan(rx, s.get(f), f"summary {s.get('id')}.{f}")
    for name in versions:
        v = load(f"versions/{name}.json", root)
        if not isinstance(v, dict):
            continue
        w = f"versions/{name}"
        need(v, {"summary": str, "roles": list, "education": list, "skills": list, "projects": list}, w)
        if "certifications" in v and not isinstance(v["certifications"], list):
            err(f"{w}: 'certifications' should be a list")
        if v.get("unmatched"):
            err(f"{w}: {len(v['unmatched'])} bullets are not in the bank")
        scan(rx, v.get("summary"), f"{w}.summary")
        for r in (v["roles"] if isinstance(v.get("roles"), list) else []) + (v["projects"] if isinstance(v.get("projects"), list) else []):
            need(r, {"bullet_ids": list}, w)
            for i in r.get("bullet_ids", []) if isinstance(r.get("bullet_ids"), list) else []:
                if isinstance(i, str):
                    if i not in idx:
                        err(f"{w}: unknown bullet {i}")
                    elif idx[i].get("status") == "candidate":
                        err(f"bank {i}: candidate bullet is used in version {name!r}")
                    elif not (idx[i].get("marks", {}).get(name) or {}).get("in"):
                        err(f"{w}: {i} ({idx[i].get('lead')}) is used but not marked for {name} in the bank")
        for s in v["skills"] if isinstance(v.get("skills"), list) else []:
            scan(rx, s.get("value"), f"{w}.skills.{s.get('label')}")
    slugs = rd.tailoring_slugs(root)
    for slug in slugs:
        t = load(f"jobs/{slug}/tailoring.json", root)
        if not isinstance(t, dict):
            continue
        w = f"jobs/{slug}"
        need(t, {"slug": str, "base": str, "status": str, "summary": str, "roles": list, "education": list, "skills": list,
                 "projects": list}, w)
        for k in ("client", "location", "rate", "recruiter", "posting", "sent_on", "bank_commit"):
            if t.get(k) is not None and not isinstance(t[k], str):
                err(f"{w}: '{k}' should be text or null")
        if t.get("slug") != slug:
            err(f"{w}: slug {t.get('slug')!r} does not match the folder name")
        if t.get("base") not in versions:
            err(f"{w}: base {t.get('base')!r} is not a version ({', '.join(versions) or 'none yet'})")
        if t.get("posting") and not (isinstance(t["posting"], str) and os.path.isfile(os.path.join(root, "jobs", slug, t["posting"]))):
            err(f"{w}: posting {t['posting']!r} is not a file in jobs/{slug}/")
        if t.get("built_on") and t["built_on"] not in slugs:
            err(f"{w}: built_on {t['built_on']!r} is not a tailoring")
        if t.get("status") not in STATUS:
            err(f"{w}: status {t.get('status')!r} not in {sorted(STATUS)}")
        tpath = os.path.join(root, "jobs", slug, "tailoring.json")
        if t.get("status") in ("submitted", "archived") and os.stat(tpath).st_mode & 0o222:
            warn(f"{w}: sent tailoring is writable; run save.py --lock so a hand edit cannot change it")
        if t.get("status") == "submitted" and not (t.get("sent_on") or t.get("bank_commit")):
            err(f"{w}: submitted tailorings are frozen: set sent_on (the date it was sent) or bank_commit (the commit it was sent from)")
        scan(rx, t.get("summary"), f"{w}.summary")
        for s in t["skills"] if isinstance(t.get("skills"), list) else []:
            scan(rx, s.get("value"), f"{w}.skills.{s.get('label')}")
        for r in (t["roles"] if isinstance(t.get("roles"), list) else []) + (t["projects"] if isinstance(t.get("projects"), list) else []):
            for b in r.get("bullets", []):
                bw = f"{w} {b.get('id')}"
                if b.get("id") not in idx:
                    err(f"{bw}: unknown bank bullet")
                    continue
                if idx[b["id"]].get("status") == "candidate":
                    err(f"bank {b['id']}: candidate bullet is used in tailoring {slug!r}")
                if not isinstance(b.get("text"), str):
                    err(f"{bw}: missing 'text'")
                    continue
                scan(rx, b.get("text"), bw)
                same = b["text"] == idx[b["id"]]["text"]
                frozen = t.get("status") in ("submitted", "archived")  # sent text stays as sent; the bank may move on
                if b.get("override") == same and not (frozen and not b.get("override")):
                    err(f"{bw}: override is {b.get('override')} but the text {'matches' if same else 'differs from'} the bank")
                bracket_only = re.sub(r"\s*\([^()]*-style\)", "", b["text"]) == idx[b["id"]]["text"]
                if b.get("override") and not bracket_only and not b.get("why"):
                    err(f"{bw}: a reworded override needs a 'why' (one line on why it stays accurate, rule 48); "
                        "only a platform bracket may go without")
                if b.get("override") and b.get("similarity", 1) < 0.5:
                    warn(f"{bw}: override is a heavy rewrite (similarity {b['similarity']}); consider a new bank row")
    settings_diff(root)
    profile = os.path.join(root, "profile.md")
    if os.path.exists(profile):
        with open(profile, encoding="utf-8") as f:
            scan(rx, f.read(), "profile.md")
    counts = {"bullets": len(bank), "summaries": len(sums), "versions": len(versions), "tailorings": len(slugs)}
    if as_json:
        print(json.dumps({"errors": errors, "warnings": warnings, "counts": counts}, ensure_ascii=False))
    else:
        for m in warnings:
            print("WARN", m)
        for m in errors:
            print("ERROR", m)
        print(f"validate: {len(bank)} bullets, {len(sums)} summaries, {len(versions)} versions, {len(slugs)} tailorings: "
              f"{len(errors)} errors, {len(warnings)} warnings")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    a = sys.argv[1:]
    if {"-h", "--help"} & set(a):
        print(__doc__); sys.exit(0)
    if [x for x in a if x != "--json"]:
        raise SystemExit(f"error: unknown argument {[x for x in a if x != '--json'][0]!r}; see --help")
    main("--json" in a)
