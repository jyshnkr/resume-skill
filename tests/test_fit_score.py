"""fit_score.py: the arithmetic of the fit score. The worked examples in references/fit.md are the spec."""
import json, os, re, unittest

from helpers import SKILL, TmpCase, run, write, edit_settings

FIT_MD = os.path.join(SKILL, "references", "fit.md")


def examples():
    with open(FIT_MD, encoding="utf-8") as f:
        blocks = re.findall(r"```json fit-example\n(.*?)\n```", f.read(), re.S)
    return [json.loads(b) for b in blocks]


class FitCase(TmpCase):
    def setUp(self):
        super().setUp()
        self.data = self.example_copy()
        self.env = self.env_for(self.data)

    def rows_file(self, doc, name="rows.json"):
        p = os.path.join(self.tmp, name)
        write(p, json.dumps(doc))
        return p

    def score(self, doc, *extra):
        p = self.rows_file(doc)
        r = run("fit_score.py", p, "--json", *extra, env=self.env)
        return r, (json.loads(r.stdout) if r.stdout.strip().startswith("{") else None)

    def pairs(self, *pairs):
        return {"kind": "posting", "rows": [list(p) for p in pairs]}


class WorkedExamples(FitCase):
    def test_examples_in_fit_md_are_found(self):
        self.assertGreaterEqual(len(examples()), 10)

    def test_every_worked_example_matches(self):
        for ex in examples():
            with self.subTest(ex["name"]):
                r, res = self.score({"kind": "posting", "rows": ex["rows"]})
                want = ex["expect"]
                self.assertIsNotNone(res, r.stderr)
                self.assertEqual(res["score"], want["score"])
                if want["score"] is None:
                    self.assertEqual(r.returncode, 2)
                    self.assertIsNone(res["pct"])
                    self.assertTrue(res["reason"])
                    continue
                self.assertEqual(r.returncode, 0)
                self.assertEqual(round(res["pct"], 2), want["pct"])
                self.assertEqual(res["lean"], want["lean"])
                self.assertEqual(res["counts"]["required"], want["required"])
                self.assertEqual(res["counts"]["preferred"], want["preferred"])

    def test_row_objects_give_the_same_answer_as_pairs(self):
        pairs = self.pairs(("required", "met"), ("required", "partly"), ("preferred", "not"))
        objs = {"kind": "posting", "rows": [{"requirement": "r%d" % i, "tier": t, "status": s, "evidence": "b001"}
                                            for i, (t, s) in enumerate(pairs["rows"])]}
        self.assertEqual(self.score(pairs)[1], self.score(objs)[1])

    def test_text_version_is_a_plain_sentence(self):
        ex = next(e for e in examples() if e["name"] == "B mixed")
        _, res = self.score({"kind": "posting", "rows": ex["rows"]})
        self.assertEqual(res["text"], "Score 4 of 5: good fit, apply. Required 3 of 4 met (1 partly), preferred 1 of 2 met.")
        self.assertEqual(res["legend"], "good fit, apply")

    def test_plain_output_is_short_text(self):
        r = run("fit_score.py", self.rows_file(self.pairs(("required", "met"), ("required", "met"), ("preferred", "met"))), env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Score 5 of 5: strong fit, apply.", r.stdout)
        self.assertFalse(r.stdout.lstrip().startswith("{"))


class NoScore(FitCase):
    def test_recruiter_introduction_never_gets_a_number(self):
        doc = self.pairs(*[("required", "met")] * 6)
        doc["kind"] = "recruiter-intro"
        r, res = self.score(doc)
        self.assertEqual(r.returncode, 2)
        self.assertIsNone(res["score"])
        self.assertIsNone(res["pct"])
        self.assertIn("recruiter", res["reason"].lower())
        self.assertTrue(res["text"].startswith("No score"))

    def test_plain_output_for_no_score_prints_the_reason(self):
        r = run("fit_score.py", self.rows_file(self.pairs(("required", "met"))), env=self.env)
        self.assertEqual(r.returncode, 2)
        self.assertIn("No score", r.stdout)

    def test_min_rows_comes_from_settings(self):
        doc = self.pairs(("required", "met"), ("required", "met"))
        self.assertEqual(self.score(doc)[0].returncode, 2)
        edit_settings(self.data, lambda s: s["fit"].update(min_rows=2))
        r, res = self.score(doc)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(res["score"], 5)


class SettingsDrive(FitCase):
    def test_weights_partial_credit_and_legend_come_from_settings(self):
        doc = self.pairs(("required", "met"), ("required", "met"), ("required", "met"), ("required", "partly"),
                         ("preferred", "met"), ("preferred", "not"))  # example B: 76.25 with the defaults
        edit_settings(self.data, lambda s: s["fit"].update(weights={"required": 50, "preferred": 50}))  # 0.5 x 87.5 + 0.5 x 50 = 68.75
        _, res = self.score(doc)
        self.assertEqual(res["pct"], 68.75)
        self.assertEqual(res["score"], 3)
        self.assertEqual(res["lean"], "your call")

        def tighter(s):
            s["fit"]["partial_credit"] = 0  # required 75, preferred 50 -> 0.5 x 75 + 0.5 x 50 = 62.5
            s["fit"]["legend"]["3"] = 65  # 62.5 is now under the 3 edge
        edit_settings(self.data, tighter)
        _, res = self.score(doc)
        self.assertEqual(res["pct"], 62.5)
        self.assertEqual(res["score"], 2)
        self.assertEqual(res["lean"], "skip")

    def test_apply_lean_from(self):
        edit_settings(self.data, lambda s: s["fit"].update(apply_lean_from=3))
        ex = next(e for e in examples() if e["name"] == "E edge 60")  # score 3
        _, res = self.score({"kind": "posting", "rows": ex["rows"]})
        self.assertEqual(res["lean"], "apply")


class Flags(FitCase):
    def test_at_most_max_flags_then_a_count(self):
        doc = self.pairs(("required", "met"), ("required", "met"), ("required", "met"))
        doc["flags"] = ["one", "two", "three", "four", "five"]
        _, res = self.score(doc)
        self.assertEqual(res["flags"], ["one", "two", "three"])
        self.assertEqual(res["more_flags"], 2)
        r = run("fit_score.py", self.rows_file(doc), env=self.env)
        self.assertIn("(+2 more)", r.stdout)

    def test_max_flags_comes_from_settings(self):
        edit_settings(self.data, lambda s: s["fit"].update(max_flags=1))
        doc = self.pairs(("required", "met"), ("required", "met"), ("required", "met"))
        doc["flags"] = ["one", "two", "three"]
        _, res = self.score(doc)
        self.assertEqual((res["flags"], res["more_flags"]), (["one"], 2))

    def test_few_flags_are_all_shown(self):
        doc = self.pairs(("required", "met"), ("required", "met"), ("required", "met"))
        doc["flags"] = ["one"]
        _, res = self.score(doc)
        self.assertEqual(res["flags"], ["one"])
        self.assertEqual(res["more_flags"], 0)


class BadInput(FitCase):
    def assert_one_line_error(self, r):
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1, r.stderr)

    def test_invalid_tier(self):
        self.assert_one_line_error(self.score(self.pairs(("must", "met"), ("required", "met"), ("required", "met")))[0])

    def test_invalid_status(self):
        self.assert_one_line_error(self.score(self.pairs(("required", "yes"), ("required", "met"), ("required", "met")))[0])

    def test_invalid_row_shape(self):
        self.assert_one_line_error(self.score({"kind": "posting", "rows": ["required"]})[0])

    def test_invalid_kind(self):
        doc = self.pairs(("required", "met"), ("required", "met"), ("required", "met"))
        doc["kind"] = "newsletter"
        self.assert_one_line_error(self.score(doc)[0])

    def test_axis_out_of_range(self):
        doc = self.pairs(("required", "met"), ("required", "met"), ("required", "met"))
        doc["axes"] = {"skills": 1.5}
        self.assert_one_line_error(self.score(doc)[0])

    def test_missing_file(self):
        self.assert_one_line_error(run("fit_score.py", os.path.join(self.tmp, "nope.json"), env=self.env))

    def test_not_json(self):
        p = os.path.join(self.tmp, "bad.json")
        write(p, "{not json")
        self.assert_one_line_error(run("fit_score.py", p, env=self.env))

    def test_help(self):
        r = run("fit_score.py", "--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("fit_score.py", r.stdout)


class Unchanged(FitCase):
    def test_input_unchanged_and_runs_are_identical(self):
        doc = self.pairs(("required", "met"), ("required", "partly"), ("required", "not"), ("preferred", "met"))
        doc["flags"] = ["a", "b"]
        doc["axes"] = {"skills": 0.8, "rate": None}
        p = self.rows_file(doc)
        with open(p, "rb") as f:
            before = f.read()
        a = run("fit_score.py", p, "--json", env=self.env)
        b = run("fit_score.py", p, "--json", env=self.env)
        with open(p, "rb") as f:
            self.assertEqual(f.read(), before)
        self.assertEqual(a.stdout, b.stdout)
        self.assertEqual(a.returncode, b.returncode)
        outs = []
        for _ in range(2):
            run("fit_score.py", p, "--slug", "orbit-platform", "--write", env=self.env)
            got = []
            for n in ("fit.json", "fit.html"):
                with open(os.path.join(self.data, "out", "orbit-platform", n), "rb") as f:
                    got.append(f.read())
            outs.append(got)
        self.assertEqual(outs[0], outs[1])


class WriteFiles(FitCase):
    def doc(self):
        return {"kind": "posting",
                "rows": [{"requirement": "Java <b>8+</b> & Spring", "tier": "required", "status": "met", "evidence": "b001"},
                         {"requirement": "AWS Lambda", "tier": "required", "status": "partly", "evidence": "b002"},
                         {"requirement": "Kafka", "tier": "preferred", "status": "not", "evidence": ""}],
                "axes": {"skills": 0.8, "level": 1, "domain": None, "location": 0.5},
                "flags": ["Needs <script>alert(1)</script> clearance", "Onsite 3 days", "Pay not listed", "Fourth flag"]}

    def write_card(self):
        p = self.rows_file(self.doc())
        r = run("fit_score.py", p, "--slug", "orbit-platform", "--write", env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        job = os.path.join(self.data, "out", "orbit-platform")
        with open(os.path.join(job, "fit.html"), encoding="utf-8") as f:
            return job, f.read()

    def test_writes_fit_json_and_fit_html(self):
        job, html = self.write_card()
        fit = self.jload(job, "fit.json")
        self.assertEqual(fit["kind"], "posting")
        self.assertEqual(len(fit["rows"]), 3)
        self.assertEqual(fit["rows"][0]["status"], "met")
        self.assertEqual(fit["result"]["score"], 2)
        self.assertTrue(html.lstrip().lower().startswith("<!doctype html"))

    def test_score_value_from_hand_calculation(self):
        # required (1 met + 0.5 partly) / 2 = 75; preferred 0 of 1 = 0; 0.7 x 75 + 0.3 x 0 = 52.5, so score 2
        job, _ = self.write_card()
        self.assertEqual(self.jload(job, "fit.json")["result"]["pct"], 52.5)
        self.assertEqual(self.jload(job, "fit.json")["result"]["score"], 2)

    def test_card_is_self_contained(self):
        _, html = self.write_card()
        low = html.lower()
        self.assertNotIn("<script", low)
        self.assertNotIn("<link", low)
        self.assertNotIn("<img", low)
        self.assertNotIn("@import", low)
        self.assertNotIn("http://", low)
        self.assertNotIn("https://", low)
        self.assertNotIn("url(", low)
        self.assertIn("prefers-color-scheme: dark", low)
        self.assertIn('name="viewport"', low)
        self.assertIn("<details", low)

    def test_every_inserted_string_is_escaped(self):
        _, html = self.write_card()
        self.assertNotIn("<script", html.lower())
        self.assertNotIn("<b>8+</b>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; clearance", html)

    def test_card_shows_score_flags_and_axes(self):
        _, html = self.write_card()
        self.assertIn("2 / 5", html)
        self.assertIn("Onsite 3 days", html)
        self.assertIn("Pay not listed", html)
        self.assertNotIn("Fourth flag", html)  # only 3 flags, then a count
        self.assertIn("(+1 more)", html)
        self.assertIn("Skills match", html)
        self.assertIn("80%", html)
        self.assertIn("Level", html)
        self.assertIn("Location or work type", html)
        self.assertNotIn("Domain", html)  # null axis is left out
        self.assertNotIn("Rate", html)  # absent axis is left out
        self.assertIn("Required 1 of 2 met (1 partly)", html)

    def test_no_score_card(self):
        p = self.rows_file({"kind": "recruiter-intro", "rows": []})
        r = run("fit_score.py", p, "--slug", "orbit-platform", "--write", env=self.env)
        self.assertEqual(r.returncode, 2)
        with open(os.path.join(self.data, "out", "orbit-platform", "fit.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertIn("No score", html)
        self.assertNotIn("/ 5", html)

    def test_job_folder_is_not_needed_and_not_written(self):
        r = run("fit_score.py", self.rows_file(self.doc()), "--slug", "brand-new", "--write", env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        for n in ("fit.json", "fit.html"):
            self.assertTrue(os.path.isfile(os.path.join(self.data, "out", "brand-new", n)))
        self.assertFalse(os.path.exists(os.path.join(self.data, "jobs", "brand-new")))
        self.assertFalse(os.path.exists(os.path.join(self.data, "jobs", "orbit-platform", "fit.json")))

    def test_write_needs_a_slug(self):
        r = run("fit_score.py", self.rows_file(self.doc()), "--write", env=self.env)
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("Traceback", r.stderr)

    def test_slug_cannot_leave_the_jobs_folder(self):
        r = run("fit_score.py", self.rows_file(self.doc()), "--slug", "../private", "--write", env=self.env)
        self.assertEqual(r.returncode, 1)

    def test_no_write_without_flag(self):
        r = run("fit_score.py", self.rows_file(self.doc()), "--slug", "orbit-platform", env=self.env)
        self.assertEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.data, "out", "orbit-platform", "fit.json")))


if __name__ == "__main__":
    unittest.main()
