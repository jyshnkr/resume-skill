#!/usr/bin/env python3
"""Grade one eval run against the assertions in evals/cases.json. Stdlib only.

    python3 evals/grade.py --case e01 --output run/output.txt --data run/data --before HASH [--json]

--before is the tree hash of the data folder taken before the run (printed by tools/run_evals.py). Assertions per case:
output_matches (every regex must match), output_not_matches (none may match), output_mentions (every word appears, any case),
files_written (each glob, relative to the data folder, must match a file), data_unchanged (the data folder, ignoring out/,
hashes the same as before), folder_not_created (the data folder path must not exist).
Exit 0 all pass, 1 any fail.
"""
import glob, hashlib, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def tree_hash(root, skip=("out",)):
    h = hashlib.sha256()
    for dp, dn, fn in os.walk(root):
        dn[:] = sorted(d for d in dn if not (dp == root and d in skip))
        for f in sorted(fn):
            if f == ".keep":
                continue
            p = os.path.join(dp, f)
            h.update(os.path.relpath(p, root).encode())
            with open(p, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()


def grade(case, output, data, before):
    a, res = case.get("assert", {}), []
    for rx in a.get("output_matches", []):
        res.append((f"matches {rx}", bool(re.search(rx, output))))
    for rx in a.get("output_not_matches", []):
        res.append((f"does not match {rx}", not re.search(rx, output)))
    for w in a.get("output_mentions", []):
        res.append((f"mentions {w}", w.lower() in output.lower()))
    for g in a.get("files_written", []):
        res.append((f"wrote {g}", bool(glob.glob(os.path.join(data, g)))))
    if a.get("data_unchanged"):
        res.append(("data folder unchanged", os.path.isdir(data) and tree_hash(data) == before))
    if a.get("folder_not_created"):
        res.append(("data folder not created", not os.path.exists(data)))
    return res


def main(a):
    if {"-h", "--help"} & set(a):
        print(__doc__)
        return 0
    opt = {k: a[i + 1] for i, k in enumerate(a) if k in ("--case", "--output", "--data", "--before") and i + 1 < len(a)}
    if not {"--case", "--output", "--data"} <= set(opt):
        print("error: --case, --output and --data are required", file=sys.stderr)
        return 1
    with open(os.path.join(HERE, "cases.json"), encoding="utf-8") as f:
        cases = {c["id"]: c for c in json.load(f)["cases"]}
    if opt["--case"] not in cases:
        print(f"error: no case {opt['--case']!r}; cases: {', '.join(sorted(cases))}", file=sys.stderr)
        return 1
    with open(opt["--output"], encoding="utf-8") as f:
        out = f.read()
    res = grade(cases[opt["--case"]], out, opt["--data"], opt.get("--before", ""))
    if "--json" in a:
        print(json.dumps([{"check": c, "pass": ok} for c, ok in res]))
    else:
        for c, ok in res:
            print(f"{'PASS' if ok else 'FAIL'} {c}")
        print(f"{opt['--case']}: {sum(ok for _, ok in res)} of {len(res)} checks pass")
    return 0 if all(ok for _, ok in res) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
