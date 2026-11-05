"""Seam: validate.py. A data folder in (via RESUME_SKILL_DATA), error and warning lines out, exit 0 clean / 1 on any error."""
import json, os, unittest
from helpers import TmpCase, run, write, edit_settings, EXAMPLE


class ValidateTests(TmpCase):
    def setUp(self):
        super().setUp()
        self.d = self.example_copy()

    def edit(self, name, fn):
        path = os.path.join(self.d, name)
        data = self.jload(path)
        fn(data)
        write(path, json.dumps(data, indent=2))

    def validate(self, *args):
        return run("validate.py", *args, env=self.env_for(self.d))

    def fresh(self):
        """A folder hand-built from the setup spec (not by running setup.py), with the older settings.json marker (legacy path)."""
        d = os.path.join(self.tmp, "fresh")
        write(os.path.join(d, "settings.json"), "{}")
        write(os.path.join(d, "bank.json"), '{"roles": [], "bullets": []}')
        write(os.path.join(d, "summaries.json"), '{"summaries": []}')
        write(os.path.join(d, "private", "terms.json"), '{"people": [], "internal_codenames": [], "patterns": [], "stage_words": []}')
        os.makedirs(os.path.join(d, "versions"))
        return d

    def test_example_data_is_clean_and_reports_the_bullet_count(self):
        r = self.validate()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("12 bullets", r.stdout)
        self.assertIn("0 errors, 0 warnings", r.stdout)

    def test_json_output_has_errors_warnings_counts(self):
        r = self.validate("--json")
        out = json.loads(r.stdout)
        self.assertEqual(out, {"errors": [], "warnings": [], "counts": {"bullets": 12, "summaries": 2, "versions": 2, "tailorings": 1}})

    def test_help_prints_docstring_and_exits_0(self):
        r = run("validate.py", "--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("Exit 0 clean", r.stdout)

    def test_no_data_folder_is_a_one_line_error(self):
        r = run("validate.py", env=self.base_env)
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("Traceback", r.stderr)

    def test_bullet_role_must_be_in_the_roles_list(self):
        self.edit("bank.json", lambda b: b["bullets"][0].update(role="elsewhere"))
        r = self.validate()
        self.assertEqual(r.returncode, 1)
        self.assertIn("ERROR bank b001: role 'elsewhere' not in", r.stdout)

    def test_project_role_needs_a_project_name(self):
        self.edit("bank.json", lambda b: b["bullets"][0].update(role="project", project=None))
        r = self.validate()
        self.assertIn("ERROR bank b001: project bullets need a project name", r.stdout)

    def test_missing_tech_is_a_warning_wrong_type_is_an_error(self):
        def drop(b):
            del b["bullets"][0]["tech"]
            b["bullets"][1]["tech"] = "Python"
        self.edit("bank.json", drop)
        r = self.validate()
        self.assertEqual(r.returncode, 1)
        self.assertIn("WARN bank b001: no 'tech' list", r.stdout)
        self.assertIn("ERROR bank b002: 'tech' should be a list of strings", r.stdout)

    def test_missing_tech_alone_still_exits_0(self):
        self.edit("bank.json", lambda b: b["bullets"][0].pop("tech"))
        r = self.validate()
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARN", r.stdout)

    def test_every_version_file_needs_marks_in_the_bank(self):
        write(os.path.join(self.d, "versions", "extra.json"), json.dumps(self.jload(self.d, "versions", "contract.json")))
        r = self.validate()
        self.assertEqual(r.returncode, 1)
        self.assertIn("marks.extra needs", r.stdout)

    def test_version_using_a_bullet_not_marked_for_it(self):
        # b012 is marked in for contract only; put it in full-time
        self.edit("versions/full-time.json", lambda v: v["roles"][0]["bullet_ids"].append("b012"))
        r = self.validate()
        self.assertIn("full-time: b012", r.stdout)
        self.assertIn("not marked for full-time", r.stdout)

    def test_version_with_unknown_bullet(self):
        self.edit("versions/contract.json", lambda v: v["roles"][0]["bullet_ids"].append("b999"))
        self.assertIn("ERROR versions/contract: unknown bullet b999", self.validate().stdout)

    def test_certifications_must_be_a_list(self):
        self.edit("versions/contract.json", lambda v: v.update(certifications="AWS SAA"))
        self.assertIn("'certifications' should be a list", self.validate().stdout)

    def test_private_codename_in_bullet_text_is_an_error(self):
        def leak(b):
            b["bullets"][0]["text"] = "Cut nightly shipment-report runtime from 6 hours to 40 minutes on Project Falcon by rewriting the AWS Glue job."
        self.edit("bank.json", leak)
        r = self.validate()
        self.assertEqual(r.returncode, 1)
        self.assertIn("private term 'Project Falcon' in a public field", r.stdout)

    def test_private_person_name_is_caught_by_first_name_too(self):
        write(os.path.join(self.d, "profile.md"), "# Profile\n\nWorked with Morgan on the migration.\n")
        self.assertIn("profile.md: private term 'Morgan'", self.validate().stdout)

    def test_private_bank_notes_are_not_scanned(self):
        write(os.path.join(self.d, "private", "bank-notes.md"), "Pat Morgan asked for a number.\n")
        self.assertEqual(self.validate().returncode, 0)

    def test_tailoring_slug_must_match_folder(self):
        self.edit("jobs/acme-backend/tailoring.json", lambda t: t.update(slug="other"))
        self.assertIn("ERROR jobs/acme-backend: slug 'other' does not match the folder name", self.validate().stdout)

    def test_tailoring_base_must_be_an_existing_version(self):
        self.edit("jobs/acme-backend/tailoring.json", lambda t: t.update(base="master"))
        self.assertIn("jobs/acme-backend: base 'master' is not a version", self.validate().stdout)

    def test_tailoring_posting_must_be_a_file_in_its_folder(self):
        self.edit("jobs/acme-backend/tailoring.json", lambda t: t.update(posting="gone.md"))
        self.assertIn("posting 'gone.md' is not a file in jobs/acme-backend/", self.validate().stdout)
        self.edit("jobs/acme-backend/tailoring.json", lambda t: t.update(posting=None))
        self.assertEqual(self.validate().returncode, 0)

    def test_tailoring_status_values(self):
        self.edit("jobs/acme-backend/tailoring.json", lambda t: t.update(status="sent"))
        self.assertIn("status 'sent' not in", self.validate().stdout)

    def test_submitted_needs_sent_on_or_bank_commit(self):
        self.edit("jobs/acme-backend/tailoring.json", lambda t: t.update(status="submitted"))
        r = self.validate()
        self.assertEqual(r.returncode, 1)
        self.assertIn("submitted tailorings are frozen", r.stdout)
        self.edit("jobs/acme-backend/tailoring.json", lambda t: t.update(sent_on="2026-03-02"))
        self.assertEqual(self.validate().returncode, 0)
        self.edit("jobs/acme-backend/tailoring.json", lambda t: t.update(sent_on=None, bank_commit="abc1234"))
        self.assertEqual(self.validate().returncode, 0)

    def test_override_flag_must_match_the_text(self):
        def reword(t):
            t["roles"][0]["bullets"][0]["text"] += " Also tidied the runbook."
        self.edit("jobs/acme-backend/tailoring.json", reword)
        self.assertIn("override is False but the text differs from the bank", self.validate().stdout)

    def reword_first_bullet(self, **extra):
        def f(t):
            b = t["roles"][0]["bullets"][0]
            b["text"] += " Also tidied the runbook."
            b["override"] = True
            b.update(extra)
        self.edit("jobs/acme-backend/tailoring.json", f)

    def test_reworded_override_without_a_why_is_an_error(self):
        self.reword_first_bullet()
        out = self.validate()
        self.assertEqual(out.returncode, 1)
        self.assertIn("a reworded override needs a 'why'", out.stdout)

    def test_reworded_override_with_a_why_passes(self):
        self.reword_first_bullet(why="Same job; the runbook sentence was confirmed by the user.")
        out = self.validate()
        self.assertNotIn("needs a 'why'", out.stdout)
        self.assertEqual(out.returncode, 0, out.stdout)

    def test_platform_bracket_alone_needs_no_why(self):
        def f(t):
            for r in t["roles"]:
                for b in r["bullets"]:
                    if b["id"] == "b002":
                        b["text"] = b["text"].replace("Amazon SQS", "Amazon SQS (Azure Service Bus-style)", 1)
                        b["override"] = True
        self.edit("jobs/acme-backend/tailoring.json", f)
        self.assertNotIn("needs a 'why'", self.validate().stdout)

    def test_frozen_tailoring_keeps_sent_text_when_bank_moved_on(self):
        def freeze(t):
            t.update(status="submitted", sent_on="2026-03-02")
            t["roles"][0]["bullets"][0]["text"] += " Also tidied the runbook."
        self.edit("jobs/acme-backend/tailoring.json", freeze)
        self.assertEqual(self.validate().returncode, 0)

    def test_new_default_setting_is_a_warning_with_the_fix(self):
        def drop(s):
            del s["output"]["font"]
        edit_settings(self.d, drop)
        r = self.validate()
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARN settings: new option 'output.font' (run setup.py --add-missing-settings)", r.stdout)

    def test_unknown_setting_is_a_warning(self):
        edit_settings(self.d, lambda s: s["limits"].update(colour="blue"))
        r = self.validate()
        self.assertEqual(r.returncode, 0)
        self.assertIn("WARN settings: unknown option 'limits.colour'", r.stdout)

    def test_fresh_folder_has_warnings_not_errors(self):
        d = self.fresh()
        r = run("validate.py", env=self.env_for(d))
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("WARN versions: none yet", r.stdout)
        self.assertIn("0 bullets", r.stdout)
        self.assertIn("0 errors", r.stdout)

    def test_empty_private_terms_do_not_flag_everything(self):
        d = self.fresh()
        write(os.path.join(d, "profile.md"), "# Profile\n\nAnything at all.\n")
        r = run("validate.py", env=self.env_for(d))
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_broken_json_is_an_error_line_not_a_traceback(self):
        write(os.path.join(self.d, "bank.json"), "{ not json")
        r = self.validate()
        self.assertEqual(r.returncode, 1)
        self.assertIn("ERROR bank.json: cannot read as JSON", r.stdout)
        self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
