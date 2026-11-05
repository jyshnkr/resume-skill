#!/usr/bin/env python3
"""Run the one-bullet checks on every bank bullet and keep the result in <data folder>/out/preflight.json.

    python3 preflight.py [--if-stale] [--json] [--quiet]

Each bullet is checked as check.py --all checks it: the leads of the other bullets in the first version that holds it count as used.
A bullet with a FAIL is listed in "hold_back": do not offer it as a swap. A WARN never holds a bullet back. The bank is never edited.
The file holds {fingerprint, ran_at, bullets: {id: {status OK|WARN|FAIL, findings}}, hold_back, summary}.
A bank row with "status": "candidate" is a draft: it is checked the same way but listed apart, in candidates: {id: {status, findings}} and
candidates_summary ("C candidates checked: a clean, b with warnings, c failing"; both keys exist only when the bank has candidates). A
candidate is never in bullets or hold_back, never changes summary or the exit code, and counts no used leads. The text summary
prints candidates_summary as its last line (not with --quiet). The fingerprint covers
bank.json, the settings file (settings.yaml, or the older settings.json), private/terms.json, the shipped rules registry, robot-phrase list, default settings and check.py, so a
stored result is stale as soon as any of them changes.

  --if-stale  run only when the stored fingerprint differs from the current one; print nothing when it is unchanged
  --json      print the result file instead of the text summary
  --quiet     print nothing (the exit code still tells)

Exit 0 no FAIL and no WARN, 1 some FAIL, 2 WARN only. An unchanged --if-stale run is silent and its exit code is the stored verdict
(0 clean, 1 a bullet is held back, 2 warnings only).
"""
import collections, datetime, hashlib, json, os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check  # noqa: E402
import resume_data as rd  # noqa: E402


def fingerprint(root):
    """sha256 over the files whose content decides a result; a missing file counts as empty."""
    files = [os.path.join(root, "bank.json"), rd.settings_path(root) or "", os.path.join(root, "private", "terms.json"),
             os.path.join(rd.SKILL_DIR, "assets", "rules", "registry.json"), check.PHRASES, rd.DEFAULT_SETTINGS, os.path.abspath(check.__file__)]
    h = hashlib.sha256()
    for p in files:
        if not p or not os.path.exists(p): continue
        with open(p, "rb") as f: h.update(os.path.basename(p).encode() + b"\0" + f.read() + b"\0")
    return h.hexdigest()


def run_checks(ctx):
    bullets, cands = {}, {}
    for b, v, leads in check.all_bullets(ctx, candidates=True):
        cand = b.get("status") == "candidate"  # a draft: checked like the rest, kept out of the approved results, no used leads
        item = check.run_one("bullet", b["text"], [] if cand else list(leads), ctx)
        (cands if cand else bullets)[b["id"]] = {"status": item["status"], "findings": [r for r in item["findings"] if r["level"] != "INFO"]}
    hold = [i for i, v in bullets.items() if v["status"] == "FAIL"]
    need = sum(v["status"] != "OK" for v in bullets.values())
    res = {"fingerprint": fingerprint(ctx["root"]), "ran_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "bullets": bullets, "hold_back": hold, "summary": f"{need} of {len(bullets)} bullets need attention"}
    if cands:  # the keys exist only when the bank holds candidates, so a bank without them gives the same file as before
        n = collections.Counter(v["status"] for v in cands.values())
        res["candidates"] = cands
        res["candidates_summary"] = (f"{len(cands)} candidates checked: {n['OK']} clean, {n['WARN']} with warnings, {n['FAIL']} failing")
    return res


def exit_of(res):
    st = {v["status"] for v in res["bullets"].values()}
    return 1 if "FAIL" in st else 2 if "WARN" in st else 0


def save(path, res):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f: json.dump(res, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def main(a):
    known = {"--if-stale", "--json", "--quiet"}
    bad = next((x for x in a if x not in known), None)
    if bad: raise SystemExit(f"error: unknown option {bad}; see --help")
    root = rd.data_root()
    out = os.path.join(root, "out", "preflight.json")
    if "--if-stale" in a and os.path.exists(out):
        try:
            with open(out, encoding="utf-8") as f: old = json.load(f)
            if old.get("fingerprint") == fingerprint(root): sys.exit(exit_of(old))
        except (OSError, ValueError, KeyError): pass  # unreadable result: run again
    res = run_checks(check.context())
    save(out, res)
    if "--quiet" not in a:
        if "--json" in a: print(json.dumps(res, indent=1, ensure_ascii=False))
        else:
            print(res["summary"])
            if res["hold_back"]: print("hold back from swap offers: " + ", ".join(res["hold_back"]))
            for i, v in res["bullets"].items():
                for r in v["findings"]:
                    if r["level"] in ("FAIL", "WARN"): print(f"{i} {r['level']} rule {r['rule']}: {r['message']}")
            if "candidates_summary" in res: print(res["candidates_summary"])
    sys.exit(exit_of(res))


if __name__ == "__main__":
    if {"-h", "--help"} & set(sys.argv[1:]): print(__doc__); sys.exit(0)
    main(sys.argv[1:])
