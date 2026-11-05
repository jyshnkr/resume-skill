"""Seam: setup.py. Flags in, a data folder (or a plan on screen) out. Expected layout is written by hand from the spec."""
import hashlib, json, os, unittest
from helpers import TmpCase, run, write, edit_settings, miniyaml, SKILL

DEFAULTS = os.path.join(SKILL, "assets", "defaults", "settings.yaml")
DIRS = ["versions", "private", "jobs", "changes", "backups", "out", "archive"]
FILES = ["settings.yaml", "profile.md", "bank.json", "summaries.json", "private/contact.json", "private/terms.json",
         "private/bank-notes.md", "private/recruiters.md"]


def tree(path):
    """Every folder and file under path with a hash of its bytes: two equal trees are byte-identical."""
    out = {}
    for dirpath, dirs, files in os.walk(path):
        for d in dirs:
            out[os.path.relpath(os.path.join(dirpath, d), path) + "/"] = ""
        for f in files:
            with open(os.path.join(dirpath, f), "rb") as fh:
                out[os.path.relpath(os.path.join(dirpath, f), path)] = hashlib.sha256(fh.read()).hexdigest()
    return out


class SetupTests(TmpCase):
    def setUp(self):
        super().setUp()
        self.d = os.path.join(self.tmp, "mydata")

    def setup(self, *args, path=None):
        return run("setup.py", "--data", path or self.d, *args, env=self.base_env)

    def test_without_yes_prints_the_plan_and_exits_2_writing_nothing(self):
        r = self.setup()
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("re-run with --yes", r.stdout)
        self.assertIn("settings.yaml", r.stdout)
        self.assertFalse(os.path.exists(self.d))
        self.assertFalse(os.path.exists(self.config))

    def test_dry_run_writes_nothing_even_with_yes(self):
        before = tree(self.tmp)
        for extra in ([], ["--yes"], ["--yes", "--save-location"]):
            r = self.setup("--dry-run", *extra)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("settings.yaml", r.stdout)
            self.assertEqual(tree(self.tmp), before)

    def test_yes_creates_the_layout_and_exits_0(self):
        r = self.setup("--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for d in DIRS:
            self.assertTrue(os.path.isdir(os.path.join(self.d, d)), d)
        for f in FILES:
            self.assertTrue(os.path.isfile(os.path.join(self.d, f)), f)
        self.assertEqual(os.listdir(os.path.join(self.d, "versions")), [])
        self.assertIn("0 errors", r.stdout)

    def test_file_contents(self):
        self.setup("--yes")
        with open(DEFAULTS, "rb") as a, open(os.path.join(self.d, "settings.yaml"), "rb") as b:
            self.assertEqual(a.read(), b.read())
        self.assertEqual(self.jload(self.d, "bank.json"), {"roles": [], "bullets": []})
        self.assertEqual(self.jload(self.d, "summaries.json"), {"summaries": []})
        self.assertEqual(self.jload(self.d, "private", "terms.json"),
                         {"people": [], "internal_codenames": [], "patterns": [], "stage_words": []})
        c = self.jload(self.d, "private", "contact.json")
        self.assertEqual(set(c), {"name", "phone", "links"})
        self.assertEqual((c["name"], c["phone"], c["links"]), ("", "", []))
        with open(os.path.join(self.d, "profile.md"), encoding="utf-8") as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
        self.assertEqual([l for l in lines if l.startswith("## ")], ["## Claim boundaries", "## Do not claim", "## Preferences"])
        self.assertEqual(len(lines), 4, "headings only: the title and three sections")

    def test_second_run_changes_nothing_and_says_already_set_up(self):
        self.setup("--yes")
        before = tree(self.d)
        for extra in ([], ["--yes"]):
            r = self.setup(*extra)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("already set up", r.stdout)
            self.assertEqual(tree(self.d), before)

    def test_never_overwrites_a_file_the_user_edited(self):
        self.setup("--yes")
        write(os.path.join(self.d, "profile.md"), "# Mine\n")
        write(os.path.join(self.d, "bank.json"), '{"roles": ["x"], "bullets": []}')
        before = tree(self.d)
        self.setup("--yes")
        self.assertEqual(tree(self.d), before)

    def test_empty_existing_folder_is_accepted(self):
        os.makedirs(self.d)
        r = self.setup("--yes")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(os.path.isfile(os.path.join(self.d, "settings.yaml")))

    def test_refuses_a_folder_inside_the_skill_folder(self):
        for sub in ("x", os.path.join("assets", "mydata")):
            p = os.path.join(SKILL, sub)
            r = self.setup("--yes", path=p)
            self.assertEqual(r.returncode, 1)
            self.assertIn("inside the skill folder", r.stderr)
            self.assertFalse(os.path.exists(p), p)
        r = self.setup("--yes", path=SKILL)
        self.assertEqual(r.returncode, 1)

    def test_refuses_a_non_empty_folder_that_is_not_a_data_folder(self):
        write(os.path.join(self.d, "notes.txt"), "keep me")
        before = tree(self.d)
        r = self.setup("--yes")
        self.assertEqual(r.returncode, 1)
        self.assertIn("not empty", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(tree(self.d), before)

    def test_refuses_a_file(self):
        write(os.path.join(self.tmp, "afile"), "x")
        r = self.setup("--yes", path=os.path.join(self.tmp, "afile"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("is a file", r.stderr)

    def test_data_flag_is_required(self):
        r = run("setup.py", "--yes", env=self.base_env)
        self.assertEqual(r.returncode, 1)
        self.assertIn("--data", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_help(self):
        r = run("setup.py", "-h")
        self.assertEqual(r.returncode, 0)
        self.assertIn("--add-missing-settings", r.stdout)

    def test_save_location_only_when_asked(self):
        self.setup("--yes")
        self.assertFalse(os.path.exists(os.path.join(self.config, "location")))
        r = self.setup("--yes", "--save-location")
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.config, "location"), encoding="utf-8") as f:
            self.assertEqual(f.read().strip(), self.d)
        again = tree(self.tmp)
        self.assertIn("already set up", self.setup("--yes", "--save-location").stdout)
        self.assertEqual(tree(self.tmp), again)

    def test_save_location_on_a_new_folder_in_one_go(self):
        r = self.setup("--yes", "--save-location")
        self.assertEqual(r.returncode, 0, r.stdout)
        where = run("where.py", env=self.base_env)
        self.assertEqual(where.stdout.splitlines()[0], self.d)
        self.assertIn("source: saved", where.stdout)

    def test_json_output(self):
        r = self.setup("--yes", "--json")
        out = json.loads(r.stdout)
        self.assertEqual(out["path"], self.d)
        self.assertEqual(out["status"], "done")
        self.assertEqual(out["validate"]["errors"], [])
        r2 = self.setup("--json")
        self.assertEqual(json.loads(r2.stdout)["status"], "already set up")

    def test_a_folder_that_fails_the_check_exits_1(self):
        d = self.example_copy()
        write(os.path.join(d, "bank.json"), "{ broken")
        r = self.setup("--yes", "--save-location", path=d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("ERROR", r.stdout)

    # --add-missing-settings
    def trimmed(self):
        d = self.example_copy()
        def cut(s):
            del s["output"]["font"]
            del s["fit"]["weights"]["preferred"]
            del s["checks"]
            s["limits"]["chars"] = 999
        s = edit_settings(d, cut)
        return d, s

    def test_add_missing_settings_dry_run_lists_and_writes_nothing(self):
        d, _ = self.trimmed()
        before = tree(d)
        r = self.setup("--add-missing-settings", "--dry-run", path=d)
        self.assertEqual(r.returncode, 0)
        for name in ("output.font", "fit.weights.preferred", "checks"):
            self.assertIn(name, r.stdout)
        self.assertEqual(tree(d), before)

    def test_add_missing_settings_adds_keys_and_keeps_values(self):
        d, mine = self.trimmed()
        r = self.setup("--add-missing-settings", "--yes", path=d)
        self.assertEqual(r.returncode, 0, r.stdout)
        got = miniyaml.load(os.path.join(d, "settings.yaml"))
        default = miniyaml.load(DEFAULTS)
        self.assertEqual(got["output"]["font"], default["output"]["font"])
        self.assertEqual(got["fit"]["weights"], default["fit"]["weights"])
        self.assertEqual(got["checks"], default["checks"])
        self.assertEqual(got["limits"]["chars"], 999, "an existing value must not change")

    def test_add_missing_settings_twice_is_byte_identical(self):
        d, _ = self.trimmed()
        self.setup("--add-missing-settings", "--yes", path=d)
        before = tree(d)
        r = self.setup("--add-missing-settings", "--yes", path=d)
        self.assertIn("already set up", r.stdout)
        self.assertEqual(tree(d), before)

    def test_add_missing_settings_then_validate_has_no_new_option_warnings(self):
        d, _ = self.trimmed()
        self.assertIn("new option", run("validate.py", env=self.env_for(d)).stdout)
        self.setup("--add-missing-settings", "--yes", path=d)
        self.assertNotIn("new option", run("validate.py", env=self.env_for(d)).stdout)

    def test_add_missing_settings_refuses_a_broken_settings_file(self):
        d = self.example_copy()
        write(os.path.join(d, "settings.yaml"), "limits:\n  no colon here\n")
        before = tree(d)
        r = self.setup("--add-missing-settings", "--yes", path=d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("settings.yaml", r.stderr)
        self.assertEqual(tree(d), before)


if __name__ == "__main__":
    unittest.main()
