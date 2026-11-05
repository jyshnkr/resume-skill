"""save.py: plan -> validate -> confirm -> apply -> verify, with a backup and an undo."""
import datetime, json, os, unittest

from helpers import TmpCase, run, write

TAILORING = os.path.join("jobs", "acme-backend", "tailoring.json")


def snapshot(root, skip=()):
    """Every file under root -> its bytes, so a test can prove nothing changed or everything came back."""
    out = {}
    for d, _, files in os.walk(root):
        for n in files:
            p = os.path.join(d, n)
            rel = os.path.relpath(p, root)
            if rel.split(os.sep)[0] in skip:
                continue
            with open(p, "rb") as f:
                out[rel] = f.read()
    return out


class SaveCase(TmpCase):
    def setUp(self):
        super().setUp()
        self.data = self.example_copy()
        self.env = self.env_for(self.data)

    def plan(self, writes, id="2026-11-04-test", note="Changed the client name.", reason="test change", correction=False, name="plan.json"):
        p = os.path.join(self.tmp, name)
        write(p, json.dumps({"id": id, "reason": reason, "note": note, "writes": writes, "correction": correction}))
        return p

    def save(self, plan, *args):
        return run("save.py", plan, *args, env=self.env)

    def tailoring_with(self, **changes):
        t = self.jload(self.data, TAILORING)
        t.update(changes)
        return t

    def freeze(self, status="submitted"):
        t = self.tailoring_with(status=status, sent_on="2026-10-01")
        write(os.path.join(self.data, TAILORING), json.dumps(t, indent=2) + "\n")

    def read(self, *parts):
        with open(os.path.join(self.data, *parts), "rb") as f:
            return f.read()


class Apply(SaveCase):
    def test_saves_with_backup_note_and_new_file(self):
        before = self.read(TAILORING)
        new = self.tailoring_with(client="Acme Freight Co")
        plan = self.plan([{"path": TAILORING, "content": new},
                          {"path": "jobs/acme-backend/notes.txt", "text": "hello\n"}])
        r = self.save(plan, "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.jload(self.data, TAILORING)["client"], "Acme Freight Co")
        self.assertEqual(self.read("jobs", "acme-backend", "notes.txt"), b"hello\n")
        self.assertEqual(self.read("backups", "2026-11-04-test", TAILORING), before)
        manifest = self.jload(self.data, "backups", "2026-11-04-test", "manifest.json")
        self.assertEqual(manifest["created"], ["jobs/acme-backend/notes.txt"])
        note = self.read("changes", "2026-11-04-test.md").decode()
        self.assertIn(datetime.date.today().isoformat(), note)
        self.assertIn("2026-11-04-test", note)
        self.assertIn("test change", note)
        self.assertIn("Changed the client name.", note)
        self.assertIn(TAILORING, note)
        self.assertIn("jobs/acme-backend/notes.txt", note)

    def test_no_tmp_files_left_behind(self):
        plan = self.plan([{"path": "jobs/acme-backend/notes.txt", "text": "x"}])
        self.save(plan, "--yes")
        left = [n for n in snapshot(self.data) if n.endswith(".tmp")]
        self.assertEqual(left, [])

    def test_delete_is_backed_up(self):
        before = self.read("jobs", "orbit-platform", "posting.md")
        r = self.save(self.plan([{"path": "jobs/orbit-platform/posting.md", "delete": True}]), "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.data, "jobs", "orbit-platform", "posting.md")))
        self.assertEqual(self.read("backups", "2026-11-04-test", "jobs", "orbit-platform", "posting.md"), before)

    def test_json_output(self):
        r = self.save(self.plan([{"path": "jobs/acme-backend/notes.txt", "text": "x"}]), "--yes", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["id"], "2026-11-04-test")
        self.assertEqual(out["status"], "saved")

    def test_existing_id_is_refused(self):
        plan = self.plan([{"path": "jobs/acme-backend/notes.txt", "text": "one"}])
        self.assertEqual(self.save(plan, "--yes").returncode, 0)
        plan2 = self.plan([{"path": "jobs/acme-backend/notes.txt", "text": "two"}], name="plan2.json")
        r = self.save(plan2, "--yes")
        self.assertEqual(r.returncode, 1)
        self.assertIn("already", r.stderr + r.stdout)
        self.assertEqual(self.read("jobs", "acme-backend", "notes.txt"), b"one")

    def test_backup_copy_to(self):
        dest = os.path.join(self.tmp, "mirror")
        s = self.jload(self.data, "settings.json")
        s["output"]["backup_copy_to"] = dest
        write(os.path.join(self.data, "settings.json"), json.dumps(s))
        self.save(self.plan([{"path": TAILORING, "content": self.tailoring_with(client="X")}]), "--yes")
        self.assertTrue(os.path.exists(os.path.join(dest, "2026-11-04-test", TAILORING)))


class Confirm(SaveCase):
    def test_without_yes_it_prints_the_plan_and_changes_nothing(self):
        before = snapshot(self.data)
        r = self.save(self.plan([{"path": TAILORING, "content": self.tailoring_with(client="X")}]))
        self.assertEqual(r.returncode, 2)
        self.assertIn(TAILORING, r.stdout)
        self.assertIn("test change", r.stdout)
        self.assertEqual(snapshot(self.data), before)

    def test_dry_run_changes_nothing_and_exits_0(self):
        before = snapshot(self.data)
        r = self.save(self.plan([{"path": TAILORING, "content": self.tailoring_with(client="X")}]), "--dry-run")
        self.assertEqual(r.returncode, 0)
        self.assertIn(TAILORING, r.stdout)
        self.assertEqual(snapshot(self.data), before)

    def test_dry_run_with_yes_still_changes_nothing(self):
        before = snapshot(self.data)
        r = self.save(self.plan([{"path": TAILORING, "content": self.tailoring_with(client="X")}]), "--dry-run", "--yes")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(snapshot(self.data), before)


class Refusals(SaveCase):
    def refused(self, writes, text=None, **kw):
        before = snapshot(self.data)
        r = self.save(self.plan(writes, **kw), "--yes")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertNotIn("Traceback", r.stderr)
        if text:
            self.assertIn(text, r.stderr + r.stdout)
        self.assertEqual(snapshot(self.data), before)

    def test_parent_escape(self):
        self.refused([{"path": "../x", "text": "no"}], "inside")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "x")))

    def test_escape_in_the_middle(self):
        self.refused([{"path": "jobs/../../x", "text": "no"}])

    def test_absolute_path(self):
        self.refused([{"path": os.path.join(self.tmp, "abs.txt"), "text": "no"}], "relative")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "abs.txt")))

    def test_backups_folder(self):
        self.refused([{"path": "backups/old/x.txt", "text": "no"}], "backups")

    def test_symlink_out_of_the_data_folder(self):
        outside = os.path.join(self.tmp, "outside")
        os.makedirs(outside)
        os.symlink(outside, os.path.join(self.data, "jobs", "link"))
        self.refused([{"path": "jobs/link/x.txt", "text": "no"}], "inside")
        self.assertEqual(os.listdir(outside), [])

    def test_same_path_twice(self):
        self.refused([{"path": "a.txt", "text": "1"}, {"path": "a.txt", "text": "2"}])

    def test_write_needs_exactly_one_of_content_text_delete(self):
        self.refused([{"path": "a.txt"}])
        self.refused([{"path": "a.txt", "text": "1", "content": {}}])

    def test_delete_of_a_missing_file(self):
        self.refused([{"path": "jobs/acme-backend/none.txt", "delete": True}], "does not exist")

    def test_bad_id(self):
        self.refused([{"path": "a.txt", "text": "1"}], id="../evil")

    def test_missing_plan_file_and_bad_json(self):
        r = self.save(os.path.join(self.tmp, "nope.json"), "--yes")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1)
        write(os.path.join(self.tmp, "bad.json"), "{no")
        r = self.save(os.path.join(self.tmp, "bad.json"), "--yes")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1)

    def test_help(self):
        r = run("save.py", "--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("save.py", r.stdout)


class Frozen(SaveCase):
    def plan_touching_tailoring(self, **kw):
        return self.plan([{"path": TAILORING, "content": self.tailoring_with(client="Acme Freight Co")}], **kw)

    def test_sent_resume_is_refused(self):
        self.freeze("submitted")
        before = snapshot(self.data)
        r = self.save(self.plan_touching_tailoring(), "--yes")
        self.assertEqual(r.returncode, 1)
        self.assertIn("correction", r.stderr.lower())
        self.assertIn("submitted", r.stderr)
        self.assertEqual(snapshot(self.data), before)

    def test_archived_resume_is_refused(self):
        self.freeze("archived")
        self.assertEqual(self.save(self.plan_touching_tailoring(), "--yes").returncode, 1)

    def test_correction_flag_alone_is_not_enough(self):
        self.freeze()
        r = self.save(self.plan_touching_tailoring(correction=True, note="Fixed the client name."), "--yes")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Correction", r.stderr)

    def test_note_starting_with_correction_alone_is_not_enough(self):
        self.freeze()
        r = self.save(self.plan_touching_tailoring(note="Correction: fixed the client name."), "--yes")
        self.assertEqual(r.returncode, 1)

    def test_correction_path_works(self):
        self.freeze()
        r = self.save(self.plan_touching_tailoring(correction=True, note="Correction: fixed the client name."), "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.jload(self.data, TAILORING)["client"], "Acme Freight Co")
        self.assertIn("Correction: fixed", self.read("changes", "2026-11-04-test.md").decode())

    def test_deleting_a_sent_tailoring_is_also_frozen(self):
        self.freeze()
        r = self.save(self.plan([{"path": TAILORING, "delete": True}]), "--yes")
        self.assertEqual(r.returncode, 1)

    def test_other_files_of_a_sent_job_are_not_frozen(self):
        self.freeze()
        r = self.save(self.plan([{"path": "jobs/acme-backend/notes.txt", "text": "follow up on Friday"}]), "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_draft_is_free_to_change(self):
        self.assertEqual(self.save(self.plan_touching_tailoring(), "--yes").returncode, 0)


class ValidateFirst(SaveCase):
    def test_a_bad_tailoring_leaves_the_folder_untouched(self):
        before = snapshot(self.data)
        bad = self.tailoring_with(status="bogus")
        del bad["roles"]
        r = self.save(self.plan([{"path": TAILORING, "content": bad}]), "--yes")
        self.assertEqual(r.returncode, 1)
        self.assertIn("ERROR", r.stdout + r.stderr)
        self.assertEqual(snapshot(self.data), before)

    def test_a_good_plan_passes_validate(self):
        r = self.save(self.plan([{"path": TAILORING, "content": self.tailoring_with(client="Acme Freight Co")}]), "--yes")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class Undo(SaveCase):
    def test_undo_restores_bytes_and_removes_created_files(self):
        before = snapshot(self.data)
        plan = self.plan([{"path": TAILORING, "content": self.tailoring_with(client="Acme Freight Co")},
                          {"path": "jobs/orbit-platform/posting.md", "delete": True},
                          {"path": "jobs/acme-backend/extra/notes.txt", "text": "new"}])
        self.assertEqual(self.save(plan, "--yes").returncode, 0)
        r = run("save.py", "--undo", "--yes", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(snapshot(self.data, skip=("changes", "backups")), {k: v for k, v in before.items() if k.split(os.sep)[0] not in ("changes", "backups")})
        self.assertFalse(os.path.exists(os.path.join(self.data, "jobs", "acme-backend", "extra")))
        undo_note = self.read("changes", "2026-11-04-test-undo.md").decode()
        self.assertIn(datetime.date.today().isoformat(), undo_note)
        self.assertIn(TAILORING, undo_note)

    def test_undo_without_yes_works_when_nothing_changed_since(self):
        self.save(self.plan([{"path": TAILORING, "content": self.tailoring_with(client="X")}]), "--yes")
        r = run("save.py", "--undo", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_undo_refuses_when_files_changed_since_the_save(self):
        self.save(self.plan([{"path": TAILORING, "content": self.tailoring_with(client="X")}]), "--yes")
        write(os.path.join(self.data, TAILORING), "edited by hand\n")
        r = run("save.py", "--undo", env=self.env)
        self.assertEqual(r.returncode, 1)
        self.assertIn(TAILORING, r.stderr + r.stdout)
        self.assertEqual(self.read(TAILORING), b"edited by hand\n")
        r = run("save.py", "--undo", "--yes", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotEqual(self.read(TAILORING), b"edited by hand\n")

    def test_undo_by_id_and_newest_first(self):
        self.save(self.plan([{"path": "a.txt", "text": "a"}], id="2026-11-04-a", name="a.json"), "--yes")
        self.save(self.plan([{"path": "b.txt", "text": "b"}], id="2026-11-04-b", name="b.json"), "--yes")
        self.assertEqual(run("save.py", "--undo", env=self.env).returncode, 0)  # newest: b
        self.assertFalse(os.path.exists(os.path.join(self.data, "b.txt")))
        self.assertTrue(os.path.exists(os.path.join(self.data, "a.txt")))
        self.assertEqual(run("save.py", "--undo", "2026-11-04-a", env=self.env).returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.data, "a.txt")))

    def test_undo_twice_is_refused(self):
        self.save(self.plan([{"path": "a.txt", "text": "a"}]), "--yes")
        self.assertEqual(run("save.py", "--undo", env=self.env).returncode, 0)
        r = run("save.py", "--undo", "2026-11-04-test", env=self.env)
        self.assertEqual(r.returncode, 1)
        self.assertIn("undone", r.stderr)

    def test_undo_with_nothing_to_undo(self):
        r = run("save.py", "--undo", env=self.env)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1)

    def test_undo_unknown_id(self):
        r = run("save.py", "--undo", "nope", env=self.env)
        self.assertEqual(r.returncode, 1)


if __name__ == "__main__":
    unittest.main()
