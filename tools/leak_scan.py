#!/usr/bin/env python3
"""Scan this repo for the user's own facts. The facts are read at run time from a data folder (or an old repo's data/ folder)
and are never written into the repo; hits are printed masked (kind, file:line, first two letters), not in full.

    python3 tools/leak_scan.py --from PATH [--from PATH ...] [--root REPO] [--min-run 6] [--json]

PATH is a resume-skill data folder (private/terms.json, private/contact.json, bank.json, summaries.json, profile.md, versions/,
jobs/) or an old-layout repo (its data/ folder). Terms taken: the person's name and parts of it, phone digits, email and link
texts, private people and codenames, employer names (role keys and tailoring clients, minus product words such as Amazon and
AWS, which the sample data uses on purpose), and every run of MIN_RUN words from bullets, summaries, profile and tailorings.
Exit 0: no hits. Exit 1: hits. Exit 2: no source found or readable (a scan with no terms proves nothing).
"""
import glob, json, os, re, sys

SKIP_DIRS = {".git", "__pycache__", "node_modules"}
PRODUCT_WORDS = {"amazon", "aws", "project", "google", "microsoft", "github", "linkedin"}  # appear in the made-up sample data
TEXT_EXT = {".py", ".md", ".json", ".yml", ".yaml", ".html", ".txt", ".toml", ".cfg", ".js", ".css", ".sh", ""}


def jload(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def words(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def collect(path, min_run):
    """Return (terms, runs): terms = list of (kind, regex_source, case_sensitive); runs = set of word tuples."""
    base = os.path.join(path, "data") if os.path.isfile(os.path.join(path, "data", "bank.json")) else path
    terms, runs, texts = [], set(), []
    contact = jload(os.path.join(base, "private", "contact.json")) or {}
    name = contact.get("name", "")
    if name and not name.startswith("<"):
        terms.append(("name", re.escape(name), False))
        for part in name.replace(",", " ").split():
            if len(part) >= 4:
                terms.append(("name part", rf"\b{re.escape(part)}\b", False))
    for k in ("phone", "email"):
        if contact.get(k):
            terms.append((k, re.escape(str(contact[k])), False))
    digits = re.sub(r"\D", "", str(contact.get("phone", "")))
    if len(digits) >= 7:
        terms.append(("phone digits", r"\D?".join(digits), False))
    for l in contact.get("links", []):
        for k in ("text", "href"):
            if l.get(k):
                terms.append(("contact link", re.escape(l[k]), False))
    t = jload(os.path.join(base, "private", "terms.json")) or {}
    for n in t.get("people", []):
        terms.append(("private person", rf"\b{re.escape(n)}\b", False))
        terms += [("private person part", rf"\b{re.escape(p)}\b", False) for p in n.split() if len(p) >= 4]
    for n in t.get("internal_codenames", []):
        terms.append(("internal name", rf"\b{re.escape(n)}\b", True))
    bank = jload(os.path.join(base, "bank.json")) or {}
    for role in bank.get("roles", []) or sorted({b.get("role", "") for b in bank.get("bullets", [])}):
        if role and role.lower() not in PRODUCT_WORDS:
            terms.append(("employer", rf"\b{re.escape(role)}\b", False))
    tail = glob.glob(os.path.join(base, "tailorings", "*.json")) + glob.glob(os.path.join(base, "jobs", "*", "tailoring.json"))
    for f in tail:
        d = jload(f) or {}
        c = d.get("client")
        if c and c.lower() not in PRODUCT_WORDS:
            terms.append(("client", rf"\b{re.escape(c)}\b", len(c) < 6))
        texts += [d.get("summary", "")] + [b.get("text", "") for r in d.get("roles", []) + d.get("projects", []) for b in r.get("bullets", [])]
    texts += [b.get("text", "") for b in bank.get("bullets", [])]
    texts += [s.get("text", "") for s in (jload(os.path.join(base, "summaries.json")) or {}).get("summaries", [])]
    for p in ("profile.md",):
        try:
            texts.append(open(os.path.join(base, p), encoding="utf-8").read())
        except OSError:
            pass
    for tx in texts:
        w = words(tx)
        runs |= {tuple(w[i:i + min_run]) for i in range(len(w) - min_run + 1)}
    return terms, runs


def repo_files(root):
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for f in fn:
            if os.path.splitext(f)[1].lower() in TEXT_EXT:
                yield os.path.join(dp, f)


def mask(s):
    return s[:2] + "*" * max(1, len(s) - 2)


def scan(root, sources, min_run=6):
    terms, runs, read = [], set(), 0
    for s in sources:
        t, r = collect(s, min_run)
        terms += t
        runs |= r
        read += bool(t or r)
    if not read:
        return None
    compiled = [(k, re.compile(rx, 0 if cs else re.I)) for k, rx, cs in terms]
    hits = []
    for f in repo_files(root):
        try:
            lines = open(f, encoding="utf-8", errors="ignore").read().split("\n")
        except OSError:
            continue
        rel = os.path.relpath(f, root)
        for i, line in enumerate(lines, 1):
            for kind, rx in compiled:
                m = rx.search(line)
                if m:
                    hits.append({"kind": kind, "file": rel, "line": i, "match": mask(m.group(0))})
            if runs:
                w = words(line)
                if any(tuple(w[j:j + min_run]) in runs for j in range(len(w) - min_run + 1)):
                    hits.append({"kind": f"{min_run}-word run from the user's text", "file": rel, "line": i, "match": ""})
    return hits


def main(a):
    if {"-h", "--help"} & set(a):
        print(__doc__)
        return 0
    sources, root, min_run = [], os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 6
    i = 0
    while i < len(a):
        if a[i] == "--from":
            sources.append(a[i + 1]); i += 2
        elif a[i] == "--root":
            root = a[i + 1]; i += 2
        elif a[i] == "--min-run":
            min_run = int(a[i + 1]); i += 2
        else:
            i += 1
    hits = scan(root, sources, min_run) if sources else None
    if hits is None:
        print("error: no readable source given (--from PATH); a scan with no terms proves nothing", file=sys.stderr)
        return 2
    if "--json" in a:
        print(json.dumps(hits))
    else:
        for h in hits:
            print(f"{h['file']}:{h['line']}: {h['kind']} {h['match']}".rstrip())
        print(f"leak scan: {len(hits)} hit(s)")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
