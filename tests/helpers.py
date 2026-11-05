"""Shared test helpers. Tests run the scripts as a user would: as separate processes, through their command line."""
import json, os, subprocess, sys, tempfile, shutil, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, "skills", "resume-skill")
SCRIPTS = os.path.join(SKILL, "scripts")
EXAMPLE = os.path.join(ROOT, "examples", "data")
FIXTURES = os.path.join(ROOT, "tests", "fixtures")


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def run(script, *args, env=None, cwd=None, root=SCRIPTS):
    """Run scripts/<script> with the current interpreter. stdin is closed so any prompt would fail the test."""
    e = {k: v for k, v in os.environ.items() if not k.startswith("RESUME_SKILL_")}
    e.update(env or {})
    path = script if os.path.isabs(script) else os.path.join(root, script)
    return subprocess.run([sys.executable, "-B", path, *map(str, args)], capture_output=True, text=True, env=e,
                          cwd=cwd, stdin=subprocess.DEVNULL, timeout=120)


class TmpCase(unittest.TestCase):
    """A test case with a scratch folder and helpers to copy the example data into it."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rs-test-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.config = os.path.join(self.tmp, "config")  # stands in for ~/.config/resume-skill
        self.base_env = {"RESUME_SKILL_CONFIG_DIR": self.config}

    def example_copy(self, name="data"):
        dest = os.path.join(self.tmp, name)
        shutil.copytree(EXAMPLE, dest)
        return dest

    def env_for(self, data):
        return {**self.base_env, "RESUME_SKILL_DATA": data}

    def jload(self, *parts):
        with open(os.path.join(*parts), encoding="utf-8") as f:
            return json.load(f)
