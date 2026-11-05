#!/usr/bin/env python3
"""Run the agent evals in Claude Code, headless, on a temporary copy of the sample data. Only when asked: every run spends usage.

    python3 tools/run_evals.py --yes [--cases e01,e05] [--model sonnet] [--baseline | --plugin-dir] [--block-skills NAME[,NAME]] [--workers N] [--strict-mcp] [--triggers] [--runs 3] [--out DIR]

Without --yes it prints the plan (number of agent calls) and exits 2. Each case runs `claude -p` in an empty scratch folder with
RESUME_SKILL_DATA pointing at a fresh copy of examples/data (a case can ask for a submitted tailoring or no data folder), loads the
skill as installed in the skills folder (--plugin-dir loads this repo instead; --baseline turns every skill off to record how the model does without it), saves the output and grades it with
evals/grade.py. --triggers runs the trigger set instead: for each query it records whether the skill was invoked (a Skill tool
call named resume-skill), --runs times each. Other skills installed on the machine can also trigger; the run records which
skill each query invoked. --block-skills switches a named competing skill (for example the old jd-fit-check) off for the session, so it is not even listed, for a fair measure of this skill alone. --workers N runs up to N calls at once (each has its own scratch folder and data copy; the same total usage, finished sooner; 4 is a safe cap). --strict-mcp starts none of the machine's MCP connectors (about 3 s faster per call). Codex is run by hand. Results go to DIR (default evals/runs/<timestamp>, not committed).
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


def skill_engaged(stream, name):
    """True when the run called the Skill tool for `name`, or read its SKILL.md or ran its scripts through other tools."""
    for line in stream.splitlines():
        try:
            o = json.loads(line)
        except ValueError:
            continue
        m = o.get("message")
        for c in (m.get("content") if isinstance(m, dict) and isinstance(m.get("content"), list) else []):
            if isinstance(c, dict) and c.get("type") == "tool_use":
                inp = c.get("input") or {}
                if c.get("name") == "Skill" and name in str(inp.get("skill", "")):
                    return True
                text = json.dumps(inp)
                if c.get("name") != "Skill" and (f"{name}/SKILL.md" in text or f"{name}/scripts/" in text
                                                 or (f"skills/{name}" in text and ("SKILL.md" in text or "scripts/" in text))):
                    return True
    return False


def init_lists_skill(stream, name):
    """True when the session's init event lists a skill or command with this name (used to prove a baseline run had no skill)."""
    for line in stream.splitlines():
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if o.get("type") == "system" and o.get("subtype") == "init":
            return any(name in str(x) for x in (o.get("skills") or []) + (o.get("slash_commands") or []))
    return False


def build_cmd(prompt, model, mode, max_turns, block=(), strict_mcp=False):
    """mode: with-skill (the skill installed in the user's skills folder), baseline (every skill off) or plugin-dir (load this repo)."""
    cmd = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose", "--max-turns", str(max_turns),
           "--permission-mode", "acceptEdits", "--allowedTools", *TOOLS]
    if model:
        cmd += ["--model", model]
    if block:  # skillOverrides "off" removes a named skill from the session's skill list (a Skill(...) deny rule only blocks the call; the model still tries it first)
        cmd += ["--settings", json.dumps({"skillOverrides": {b: "off" for b in block}})]
    if strict_mcp:  # do not start the machine's MCP connectors (mail, calendar, browser ...): about 3 s faster per call, and no unrelated tools
        cmd.append("--strict-mcp-config")
    if mode == "baseline":
        cmd.append("--disable-slash-commands")
    elif mode == "plugin-dir":
        cmd += ["--plugin-dir", ROOT]
    return cmd


def claude(prompt, model, cwd, env, mode, max_turns, block=(), strict_mcp=False):
    r = subprocess.run(build_cmd(prompt, model, mode, max_turns, block, strict_mcp), cwd=cwd, env=env, capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, timeout=900)
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
        os.chmod(p, 0o444)  # a sent tailoring is read-only on disk, as save.py leaves it
    return data


class BaselineLeak(Exception):
    """A baseline run had resume-skill in its skill list, so the comparison would be invalid."""


def run_jobs(jobs, workers, fn):
    """Run fn(job) for every job with at most `workers` at once; results come back in job order. A failing job raises after the others finish."""
    if workers <= 1:
        return [fn(j) for j in jobs]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(fn, j) for j in jobs]
        return [f.result() for f in futures]


def trigger_job(job, ctx):
    q, expect, i = job
    scratch = tempfile.mkdtemp(prefix="rs-trig-")
    try:
        env = {**os.environ, "RESUME_SKILL_DATA": os.path.join(scratch, "data")}
        _, stream = claude(q["query"], ctx["model"], scratch, env, ctx["mode"], 3, ctx["block"], ctx["strict_mcp"])
        if ctx["baseline"] and init_lists_skill(stream, "resume-skill"):
            raise BaselineLeak()
        with open(os.path.join(ctx["out"], f"{q['id']}-{i + 1}.stream.jsonl"), "w", encoding="utf-8") as sf:
            sf.write(stream)  # kept so a miss can be read, not guessed
        called = skills_called(stream)
        fired = any("resume-skill" in c for c in called)
        return {"id": q["id"], "run": i + 1, "expect_fire": expect, "fired": fired, "engaged": skill_engaged(stream, "resume-skill"),
                "skill_loaded": init_lists_skill(stream, "resume-skill"), "skills": called, "pass": fired == expect}
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def case_job(job, ctx):
    c, i = job
    scratch = tempfile.mkdtemp(prefix="rs-eval-")
    try:
        data = make_data(c, scratch)
        before = G.tree_hash(data) if os.path.isdir(data) else ""
        env = {**os.environ, "RESUME_SKILL_DATA": data, "RESUME_SKILL_CONFIG_DIR": os.path.join(scratch, "config")}
        final, stream = claude(c["prompt"], ctx["model"], scratch, env, ctx["mode"], 25, ctx["block"], ctx["strict_mcp"])
        if ctx["baseline"] and init_lists_skill(stream, "resume-skill"):
            raise BaselineLeak()
        with open(os.path.join(ctx["out"], f"{c['id']}-{i + 1}.stream.jsonl"), "w", encoding="utf-8") as sf:
            sf.write(stream)  # every tool call, to see which skill fired and what the agent ran
        with open(os.path.join(ctx["out"], f"{c['id']}-{i + 1}.txt"), "w", encoding="utf-8") as f:
            f.write(final)
        res = G.grade(c, final, data, before)
        return {"id": c["id"], "run": i + 1, "skill_loaded": init_lists_skill(stream, "resume-skill"), "skills_called": skills_called(stream),
                "pass": all(ok for _, ok in res), "checks": [{"check": k, "pass": ok} for k, ok in res]}
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


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
        for g in ("should_fire", "should_not_fire"):  # with --triggers the same option picks trigger ids (t03, n02, ...)
            trig[g] = [q for q in trig[g] if q["id"] in ids.split(",")]
    runs = int(opt(a, "--runs", trig["runs_each"] if "--triggers" in a else 1))
    n = (len(trig["should_fire"]) + len(trig["should_not_fire"])) * runs if "--triggers" in a else len(cases) * runs
    model, baseline = opt(a, "--model"), "--baseline" in a
    block = [b for b in (opt(a, "--block-skills") or "").split(",") if b]
    mode = "baseline" if baseline else "plugin-dir" if "--plugin-dir" in a else "with-skill"
    workers, strict_mcp = max(1, int(opt(a, "--workers", 1))), "--strict-mcp" in a
    print(f"plan: {n} agent call(s), model {model or 'default'}, {'baseline (no skill)' if baseline else 'with the skill'}"
          f"{', blocking ' + ','.join(block) if block else ''}{', ' + str(workers) + ' workers' if workers > 1 else ''}"
          f"{', without connectors' if strict_mcp else ''}, "
          f"{'trigger set' if '--triggers' in a else 'cases ' + ','.join(c['id'] for c in cases)}")
    if "--yes" not in a:
        print("not run: add --yes to spend the usage", file=sys.stderr)
        return 2
    if not shutil.which("claude"):
        print("error: the claude command is not on PATH", file=sys.stderr)
        return 1
    out = opt(a, "--out") or os.path.join(ROOT, "evals", "runs", time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(out, exist_ok=True)
    ctx = {"model": model, "mode": mode, "block": block, "baseline": baseline, "strict_mcp": strict_mcp, "out": out}
    try:
        if "--triggers" in a:
            jobs = [(q, expect, i) for group, expect in (("should_fire", True), ("should_not_fire", False)) for q in trig[group] for i in range(runs)]
            summary = run_jobs(jobs, workers, lambda j: trigger_job(j, ctx))
        else:
            jobs = [(c, i) for c in cases for i in range(runs)]
            summary = run_jobs(jobs, workers, lambda j: case_job(j, ctx))
    except BaselineLeak:
        print("error: a baseline run had resume-skill loaded; the comparison would be invalid", file=sys.stderr)
        return 1
    with open(os.path.join(out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1)
    ok = sum(s["pass"] for s in summary)
    print(f"{ok} of {len(summary)} runs pass; details in {out}")
    return 0 if ok == len(summary) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
