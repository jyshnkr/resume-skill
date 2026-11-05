"""Seam 5: preflight.py runs the one-bullet checks on every bank bullet and writes out/preflight.json. It never edits the bank."""
import hashlib, json, os, re, time, unittest
from helpers import TmpCase, run, write, edit_settings, EXAMPLE


try:  # Pillow plus the Liberation Serif font (found by name, or in the current folder)
    from PIL import ImageFont
    ImageFont.truetype("LiberationSerif-Regular.ttf", 11)
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False


def digest(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class PreflightCase(TmpCase):
    def setUp(self):
        super().setUp()
        self.data = self.example_copy()
        self.out = os.path.join(self.data, "out", "preflight.json")

    def pre(self, *args, data=None):
        return run("preflight.py", *args, env=self.env_for(data or self.data))

    def result(self):
        return self.jload(self.out)

    def edit_bullet(self, bid, fn):
        p = os.path.join(self.data, "bank.json")
        bank = self.jload(p)
        fn(next(b for b in bank["bullets"] if b["id"] == bid))
        write(p, json.dumps(bank, indent=2))


class WritesTheResultTests(PreflightCase):
    def test_sample_bank_is_clean_and_the_file_has_the_agreed_shape(self):
        r = self.pre()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        res = self.result()
        self.assertEqual(sorted(res), ["bullets", "fingerprint", "hold_back", "ran_at", "summary"])
        self.assertRegex(res["fingerprint"], r"^[0-9a-f]{64}$")
        self.assertRegex(res["ran_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d")
        self.assertEqual(sorted(res["bullets"]), ["b%03d" % i for i in range(1, 13)])
        self.assertEqual({v["status"] for v in res["bullets"].values()}, {"OK"})
        self.assertEqual(res["hold_back"], [])
        self.assertEqual(res["summary"], "0 of 12 bullets need attention")
        for v in res["bullets"].values():
            self.assertEqual(sorted(v), ["findings", "status"])
        f = res["bullets"]["b012"]["findings"][0]  # a finding keeps level, rule, check and message
        self.assertEqual((f["level"], f["rule"], f["check"]), ("NOTE", 10, "no_metric"))

    def test_b002_is_clean_only_because_of_its_allowed_repeat(self):
        self.edit_bullet("b002", lambda b: b.__setitem__("allowed_repeats", []))
        r = self.pre()
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertEqual(self.result()["bullets"]["b002"]["status"], "WARN")

    def test_a_fail_holds_the_bullet_back_and_a_warn_does_not(self):
        self.edit_bullet("b003", lambda b: b.__setitem__("text", b["text"].replace(" by moving", " while moving")))  # no 'by': rule 2
        self.edit_bullet("b001", lambda b: b.__setitem__("text", b["text"].replace("partitioned", "robust partitioned")))  # robot phrase: WARN
        r = self.pre()
        self.assertEqual(r.returncode, 1, r.stdout)
        res = self.result()
        self.assertEqual(res["hold_back"], ["b003"])
        self.assertEqual(res["bullets"]["b003"]["status"], "FAIL")
        self.assertEqual(res["bullets"]["b001"]["status"], "WARN")
        self.assertEqual(res["summary"], "2 of 12 bullets need attention")
        self.assertIn("b003", r.stdout)
        self.assertIn("rule 2", r.stdout)

    def test_a_warn_only_run_exits_2_and_holds_nothing_back(self):
        self.edit_bullet("b001", lambda b: b.__setitem__("text", b["text"].replace("partitioned", "robust partitioned")))
        r = self.pre()
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertEqual(self.result()["hold_back"], [])

    def test_leads_of_the_other_bullets_in_the_same_version_are_used(self):
        self.edit_bullet("b002", lambda b: b.__setitem__("lead", "Cut"))
        self.edit_bullet("b002", lambda b: b.__setitem__("text", "Cut" + b["text"][len("Reduced"):]))
        r = self.pre()
        res = self.result()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(res["hold_back"], ["b001", "b002"])

    def test_the_bank_is_never_edited(self):
        self.edit_bullet("b003", lambda b: b.__setitem__("text", "x"))
        bank = os.path.join(self.data, "bank.json")
        before = digest(bank)
        for args in ([], ["--json"], ["--quiet"], ["--if-stale"]):
            self.pre(*args)
            self.assertEqual(digest(bank), before, args)

    def test_plain_run_rewrites_and_json_prints_what_was_written(self):
        self.pre()
        res = self.result()
        res["ran_at"] = "2000-01-01T00:00:00"
        write(self.out, json.dumps(res))
        r = self.pre("--json")
        self.assertEqual(r.returncode, 0)
        printed = json.loads(r.stdout)
        self.assertEqual(printed, self.result())
        self.assertNotEqual(printed["ran_at"], "2000-01-01T00:00:00")

    def test_quiet_prints_nothing_but_still_writes_and_exits(self):
        self.edit_bullet("b003", lambda b: b.__setitem__("text", "x"))
        r = self.pre("--quiet")
        self.assertEqual((r.stdout, r.returncode), ("", 1))
        self.assertEqual(self.result()["hold_back"], ["b003"])


class ShortLastLineTests(PreflightCase):
    @unittest.skipUnless(HAVE_PIL, "needs Pillow and Liberation Serif")
    def test_each_short_last_line_note_stays_on_its_own_bullet(self):
        self.pre()
        notes = {i: [f for f in v["findings"] if f["check"] == "short_last_line"] for i, v in self.result()["bullets"].items()}
        short = [i for i, n in notes.items() if n]
        self.assertTrue(short)
        for i in short:
            self.assertEqual((len(notes[i]), notes[i][0]["rule"], notes[i][0]["level"]), (1, 60, "NOTE"))
            self.assertEqual(self.result()["bullets"][i]["status"], "OK")


class StaleTests(PreflightCase):
    def test_if_stale_runs_when_there_is_no_result_yet(self):
        r = self.pre("--if-stale")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.exists(self.out))

    def test_if_stale_is_silent_and_leaves_the_file_alone_when_nothing_changed(self):
        self.pre()
        before = digest(self.out)
        r = self.pre("--if-stale")
        self.assertEqual((r.stdout, r.stderr, r.returncode), ("", "", 0))
        self.assertEqual(digest(self.out), before)

    def test_if_stale_reruns_after_a_bullet_edit(self):
        self.pre()
        old = self.result()
        self.edit_bullet("b003", lambda b: b.__setitem__("text", b["text"].replace(" by moving", " while moving")))
        r = self.pre("--if-stale")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertNotEqual(self.result()["fingerprint"], old["fingerprint"])
        self.assertEqual(self.result()["hold_back"], ["b003"])

    def test_if_stale_reruns_after_a_settings_edit(self):
        self.pre()
        old = self.result()
        edit_settings(self.data, lambda s: s["limits"].update(words=[5, 9]))
        r = self.pre("--if-stale")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertNotEqual(self.result()["fingerprint"], old["fingerprint"])
        self.assertEqual(len(self.result()["hold_back"]), 12)

    def test_if_stale_reruns_after_a_terms_edit(self):
        self.pre()
        old = self.result()["fingerprint"]
        p = os.path.join(self.data, "private", "terms.json")
        t = self.jload(p)
        t["internal_codenames"].append("Orion")
        write(p, json.dumps(t))
        self.pre("--if-stale")
        self.assertNotEqual(self.result()["fingerprint"], old)

    def test_unchanged_stale_run_keeps_the_stored_verdict_in_its_exit_code(self):
        self.edit_bullet("b003", lambda b: b.__setitem__("text", "x"))
        self.pre()
        r = self.pre("--if-stale")
        self.assertEqual((r.stdout, r.returncode), ("", 1))


class RobustnessTests(PreflightCase):
    def test_whole_example_bank_in_under_two_seconds_with_stdin_closed(self):
        t = time.time()
        r = self.pre()  # tests/helpers.run closes stdin
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertLess(time.time() - t, 2.0)

    def test_no_data_folder_is_a_one_line_error(self):
        r = run("preflight.py", env=self.base_env)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)
        self.assertTrue(r.stderr.strip())

    def test_help(self):
        r = self.pre("--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("--if-stale", r.stdout)
        self.assertIn("Exit", r.stdout)
        self.assertIn("silent and its exit code is the stored verdict", r.stdout.replace("\n", " "))

    def test_unknown_option_is_a_one_line_error(self):
        r = self.pre("--nope")
        self.assertEqual(r.returncode, 1)
        self.assertIn("error: unknown option --nope", r.stderr)

    def test_running_twice_gives_the_same_result_apart_from_the_time(self):
        self.pre()
        a = self.result()
        self.pre()
        b = self.result()
        a.pop("ran_at"), b.pop("ran_at")
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
