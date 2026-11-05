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

Limits, word lists and private names come from the data folder (settings.yaml, bank.json, private/terms.json; where.py finds it).
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
    "private_pattern": {"rule": 16, "level": "FAIL", "when": "bullet", "doc": "Text matches a private pattern from private/terms.json (the match is not printed in full)."},
    "stage_word": {"rule": 16, "level": "NOTE", "when": "bullet", "doc": "A stage word from private/terms.json appears; it may be an internal stage name."},
    "adr_number": {"rule": 16, "level": "FAIL", "when": "bullet", "doc": "An architecture decision record number appears."},
    "bold": {"rule": 29, "level": "FAIL", "when": "bullet", "doc": "Bold markers (**) were pasted into the text."},
    "summary_sentences": {"rule": 23, "level": "FAIL", "when": "summary", "doc": "The summary does not have the required number of sentences."},
    "summary_opening": {"rule": 23, "level": "FAIL", "when": "summary", "doc": "The first sentence does not match the opening pattern in settings."},
    "summary_past": {"rule": 24, "level": "FAIL", "when": "summary", "doc": "Sentence 2 or 3 does not open in past tense."},
    "summary_retired": {"rule": 25, "level": "FAIL", "when": "summary", "doc": "A wording you retired in settings appears."},
    "first_person": {"rule": 20, "level": "FAIL", "when": "bullet", "doc": "I, we, my, our, us or me (or a contraction of them) appears; also checked in a summary."},
    "vague_size": {"rule": 12, "level": "FAIL", "when": "bullet", "doc": "A size is given as millions, thousands, hundreds of, dozens of or billions with no number; also checked in a summary."},
    "number_word": {"rule": 5, "level": "WARN", "when": "bullet", "doc": "A number from two up is spelled as a word instead of digits; also checked in a summary."},
    "vague_ing": {"rule": 19, "level": "WARN", "when": "bullet", "doc": "The last clause after the final comma opens with a vague outcome verb ending in -ing."},
    "em_dash": {"rule": 19, "level": "WARN", "when": "document", "doc": "The document contains em dashes."},
    "mixed_endings": {"rule": 37, "level": "WARN", "when": "document", "doc": "Some bullets end with a period and others do not."},
    "passive": {"rule": 19, "level": "NOTE", "when": "bullet", "doc": "A passive-voice phrase such as 'was added' appears; also checked in a summary."},
    "robot_phrase": {"rule": 18, "level": "WARN", "when": "bullet", "doc": "A word or phrase from the robot-phrase list appears; also checked in a summary."},
    "short_last_line": {"rule": 60, "level": "NOTE", "when": "bullet", "doc": "The last printed line is shorter than the share of the width set in settings (needs Pillow)."},
    "stack_coverage": {"rule": 67, "level": "NOTE", "when": "document", "doc": "A technology listed on the bank row is not named in the bullet text."},
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
    pats = []
    for pat in terms.get("patterns", []):  # private patterns (regex strings); one that does not compile is skipped
        try: pats += [m.group() for m in re.finditer(pat, t) if m.group()]
        except re.error: pass
    stage = re.compile(r"(?i)\b(?:" + "|".join(map(re.escape, stages)) + r")\b") if stages else None  # bare word: maybe a stage name, maybe "public beta"
    return ([F("FAIL", 16, "internal_name", f"'{t[a:b]}' is an internal name; remove it or use a public term.") for a, b in hit]
            + [F("FAIL", 16, "private_pattern", f"private pattern matched: {g[:2]}...; remove it or use a public term.") for g in pats]
            + [F("NOTE", 16, "stage_word", f"'{m.group()}' may be an internal stage name; if it is, say 'pre-production'.") for m in (stage.finditer(t) if stage else []) if m.span() not in hit]
            + [F("FAIL", 16, "adr_number", "an ADR number is internal; remove it.")] * bool(re.search(r"\bADR[ -]?\d", t))
            + [F("FAIL", 29, "bold", "** bold markers; paste plain text.")] * ("**" in t))


# The resume font is Times New Roman: use the system's own copy when there is one, else Liberation Serif (same letter widths).
FONT_FILES = ["/System/Library/Fonts/Supplemental/Times New Roman.ttf", "C:\\Windows\\Fonts\\times.ttf",
              "/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman.ttf", "/usr/share/fonts/truetype/msttcorefonts/times.ttf",
              "LiberationSerif-Regular.ttf"]


def load_font(ImageFont):
    for f in FONT_FILES:
        try: return ImageFont.truetype(f, 1100)  # 11pt drawn x100 for precision
        except Exception: continue
    raise OSError("no Times New Roman or Liberation Serif font found")


def wrap(t, width, lo, hi, rule, short_pct=0):  # no kerning
    try: from PIL import ImageFont, features; font = load_font(ImageFont)
    except Exception: return [F("NOTE", rule, "wrap", "wrap: not checked (needs Pillow and Times New Roman or Liberation Serif)")]
    w, n, cur = lambda s: font.getlength(s, **({"features": ["-kern"]} if features.check("raqm") else {})) / 100, 1, ""
    for word in t.split(): n, cur = (n + 1, word) if cur and w(cur + " " + word) > width else (n, (cur + " " + word).strip())
    out = [F("INFO" if lo <= n <= hi else "FAIL", rule, "wrap", f"wrap: {n} lines (want {lo} to {hi}), last {w(cur):.0f}/{width}pt")]
    if short_pct and n > 1 and w(cur) < width * short_pct / 100: out.append(F("NOTE", 60, "short_last_line", f"the last line fills {w(cur) * 100 / width:.0f}% of the width; under {short_pct}% leaves a short last line."))
    return out


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
    used.append(lead); return res + repeats(b, lead, bl, kept) + common(b, terms) + wrap(b, lim["text_pt"] - lim["bullet_indent_pt"], lim["bullet_lines"][0], lim["bullet_lines"][1], 4, cfg["checks"]["short_last_line_pct"])


def summary(t, cfg, terms):
    lim, sm, bl = cfg["limits"], cfg["summary"], cfg["bullets"]
    s = re.split(r"(?<=[.!?])\s+", t); res = [] if len(s) == lim["summary_sentences"] else [F("FAIL", 23, "summary_sentences", f"{len(s)} sentences; the summary needs {lim['summary_sentences']}.")]
    if sm["opening_pattern"] and not re.match(sm["opening_pattern"], t): res.append(F("FAIL", 23, "summary_opening", "sentence 1 does not open as required by the opening pattern in settings."))
    res += [F("FAIL", 24, "summary_past", f"sentence {i} must open in past tense.") for i, x in enumerate(s[1:], 2) if not past(re.sub(r"\W", "", x.split()[0]).lower(), bl)]
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


NUMBER_WORDS = "two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety".split()  # zero, one and single stay allowed
FIRST_PERSON = re.compile(r"(?<![\w/@-])(I|(?i:we|my|our|us|me))(?![\w/@-])")  # 'I' and 'US' are case-sensitive; I/O is skipped by the lookarounds
VAGUE_SIZE = re.compile(r"(?i)\b(millions|thousands|billions|hundreds of|dozens of)\b")
NUMBER_WORD = re.compile(r"(?i)(?<![\w-])(" + "|".join(NUMBER_WORDS) + r")(?!\w)")
SENTENCES = r"(?<=[.!?])\s+"


_PHRASE_ROWS = []  # the shipped file, read once per run


def robot_rows(cfg):
    """The shipped robot-phrase rows plus checks.robot_phrases_extra, minus checks.robot_phrases_ignore."""
    if not _PHRASE_ROWS:
        with open(PHRASES, encoding="utf-8") as f: _PHRASE_ROWS.extend(json.load(f)["phrases"])
    rows = list(_PHRASE_ROWS)
    rows = rows + [{"phrase": x, "forms": [x], "kind": "phrase", "start_only": False} for x in cfg["checks"]["robot_phrases_extra"]]
    ignore = {x.lower() for x in cfg["checks"]["robot_phrases_ignore"]}
    return [dict(r, forms=[f for f in r["forms"] if f.lower() not in ignore]) for r in rows if r["phrase"].lower() not in ignore]


def text_checks(t, cfg, summary=False, skip_start=False):
    """Wave 1 text checks that read one bullet or one summary. skip_start: the lead check already flagged the opening word."""
    res, t = [], t.replace("\u2019", "'")
    for m in FIRST_PERSON.finditer(t):
        if m.group() != "US": res.append(F("FAIL", 20, "first_person", f"'{m.group()}' is first person; write the bullet without it."))
    for m in VAGUE_SIZE.finditer(t):
        if not re.search(r"\d[\d.,]*\s*$", t[:m.start()]): res.append(F("FAIL", 12, "vague_size", f"'{m.group()}' is a vague size; give the number."))
    res += [F("WARN", 5, "number_word", f"'{m.group()}': write the number as digits.") for m in NUMBER_WORD.finditer(t)]
    if not summary and "," in t:
        word = (t.rsplit(",", 1)[1].split() or [""])[0].lower().strip(".,;:")
        if word in cfg["checks"]["vague_ing_verbs"]: res.append(F("WARN", 19, "vague_ing", f"the last clause opens with '{word}'; name the result instead."))
    sents, bl = re.split(SENTENCES, t), cfg["bullets"]
    part = set(cfg["checks"]["passive_participles"])
    for m in re.finditer(r"\b(?:was|were|is|are|be|been|being|get|got)\s+(\w+)", t, re.I):
        w = m.group(1).lower()
        if (w.endswith("ed") and len(w) > 3 and w not in bl["not_past"]) or w in part: res.append(F("NOTE", 19, "passive", f"passive voice: '{m.group()}'; say who did it."))
    for row in robot_rows(cfg):
        for f in row["forms"]:
            esc = re.escape(f.replace("\u2019", "'"))
            if row["start_only"]:
                hit = None if skip_start else next((m for m in (re.match(r"(?i)" + esc + r"(?![\w-])", x) for x in sents) if m), None)
            else: hit = re.search(r"(?i)(?<![\w-])" + esc + r"(?![\w-])", t)
            if hit:
                res.append(F("WARN", 18, "robot_phrase", f"'{hit.group()}' sounds like a robot phrase; use a plainer word."))
                break
    return res


def check_document(raws, text, cfg):
    """Document checks: raws = the bullets as written (final period kept); text = the whole document text."""
    res, n = [], text.count("\u2014")
    if n: res.append(F("WARN", 19, "em_dash", f"{n} em dash{'es' if n > 1 else ''} in the document; use a comma, colon or period."))
    no = sum(not r.rstrip().endswith(".") for r in raws)
    if raws and 0 < no < len(raws): res.append(F("WARN", 37, "mixed_endings", f"{no} of {len(raws)} bullets have no final period; end them all the same way."))
    return res


def check_bullet(text, used_leads, cfg, terms, kept=None):
    """All one-bullet checks. used_leads (lowercase first words of the other bullets) gets this bullet's lead appended."""
    res = bullet(text, used_leads, cfg, terms, kept or {})
    return res + text_checks(text, cfg, skip_start=any(r["check"] == "lead_not_past" for r in res)) if text.split() else res


def check_summary(text, cfg, terms):
    return summary(text, cfg, terms) + text_checks(text, cfg, summary=True)


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
    return {"text": t, "status": status_of(res), "words": len(t.split()), "chars": len(t), "findings": res, "kind": kind, "label": (t.split() or [""])[0]}


CODE = {"OK": 0, "FAIL": 1, "WARN": 2, "NOT CHECKED": 2}


def show(items, as_json):
    if as_json:
        print(json.dumps([{k: v for k, v in it.items() if k not in ("head", "kind", "label")} for it in items], indent=1, ensure_ascii=False))
    else:
        for it in items:
            print(it.get("head") or f"{it['status']} {it['words']}w {it['chars']}c :: {it['text'][:80]}")
            for r in it["findings"]: print(f"    {r['level']} rule {r['rule']}: {r['message']}")
    codes = [CODE[it["status"]] for it in items]
    return 1 if 1 in codes else 2 if 2 in codes else 0


def short_last_lines(items):
    """k11: take the per-bullet short-last-line notes out of the results and return ONE finding naming the bullets (None when none)."""
    bl, ids = [it for it in items if it.get("kind") == "bullet"], []
    for it in bl:
        if any(r["check"] == "short_last_line" for r in it["findings"]):
            it["findings"] = [r for r in it["findings"] if r["check"] != "short_last_line"]
            ids.append(it.get("label") or "?")
    return F("NOTE", 60, "short_last_line", f"{len(ids)} of {len(bl)} bullets end on a short last line: {', '.join(ids)}") if ids else None


def document_item(raws, text, ctx, extra=None):
    """The document-level findings as one extra result (None when there are none)."""
    res = check_document(raws, text, ctx["cfg"]) + ([extra] if extra else [])
    return {"text": "document", "status": status_of(res), "words": 0, "chars": 0, "findings": res, "head": f"{status_of(res)} document ({len(raws)} bullets)"} if res else None


def need_root(ctx, flag):
    if not ctx["root"]: raise SystemExit(f"error: {flag} needs a data folder (run where.py to see where it should be).")


def lead_of(text):
    return re.sub(r"\W", "", text.split()[0]).lower() if text.split() else ""


def all_bullets(ctx):
    """Expand --all into one (bank row, version, leads) per bank bullet: leads are the other bullets of the first version that holds it."""
    need_root(ctx, "--all")
    bank = rd.load("bank.json", ctx["root"])["bullets"]
    versions = rd.version_names(ctx["root"])
    for b in bank:
        v = next((n for n in versions if b["marks"].get(n, {}).get("in")), None)
        leads = [re.sub(r"\W", "", x["lead"]).lower() for x in bank if v and x["marks"].get(v, {}).get("in") and x["id"] != b["id"]]
        yield b, v, leads


def whole_resume(bullets, summary_text, text, ctx, labels=None):
    """Items for a list of bullets (leads = the other bullets), an optional summary, and the document checks."""
    items, leads = [], [lead_of(b) for b in bullets]
    for i, b in enumerate(bullets):
        items.append(run_one("bullet", b, leads[:i] + leads[i + 1:], ctx))
        if labels and labels[i]: items[-1]["label"] = labels[i]
    short = short_last_lines(items)
    if summary_text: items.append(run_one("summary", summary_text, [], ctx))
    doc = document_item([b.strip() for b in bullets], text, ctx, short)
    return items + ([doc] if doc else [])


def resume_bullets(target, ctx):
    """[(bank id or None, text, tech list)] for a version, a tailoring or a draft file, in resume order."""
    need_root(ctx, "--stack")
    rd.resolve(target, ctx["root"])  # same errors as every other script for an unknown name
    bank = rd.bank_index(ctx["root"])
    if target.startswith(("tailoring:", "file:")):
        kind, ref = target.split(":", 1)
        if kind == "tailoring": t = rd.load(os.path.join("jobs", ref, "tailoring.json"), ctx["root"])
        else:
            with open(ref, encoding="utf-8") as f: t = json.load(f)
        refs = [b for g in t["roles"] + t["projects"] for b in g["bullets"]]
    else:
        v = rd.load(f"versions/{target}.json", ctx["root"])
        refs = [b for g in v["roles"] + v["projects"] for b in g["bullet_ids"]]
    out = []
    for r in refs:
        i = r.get("id") if isinstance(r, dict) else r
        out.append((i, r["text"] if isinstance(r, dict) and "text" in r else bank[i]["text"], bank.get(i, {}).get("tech", [])))
    return out


def stack_items(rows, cfg):
    """k39: per bullet, the terms of its bank row's tech list the text does not name (language and runtime first), then one line per
    term that 2+ bullets use and fewer name. Never fails."""
    langs = {x.lower() for x in cfg["checks"]["stack_languages"]}
    first = lambda term: 0 if term.lower() in langs or term.split()[0].lower() in langs else 1

    def names(text, term):
        forms = [term] + ([term.split(" ", 1)[1]] if term.split(" ", 1)[0] in ("AWS", "Amazon") and " " in term else [])
        return any(re.search(r"(?i)(?<![\w-])" + re.escape(f) + r"(?![\w])", text) for f in forms)
    items, used, named = [], collections.Counter(), collections.Counter()
    for i, text, tech in rows:
        missing = [x for x in sorted(tech, key=first) if not names(text, x)]
        for x in tech:
            used[x] += 1; named[x] += names(text, x)
        res = [F("NOTE", 67, "stack_coverage", f"not named in this bullet: {', '.join(missing)}.")] if missing else []
        items.append({"text": f"{i or 'bullet'}: {text}", "status": "OK", "words": len(text.split()), "chars": len(text), "findings": res})
    lines = [F("NOTE", 67, "stack_coverage", f"{x}: used in {used[x]} bullets, named in {named[x]}.") for x in sorted(used, key=lambda x: (first(x), x)) if used[x] >= 2 and named[x] < used[x]]
    items.append({"text": "stack summary", "status": "OK", "words": 0, "chars": 0, "findings": lines, "head": "OK stack summary"})
    return items


def main(a):
    as_json = "--json" in a
    a = [x for x in a if x != "--json"]
    ctx = context()
    if a == ["--all"]:
        worst, done = 0, []
        for b, v, leads in all_bullets(ctx):
            item = run_one("bullet", b["text"], list(leads), ctx)
            item["label"], item["version"] = b["id"], v; done.append(item)
            code = CODE[item["status"]]
            worst = 1 if 1 in (worst, code) else max(worst, code)
        if as_json:
            out = [dict({"id": it["label"], "version": it["version"], "exit": CODE[it["status"]]}, **{k: v for k, v in it.items() if k not in ("kind", "label", "version", "head")}) for it in done]
            print(json.dumps(out, indent=1, ensure_ascii=False)); sys.exit(worst)
        short = short_last_lines(done)  # removes the per-bullet notes from the results
        for item in done:
            print(f"## {item['label']} ({item['version'] or 'none'}) exit={CODE[item['status']]}")
            show([item], False)
        if short: print("## all bullets"); print(f"    NOTE rule 60: {short['message']}")
        sys.exit(worst)
    if a[:1] == ["--stack"] and len(a) == 2:
        show(stack_items(resume_bullets(a[1], ctx), ctx["cfg"]), as_json); sys.exit(0)
    if a[:1] == ["--resume"] and len(a) == 2:
        need_root(ctx, "--resume")
        r = rd.resolve(a[1], ctx["root"])
        bullets = [b for g in r["roles"] + r["projects"] for b in g["bullets"]]
        ids = [i for i, _, _ in resume_bullets(a[1], ctx)]  # bank ids, in the same order as the resolved bullets
        sys.exit(show(whole_resume(bullets, r["summary"], rd.render_text(r), ctx, ids if len(ids) == len(bullets) else None), as_json))
    if a[:1] == ["--document-file"] and len(a) == 2:
        try:
            with open(a[1], encoding="utf-8") as f: lines = [x.strip() for x in f.read().splitlines() if x.strip()]
        except OSError as e: raise SystemExit(f"error: cannot read {a[1]}: {e.strerror}")
        sm = next((x[len("SUMMARY:"):].strip() for x in lines if x.startswith("SUMMARY:")), "")
        sys.exit(show(whole_resume([x for x in lines if not x.startswith("SUMMARY:")], sm, "\n".join(lines), ctx), as_json))
    items, raws, texts, used, kind = [], [], [], [], "bullet"
    if not ctx["root"] and not as_json: print("NOTE rule 16: no data folder found, private names were not checked")
    while a:
        x = a.pop(0)
        if x == "--leads" and a: used += re.sub(r"[^A-Za-z]", " ", a.pop(0)).lower().split(); continue
        if x == "--summary": kind = "summary"; continue
        if x == "--pages":
            if len(a) < 2 or not a[0].isdigit(): raise SystemExit("error: --pages needs a page cap and a file, for example: --pages 2 resume.pdf")
            cap, path = int(a.pop(0)), a.pop(0)
            res = pages(cap, path)
            st = "NOT CHECKED" if res[0]["level"] == "NOTE" else status_of(res)
            items.append({"text": path, "status": st, "words": 0, "chars": 0, "findings": res, "head": st}); continue
        if x.startswith("--"): raise SystemExit(f"error: unknown option {x}; see --help")
        items.append(run_one(kind, x, used, ctx))
        texts.append(x.strip())
        if kind == "bullet": raws.append(x.strip())
    doc = document_item(raws, "\n".join(texts), ctx, short_last_lines(items))
    if doc: items.append(doc)
    if as_json and not ctx["root"]:
        for it in items: it["findings"].append(F("NOTE", 16, "no_data_folder", "no data folder found, private names were not checked"))
    sys.exit(show(items, as_json))


if __name__ == "__main__":
    if {"-h", "--help"} & set(sys.argv[1:]): print(__doc__); sys.exit(0)
    main(sys.argv[1:])
