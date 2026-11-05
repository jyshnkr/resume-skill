"""Seam: tools/import_old.py. An old-layout repo (made-up fixture) in, a new data folder out. Expected values are hand-written."""
import hashlib, json, os, shutil, unittest
from helpers import TmpCase, run, write, ROOT, FIXTURES, SKILL

TOOLS = os.path.join(ROOT, "tools")
OLD = os.path.join(FIXTURES, "old-repo")
DEFAULTS = os.path.join(SKILL, "assets", "defaults", "settings.json")

FIXES = [
    {"id": "f1", "description": "Say the course use of Kubernetes", "op": "replace", "file": "profile.md", "find": "- Kubernetes.", "replace": "- Kubernetes (course only)."},
    {"id": "f2", "description": "Text that is not there", "op": "replace", "file": "profile.md", "find": "NO SUCH TEXT", "replace": "x"},
    {"id": "f3", "description": "Add Kafka to the do-not-claim list", "op": "append_line", "file": "profile.md", "after_heading": "Do not claim", "line": "- Kafka."},
    {"id": "f4", "description": "Mark b003 as needing a number", "op": "set_bank_field", "ids": ["b003"], "field": "needs_metric", "value": True},
    {"id": "f5", "description": "Maybe merge two bullets", "op": "offer", "note": "ask first"},
    {"id": "f6", "description": "Unknown bullet", "op": "set_bank_field", "ids": ["b099"], "field": "note", "value": "x"},
    {"id": "f7", "description": "Text that occurs twice", "op": "replace", "file": "profile.md", "find": "in ", "replace": "inside "},
]


def slurp(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


def tree(path):
    out = {}
    for dirpath, dirs, files in os.walk(path):
        for d in dirs:
            out[os.path.relpath(os.path.join(dirpath, d), path) + "/"] = ""
        for f in files:
            with open(os.path.join(dirpath, f), "rb") as fh:
                out[os.path.relpath(os.path.join(dirpath, f), path)] = hashlib.sha256(fh.read()).hexdigest()
    return out


class ImportOldTests(TmpCase):
    def setUp(self):
        super().setUp()
        self.old = os.path.join(self.tmp, "old")
        shutil.copytree(OLD, self.old)
        self.new = os.path.join(self.tmp, "new")
        self.fixes = os.path.join(self.tmp, "fixes.json")
        write(self.fixes, json.dumps(FIXES))

    def imp(self, *args, root=TOOLS):
        return run("import_old.py", "--old", self.old, "--data", self.new, *args, root=root, env=self.base_env, cwd=self.tmp)

    def text(self, *parts):
        with open(os.path.join(self.new, *parts), encoding="utf-8") as f:
            return f.read()

    def test_dry_run_lists_fixes_and_writes_nothing_anywhere(self):
        before = tree(self.tmp)
        r = self.imp("--dry-run", "--fixes", self.fixes)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        want = {"f1": "yes", "f2": "no", "f3": "yes", "f4": "yes", "f5": "offer", "f6": "no", "f7": "no"}
        for fid, state in want.items():
            line = next(l for l in r.stdout.splitlines() if f"[{fid}]" in l)
            self.assertIn(f"applicable: {state}", line)
        self.assertIn("text not found", r.stdout)
        self.assertIn("unknown bullet b099", r.stdout)
        self.assertIn("times (it must occur once)", r.stdout)
        self.assertEqual(tree(self.tmp), before)
        self.assertFalse(os.path.exists(self.new))
        for dirpath, dirs, files in os.walk(self.tmp):
            self.assertNotIn("out", dirs)

    def test_dry_run_with_apply_still_changes_nothing(self):
        before = tree(self.tmp)
        r = self.imp("--dry-run", "--fixes", self.fixes, "--apply", "f1", "f3")
        self.assertEqual(r.returncode, 0)
        self.assertIn("selected by --apply", r.stdout)
        self.assertEqual(tree(self.tmp), before)

    def test_real_run_maps_the_old_layout(self):
        old_before = tree(self.old)
        r = self.imp()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("0 errors", r.stdout)
        self.assertIn("by hand", r.stdout)  # the old check.py values are not carried
        bank = self.jload(self.new, "bank.json")
        self.assertEqual(bank["roles"], ["northwind", "larkspur", "project"])
        self.assertEqual(len(bank["bullets"]), 6)
        self.assertTrue(all(b["tech"] == [] for b in bank["bullets"]))
        self.assertEqual(sorted(os.listdir(os.path.join(self.new, "versions"))), ["contract.json", "master.json"])
        for name in ("master", "contract"):
            v = self.jload(self.new, "versions", name + ".json")
            self.assertEqual(v["certifications"], [])
        self.assertIn("raw", bank["bullets"][0]["marks"]["master"])
        self.assertEqual(self.jload(self.new, "summaries.json"), self.jload(self.old, "data", "summaries.json"))
        self.assertEqual(self.text("profile.md"), slurp(self.old, "data", "profile.md"))
        self.assertEqual(self.jload(self.new, "private", "terms.json"), self.jload(self.old, "data", "private", "terms.json"))
        self.assertEqual(self.jload(self.new, "private", "contact.json"), self.jload(self.old, "data", "private", "contact.json"))
        self.assertTrue(os.path.isfile(os.path.join(self.new, "private", "bank-notes.md")))
        self.assertEqual(tree(self.old), old_before, "the old repo must not change")

    def test_tailorings_move_into_jobs_folders(self):
        self.imp()
        t = self.jload(self.new, "jobs", "acme-api", "tailoring.json")
        self.assertEqual((t["slug"], t["base"], t["status"]), ("acme-api", "contract", "submitted"))
        self.assertEqual(t["posting"], "posting.md")
        self.assertIsNone(t["sent_on"])
        self.assertEqual(t["bank_commit"], "a1b2c3d")
        self.assertNotIn("jd_files", t)
        self.assertEqual(self.text("jobs", "acme-api", "posting.md"), slurp(self.old, "data", "jds", "acme-api.md"))
        d = self.jload(self.new, "jobs", "borealis-data", "tailoring.json")
        self.assertEqual(d["status"], "draft")
        self.assertEqual(d["posting"], "posting.md")
        self.assertTrue(d["roles"][0]["bullets"][0]["override"])

    def test_a_second_jd_becomes_posting_2(self):
        write(os.path.join(self.old, "data", "jds", "acme-api-extra.md"), "# Second posting (made-up)\n")
        p = os.path.join(self.old, "data", "tailorings", "acme-api.json")
        with open(p, encoding="utf-8") as f:
            t = json.load(f)
        t["jd_files"].append("data/jds/acme-api-extra.md")
        write(p, json.dumps(t))
        self.imp()
        self.assertEqual(self.text("jobs", "acme-api", "posting-2.md"), "# Second posting (made-up)\n")
        self.assertEqual(self.jload(self.new, "jobs", "acme-api", "tailoring.json")["posting"], "posting.md")

    def test_old_files_go_to_archive(self):
        self.imp()
        a = lambda *p: os.path.join(self.new, "archive", *p)
        for rel in (("retired.json",), ("bank-notes.md",), ("drive.json",), ("CHANGELOG.md",), ("history", "README.md"),
                    ("history", "2026-01-05-example.md"), ("resumes", "Casey_Marlow_Master.txt"), ("resumes", "Casey_Marlow_Contract.txt")):
            self.assertTrue(os.path.isfile(a(*rel)), rel)
        self.assertFalse(os.path.exists(os.path.join(self.new, "retired.json")))
        self.assertFalse(os.path.exists(os.path.join(self.new, "changelog")))

    def test_settings_are_the_shipped_defaults(self):
        self.imp()
        with open(DEFAULTS, "rb") as a, open(os.path.join(self.new, "settings.json"), "rb") as b:
            self.assertEqual(a.read(), b.read())

    def test_the_new_folder_has_the_standard_layout(self):
        self.imp()
        for d in ("versions", "private", "jobs", "changes", "backups", "out", "archive"):
            self.assertTrue(os.path.isdir(os.path.join(self.new, d)), d)
        self.assertTrue(os.path.isfile(os.path.join(self.new, "private", "recruiters.md")))

    def test_imported_folder_passes_validate_on_its_own(self):
        self.imp()
        r = run("validate.py", env=self.env_for(self.new))
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_refuses_a_non_empty_data_folder_and_accepts_an_empty_one(self):
        write(os.path.join(self.new, "x.txt"), "mine")
        before = tree(self.new)
        r = self.imp()
        self.assertEqual(r.returncode, 1)
        self.assertIn("not empty", r.stderr)
        self.assertEqual(tree(self.new), before)
        os.remove(os.path.join(self.new, "x.txt"))
        self.assertEqual(self.imp().returncode, 0)

    def test_refuses_something_that_is_not_the_old_repo(self):
        os.remove(os.path.join(self.old, "data", "bank.json"))
        r = self.imp()
        self.assertEqual(r.returncode, 1)
        self.assertIn("data/bank.json not found", r.stderr)
        self.assertFalse(os.path.exists(self.new))

    # fixes
    def test_only_the_ids_passed_to_apply_run_and_each_prints_before_and_after(self):
        r = self.imp("--fixes", self.fixes, "--apply", "f1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("before: - Kubernetes.", r.stdout)
        self.assertIn("after:  - Kubernetes (course only).", r.stdout)
        self.assertIn("- Kubernetes (course only).", self.text("profile.md"))
        self.assertNotIn("Kafka", self.text("profile.md"))  # f3 was not selected
        bank = self.jload(self.new, "bank.json")
        self.assertFalse(bank["bullets"][2]["needs_metric"])  # f4 was not selected

    def test_no_apply_means_no_fix_runs(self):
        self.imp("--fixes", self.fixes)
        self.assertNotIn("course only", self.text("profile.md"))

    def test_append_line_goes_to_the_end_of_the_named_section(self):
        r = self.imp("--fixes", self.fixes, "--apply", "f3")
        self.assertIn("applied", r.stdout)
        lines = self.text("profile.md").splitlines()
        i = lines.index("- Kubernetes.")
        self.assertEqual(lines[i + 1], "- Kafka.")
        self.assertEqual(lines[i + 2], "")
        self.assertEqual(lines[i + 3], "## Preferences")

    def test_set_bank_field_changes_the_listed_rows_only(self):
        r = self.imp("--fixes", self.fixes, "--apply", "f4")
        self.assertIn("b003.needs_metric: false -> true", r.stdout)
        flags = {b["id"]: b["needs_metric"] for b in self.jload(self.new, "bank.json")["bullets"]}
        self.assertEqual([k for k, v in flags.items() if v], ["b003"])

    def test_a_fix_that_does_not_apply_says_why_and_changes_nothing(self):
        r = self.imp("--fixes", self.fixes, "--apply", "f2", "f6", "f7")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("not applicable: text not found", r.stdout)
        self.assertIn("not applicable: unknown bullet b099", r.stdout)
        self.assertIn("times (it must occur once)", r.stdout)
        self.assertIn("3 not applied", r.stdout)

    def test_offers_are_never_applied_even_when_asked(self):
        r = self.imp("--fixes", self.fixes, "--apply", "f5")
        self.assertEqual(r.returncode, 0)
        self.assertIn("never applied automatically", r.stdout)

    def test_unknown_apply_id_stops_before_writing(self):
        r = self.imp("--fixes", self.fixes, "--apply", "f99")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no fix with id f99", r.stderr)
        self.assertFalse(os.path.exists(self.new))

    def test_malformed_fix_is_a_one_line_error(self):
        write(self.fixes, json.dumps([{"id": "z", "op": "replace", "file": "profile.md"}]))
        r = self.imp("--fixes", self.fixes, "--dry-run")
        self.assertEqual(r.returncode, 1)
        self.assertIn("needs find, replace", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    # preflight: a made-up stand-in script in a copy of the skill, because preflight.py belongs to another slice
    def staged_repo(self, preflight_json):
        repo = os.path.join(self.tmp, "repo")
        shutil.copytree(os.path.join(ROOT, "skills"), os.path.join(repo, "skills"), ignore=shutil.ignore_patterns("__pycache__", "preflight.py"))
        os.makedirs(os.path.join(repo, "tools"))
        shutil.copy(os.path.join(TOOLS, "import_old.py"), os.path.join(repo, "tools", "import_old.py"))
        if preflight_json is None:
            return os.path.join(repo, "tools")
        write(os.path.join(repo, "skills", "resume-skill", "scripts", "preflight.py"),
              "import json, os, sys\nassert '--quiet' in sys.argv\nroot = os.environ['RESUME_SKILL_DATA']\nos.makedirs(os.path.join(root, 'out'), exist_ok=True)\n"
              "open(os.path.join(root, 'out', 'preflight.json'), 'w').write(%r)\n" % preflight_json)
        return os.path.join(repo, "tools")

    def test_prints_how_many_bullets_need_attention_when_preflight_exists(self):
        doc = {"bullets": [{"id": "b%03d" % i, "findings": ["x"] if i in (2, 5) else []} for i in range(1, 7)]}
        r = self.imp(root=self.staged_repo(json.dumps(doc)))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("2 of 6 bullets need attention", r.stdout)

    def test_no_attention_line_without_preflight(self):
        r = self.imp(root=self.staged_repo(None))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("need attention", r.stdout)

    def test_the_real_preflight_line_is_printed(self):
        r = self.imp()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r"\d+ of \d+ bullets need attention")


if __name__ == "__main__":
    unittest.main()
