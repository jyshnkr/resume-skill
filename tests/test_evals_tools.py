"""evals/grade.py and tools/run_evals.py: the parts that run without spending agent usage."""
import json, os, subprocess, sys, unittest
from helpers import ROOT, TmpCase, write

GRADE = os.path.join(ROOT, "evals", "grade.py")
RUNNER = os.path.join(ROOT, "tools", "run_evals.py")


def sh(*cmd):
    return subprocess.run([sys.executable, "-B", *cmd], capture_output=True, text=True, stdin=subprocess.DEVNULL)


class GradeTests(TmpCase):
    def case_run(self, case_id, output, make_data=True):
        out = os.path.join(self.tmp, "out.txt")
        write(out, output)
        data = self.example_copy() if make_data else os.path.join(self.tmp, "none")
        return out, data

    def test_passing_output_for_the_incomplete_input_case(self):
        out, data = self.case_run("e10", "I need the job posting first. Paste the job description and I will check the fit.")
        r = sh(GRADE, "--case", "e10", "--output", out, "--data", data)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_failing_output_is_reported_check_by_check(self):
        out, data = self.case_run("e10", "Sure, you fit great!")
        r = sh(GRADE, "--case", "e10", "--output", out, "--data", data)
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL matches", r.stdout)

    def test_data_unchanged_detects_a_changed_data_folder(self):
        sys.path.insert(0, os.path.join(ROOT, "evals"))
        import grade
        out, data = self.case_run("e12", "That is a private internal name, so it cannot go on the resume. New bullet writing is out of scope.")
        before = grade.tree_hash(data)
        ok = sh(GRADE, "--case", "e12", "--output", out, "--data", data, "--before", before)
        self.assertEqual(ok.returncode, 0, ok.stdout)
        write(os.path.join(data, "bank-extra.txt"), "changed")
        bad = sh(GRADE, "--case", "e12", "--output", out, "--data", data, "--before", before)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("FAIL data folder unchanged", bad.stdout)

    def test_tree_hash_ignores_out_but_sees_everything_else(self):
        sys.path.insert(0, os.path.join(ROOT, "evals"))
        import grade
        d = self.example_copy()
        base = grade.tree_hash(d)
        write(os.path.join(d, "out", "x", "new.docx"), "derived")
        self.assertEqual(grade.tree_hash(d), base, "out/ is derived output")
        write(os.path.join(d, "jobs", "new", "posting.md"), "saved data")
        self.assertNotEqual(grade.tree_hash(d), base)

    def test_folder_not_created_case(self):
        out, data = self.case_run("e13", "There is no data folder yet. Where should the data live? Run setup after you choose.", make_data=False)
        self.assertEqual(sh(GRADE, "--case", "e13", "--output", out, "--data", data).returncode, 0)
        os.makedirs(data)
        self.assertEqual(sh(GRADE, "--case", "e13", "--output", out, "--data", data).returncode, 1)

    def test_unknown_case_is_a_clear_error(self):
        out, data = self.case_run("x", "x")
        r = sh(GRADE, "--case", "nope", "--output", out, "--data", data)
        self.assertEqual(r.returncode, 1)
        self.assertIn("no case", r.stderr)


class RunnerCommandTests(unittest.TestCase):
    """The claude command line the runner builds, tested without running claude."""

    def setUp(self):
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import run_evals
        self.build = run_evals.build_cmd

    def test_default_run_uses_the_installed_skill_and_nothing_extra(self):
        cmd = self.build("hi", None, "with-skill", 25)
        self.assertNotIn("--plugin-dir", cmd)
        self.assertNotIn("--disable-slash-commands", cmd)
        self.assertEqual(cmd[:3], ["claude", "-p", "hi"])

    def test_baseline_turns_every_skill_off_even_when_the_skill_is_linked(self):
        cmd = self.build("hi", "haiku", "baseline", 25)
        self.assertIn("--disable-slash-commands", cmd)
        self.assertNotIn("--plugin-dir", cmd)
        self.assertEqual(cmd[cmd.index("--model") + 1], "haiku")

    def test_blocked_skills_are_switched_off_in_the_session_settings(self):
        cmd = self.build("hi", None, "with-skill", 25, block=["anthropic-skills:jd-fit-check", "other"])
        i = cmd.index("--settings")
        self.assertEqual(json.loads(cmd[i + 1]), {"skillOverrides": {"anthropic-skills:jd-fit-check": "off", "other": "off"}})
        self.assertNotIn("--disallowedTools", cmd)

    def test_no_block_list_means_no_settings_flag(self):
        self.assertNotIn("--settings", self.build("hi", None, "with-skill", 25))

    def test_plugin_dir_mode_loads_the_repo(self):
        cmd = self.build("hi", None, "plugin-dir", 3)
        self.assertEqual(cmd[cmd.index("--plugin-dir") + 1], ROOT)
        self.assertEqual(cmd[cmd.index("--max-turns") + 1], "3")


class InitSkillListTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import run_evals
        self.f = run_evals.init_lists_skill

    def stream(self, skills):
        return "\n".join([json.dumps({"type": "system", "subtype": "hook"}),
                          json.dumps({"type": "system", "subtype": "init", "skills": skills, "slash_commands": []}),
                          json.dumps({"type": "result", "result": "x"})])

    def test_sees_the_skill_in_the_init_event(self):
        self.assertTrue(self.f(self.stream(["pdf", "resume-skill", "docx"]), "resume-skill"))

    def test_absent_when_all_skills_are_off(self):
        self.assertFalse(self.f(self.stream([]), "resume-skill"))

    def test_a_stream_with_no_init_event_is_not_a_yes(self):
        self.assertFalse(self.f(json.dumps({"type": "result", "result": "x"}), "resume-skill"))


class EngagedTests(unittest.TestCase):
    """A run engaged the skill when it called the Skill tool OR read its SKILL.md / ran its scripts directly."""

    def setUp(self):
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import run_evals
        self.f = run_evals.skill_engaged

    def line(self, name, **inp):
        return json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}})

    def test_skill_tool_call_counts(self):
        self.assertTrue(self.f(self.line("Skill", skill="resume-skill"), "resume-skill"))

    def test_reading_skill_md_counts(self):
        self.assertTrue(self.f(self.line("Bash", command="cd ~/.agents/skills/resume-skill && cat SKILL.md"), "resume-skill"))
        self.assertTrue(self.f(self.line("Read", file_path="/x/.claude/skills/resume-skill/SKILL.md"), "resume-skill"))

    def test_running_its_scripts_counts(self):
        self.assertTrue(self.f(self.line("Bash", command="python3 /x/resume-skill/scripts/where.py"), "resume-skill"))

    def test_other_tool_calls_do_not(self):
        self.assertFalse(self.f(self.line("Bash", command="ls -la"), "resume-skill"))
        self.assertFalse(self.f(self.line("Skill", skill="pdf"), "resume-skill"))


class RunnerPlanTests(unittest.TestCase):
    def test_without_yes_it_prints_the_plan_and_runs_nothing(self):
        r = sh(RUNNER, "--cases", "e01,e02")
        self.assertEqual(r.returncode, 2)
        self.assertIn("plan: 2 agent call(s)", r.stdout)
        self.assertIn("add --yes", r.stderr)

    def test_trigger_plan_counts_sixty_calls(self):
        r = sh(RUNNER, "--triggers")
        self.assertEqual(r.returncode, 2)
        self.assertIn("plan: 60 agent call(s)", r.stdout)

    def test_trigger_subset_by_id(self):
        r = sh(RUNNER, "--triggers", "--cases", "t03,t05", "--runs", "3")
        self.assertEqual(r.returncode, 2)
        self.assertIn("plan: 6 agent call(s)", r.stdout)

    def test_blocked_skills_are_named_in_the_plan(self):
        r = sh(RUNNER, "--cases", "e01", "--block-skills", "anthropic-skills:jd-fit-check")
        self.assertIn("blocking anthropic-skills:jd-fit-check", r.stdout)

    def test_baseline_is_named_in_the_plan(self):
        self.assertIn("baseline (no skill)", sh(RUNNER, "--baseline", "--cases", "e01").stdout)


if __name__ == "__main__":
    unittest.main()
