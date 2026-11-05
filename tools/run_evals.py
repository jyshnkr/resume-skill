#!/usr/bin/env python3
"""Run the agent evals in Claude Code, headless, on a temporary copy of the sample data. Only when asked: every run spends usage.

    python3 tools/run_evals.py --yes [--cases e01,e05] [--model sonnet] [--baseline] [--triggers] [--runs 3] [--out DIR]

Without --yes it prints the plan (number of agent calls) and exits 2. Each case runs `claude -p` in an empty scratch folder with
RESUME_SKILL_DATA pointing at a fresh copy of examples/data (a case can ask for a submitted tailoring or no data folder), loads the
skill with --plugin-dir (or not, with --baseline, to record how the model does without it), saves the output and grades it with
evals/grade.py. --triggers runs the trigger set instead: for each query it records whether the skill was invoked (a Skill tool
call named resume-skill), --runs times each. Other skills installed on the machine can also trigger; the run records which
skill each query invoked. Codex is run by hand. Results go to DIR (default evals/runs/<timestamp>, not committed).
"""
import json, os, shutil, subprocess, sys, tempfile, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "evals"))
import grade as G  # noqa: E402

TOOLS = ["Bash(python3 *)", "Read", "Write", "Edit", "Glob", "Grep"]


def opt(a, name, default=None):
    return a[a.index(name) + 1] if name in a else default


def skills_called(stream):
    out = []
    for line in stream.splitlines():
        try:
            o = json.loads(line)
        except ValueError:
            continue
        for c in (o.get("message") or {}).get("content", []) if isinstance(o.get("message"), dict) else []:
            if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") == "Skill":
                out.append(str((c.get("input") or {}).get("skill", "")))
    return out


def claude(prompt, model, cwd, env, with_skill, max_turns):
    cmd = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose", "--max-turns", str(max_turns),
           "--permission-mode", "acceptEdits", "--allowedTools", *TOOLS]
    if model:
        cmd += ["--model", model]
    if with_skill:
        cmd += ["--plugin-dir", ROOT]
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=900)
    final = ""
    for line in r.stdout.splitlines():
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if o.get("type") == "result":
            final = o.get("result", "")
    return final, r.stdout


def make_data(case, scratch):
    data = os.path.join(scratch, "data")
    if case.get("setup") == "no data folder exists":
        return data
    shutil.copytree(os.path.join(ROOT, "examples", "data"), data)
    if case.get("setup", "").startswith("acme-backend tailoring has status submitted"):
        p = os.path.join(data, "jobs", "acme-backend", "tailoring.json")
        with open(p, encoding="utf-8") as f:
            t = json.load(f)
        t.update({"status": "submitted", "sent_on": "2000-01-01"})
        with open(p, "w", encoding="utf-8") as f:
            json.dump(t, f, indent=2)
    return data


def main(a):
    if {"-h", "--help"} & set(a):
        print(__doc__)
        return 0
    with open(os.path.join(ROOT, "evals", "cases.json"), encoding="utf-8") as f:
        cases = json.load(f)["cases"]
    with open(os.path.join(ROOT, "evals", "triggers.json"), encoding="utf-8") as f:
        trig = json.load(f)
    ids = opt(a, "--cases")
    if ids:
        cases = [c for c in cases if c["id"] in ids.split(",")]
    runs = int(opt(a, "--runs", trig["runs_each"] if "--triggers" in a else 1))
    n = (len(trig["should_fire"]) + len(trig["should_not_fire"])) * runs if "--triggers" in a else len(cases) * runs
    model, baseline = opt(a, "--model"), "--baseline" in a
    print(f"plan: {n} agent call(s), model {model or 'default'}, {'baseline (no skill)' if baseline else 'with the skill'}, "
          f"{'trigger set' if '--triggers' in a else 'cases ' + ','.join(c['id'] for c in cases)}")
    if "--yes" not in a:
        print("not run: add --yes to spend the usage", file=sys.stderr)
        return 2
    if not shutil.which("claude"):
        print("error: the claude command is not on PATH", file=sys.stderr)
        return 1
    out = opt(a, "--out") or os.path.join(ROOT, "evals", "runs", time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(out, exist_ok=True)
    summary = []
    if "--triggers" in a:
        for group, expect in (("should_fire", True), ("should_not_fire", False)):
            for q in trig[group]:
                for i in range(runs):
                    scratch = tempfile.mkdtemp(prefix="rs-trig-")
                    env = {**os.environ, "RESUME_SKILL_DATA": os.path.join(scratch, "data")}
                    _, stream = claude(q["query"], model, scratch, env, not baseline, 3)
                    called = skills_called(stream)
                    fired = any("resume-skill" in c for c in called)
                    summary.append({"id": q["id"], "run": i + 1, "expect_fire": expect, "fired": fired, "skills": called, "pass": fired == expect})
                    shutil.rmtree(scratch, ignore_errors=True)
    else:
        for c in cases:
            for i in range(runs):
                scratch = tempfile.mkdtemp(prefix="rs-eval-")
                data = make_data(c, scratch)
                before = G.tree_hash(data) if os.path.isdir(data) else ""
                env = {**os.environ, "RESUME_SKILL_DATA": data, "RESUME_SKILL_CONFIG_DIR": os.path.join(scratch, "config")}
                final, stream = claude(c["prompt"], model, scratch, env, not baseline, 25)
                text_path = os.path.join(out, f"{c['id']}-{i + 1}.txt")
                with open(text_path, "w", encoding="utf-8") as f:
                    f.write(final)
                res = G.grade(c, final, data, before)
                summary.append({"id": c["id"], "run": i + 1, "pass": all(ok for _, ok in res), "checks": [{"check": k, "pass": ok} for k, ok in res]})
                shutil.rmtree(scratch, ignore_errors=True)
    with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1)
    ok = sum(s["pass"] for s in summary)
    print(f"{ok} of {len(summary)} runs pass; details in {out}")
    return 0 if ok == len(summary) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
