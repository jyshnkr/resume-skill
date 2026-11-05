"""Seam 10/11 bridge: the commands in SKILL.md, in order, on a copy of the made-up sample data (no agent involved)."""
import json, os, unittest
from helpers import TmpCase, run, write, SCRIPTS


class SmokeRunTests(TmpCase):
    def test_a_whole_run_from_posting_to_saved_change_and_undo(self):
        data = self.example_copy()
        env = self.env_for(data)
        r = run("where.py", env=env)
        self.assertEqual((r.returncode, r.stdout.splitlines()[0]), (0, data))
        r = run("validate.py", env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run("preflight.py", "--if-stale", env=env)
        self.assertIn(r.returncode, (0, 2), r.stdout + r.stderr)  # 0 clean, 2 warnings only
        self.assertTrue(os.path.isfile(os.path.join(data, "out", "preflight.json")))
        again = run("preflight.py", "--if-stale", env=env)
        self.assertEqual(again.stdout.strip(), "", "second run with nothing changed is silent")
        bank = self.jload(data, "bank.json")["bullets"]
        b = next(x for x in bank if x["id"] == "b001")
        r = run("check.py", "--leads", "Reduced Ended Shipped Led", b["text"], env=env)
        self.assertEqual(r.returncode, 0, r.stdout)
        rows = {"kind": "posting", "rows": [
            {"requirement": "Java 11+", "tier": "required", "status": "met", "evidence": "b005"},
            {"requirement": "AWS Lambda and Amazon SQS", "tier": "required", "status": "partly", "evidence": "b002"},
            {"requirement": "Relational database tuning", "tier": "required", "status": "met", "evidence": "b011"},
            {"requirement": "Terraform", "tier": "preferred", "status": "met", "evidence": "b003"},
            {"requirement": "Kafka", "tier": "preferred", "status": "not", "evidence": ""}],
            "flags": ["Kafka is preferred and not claimed"]}
        rows_path = os.path.join(self.tmp, "rows.json")
        write(rows_path, json.dumps(rows))
        r = run("fit_score.py", rows_path, "--slug", "acme-backend", "--write", "--json", env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        res = json.loads(r.stdout)
        # hand-worked: required (2 met + 0.5 x 1 partly) / 3 = 83.33; preferred 1 met of 2 = 50; 0.7 x 83.33 + 0.3 x 50 = 73.33 -> score 3
        self.assertEqual((res["score"], res["pct"]), (3, 73.33))
        self.assertTrue(os.path.isfile(os.path.join(data, "out", "acme-backend", "fit.json")))
        self.assertTrue(os.path.isfile(os.path.join(data, "out", "acme-backend", "fit.html")))
        draft = self.jload(data, "jobs", "acme-backend", "tailoring.json")
        draft["slug"] = "orbit-draft"
        write(os.path.join(data, "out", "orbit-draft", "tailoring.json"), json.dumps(draft))
        r = run("export.py", "file:" + os.path.join(data, "out", "orbit-draft", "tailoring.json"), os.path.join(data, "out", "orbit-draft"), "--label", "orbit-draft", env=env)
        self.assertIn(r.returncode, (0, 2), r.stdout + r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(data, "out", "orbit-draft", "Jordan_Ellis_orbit-draft.docx")), os.listdir(os.path.join(data, "out", "orbit-draft")))
        outdir = os.path.join(self.tmp, "resumes")
        r = run("export.py", "tailoring:acme-backend", outdir, env=env)
        self.assertIn(r.returncode, (0, 2), r.stdout + r.stderr)  # 2 = pages not checked (no LibreOffice)
        self.assertTrue(any(f.endswith(".docx") for f in os.listdir(outdir)))
        # save the fit files into the job folder
        fit_json = self.jload(data, "out", "acme-backend", "fit.json")
        plan = {"id": "smoke-1", "reason": "keep the fit result", "note": "Saved the fit result for acme-backend.",
                "writes": [{"path": "jobs/acme-backend/fit.json", "content": fit_json}]}
        plan_path = os.path.join(self.tmp, "plan.json")
        write(plan_path, json.dumps(plan))
        before = os.listdir(os.path.join(data, "jobs", "acme-backend"))
        r = run("save.py", plan_path, "--dry-run", env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(os.listdir(os.path.join(data, "jobs", "acme-backend")), before)
        r = run("save.py", plan_path, "--yes", env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(data, "jobs", "acme-backend", "fit.json")))
        self.assertTrue(os.path.isdir(os.path.join(data, "backups", "smoke-1")))
        r = run("save.py", "--undo", "smoke-1", "--yes", env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(os.path.join(data, "jobs", "acme-backend", "fit.json")))


if __name__ == "__main__":
    unittest.main()
