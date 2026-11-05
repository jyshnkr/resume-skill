"""Seam: the user's settings file is settings.yaml (commented YAML); a legacy settings.json is still read.
Tested through the scripts' command lines: check.py (reads the limits), where.py, setup.py, validate.py, preflight.py."""
import glob, json, os, unittest
from helpers import TmpCase, run, write, edit_settings, miniyaml, EXAMPLE, SKILL

SHIPPED = os.path.join(SKILL, "assets", "defaults", "settings.yaml")
LONG = "Cut nightly batch time from six hours to ninety minutes by moving the slowest report steps into parallel workers"  # 112 chars


def tree(path):
    out = {}
    for dirpath, dirs, files in os.walk(path):
        for d in dirs:
            out[os.path.relpath(os.path.join(dirpath, d), path) + "/"] = ""
        for f in files:
            with open(os.path.join(dirpath, f), "rb") as fh:
                out[os.path.relpath(os.path.join(dirpath, f), path)] = fh.read()
    return out


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


class Case(TmpCase):
    def folder(self, name="data"):
        """A copy of the example data with no settings file at all."""
        d = self.example_copy(name)
        for f in ("settings.yaml", "settings.json"):
            if os.path.exists(os.path.join(d, f)):
                os.remove(os.path.join(d, f))
        return d

    def limit_line(self, d, text=LONG):
        """What check.py says about a bullet (the character limit is one of its lines)."""
        return run("check.py", "--leads", "", text, env=self.env_for(d))

    def setup(self, d, *args):
        return run("setup.py", "--data", d, *args, env=self.base_env)

    def validate(self, d, *args):
        return run("validate.py", *args, env=self.env_for(d))


class ReadingTheFile(Case):
    def test_yaml_values_are_used(self):
        d = self.folder()
        write(os.path.join(d, "settings.yaml"), "limits:\n  chars: 111\n")
        r = self.limit_line(d)
        self.assertIn("112 characters; the limit is 111", r.stdout)

    def test_yml_is_accepted(self):
        d = self.folder()
        write(os.path.join(d, "settings.yml"), "limits:\n  chars: 90\n")
        self.assertIn("112 characters; the limit is 90", self.limit_line(d).stdout)

    def test_yaml_wins_over_yml(self):
        d = self.folder()
        write(os.path.join(d, "settings.yaml"), "limits:\n  chars: 111\n")
        write(os.path.join(d, "settings.yml"), "limits:\n  chars: 90\n")
        self.assertIn("112 characters; the limit is 111", self.limit_line(d).stdout)

    def test_a_legacy_json_is_read_when_there_is_no_yaml(self):
        d = self.folder()
        write(os.path.join(d, "settings.json"), '{"limits": {"chars": 222}}')
        self.assertNotIn("characters; the limit", self.limit_line(d).stdout)  # 112 chars is under 222
        write(os.path.join(d, "settings.json"), '{"limits": {"chars": 100}}')
        self.assertIn("112 characters; the limit is 100", self.limit_line(d).stdout)

    def test_yaml_wins_over_json_when_both_exist(self):
        d = self.folder()
        write(os.path.join(d, "settings.yaml"), "limits:\n  chars: 111\n")
        write(os.path.join(d, "settings.json"), '{"limits": {"chars": 999}}')
        self.assertIn("112 characters; the limit is 111", self.limit_line(d).stdout)

    def test_options_the_file_lacks_come_from_the_shipped_defaults(self):
        d = self.folder()
        write(os.path.join(d, "settings.yaml"), "preferences:\n  location: Denver\n")
        self.assertIn("characters; the limit is 215", self.limit_line(d, LONG + " " + LONG).stdout)

    def test_a_broken_yaml_gives_one_error_line_with_the_line_number(self):
        d = self.folder()
        write(os.path.join(d, "settings.yaml"), "limits:\n  chars: 111\n  this line has no colon\n")
        r = self.limit_line(d)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(r.stderr, "error: settings.yaml: line 3: expected 'key: value'\n")
        self.assertNotIn("Traceback", r.stderr)


class WhereReadiness(Case):
    def test_a_folder_with_only_settings_yaml_is_ready(self):
        p = os.path.join(self.tmp, "mine")
        write(os.path.join(p, "settings.yaml"), "")
        r = run("where.py", env=self.env_for(p))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines()[0], p)

    def test_a_folder_with_only_settings_yml_is_ready(self):
        p = os.path.join(self.tmp, "mine")
        write(os.path.join(p, "settings.yml"), "")
        self.assertEqual(run("where.py", env=self.env_for(p)).returncode, 0)

    def test_a_folder_with_only_the_legacy_json_is_ready(self):
        p = os.path.join(self.tmp, "mine")
        write(os.path.join(p, "settings.json"), "{}")
        self.assertEqual(run("where.py", env=self.env_for(p)).returncode, 0)

    def test_a_folder_without_a_settings_file_names_settings_yaml(self):
        p = os.path.join(self.tmp, "mine")
        write(os.path.join(p, "notes.txt"), "x")
        r = run("where.py", env=self.env_for(p))
        self.assertEqual(r.returncode, 1)
        self.assertIn("settings.yaml", r.stderr)


class SetupNewFolder(Case):
    def test_a_new_folder_gets_settings_yaml_as_a_byte_copy_of_the_defaults(self):
        d = os.path.join(self.tmp, "mydata")
        r = self.setup(d, "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(os.path.join(d, "settings.json")))
        with open(SHIPPED, "rb") as a, open(os.path.join(d, "settings.yaml"), "rb") as b:
            self.assertEqual(a.read(), b.read())

    def test_the_plan_names_settings_yaml(self):
        r = self.setup(os.path.join(self.tmp, "mydata"))
        self.assertIn("settings.yaml", r.stdout)
        self.assertNotIn("settings.json", r.stdout)

    def test_a_fresh_folder_validates_with_no_errors(self):
        d = os.path.join(self.tmp, "mydata")
        self.setup(d, "--yes")
        r = self.validate(d)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("0 errors", r.stdout)
        self.assertNotIn("settings:", r.stdout)  # no new, unknown or old-format notes

    def test_running_setup_again_changes_nothing(self):
        d = os.path.join(self.tmp, "mydata")
        self.setup(d, "--yes")
        before = tree(d)
        r = self.setup(d, "--yes")
        self.assertIn("already set up", r.stdout)
        self.assertEqual(tree(d), before)

    def test_a_folder_with_only_the_legacy_json_counts_as_set_up(self):
        d = os.path.join(self.tmp, "old")
        write(os.path.join(d, "settings.json"), "{}")
        before = tree(d)
        self.assertIn("already set up", self.setup(d, "--yes").stdout)
        self.assertEqual(tree(d), before)


def trimmed_yaml(case):
    """The example data with some options removed, one value changed, an extra option added and one user comment."""
    d = case.example_copy()

    def cut(s):
        del s["output"]["font"]
        del s["fit"]["weights"]["preferred"]
        del s["checks"]
        s["limits"]["chars"] = 999
        s["limits"]["my_extra"] = 7
        s["preferences"]["location"] = "Denver, CO"
    edit_settings(d, cut)
    path = os.path.join(d, "settings.yaml")
    write(path, "# my own note\n" + read(path))
    return d


class AddMissingSettings(Case):
    def test_dry_run_lists_the_keys_and_writes_nothing(self):
        d = trimmed_yaml(self)
        before = tree(d)
        r = self.setup(d, "--add-missing-settings", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        for name in ("output.font", "fit.weights.preferred", "checks"):
            self.assertIn(name, r.stdout)
        self.assertEqual(tree(d), before)

    def test_without_yes_it_prints_the_plan_and_exits_2(self):
        d = trimmed_yaml(self)
        before = tree(d)
        r = self.setup(d, "--add-missing-settings")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(tree(d), before)

    def test_adds_the_keys_and_keeps_every_user_value(self):
        d = trimmed_yaml(self)
        r = self.setup(d, "--add-missing-settings", "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        got = miniyaml.load(os.path.join(d, "settings.yaml"))
        want = miniyaml.load(SHIPPED)
        self.assertEqual(got["output"]["font"], want["output"]["font"])
        self.assertEqual(got["fit"]["weights"], want["fit"]["weights"])
        self.assertEqual(got["checks"], want["checks"])
        self.assertEqual(got["limits"]["chars"], 999)
        self.assertEqual(got["limits"]["my_extra"], 7)
        self.assertEqual(got["preferences"]["location"], "Denver, CO")
        self.assertEqual(got["preferences"]["domains"], ["logistics", "payments"])

    def test_a_key_the_user_added_stays_at_the_end_of_its_section(self):
        d = trimmed_yaml(self)
        self.setup(d, "--add-missing-settings", "--yes")
        got = miniyaml.load(os.path.join(d, "settings.yaml"))
        self.assertEqual(list(got["limits"])[-1], "my_extra")
        self.assertEqual(list(got["limits"])[:-1], list(miniyaml.load(SHIPPED)["limits"]))

    def test_the_shipped_hints_are_written_and_the_user_comments_are_replaced(self):
        d = trimmed_yaml(self)
        r = self.setup(d, "--add-missing-settings", "--yes")
        text = read(d, "settings.yaml")
        self.assertIn("# START HERE.", text)
        self.assertNotIn("my own note", text)
        self.assertIn("comments", r.stdout)  # the command says the user's own comments are replaced

    def test_running_it_twice_changes_nothing(self):
        d = trimmed_yaml(self)
        self.setup(d, "--add-missing-settings", "--yes")
        before = tree(d)
        r = self.setup(d, "--add-missing-settings", "--yes")
        self.assertIn("already set up", r.stdout)
        self.assertEqual(tree(d), before)

    def test_validate_has_no_new_option_warnings_afterwards(self):
        d = trimmed_yaml(self)
        self.assertIn("new option", self.validate(d).stdout)
        self.setup(d, "--add-missing-settings", "--yes")
        self.assertNotIn("new option", self.validate(d).stdout)

    def test_a_json_only_folder_gets_a_settings_yaml_and_keeps_its_values(self):
        d = self.folder()
        write(os.path.join(d, "settings.json"), json.dumps({"limits": {"chars": 999}, "preferences": {"location": "Reno"}}))
        r = self.setup(d, "--add-missing-settings", "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        got = miniyaml.load(os.path.join(d, "settings.yaml"))
        self.assertEqual(got["limits"]["chars"], 999)
        self.assertEqual(got["preferences"]["location"], "Reno")
        self.assertEqual(got["output"]["font"], "Times New Roman")

    def test_add_missing_on_a_json_only_folder_converts_it_fully(self):
        d = self.folder()
        write(os.path.join(d, "settings.json"), json.dumps({"limits": {"chars": 999}, "preferences": {"location": "Reno"}}))
        r = self.setup(d, "--add-missing-settings", "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(os.path.join(d, "settings.json")), "the old file is moved away, not left beside the new one")
        self.assertTrue(os.path.exists(os.path.join(d, "archive", "settings.json")))
        again = self.setup(d, "--convert-settings", "--yes")
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertIn("nothing to convert", again.stdout)
        self.assertNotIn("old format", self.validate(d).stdout)

    def test_a_broken_yaml_is_refused_and_nothing_changes(self):
        d = self.example_copy()
        write(os.path.join(d, "settings.yaml"), "limits:\n  chars: 5\n  no colon here\n")
        before = tree(d)
        r = self.setup(d, "--add-missing-settings", "--yes")
        self.assertEqual(r.returncode, 1)
        self.assertIn("settings.yaml: line 3", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(tree(d), before)


def json_folder(case, chars=999):
    """The example data with a legacy settings.json (a trimmed one) instead of settings.yaml."""
    d = case.folder()
    write(os.path.join(d, "settings.json"), json.dumps(
        {"schema": 1, "limits": {"chars": chars}, "preferences": {"location": "Reno", "domains": ["retail"]}}, indent=2))
    return d


class ConvertSettings(Case):
    def test_dry_run_lists_the_change_and_writes_nothing(self):
        d = json_folder(self)
        before = tree(d)
        r = self.setup(d, "--convert-settings", "--dry-run", "--yes")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("settings.yaml", r.stdout)
        self.assertIn("archive/settings.json", r.stdout)
        self.assertEqual(tree(d), before)

    def test_without_yes_it_prints_the_plan_and_exits_2(self):
        d = json_folder(self)
        before = tree(d)
        self.assertEqual(self.setup(d, "--convert-settings").returncode, 2)
        self.assertEqual(tree(d), before)

    def test_writes_settings_yaml_with_all_values_and_hints_and_archives_the_json(self):
        d = json_folder(self)
        original = read(d, "settings.json")
        r = self.setup(d, "--convert-settings", "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(os.path.join(d, "settings.json")))
        self.assertEqual(read(d, "archive", "settings.json"), original)
        got = miniyaml.load(os.path.join(d, "settings.yaml"))
        want = miniyaml.load(SHIPPED)
        want["limits"]["chars"] = 999
        want["preferences"]["location"] = "Reno"
        want["preferences"]["domains"] = ["retail"]
        self.assertEqual(got, want)
        self.assertIn("# START HERE.", read(d, "settings.yaml"))

    def test_the_converted_folder_validates_without_settings_notes(self):
        d = json_folder(self)
        self.setup(d, "--convert-settings", "--yes")
        r = self.validate(d)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn("settings:", r.stdout)

    def test_an_existing_archive_file_is_never_overwritten(self):
        d = json_folder(self)
        write(os.path.join(d, "archive", "settings.json"), '{"older": true}')
        r = self.setup(d, "--convert-settings", "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(read(d, "archive", "settings.json"), '{"older": true}')
        moved = [f for f in glob.glob(os.path.join(d, "archive", "settings*.json")) if not f.endswith(os.sep + "settings.json")]
        self.assertEqual(len(moved), 1)
        self.assertEqual(os.path.basename(moved[0]), "settings-1.json")
        self.assertEqual(json.loads(read(moved[0]))["limits"]["chars"], 999)

    def test_a_folder_that_already_has_settings_yaml_is_refused(self):
        d = self.example_copy()
        write(os.path.join(d, "settings.json"), "{}")
        before = tree(d)
        r = self.setup(d, "--convert-settings", "--yes")
        self.assertEqual(r.returncode, 1)
        self.assertIn("settings.yaml", r.stderr)
        self.assertEqual(tree(d), before)

    def test_a_folder_without_a_json_has_nothing_to_convert(self):
        d = self.example_copy()
        before = tree(d)
        r = self.setup(d, "--convert-settings", "--yes")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("nothing to convert", r.stdout)
        self.assertEqual(tree(d), before)

    def test_a_broken_json_is_refused_and_nothing_changes(self):
        d = self.folder()
        write(os.path.join(d, "settings.json"), "{ nope")
        before = tree(d)
        r = self.setup(d, "--convert-settings", "--yes")
        self.assertEqual(r.returncode, 1)
        self.assertIn("settings.json", r.stderr)
        self.assertEqual(tree(d), before)

    def test_converting_twice_changes_nothing(self):
        d = json_folder(self)
        self.setup(d, "--convert-settings", "--yes")
        before = tree(d)
        r = self.setup(d, "--convert-settings", "--yes")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(tree(d), before)


class ValidateSettings(Case):
    def setUp(self):
        super().setUp()
        self.d = self.example_copy()

    def drop_yaml(self):
        for f in ("settings.yaml", "settings.json"):
            if os.path.exists(os.path.join(self.d, f)):
                os.remove(os.path.join(self.d, f))

    def errors(self):
        r = self.validate(self.d)
        return r, [l for l in r.stdout.splitlines() if l.startswith("ERROR")]

    def test_the_example_data_validates_clean(self):
        r = self.validate(self.d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("0 errors, 0 warnings", r.stdout)

    def test_a_settings_file_that_does_not_parse_is_one_error_with_the_line(self):
        write(os.path.join(self.d, "settings.yaml"), "limits:\n  chars: 5\n\tlines: 2\n")
        r, errs = self.errors()
        self.assertEqual(r.returncode, 1)
        self.assertEqual(len(errs), 1, r.stdout)
        self.assertIn("settings.yaml: line 3", errs[0])
        self.assertNotIn("Traceback", r.stderr)

    def test_a_legacy_json_that_does_not_parse_is_one_error_with_the_file_name(self):
        self.drop_yaml()
        write(os.path.join(self.d, "settings.json"), "{ nope")
        r, errs = self.errors()
        self.assertEqual(len(errs), 1, r.stdout)
        self.assertIn("settings.json", errs[0])

    def test_a_legacy_json_gets_the_old_format_warning(self):
        self.drop_yaml()
        write(os.path.join(self.d, "settings.json"), "{}")
        r = self.validate(self.d)
        self.assertIn("WARN settings: settings.json is the old format; run setup.py --convert-settings --yes "
                      "for settings.yaml with hints", r.stdout)

    def test_valid_hand_edits_pass(self):
        def ok(s):
            s["preferences"].update(work_type=["contract"], location="Boise, ID", remote="remote", minimum_rate=62.5,
                                    minimum_rate_unit="year", domains=[])
            s["output"].update(copy_resumes_to="~/Documents/resumes", backup_copy_to=None)
            s["fit"]["weights"].update(required=60, preferred=40.5)
        edit_settings(self.d, ok)
        r = self.validate(self.d)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("0 errors", r.stdout)

    def test_minimum_rate_may_be_null(self):
        edit_settings(self.d, lambda s: s["preferences"].update(minimum_rate=None))
        self.assertEqual(self.validate(self.d).returncode, 0)

    def test_each_wrong_type_is_an_error_naming_the_key(self):
        bad = [
            ("preferences.work_type", lambda s: s["preferences"].update(work_type="contract")),
            ("preferences.work_type", lambda s: s["preferences"].update(work_type=[1, 2])),
            ("preferences.location", lambda s: s["preferences"].update(location=["Austin"])),
            ("preferences.remote", lambda s: s["preferences"].update(remote=3)),
            ("preferences.minimum_rate", lambda s: s["preferences"].update(minimum_rate="70")),
            ("preferences.minimum_rate", lambda s: s["preferences"].update(minimum_rate=True)),
            ("preferences.minimum_rate_unit", lambda s: s["preferences"].update(minimum_rate_unit="month")),
            ("preferences.minimum_rate_unit", lambda s: s["preferences"].update(minimum_rate_unit=None)),
            ("preferences.domains", lambda s: s["preferences"].update(domains="logistics")),
            ("preferences.domains", lambda s: s["preferences"].update(domains=[["a"]])),
            ("output.copy_resumes_to", lambda s: s["output"].update(copy_resumes_to=5)),
            ("output.backup_copy_to", lambda s: s["output"].update(backup_copy_to=["x"])),
            ("fit.weights.required", lambda s: s["fit"]["weights"].update(required="high")),
            ("fit.weights.preferred", lambda s: s["fit"]["weights"].update(preferred=False)),
            ("fit.weights", lambda s: s["fit"].update(weights=[70, 30])),
        ]
        for n, (key, change) in enumerate(bad):
            with self.subTest(n=n, key=key):
                d = self.example_copy(f"case{n}")
                edit_settings(d, change)
                r = self.validate(d)
                errs = [l for l in r.stdout.splitlines() if l.startswith("ERROR") and key in l]
                self.assertEqual(r.returncode, 1, r.stdout)
                self.assertTrue(errs, r.stdout)

    def test_a_missing_key_is_a_new_option_warning_not_a_type_error(self):
        def drop(s):
            del s["preferences"]["minimum_rate_unit"]
        edit_settings(self.d, drop)
        r = self.validate(self.d)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("WARN settings: new option 'preferences.minimum_rate_unit' (run setup.py --add-missing-settings)", r.stdout)

    def test_unknown_option_is_still_a_warning(self):
        edit_settings(self.d, lambda s: s["limits"].update(colour="blue"))
        r = self.validate(self.d)
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARN settings: unknown option 'limits.colour'", r.stdout)


class ExampleData(Case):
    def test_the_example_folder_has_settings_yaml_and_no_json(self):
        self.assertTrue(os.path.isfile(os.path.join(EXAMPLE, "settings.yaml")))
        self.assertFalse(os.path.exists(os.path.join(EXAMPLE, "settings.json")))
        self.assertFalse(os.path.exists(os.path.join(SKILL, "assets", "defaults", "settings.json")))

    def test_the_sample_preferences(self):
        got = miniyaml.load(os.path.join(EXAMPLE, "settings.yaml"))["preferences"]
        self.assertEqual(got, {"work_type": ["full-time", "contract"], "location": "Austin, TX", "remote": "remote or hybrid",
                               "minimum_rate": 70, "minimum_rate_unit": "hour", "domains": ["logistics", "payments"]})

    def test_everything_else_is_the_shipped_default(self):
        got = miniyaml.load(os.path.join(EXAMPLE, "settings.yaml"))
        want = miniyaml.load(SHIPPED)
        got.pop("preferences"), want.pop("preferences")
        self.assertEqual(got, want)

    def test_the_example_file_keeps_the_hints(self):
        self.assertIn("# START HERE.", read(EXAMPLE, "settings.yaml"))


class PreflightFingerprint(Case):
    def test_a_settings_yaml_edit_makes_the_stored_result_stale(self):
        d = self.example_copy()
        env = self.env_for(d)
        run("preflight.py", "--quiet", env=env)
        with open(os.path.join(d, "out", "preflight.json"), encoding="utf-8") as f:
            old = json.load(f)["fingerprint"]
        edit_settings(d, lambda s: s["limits"].update(words=[5, 9]))
        r = run("preflight.py", "--if-stale", "--quiet", env=env)
        self.assertEqual(r.returncode, 1)
        with open(os.path.join(d, "out", "preflight.json"), encoding="utf-8") as f:
            self.assertNotEqual(json.load(f)["fingerprint"], old)

    def test_a_legacy_json_edit_makes_it_stale_too(self):
        d = self.folder()
        write(os.path.join(d, "settings.json"), "{}")
        env = self.env_for(d)
        run("preflight.py", "--quiet", env=env)
        with open(os.path.join(d, "out", "preflight.json"), encoding="utf-8") as f:
            old = json.load(f)["fingerprint"]
        write(os.path.join(d, "settings.json"), '{"limits": {"words": [5, 9]}}')
        run("preflight.py", "--if-stale", "--quiet", env=env)
        with open(os.path.join(d, "out", "preflight.json"), encoding="utf-8") as f:
            self.assertNotEqual(json.load(f)["fingerprint"], old)


class DocsSayYaml(unittest.TestCase):
    def test_skill_md_and_workflow_point_to_the_preferences_block_of_settings_yaml(self):
        skill = read(SKILL, "SKILL.md")
        self.assertIn("settings.yaml", skill)
        self.assertNotIn("settings.json", skill)
        self.assertIn("`preferences` block of settings.yaml", read(SKILL, "references", "workflow.md") + skill)


if __name__ == "__main__":
    unittest.main()
