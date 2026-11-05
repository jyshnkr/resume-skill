"""File-level guard for sent resumes: a submitted or archived tailoring is read-only on disk, so an agent that never loaded the
skill (and so never met save.py's frozen rule) cannot edit it by hand. Also the CLAUDE.md / AGENTS.md note in the data folder."""
import json, os, shutil, stat, subprocess, sys, unittest
from helpers import TmpCase, run, write, ROOT, EXAMPLE

TOOLS = os.path.join(ROOT, "tools")
TAIL = os.path.join("jobs", "acme-backend", "tailoring.json")


def writable(path):
    return bool(os.stat(path).st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


class LockTests(TmpCase):
    def setUp(self):
        super().setUp()
        self.d = self.example_copy()
        self.env = self.env_for(self.d)
        self.path = os.path.join(self.d, TAIL)

    def mark_sent(self):
        t = self.jload(self.path)
        t.update({"status": "submitted", "sent_on": "2000-01-01"})
        write(self.path, json.dumps(t, indent=2))

    def test_validate_warns_about_a_writable_sent_tailoring(self):
        self.mark_sent()
        r = run("validate.py", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("sent tailoring is writable", r.stdout)
        self.assertIn("save.py --lock", r.stdout)

    def test_a_draft_is_never_flagged(self):
        r = run("validate.py", env=self.env)
        self.assertNotIn("writable", r.stdout)
        self.assertTrue(writable(self.path))

    def test_lock_makes_sent_tailorings_read_only_and_is_idempotent(self):
        self.mark_sent()
        r = run("save.py", "--lock", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(TAIL.replace(os.sep, "/"), r.stdout)
        self.assertFalse(writable(self.path))
        again = run("save.py", "--lock", env=self.env)
        self.assertEqual(again.returncode, 0)
        self.assertIn("nothing to lock", again.stdout)
        self.assertNotIn("writable", run("validate.py", env=self.env).stdout)

    def test_lock_leaves_drafts_alone(self):
        r = run("save.py", "--lock", env=self.env)
        self.assertEqual(r.returncode, 0)
        self.assertIn("nothing to lock", r.stdout)
        self.assertTrue(writable(self.path))

    def test_a_hand_edit_of_a_locked_file_fails(self):
        self.mark_sent()
        run("save.py", "--lock", env=self.env)
        with self.assertRaises(PermissionError):
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(" ")

    def test_marking_a_draft_as_sent_through_save_locks_it(self):
        t = self.jload(self.path)
        t.update({"status": "submitted", "sent_on": "2000-01-01"})
        plan = {"id": "mark-sent", "reason": "sent it", "note": "Marked acme-backend as sent.", "writes": [{"path": TAIL.replace(os.sep, "/"), "content": t}]}
        write(os.path.join(self.tmp, "plan.json"), json.dumps(plan))
        r = run("save.py", os.path.join(self.tmp, "plan.json"), "--yes", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(writable(self.path))

    def test_a_correction_still_works_on_a_locked_file_and_re_locks_it(self):
        self.mark_sent()
        run("save.py", "--lock", env=self.env)
        t = self.jload(self.path)
        t["client"] = "Acme Freight Co"
        plan = {"id": "fix-1", "reason": "wrong client name", "note": "Correction: client name was wrong.", "correction": True,
                "writes": [{"path": TAIL.replace(os.sep, "/"), "content": t}]}
        write(os.path.join(self.tmp, "plan.json"), json.dumps(plan))
        r = run("save.py", os.path.join(self.tmp, "plan.json"), "--yes", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.jload(self.path)["client"], "Acme Freight Co")
        self.assertFalse(writable(self.path))

    def test_a_locked_tailoring_still_reads_and_exports(self):
        self.mark_sent()
        run("save.py", "--lock", env=self.env)
        r = run("export.py", "tailoring:acme-backend", os.path.join(self.tmp, "out"), "--no-contact", env=self.env)
        self.assertIn(r.returncode, (0, 2), r.stdout + r.stderr)
        self.assertEqual(run("validate.py", env=self.env).returncode, 0)

    def test_lock_with_no_data_folder_is_a_clear_error(self):
        r = run("save.py", "--lock", env=self.base_env)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no data folder", r.stderr)


class GuardNoteTests(TmpCase):
    def test_setup_writes_a_claude_and_agents_note_into_a_new_data_folder(self):
        d = os.path.join(self.tmp, "fresh")
        r = run("setup.py", "--data", d, "--yes", env=self.base_env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for name in ("CLAUDE.md", "AGENTS.md"):
            text = open(os.path.join(d, name), encoding="utf-8").read()
            self.assertIn("resume-skill", text)
            self.assertIn("Never edit", text)
            self.assertIn("sent", text)

    def test_the_example_data_carries_the_same_note(self):
        for name in ("CLAUDE.md", "AGENTS.md"):
            with open(os.path.join(EXAMPLE, name), encoding="utf-8") as f:
                self.assertIn("Never edit", f.read())

    def test_validate_ignores_the_note_files(self):
        r = run("validate.py", env=self.env_for(EXAMPLE))
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn("CLAUDE.md", r.stdout)

    def test_import_old_locks_the_sent_tailorings(self):
        new = os.path.join(self.tmp, "imported")
        old = os.path.join(ROOT, "tests", "fixtures", "old-repo")
        r = subprocess.run([sys.executable, "-B", os.path.join(TOOLS, "import_old.py"), "--old", old, "--data", new],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL, env={**os.environ, **self.base_env})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        sent = []
        for slug in os.listdir(os.path.join(new, "jobs")):
            p = os.path.join(new, "jobs", slug, "tailoring.json")
            if os.path.exists(p):
                t = json.load(open(p, encoding="utf-8"))
                if t["status"] in ("submitted", "archived"):
                    sent.append(p)
                    self.assertFalse(writable(p), p)
        self.assertTrue(sent, "the fixture has a submitted tailoring")


if __name__ == "__main__":
    unittest.main()
