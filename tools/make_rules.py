#!/usr/bin/env python3
"""Generate skills/resume-skill/references/rules-1.md, rules-2.md and rules-3.md from assets/rules/registry.json.

    python3 tools/make_rules.py           # write the three files
    python3 tools/make_rules.py --check   # exit 1 if the files on disk differ from the registry (CI and tests use this)

The registry is the single source of the 67 rules. Each live rule has:
  when      preflight | posting | tailoring | final | reading ... see "when_meaning" in the registry. The tag is assigned by
            this rule of thumb: a rule that a script can test on one bank bullet = preflight; a rule that only makes sense
            with a posting in hand = posting; a rule about editing the resume for a posting (choosing bullets, summary,
            skills, honesty) = tailoring; layout, delivery and the last look = final.
  enforced  check (check.py emits findings with that rule number), build (a named script does it; field "by"), or
            reading (a person or the model reads it; the final-read list covers the judgement ones).
Rules 64 and 65 are kept as pointers (merged into 42 and 25). Rule 11 is written out in brackets.md, not here.
Every generated file stays under 5,000 characters.
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, "skills", "resume-skill")
REGISTRY = os.path.join(SKILL, "assets", "rules", "registry.json")
LIMIT = 5000
GROUPS = [  # file number -> research sections that go into it (balanced so each file stays under the limit)
    (1, ["Building a bullet", "Words and style"]),
    (2, ["Numbers and honesty", "The summary", "Skills and posting words"]),
    (3, ["Layout and length", "Tailoring for a posting", "Other"]),
]
ENF = {"check": "checker", "build": "build", "reading": "read"}


def render(rules, number, sections):
    lines = [f"# Rules, part {number}", "",
             "Generated from assets/rules/registry.json by tools/make_rules.py. Do not edit by hand.",
             "Tag = when the rule applies, then who enforces it (checker = scripts/check.py, build = a script, read = you).", ""]
    for sec in sections:
        lines += [f"## {sec}", ""]
        for r in rules:
            if r["section"] != sec:
                continue
            if r["status"] == "merged":
                lines.append(f"**{r['n']}** merged into rule {r['into']}.")
            elif r["n"] == 11:
                lines.append(f"**11** [{r['when']} · read] Platform brackets: read brackets.md before adding one.")
            else:
                lines.append(f"**{r['n']}** [{r['when']} · {ENF[r['enforced']]}] {r['text']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build():
    with open(REGISTRY, encoding="utf-8") as f:
        rules = json.load(f)["rules"]
    return {f"rules-{n}.md": render(rules, n, secs) for n, secs in GROUPS}


def main(a):
    if {"-h", "--help"} & set(a):
        print(__doc__)
        return 0
    files, bad = build(), 0
    for name, text in files.items():
        path = os.path.join(SKILL, "references", name)
        if len(text) >= LIMIT:
            print(f"error: {name} is {len(text)} characters (limit {LIMIT})", file=sys.stderr)
            bad = 1
        if "--check" in a:
            cur = open(path, encoding="utf-8").read() if os.path.exists(path) else None
            if cur != text:
                print(f"stale: {name} differs from the registry; run tools/make_rules.py", file=sys.stderr)
                bad = 1
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"wrote {name} ({len(text)} characters)")
    return bad


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
