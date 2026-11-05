"""Candidate bank rows: a row with "status": "candidate" lives in the bank and is checked, but is never an approved bullet.
Seams: validate.py and preflight.py (command line and out/preflight.json)."""
import json, os, unittest
from helpers import TmpCase, run, write

GOOD = ("Trimmed weekly carrier-invoice reconciliation from 3 days to 4 hours by loading the files "
        "into Amazon Athena and flagging mismatches with a scheduled SQL report.")
BAD = "Responsible for a lot of various things across many teams and systems."  # no metric, weak opener, too short


def candidate(cid="b013", text=GOOD, **extra):
    row = {"id": cid, "role": "harbor", "project": None, "lead": text.split(" ", 1)[0], "text": text,
           "marks": {"full-time": {"raw": None, "in": False}, "contract": {"raw": None, "in": False}},
           "held_back": False, "needs_metric": False, "allowed_repeats": [], "note": "", "private_note": "",
           "tech": ["Amazon Athena"], "status": "candidate"}
    row.update(extra)
    return row


class CandidateCase(TmpCase):
    def setUp(self):
        super().setUp()
        self.data = self.example_copy()
        self.bank_path = os.path.join(self.data, "bank.json")

    def edit_bank(self, fn):
        bank = self.jload(self.bank_path)
        fn(bank)
        write(self.bank_path, json.dumps(bank, indent=2))

    def add(self, **kw):
        row = candidate(**kw)
        self.edit_bank(lambda b: b["bullets"].append(row))
        return row

    def validate(self, *args):
        return run("validate.py", *args, env=self.env_for(self.data))

    def pre(self, *args):
        return run("preflight.py", *args, env=self.env_for(self.data))


class ValidateCandidateTests(CandidateCase):
    def test_clean_candidate_validates(self):
        self.add()
        r = self.validate()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("13 bullets", r.stdout)

    def test_invalid_status_is_an_error_naming_the_row(self):
        self.add(status="maybe")
        r = self.validate()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("bank b013: status 'maybe' should be approved or candidate", r.stdout)

    def test_explicit_approved_status_is_fine(self):
        self.edit_bank(lambda b: b["bullets"][0].__setitem__("status", "approved"))
        r = self.validate()
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_candidate_marked_in_a_version_is_an_error(self):
        row = self.add()
        self.edit_bank(lambda b: b["bullets"][-1]["marks"]["contract"].__setitem__("in", True))
        r = self.validate()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn(f"bank {row['id']}: candidate bullet is marked in version 'contract'", r.stdout)

    def test_candidate_placed_in_a_version_is_an_error(self):
        self.add()
        p = os.path.join(self.data, "versions", "contract.json")
        v = self.jload(p)
        v["roles"][0]["bullet_ids"].append("b013")
        write(p, json.dumps(v, indent=2))
        r = self.validate()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("bank b013: candidate bullet is used in version 'contract'", r.stdout)

    def test_candidate_used_in_a_tailoring_is_an_error(self):
        self.add()
        p = os.path.join(self.data, "jobs", "acme-backend", "tailoring.json")
        t = self.jload(p)
        t["roles"][0]["bullets"].append({"id": "b013", "text": GOOD, "override": False})
        write(p, json.dumps(t, indent=2))
        r = self.validate()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("bank b013: candidate bullet is used in tailoring 'acme-backend'", r.stdout)

    def test_candidate_without_tech_is_not_warned_but_approved_row_is(self):
        self.add()
        self.edit_bank(lambda b: (b["bullets"][-1].pop("tech"), b["bullets"][0].pop("tech")))
        r = self.validate()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("bank b001: no 'tech' list", r.stdout)
        self.assertNotIn("b013", r.stdout)

    def test_other_row_checks_still_apply_to_candidates(self):
        self.add(role="nowhere", lead="Wrong")
        r = self.validate()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("bank b013: role 'nowhere' not in", r.stdout)
        self.assertIn("bank b013: lead 'Wrong' is not the first word of the text", r.stdout)

    def test_private_term_in_candidate_text_is_an_error(self):
        with open(os.path.join(self.data, "private", "terms.json"), encoding="utf-8") as f:
            people = json.load(f)["people"]
        self.assertTrue(people)
        self.add(text="Trimmed invoice work with %s from 3 days to 4 hours." % people[0])
        r = self.validate()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("bank b013.text: private term", r.stdout)


class PreflightCandidateTests(CandidateCase):
    def setUp(self):
        super().setUp()
        self.out = os.path.join(self.data, "out", "preflight.json")

    def test_no_candidates_output_is_unchanged(self):
        r = self.pre()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout, "0 of 12 bullets need attention\n")
        res = self.jload(self.out)
        self.assertEqual(sorted(res), ["bullets", "fingerprint", "hold_back", "ran_at", "summary"])
        j = json.loads(self.pre("--json").stdout)
        self.assertNotIn("candidates", j)
        self.assertNotIn("candidates_summary", j)

    def test_clean_candidate_is_reported_separately_and_approved_summary_stays(self):
        self.add()
        r = self.pre()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.splitlines(), ["0 of 12 bullets need attention",
                                                 "1 candidates checked: 1 clean, 0 with warnings, 0 failing"])
        res = self.jload(self.out)
        self.assertEqual(sorted(res["bullets"]), ["b%03d" % i for i in range(1, 13)])
        self.assertEqual(res["summary"], "0 of 12 bullets need attention")
        self.assertEqual(sorted(res["candidates"]), ["b013"])
        self.assertEqual(sorted(res["candidates"]["b013"]), ["findings", "status"])
        self.assertEqual(res["candidates"]["b013"]["status"], "OK")
        self.assertEqual(res["candidates_summary"], "1 candidates checked: 1 clean, 0 with warnings, 0 failing")

    def test_failing_candidate_is_not_held_back_and_does_not_change_the_exit_code(self):
        self.add(text=BAD)
        r = self.pre()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        res = self.jload(self.out)
        self.assertEqual(res["candidates"]["b013"]["status"], "FAIL")
        self.assertTrue(res["candidates"]["b013"]["findings"])
        self.assertEqual(res["hold_back"], [])
        self.assertEqual(res["summary"], "0 of 12 bullets need attention")
        self.assertEqual(res["candidates_summary"], "1 candidates checked: 0 clean, 0 with warnings, 1 failing")
        self.assertEqual(r.stdout.splitlines()[-1], res["candidates_summary"])
        self.assertNotIn("b013", r.stdout.splitlines()[0])

    def test_warning_candidate_counts_as_warning_and_exit_code_stays_zero(self):
        self.add(text=GOOD.replace("from 3 days", "from three days"))
        r = self.pre()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        res = self.jload(self.out)
        self.assertEqual(res["candidates"]["b013"]["status"], "WARN")
        self.assertEqual(res["candidates_summary"], "1 candidates checked: 0 clean, 1 with warnings, 0 failing")
        self.assertEqual(res["hold_back"], [])

    def test_approved_failure_still_decides_exit_and_hold_back_with_candidates_present(self):
        self.add()
        self.edit_bank(lambda b: b["bullets"][0].__setitem__("text", "Cut it."))
        self.edit_bank(lambda b: b["bullets"][0].__setitem__("lead", "Cut"))
        r = self.pre()
        self.assertEqual(r.returncode, 1, r.stdout)
        res = self.jload(self.out)
        self.assertEqual(res["hold_back"], ["b001"])
        self.assertNotIn("b013", res["hold_back"])
        self.assertEqual(res["summary"], "1 of 12 bullets need attention")

    def test_quiet_hides_the_candidates_line(self):
        self.add()
        r = self.pre("--quiet")
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertIn("candidates_summary", self.jload(self.out))

    def test_json_includes_both_parts(self):
        self.add()
        j = json.loads(self.pre("--json").stdout)
        self.assertEqual(sorted(j), ["bullets", "candidates", "candidates_summary", "fingerprint", "hold_back", "ran_at", "summary"])
        self.assertEqual(sorted(j["candidates"]), ["b013"])
        self.assertEqual(j["summary"], "0 of 12 bullets need attention")

    def test_candidate_lead_does_not_count_as_used_by_approved_bullets(self):
        # b013 leads with 'Cut' like b001; the approved summary must not change and b001 stays clean
        self.add(text="Cut weekly carrier-invoice reconciliation from 3 days to 4 hours by loading the files into Amazon Athena.")
        res = json.loads(self.pre("--json").stdout)
        self.assertEqual(res["bullets"]["b001"]["status"], "OK")
        self.assertEqual(res["summary"], "0 of 12 bullets need attention")

    def test_editing_a_candidate_makes_the_stored_result_stale(self):
        self.add()
        self.pre()
        self.edit_bank(lambda b: b["bullets"][-1].__setitem__("text", BAD))
        self.pre("--if-stale", "--quiet")
        self.assertEqual(self.jload(self.out)["candidates"]["b013"]["status"], "FAIL")


class CheckAllIgnoresCandidates(CandidateCase):
    """check.py --all is about the approved bank: a failing draft must not change its output or its exit code."""

    def chk(self, *args):
        return run("check.py", "--all", *args, env=self.env_for(self.data))

    def test_text_output_and_exit_code_are_unchanged_by_candidates(self):
        before = self.chk()
        self.add(text=BAD)
        after = self.chk()
        self.assertEqual((after.returncode, after.stdout), (before.returncode, before.stdout))
        self.assertNotIn("b013", after.stdout)

    def test_json_output_is_unchanged_by_candidates(self):
        before = self.chk("--json")
        self.add(text=BAD)
        after = self.chk("--json")
        self.assertEqual(after.stdout, before.stdout)
        self.assertNotIn("b013", after.stdout)


if __name__ == "__main__":
    unittest.main()
