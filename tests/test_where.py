"""Seam 1: where.py. Args and environment in, a printed path and its source out, exit code 0 / 1 / 2."""
import json, os, unittest
from helpers import TmpCase, run, write


class WhereTests(TmpCase):
    def ready(self, name="d"):
        p = os.path.join(self.tmp, name)
        os.makedirs(p)
        write(os.path.join(p, "settings.json"), "{}")
        return p

    def test_env_variable_wins_and_is_reported(self):
        p = self.ready()
        r = run("where.py", env={**self.base_env, "RESUME_SKILL_DATA": p})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines()[0], p)
        self.assertIn("source: env", r.stdout)

    def test_env_variable_pointing_nowhere_is_an_error_not_a_new_folder(self):
        p = os.path.join(self.tmp, "typo")
        r = run("where.py", env={**self.base_env, "RESUME_SKILL_DATA": p})
        self.assertEqual(r.returncode, 1)
        self.assertIn("RESUME_SKILL_DATA", r.stderr)
        self.assertFalse(os.path.exists(p), "where.py must never create a folder")

    def test_folder_without_settings_is_not_a_data_folder(self):
        p = os.path.join(self.tmp, "plain")
        os.makedirs(p)
        r = run("where.py", env={**self.base_env, "RESUME_SKILL_DATA": p})
        self.assertEqual(r.returncode, 1)
        self.assertIn("not a resume-skill data folder", r.stderr)

    def test_nothing_set_up_exits_2_and_says_run_setup(self):
        r = run("where.py", env=self.base_env)
        self.assertEqual(r.returncode, 2)
        self.assertIn("setup.py", r.stderr)
        self.assertFalse(os.path.exists(self.config))

    def test_saved_location_file_is_used(self):
        p = self.ready()
        os.makedirs(self.config)
        write(os.path.join(self.config, "location"), p + "\n")
        r = run("where.py", env=self.base_env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines()[0], p)
        self.assertIn("source: saved", r.stdout)

    def test_saved_location_that_vanished_is_an_error(self):
        os.makedirs(self.config)
        write(os.path.join(self.config, "location"), os.path.join(self.tmp, "gone") + "\n")
        r = run("where.py", env=self.base_env)
        self.assertEqual(r.returncode, 1)
        self.assertIn("location", r.stderr)

    def test_default_folder_is_used_when_it_exists(self):
        d = os.path.join(self.config, "data")
        os.makedirs(d)
        write(os.path.join(d, "settings.json"), "{}")
        r = run("where.py", env=self.base_env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines()[0], d)
        self.assertIn("source: default", r.stdout)

    def test_env_beats_saved_and_json_shows_both(self):
        env_dir, saved_dir = self.ready("e"), self.ready("s")
        os.makedirs(self.config)
        write(os.path.join(self.config, "location"), saved_dir)
        r = run("where.py", "--json", env={**self.base_env, "RESUME_SKILL_DATA": env_dir})
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual((out["path"], out["source"], out["saved"]), (env_dir, "env", saved_dir))

    def test_tilde_is_expanded(self):
        r = run("where.py", env={**self.base_env, "RESUME_SKILL_DATA": "~/definitely-not-here-xyz"})
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("~", r.stderr.split("RESUME_SKILL_DATA", 1)[1].split("\n")[0])

    def test_help_exits_0(self):
        r = run("where.py", "--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("RESUME_SKILL_DATA", r.stdout)


if __name__ == "__main__":
    unittest.main()
