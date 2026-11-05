#!/usr/bin/env python3
"""Turn the requirement rows of a fit check into a score. The model fills the rows; this script only does the arithmetic.

    python3 fit_score.py ROWS.json [--slug SLUG] [--write] [--json]

ROWS.json:
    {"kind": "posting" | "recruiter-intro",
     "rows": [{"requirement": "text", "tier": "required|preferred", "status": "met|partly|not", "evidence": "b001 or text"}],
     "axes": {"skills": 0.8, "level": 1, "domain": null, "location": 0.5, "rate": null},   (optional, each 0 to 1 or null)
     "flags": ["short text", ...]}                                                           (optional)
A row may also be a pair: ["required", "met"].

Arithmetic (weights, partial credit, legend edges, min_rows, apply_lean_from, max_flags come from the settings "fit" section):
    tier percent  = (met + partial_credit x partly) / rows in that tier x 100
    score percent = weighted mean of the two tier percents; with rows in one tier only, that tier's percent
    score         = highest legend step whose edge the percent reaches (an edge counts in the higher score), else 1
A recruiter introduction, or fewer than min_rows rows, gets no score (score null and a reason), never a number.

Output: a short plain text block, or JSON with --json (score, pct, counts, legend, lean, reason, flags, more_flags, axes, text).
With --slug and --write: out/<slug>/fit.json (rows and result) and out/<slug>/fit.html (the fit card) in the data folder.
out/<slug>/ is created if missing; jobs/<slug>/ does not need to exist and is never written (save.py moves the files into
jobs/<slug>/ after the user's OK). Nothing else is written; the input file is never changed.

Exit 0: a score was given. Exit 2: no score could be given (the reason is printed). Exit 1: a mistake (bad file, bad row, bad slug).
"""
import html, json, os, re, sys
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resume_data as rd  # noqa: E402
import where  # noqa: E402

TIERS = ("required", "preferred")
STATUSES = ("met", "partly", "not")
KINDS = ("posting", "recruiter-intro")
AXES = (("skills", "Skills match"), ("level", "Level"), ("domain", "Domain"),
        ("location", "Location or work type"), ("rate", "Rate"))
TEMPLATE = os.path.join(rd.SKILL_DIR, "assets", "templates", "fit-card.html")


def fail(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def read_input(path):
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except OSError as e:
        fail(f"cannot read {path}: {e.strerror or e}")
    except ValueError as e:
        fail(f"{path} is not valid JSON: {e}")
    if isinstance(doc, list):
        doc = {"rows": doc}
    if not isinstance(doc, dict) or not isinstance(doc.get("rows"), list):
        fail(f"{path} needs a \"rows\" list")
    kind = doc.get("kind", "posting")
    if kind not in KINDS:
        fail(f"kind {kind!r} is not one of {', '.join(KINDS)}")
    rows = []
    for i, r in enumerate(doc["rows"], 1):
        if isinstance(r, (list, tuple)) and len(r) == 2:
            r = {"tier": r[0], "status": r[1]}
        if not isinstance(r, dict):
            fail(f"row {i} must be an object or a [tier, status] pair")
        if r.get("tier") not in TIERS:
            fail(f"row {i}: tier {r.get('tier')!r} is not one of {', '.join(TIERS)}")
        if r.get("status") not in STATUSES:
            fail(f"row {i}: status {r.get('status')!r} is not one of {', '.join(STATUSES)}")
        rows.append({"requirement": str(r.get("requirement", "")), "tier": r["tier"], "status": r["status"],
                     "evidence": str(r.get("evidence", ""))})
    axes = doc.get("axes") or {}
    if not isinstance(axes, dict):
        fail("axes must be an object")
    clean_axes = {}
    for k, v in axes.items():
        if v is None:
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1:
            fail(f"axis {k!r} must be a number from 0 to 1 or null")
        clean_axes[k] = v
    flags = doc.get("flags") or []
    if not isinstance(flags, list) or not all(isinstance(x, str) for x in flags):
        fail("flags must be a list of strings")
    return kind, rows, clean_axes, flags


def load_settings(need_root):
    r = where.resolve()
    if r["state"] == "ready":
        return rd.settings(r["path"]), r["path"]
    if need_root:
        rd.data_root()  # exits with where.py's message
    return rd.default_settings(), None


def two_places(x):
    """Fraction -> float rounded half up to 2 decimals."""
    d = (Decimal(x.numerator) / Decimal(x.denominator)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(d)


def count(rows, tier):
    r = [x for x in rows if x["tier"] == tier]
    return {"met": sum(x["status"] == "met" for x in r), "partly": sum(x["status"] == "partly" for x in r), "total": len(r)}


def compute(kind, rows, axes, flags, fit):
    counts = {t: count(rows, t) for t in TIERS}
    legend_text = fit["legend_text"]
    res = {"kind": kind, "score": None, "pct": None, "counts": counts, "legend": None, "lean": None, "reason": None,
           "axes": axes}
    if kind == "recruiter-intro":
        res["reason"] = "This is a recruiter introduction, not a job description, so there is no score."
    elif len(rows) < fit["min_rows"]:
        res["reason"] = f"Only {len(rows)} requirement rows (the minimum is {fit['min_rows']}), so there is no score."
    if res["reason"] is None:
        partial = Fraction(str(fit["partial_credit"]))
        pcts = {t: (counts[t]["met"] + partial * counts[t]["partly"]) / counts[t]["total"] * 100
                for t in TIERS if counts[t]["total"]}
        if len(pcts) == 2:
            w = {t: Fraction(str(fit["weights"][t])) for t in TIERS}
            pct = sum(w[t] * pcts[t] for t in TIERS) / sum(w.values())
        else:
            pct = list(pcts.values())[0]
        edges = sorted(((int(k), Fraction(str(v))) for k, v in fit["legend"].items()), reverse=True)
        score = next((k for k, edge in edges if pct >= edge), 1)
        lean = "apply" if score >= fit["apply_lean_from"] else "your call" if score == fit["apply_lean_from"] - 1 else "skip"
        res.update(score=score, pct=two_places(pct), legend=legend_text[str(score)], lean=lean)
    shown = flags[:fit["max_flags"]]
    res["flags"] = shown
    res["more_flags"] = len(flags) - len(shown)
    res["text"] = text_version(res)
    return res


def tier_words(label, c):
    if not c["total"]:
        return None
    s = f"{label} {c['met']} of {c['total']} met"
    return s + (f" ({c['partly']} partly)" if c["partly"] else "")


def text_version(res):
    if res["score"] is None:
        return "No score: " + res["reason"][0].lower() + res["reason"][1:]
    parts = [tier_words("Required", res["counts"]["required"]), tier_words("preferred", res["counts"]["preferred"])]
    if parts[0] is None and parts[1]:
        parts[1] = parts[1][0].upper() + parts[1][1:]
    return f"Score {res['score']} of 5: {res['legend']}. " + ", ".join(p for p in parts if p) + "."


def plain(res):
    out = [res["text"]]
    if res["score"] is not None:
        out.append(f"Percent: {res['pct']:g}. Lean: {res['lean']}.")
    if res["flags"]:
        out.append("Flags: " + "; ".join(res["flags"]) + (f" (+{res['more_flags']} more)" if res["more_flags"] else ""))
    return "\n".join(out)


def esc(s):
    return html.escape(str(s), quote=True)


def card(res, slug):
    """Fill assets/templates/fit-card.html. Every inserted string is escaped; values are filled in one pass."""
    with open(TEMPLATE, encoding="utf-8") as f:
        tpl = f.read()
    flags = "".join(f"<li>{esc(x)}</li>" for x in res["flags"])
    if res["more_flags"]:
        flags += f"<li>(+{res['more_flags']} more)</li>"
    bars = ""
    for key, label in AXES:
        if key in res["axes"]:
            n = int(round(res["axes"][key] * 100))
            bars += (f'<div class="axis"><span class="axis-label">{esc(label)}</span>'
                     f'<span class="bar"><span class="fill" style="width:{n}%"></span></span>'
                     f'<span class="axis-val">{n}%</span></div>')
    cts = []
    for t, label in (("required", "Required"), ("preferred", "Preferred")):
        c = res["counts"][t]
        if c["total"]:
            cts.append(f"<li>{esc(tier_words(label, c))}</li>")
    values = {
        "title": "Fit card" + (f": {slug}" if slug else ""),
        "score": f"{res['score']} / 5" if res["score"] is not None else "No score",
        "legend": res["legend"] if res["score"] is not None else res["reason"],
        "lean": f"Lean: {res['lean']}" if res["score"] is not None else "",
        "counts": "".join(cts),
        "flags": flags,
        "axes": bars,
        "text": res["text"],
    }
    raw = {"counts", "flags", "axes"}  # built above from escaped pieces
    return re.sub(r"\{\{(\w+)\}\}", lambda m: values[m.group(1)] if m.group(1) in raw else esc(values[m.group(1)]), tpl)


def write_atomic(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def main(argv):
    if {"-h", "--help"} & set(argv):
        print(__doc__)
        return 0
    args = [a for a in argv if not a.startswith("--")]
    slug = None
    if "--slug" in argv:
        i = argv.index("--slug")
        slug = argv[i + 1] if i + 1 < len(argv) else None
        args = [a for a in args if a != slug]
        if not slug:
            fail("--slug needs a value")
    if len(args) != 1:
        fail("usage: fit_score.py ROWS.json [--slug SLUG] [--write] [--json]")
    write = "--write" in argv
    if write and not slug:
        fail("--write needs --slug")
    kind, rows, axes, flags = read_input(args[0])
    settings, root = load_settings(write)
    res = compute(kind, rows, axes, flags, settings["fit"])
    if write:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", slug):
            fail(f"slug {slug!r} must be letters, digits, dot, dash or underscore")
        job = os.path.join(root, "out", slug)
        os.makedirs(job, exist_ok=True)
        out = {"kind": kind, "rows": rows, "axes": axes, "flags": flags, "result": res}
        write_atomic(os.path.join(job, "fit.json"), json.dumps(out, indent=2, ensure_ascii=False) + "\n")
        write_atomic(os.path.join(job, "fit.html"), card(res, slug))
    print(json.dumps(res, indent=2, ensure_ascii=False) if "--json" in argv else plain(res))
    return 0 if res["score"] is not None else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
