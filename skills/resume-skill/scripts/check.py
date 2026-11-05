#!/usr/bin/env python3
"""resume-skill bullet, summary and document checker. Stdlib; Pillow and LibreOffice optional.

  check.py [--leads "Cut Moved ..."] "bullet text" ...      check bullets (leads = first words of the other bullets in the resume)
  check.py --summary "summary text"                         check a summary
  check.py --resume NAME|tailoring:SLUG|file:PATH           check a whole resume: every bullet, the summary and the document checks
  check.py --document-file FILE                             same for plain text: one bullet per line, a line "SUMMARY: ..." for the summary
  check.py --pages 2 file.pdf|file.docx                     page cap
  check.py --stack NAME|tailoring:SLUG                      per bullet, the technologies of its bank row that its text does not name
  check.py --all                                            every bank bullet, leads per version (needs a data folder)
  add --json to print the results as a list of {text, status, words, chars, findings[]}

Limits, word lists and private names come from the data folder (settings.json, bank.json, private/terms.json; where.py finds it).
Without a data folder the shipped default settings run and private names are not checked (a NOTE says so).
A result line is a plain sentence: LEVEL rule N: what is wrong. Rule numbers are the rule numbers of the resume rule list.
Exit 0 clean, 1 any FAIL, 2 WARN only (NOTE and INFO never change the exit code), except --pages, which exits 2 when the page count
cannot be read. --stack never fails.
"""
import collections, json, os, re, shutil, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resume_data as rd  # noqa: E402
import where  # noqa: E402

PHRASES = os.path.join(rd.SKILL_DIR, "assets", "phrases", "robot-phrases.json")
BY = r"(?<![\w-])by\b"  # the XYZ "by", also next to a dash or comma
DESIGN = r"(?i)\b(designed|designing|architected|architecting)\b"
NO_TERMS = {"people": [], "internal_codenames": [], "patterns": [], "stage_words": []}

# One entry per check: its rule number, usual level, what it looks at and what it says. "bullet" checks also run on a summary where the
# doc says so. The command line, preflight.py and the tests read this table.
CHECKS = {
    "empty_bullet": {"rule": 4, "level": "FAIL", "when": "bullet", "doc": "The bullet has no text."},
    "words": {"rule": 4, "level": "FAIL", "when": "bullet", "doc": "The bullet has too few or too many words."},
    "chars": {"rule": 4, "level": "FAIL", "when": "bullet", "doc": "The bullet is longer than the character limit."},
    "wrap": {"rule": 4, "level": "FAIL", "when": "bullet", "doc": "The bullet or summary prints on too many or too few lines (needs Pillow)."},
    "lead_not_past": {"rule": 3, "level": "FAIL", "when": "bullet", "doc": "The first word is banned or is not past tense."},
    "lead_reused": {"rule": 3, "level": "FAIL", "when": "bullet", "doc": "Another bullet in the resume opens with the same word."},
    "by_count": {"rule": 2, "level": "FAIL", "when": "bullet", "doc": "The word 'by' must appear exactly once."},
    "aws_prefix": {"rule": 8, "level": "FAIL", "when": "bullet", "doc": "The first AWS service is not preceded by AWS or Amazon."},
    "jargon": {"rule": 9, "level": "FAIL", "when": "bullet", "doc": "A class or API name appears where the product name belongs."},
    "phrase_replacement": {"rule": 15, "level": "FAIL", "when": "bullet", "doc": "A phrase from the replacement list in settings appears."},
    "design_claim": {"rule": 15, "level": "NOTE", "when": "bullet", "doc": "The bullet claims a design; keep it only for designs you wrote."},
    "no_metric": {"rule": 10, "level": "NOTE", "when": "bullet", "doc": "No number appears before 'by' (the result)."},
    "repeated_word": {"rule": 6, "level": "FAIL", "when": "bullet", "doc": "The same word appears twice in one bullet."},
    "repeated_stem": {"rule": 6, "level": "WARN", "when": "bullet", "doc": "Two forms of one word appear in one bullet."},
    "internal_name": {"rule": 16, "level": "FAIL", "when": "bullet", "doc": "A private codename from private/terms.json appears (also checked in a summary)."},
    "stage_word": {"rule": 16, "level": "NOTE", "when": "bullet", "doc": "A stage word from private/terms.json appears; it may be an internal stage name."},
    "adr_number": {"rule": 16, "level": "FAIL", "when": "bullet", "doc": "An architecture decision record number appears."},
    "bold": {"rule": 29, "level": "FAIL", "when": "bullet", "doc": "Bold markers (**) were pasted into the text."},
    "summary_sentences": {"rule": 23, "level": "FAIL", "when": "summary", "doc": "The summary does not have the required number of sentences."},
    "summary_opening": {"rule": 23, "level": "FAIL", "when": "summary", "doc": "The first sentence does not match the opening pattern in settings."},
    "summary_past": {"rule": 24, "level": "FAIL", "when": "summary", "doc": "Sentence 2 or 3 does not open in past tense."},
    "summary_retired": {"rule": 25, "level": "FAIL", "when": "summary", "doc": "A wording you retired in settings appears."},
    "pages": {"rule": 32, "level": "FAIL", "when": "document", "doc": "The file has more pages than the cap, or the page count cannot be read."},
    "no_data_folder": {"rule": 16, "level": "NOTE", "when": "document", "doc": "No data folder was found, so private names were not checked."},
}

F = lambda level, rule, check, message: {"level": level, "rule": rule, "check": check, "message": message}
past = lambda w, b: (w.endswith("ed") and w not in b["not_past"]) or w in b["irregular_past"]


def stem(p):  # crude suffix strip, then a final "e" (sites/site, deletion/deletes)
    p = next((p[:-len(s)] for s in ("ations", "ation", "ions", "ion", "ing", "ies", "es", "ed", "s", "y") if p.endswith(s) and len(p) - len(s) > 2), p)
    return p[:-1] if p.endswith("e") and len(p) > 3 else p


def repeats(t, lead, b, kept):  # FAIL same word, WARN shared stem; 2-part compounds split, end-to-end is one term
    words, seen, out = [], [], []
    stop = set(b["stop_words"])
    for tok in t.lower().replace("'s", "").split():
        tok = tok.strip(".,;:()\"'"); parts = re.split(r"[-/@]", tok)
        words += [p for p in (parts if len(parts) == 2 else [tok]) if p not in stop and not re.fullmatch(r"[\d.,~%x+$]*", p)]
    for f, sev in ((str, "FAIL"), (stem, "WARN")):
        groups = collections.defaultdict(list)
        for w in words: groups[f(w)].append(w)
        for ws in groups.values():
            if len(ws) > 1 + any(stem(k) == stem(ws[0]) for k in kept.get(lead, [])) and not any(set(ws) <= g for g in seen):
                seen.append(set(ws)); out.append(F(sev, 6, "repeated_word" if sev == "FAIL" else "repeated_stem",
                                                   f"{'word repeated' if sev == 'FAIL' else 'two forms of one word'}: {' / '.join(ws)}."))
    return out


def internal_re(terms):
    """Private codenames and stage words from private/terms.json as one pattern, or None when there is nothing to look for."""
    names, stages = terms.get("internal_codenames", []), terms.get("stage_words", [])
    plain = [n for n in names if n.isalnum()]
    hyph = [re.escape(n) for n in names if not n.isalnum()]
    parts = ([r"\b(" + "|".join(plain) + r")\b"] if plain else [])
    ci = ["\\b" + h + "\\b" for h in hyph]
    if stages:  # stage names: say "pre-production"
        ci.append(r"\b(?:" + "|".join(map(re.escape, stages)) + r")\b(?=(?:\s+and\s+(?:" + "|".join(map(re.escape, stages)) + r"))?[-\s]+(?:stages?|canar(?:y|ies)|environments?|accounts?|fleet)\b)")
    if ci: parts.append(r"(?i:" + "|".join(ci) + ")")
    return re.compile("|".join(parts)) if parts else None


def common(t, terms):  # internal names, ADR numbers, bold markers
    rx = internal_re(terms)
    hit = [m.span() for m in rx.finditer(t)] if rx else []
    stages = terms.get("stage_words", [])
    stage = re.compile(r"(?i)\b(?:" + "|".join(map(re.escape, stages)) + r")\b") if stages else None  # bare word: maybe a stage name, maybe "public beta"
    return ([F("FAIL", 16, "internal_name", f"'{t[a:b]}' is an internal name; remove it or use a public term.") for a, b in hit]
            + [F("NOTE", 16, "stage_word", f"'{m.group()}' may be an internal stage name; if it is, say 'pre-production'.") for m in (stage.finditer(t) if stage else []) if m.span() not in hit]
            + [F("FAIL", 16, "adr_number", "an ADR number is internal; remove it.")] * bool(re.search(r"\bADR[ -]?\d", t))
            + [F("FAIL", 29, "bold", "** bold markers; paste plain text.")] * ("**" in t))


def wrap(t, width, lo, hi, rule):  # Liberation Serif has Times New Roman's metrics; 11pt drawn x100 for precision; no kerning
    try: from PIL import ImageFont, features; font = ImageFont.truetype("LiberationSerif-Regular.ttf", 1100)
    except Exception: return [F("NOTE", rule, "wrap", "wrap: not checked (needs Pillow and Liberation Serif)")]
    w, n, cur = lambda s: font.getlength(s, **({"features": ["-kern"]} if features.check("raqm") else {})) / 100, 1, ""
    for word in t.split(): n, cur = (n + 1, word) if cur and w(cur + " " + word) > width else (n, (cur + " " + word).strip())
    return [F("INFO" if lo <= n <= hi else "FAIL", rule, "wrap", f"wrap: {n} lines (want {lo} to {hi}), last {w(cur):.0f}/{width}pt")]


def bullet(b, used, cfg, terms, kept):
    lim, bl = cfg["limits"], cfg["bullets"]
    w, res = b.split(), []
    aws = "|".join(map(re.escape, sorted(bl["aws_services"], key=len, reverse=True)))
    m = re.search(r"\b(" + aws + r")\b", b) if aws else None
    if not w: return [F("FAIL", 4, "empty_bullet", "empty bullet; write the bullet text.")]
    lead = re.sub(r"\W", "", w[0]).lower()
    if not lim["words"][0] <= len(w) <= lim["words"][1]: res.append(F("FAIL", 4, "words", f"{len(w)} words; the limit is {lim['words'][0]} to {lim['words'][1]}."))
    if len(b) > lim["chars"]: res.append(F("FAIL", 4, "chars", f"{len(b)} characters; the limit is {lim['chars']}."))
    if lead in bl["banned_leads"] or not past(lead, bl): res.append(F("FAIL", 3, "lead_not_past", f"lead '{w[0]}' is banned or not past tense."))
    if lead in used: res.append(F("FAIL", 3, "lead_reused", f"lead '{w[0]}' is already used in this resume."))
    nby = len(re.findall(BY, b))
    if nby != 1: res.append(F("FAIL", 2, "by_count", f"'by' appears {nby} times; it must appear once."))
    if m and bl["require_aws_prefix"] and not b[:m.start()].endswith(("AWS ", "Amazon ")): res.append(F("FAIL", 8, "aws_prefix", f"first AWS service '{m.group()}' needs AWS or Amazon in front."))
    if bl["jargon"]:
        jargon = "|".join("(?<!\\w)" + re.escape(j) + "(?!\\w)" for j in bl["jargon"])
        res += [F("FAIL", 9, "jargon", f"class or API name '{j.group()}': name the product.") for j in re.finditer(jargon, b)]
    for rep in bl["phrase_replacements"]:
        hit = re.search(rep["pattern"], b)
        if hit: res.append(F("FAIL", rep.get("rule", 15), "phrase_replacement", f"'{hit.group()}' is not allowed; say '{rep['say']}'."))
    if not re.search(r"\d", re.split(BY, b)[0]): res.append(F("NOTE", 10, "no_metric", "no number in the result before 'by'."))
    if re.search(DESIGN, b): res.append(F("NOTE", 15, "design_claim", "design claim: keep it only for designs you wrote."))
    used.append(lead); return res + repeats(b, lead, bl, kept) + common(b, terms) + wrap(b, lim["text_pt"] - lim["bullet_indent_pt"], lim["bullet_lines"][0], lim["bullet_lines"][1], 4)


def summary(t, cfg, terms):
    lim, sm, bl = cfg["limits"], cfg["summary"], cfg["bullets"]
    s = re.split(r"(?<=[.!?])\s+", t); res = [] if len(s) == lim["summary_sentences"] else [F("FAIL", 23, "summary_sentences", f"{len(s)} sentences; the summary needs {lim['summary_sentences']}.")]
    if sm["opening_pattern"] and not re.match(sm["opening_pattern"], t): res.append(F("FAIL", 23, "summary_opening", "sentence 1 does not open as required by the opening pattern in settings."))
    res += [F("FAIL", 24, "summary_past", f"sentence {i} must open in past tense.") for i, x in enumerate(s[1:], 2) if not past(x.split()[0].lower(), bl)]
    retired = "|".join(sm["retired_wording"])
    res += [F("FAIL", 25, "summary_retired", f"retired wording '{r.group()}'.") for r in re.finditer(retired, t)] if retired else []
    return res + common(t, terms) + wrap(t, lim["text_pt"], lim["summary_lines"], lim["summary_lines"], 23)


def pages(cap, path):  # a .docx is rendered with LibreOffice when installed
    exe, out, orig = shutil.which("soffice"), os.path.abspath(tempfile.mkdtemp()), path
    try:
        if path.endswith(".docx") and exe:
            try: subprocess.run([exe, f"-env:UserInstallation=file://{out}/lo-profile", "--headless", "--convert-to", "pdf", "--outdir", out, os.path.abspath(path)], capture_output=True, timeout=180, env={**os.environ, "TMPDIR": out})
            except (subprocess.TimeoutExpired, OSError): pass  # no PDF -> "not checked" below
            path = f"{out}/{os.path.basename(path)[:-5]}.pdf"
        n = 0
        if path.endswith(".pdf") and os.path.exists(path):
            with open(path, "rb") as f: n = len(re.findall(rb"/Type\s*/Page\b", f.read()))
    finally:
        shutil.rmtree(out, ignore_errors=True)
    if n: return [F("INFO" if n <= cap else "FAIL", 32, "pages", f"pages: {n} (cap {cap})")]
    return [F("NOTE", 32, "pages", f"pages: not checked ({'no such file' if not os.path.exists(orig) else 'no PDF renderer'})")]


def check_bullet(text, used_leads, cfg, terms, kept=None):
    """All one-bullet checks. used_leads (lowercase first words of the other bullets) gets this bullet's lead appended."""
    return bullet(text, used_leads, cfg, terms, kept or {})


def check_summary(text, cfg, terms):
    return summary(text, cfg, terms)


def kept_repeats(bank):
    """Words each bank row allows twice: {lead word: [words]} from allowed_repeats."""
    out = collections.defaultdict(list)
    for b in bank:
        out[re.sub(r"\W", "", b.get("lead", "")).lower()] += b.get("allowed_repeats", [])
    return dict(out)


def context():
    """Settings, private terms and kept repeats from the data folder; defaults and no terms when there is none (root is None)."""
    r = where.resolve()
    if r["state"] != "ready": return {"root": None, "cfg": rd.default_settings(), "terms": dict(NO_TERMS), "kept": {}}
    root = r["path"]
    try: kept = kept_repeats(rd.load("bank.json", root)["bullets"])
    except (OSError, ValueError, KeyError): kept = {}
    return {"root": root, "cfg": rd.settings(root), "terms": rd.private_terms(root), "kept": kept}


def status_of(res):
    return next((s for s in ("FAIL", "WARN") if any(r["level"] == s for r in res)), "OK")


def run_one(kind, x, used, ctx):
    t = x.strip().rstrip(".") if kind == "bullet" else x.strip()
    res = check_bullet(t, used, ctx["cfg"], ctx["terms"], ctx["kept"]) if kind == "bullet" else check_summary(t, ctx["cfg"], ctx["terms"])
    return {"text": t, "status": status_of(res), "words": len(t.split()), "chars": len(t), "findings": res}


CODE = {"OK": 0, "FAIL": 1, "WARN": 2, "NOT CHECKED": 2}


def show(items, as_json):
    if as_json:
        print(json.dumps(items, indent=1, ensure_ascii=False))
    else:
        for it in items:
            print(it["status"] if it.get("head") is False else f"{it['status']} {it['words']}w {it['chars']}c :: {it['text'][:80]}")
            for r in it["findings"]: print(f"    {r['level']} rule {r['rule']}: {r['message']}")
    codes = [CODE[it["status"]] for it in items]
    return 1 if 1 in codes else 2 if 2 in codes else 0


def all_bullets(ctx):
    """Expand --all into one (bank row, version, leads) per bank bullet: leads are the other bullets of the first version that holds it."""
    if not ctx["root"]: raise SystemExit("error: --all needs a data folder (run where.py to see where it should be).")
    bank = rd.load("bank.json", ctx["root"])["bullets"]
    versions = rd.version_names(ctx["root"])
    for b in bank:
        v = next((n for n in versions if b["marks"].get(n, {}).get("in")), None)
        leads = [re.sub(r"\W", "", x["lead"]).lower() for x in bank if v and x["marks"].get(v, {}).get("in") and x["id"] != b["id"]]
        yield b, v, leads


def main(a):
    as_json = "--json" in a
    a = [x for x in a if x != "--json"]
    ctx = context()
    if a == ["--all"]:
        worst = 0
        for b, v, leads in all_bullets(ctx):
            item = run_one("bullet", b["text"], list(leads), ctx)
            code = CODE[item["status"]]
            print(f"## {b['id']} ({v or 'none'}) exit={code}")
            show([item], False)
            worst = 1 if 1 in (worst, code) else max(worst, code)
        sys.exit(worst)
    items, used, kind = [], [], "bullet"
    if not ctx["root"] and not as_json: print("NOTE rule 16: no data folder found, private names were not checked")
    while a:
        x = a.pop(0)
        if x == "--leads": used += re.sub(r"[^A-Za-z]", " ", a.pop(0)).lower().split(); continue
        if x == "--summary": kind = "summary"; continue
        if x == "--pages":
            cap, path = int(a.pop(0)), a.pop(0)
            res = pages(cap, path)
            st = "NOT CHECKED" if res[0]["level"] == "NOTE" else status_of(res)
            items.append({"text": path, "status": st, "words": 0, "chars": 0, "findings": res, "head": False}); continue
        items.append(run_one(kind, x, used, ctx))
    if as_json and not ctx["root"]:
        for it in items: it["findings"].append(F("NOTE", 16, "no_data_folder", "no data folder found, private names were not checked"))
    sys.exit(show(items, as_json))


if __name__ == "__main__":
    if {"-h", "--help"} & set(sys.argv[1:]): print(__doc__); sys.exit(0)
    main(sys.argv[1:])
