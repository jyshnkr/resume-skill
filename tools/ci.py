#!/usr/bin/env python3
"""Run every gate CI runs: the unit tests, the rules files in step with the registry, and (when LibreOffice is installed)
the page counts of the sample resumes. Exit 0 when all pass, 1 otherwise. Stdlib only; no network.

    python3 tools/ci.py
"""
import os, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "resume-skill", "scripts")


def gate(name, cmd, env=None):
    r = subprocess.run(cmd, cwd=ROOT, env={**os.environ, **(env or {})}, stdin=subprocess.DEVNULL)
    print(f"{'PASS' if r.returncode == 0 else 'FAIL'} {name}")
    return r.returncode == 0


def main(a):
    if {"-h", "--help"} & set(a):
        print(__doc__)
        return 0
    ok = [gate("unit tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests"]),
          gate("rules files match the registry", [sys.executable, "tools/make_rules.py", "--check"])]
    if shutil.which("soffice") or shutil.which("libreoffice"):
        env = {"RESUME_SKILL_DATA": os.path.join(ROOT, "examples", "data")}
        out = tempfile.mkdtemp(prefix="rs-ci-")
        for target in ("full-time", "contract", "tailoring:acme-backend"):
            ok.append(gate(f"page cap {target}", [sys.executable, os.path.join(SCRIPTS, "export.py"), target, out, "--no-contact"], env))
    else:
        print("SKIP page caps: LibreOffice is not installed")
    return 0 if all(ok) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
