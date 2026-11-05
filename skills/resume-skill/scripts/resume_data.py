#!/usr/bin/env python3
"""Load the user's data folder and resolve a version or a tailoring into one plain structure.

Stdlib only. Used by build_docx.py, export.py, check.py, preflight.py and save.py.

    python3 resume_data.py full-time                # print the resolved resume as plain text (a version name)
    python3 resume_data.py tailoring:acme-backend   # jobs/acme-backend/tailoring.json
    python3 resume_data.py file:/tmp/draft.json     # a draft tailoring kept outside the data folder
    add --with-contact to print the real contact line (otherwise a placeholder keeps it out of agent context)

The data folder comes from where.py (RESUME_SKILL_DATA, saved location, default). Pass root= to use another.
"""
import copy, glob, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import where  # noqa: E402

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SETTINGS = os.path.join(SKILL_DIR, "assets", "defaults", "settings.json")


def data_root(start=None):
    """The ready data folder from where.py, or exit with its message."""
    return start or where.data_root()


def load(name, root=None):
    with open(os.path.join(root or data_root(), name), encoding="utf-8") as f:
        return json.load(f)


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def default_settings():
    with open(DEFAULT_SETTINGS, encoding="utf-8") as f:
        return json.load(f)


def settings(root=None):
    """Shipped defaults with the user's settings.json laid over them (nested keys merged)."""
    root = root or data_root()
    try:
        mine = load("settings.json", root)
    except (OSError, ValueError):
        mine = {}
    return _merge(default_settings(), mine)


def version_names(root=None):
    root = root or data_root()
    return sorted(os.path.splitext(os.path.basename(f))[0] for f in glob.glob(os.path.join(root, "versions", "*.json")))


def tailoring_slugs(root=None):
    root = root or data_root()
    return sorted(os.path.basename(os.path.dirname(f)) for f in glob.glob(os.path.join(root, "jobs", "*", "tailoring.json")))


def bank_index(root=None):
    return {b["id"]: b for b in load("bank.json", root)["bullets"]}


def contact(root=None):
    """Contact block lives in private/contact.json. Without it a placeholder is returned (no name is invented)."""
    root = root or data_root()
    p = os.path.join(root, "private", "contact.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {"name": "<your name>", "phone": "<phone>", "links": [], "placeholder": True}


def private_terms(root=None):
    """private/terms.json: people, internal_codenames, patterns, stage_words. Empty lists when the file is missing."""
    root = root or data_root()
    p = os.path.join(root, "private", "terms.json")
    t = {}
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            t = json.load(f)
    return {k: t.get(k, []) for k in ("people", "internal_codenames", "patterns", "stage_words")}


def resolve(target, root=None):
    """target: '<version name>' | 'tailoring:<slug>' | 'file:<path>' (a draft tailoring JSON kept outside the data folder,
    for page-checking a proposal before the user approves it). Returns a resolved resume dict."""
    root = root or data_root()
    bank = bank_index(root)
    c = contact(root)
    if target.startswith(("tailoring:", "file:")):
        kind, ref = target.split(":", 1)
        if kind == "tailoring":
            if ref not in tailoring_slugs(root):
                raise SystemExit(f"error: no tailoring named {ref!r}; tailorings in the data folder: {', '.join(tailoring_slugs(root)) or 'none'}")
            t = load(os.path.join("jobs", ref, "tailoring.json"), root)
        else:
            with open(ref, encoding="utf-8") as f:
                t = json.load(f)
        roles = [{k: r[k] for k in ("title", "location", "dates", "sub")} | {"bullets": [b["text"] if "text" in b else bank[b["id"]]["text"] for b in r["bullets"]]}
                 for r in t["roles"]]
        projects = [{k: p[k] for k in ("title", "link_text", "url")} | {"bullets": [b["text"] if "text" in b else bank[b["id"]]["text"] for b in p["bullets"]]}
                    for p in t["projects"]]
        return {"target": target, "base": t["base"], "page_cap": load(f"versions/{t['base']}.json", root).get("page_cap"),
                "name": c["name"], "contact": c, "summary": t["summary"], "roles": roles, "education": t["education"], "skills": t["skills"],
                "projects": projects, "certifications": t.get("certifications", [])}
    if target not in version_names(root):
        raise SystemExit(f"error: no version named {target!r}; versions in the data folder: {', '.join(version_names(root)) or 'none'}")
    v = load(f"versions/{target}.json", root)

    def text(ref):
        return ref["text"] if isinstance(ref, dict) else bank[ref]["text"]
    roles = [{k: r[k] for k in ("title", "location", "dates", "sub")} | {"bullets": [text(i) for i in r["bullet_ids"]]}
             for r in v["roles"]]
    projects = [{k: p[k] for k in ("title", "link_text", "url")} | {"bullets": [text(i) for i in p["bullet_ids"]]}
                for p in v["projects"]]
    return {"target": target, "base": target, "page_cap": v.get("page_cap"), "name": c["name"], "contact": c, "summary": v["summary"],
            "roles": roles, "education": v["education"], "skills": v["skills"], "projects": projects,
            "certifications": v.get("certifications", [])}


def contact_line(c):
    return " | ".join([c["phone"]] + [l["text"] for l in c.get("links", [])])


def render_text(r):
    """Plain text in the same shape as a Google Docs 'Download as .txt' of the resume."""
    out = [r["name"], contact_line(r["contact"]), "SUMMARY", r["summary"], "PROFESSIONAL EXPERIENCE"]
    for role in r["roles"]:
        out.append(f"{role['title']} – {role['location']}        {role['dates']}")
        if role["sub"]:
            out.append(role["sub"])
        out += ["* " + b for b in role["bullets"]]
    out.append("EDUCATION")
    out += [f"{e['degree']}, {e['school']}        {e['dates']}" for e in r["education"]]
    out.append("TECHNICAL SKILLS")
    out += [f"* {s['label']}: {s['value']}" for s in r["skills"]]
    if r["projects"]:
        out.append("PROJECTS")
        for p in r["projects"]:
            out.append(f"{p['title']}        {p['link_text']}")
            out += ["* " + b for b in p["bullets"]]
    if r.get("certifications"):
        out.append("CERTIFICATIONS")
        out += ["* " + (c if isinstance(c, str) else " ".join(str(c[k]) for k in ("name", "issuer", "dates") if c.get(k))) for c in r["certifications"]]
    return "\n".join(out)


if __name__ == "__main__":
    if {"-h", "--help"} & set(sys.argv[1:]):
        print(__doc__)
        sys.exit(0)
    a = sys.argv[1:]
    target = next((x for x in a if not x.startswith("--")), None)
    if not target:
        raise SystemExit(__doc__)
    r = resolve(target)
    if "--with-contact" not in a:  # keep phone and email out of agent context unless asked
        r["contact"] = {"name": r["name"], "phone": "<contact line: private/contact.json>", "links": []}
    print(render_text(r))
