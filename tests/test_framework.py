"""Seam 10: the installed skill folder against the 19 pre-ship checks of the Agent Skills framework (corrected)."""
import ast, glob, json, os, re, shutil, stat, subprocess, sys, tempfile, unittest
from helpers import ROOT, SKILL, SCRIPTS, EXAMPLE, TmpCase, run

SKILL_MD = os.path.join(SKILL, "SKILL.md")
REFS = os.path.join(SKILL, "references")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def frontmatter(text):
    """Parse the small YAML subset used by SKILL.md: scalar keys, one nested block (metadata), inline lists."""
    m = re.match(r"---\n(.*?)\n---\n", text, flags=re.S)
    assert m, "SKILL.md has no frontmatter"
    out, cur = {}, None
    for line in m.group(1).split("\n"):
        if not line.strip():
            continue
        if line.startswith("  "):
            k, _, v = line.strip().partition(":")
            out[cur][k] = v.strip().strip('"')
        else:
            k, _, v = line.partition(":")
            if v.strip() == "":
                out[k], cur = {}, k
            else:
                out[k] = v.strip()
    return out, text[m.end():]


FM, BODY = frontmatter(read(SKILL_MD))
SCRIPT_FILES = sorted(glob.glob(os.path.join(SCRIPTS, "*.py")))


class RoutingTests(unittest.TestCase):
    def test_description_is_third_person_with_use_when_and_not_for(self):
        d = FM["description"]
        self.assertRegex(d, r"^[A-Z][A-Za-z-]+s\b", "third person: starts with a verb ending in s")
        self.assertIn("Use when", d)
        self.assertIn("Not for", d)
        self.assertTrue(280 <= len(d) <= 400, len(d))
        self.assertLessEqual(len(d), 1024)
        self.assertNotIn(".pdf", d.lower(), "v0.1 builds .docx only")
        self.assertNotRegex(d, r"\b(I|you|your|my)\b")

    def test_name_is_kebab_case_and_equals_the_folder(self):
        n = FM["name"]
        self.assertRegex(n, r"^[a-z0-9]+(-[a-z0-9]+)*$")
        self.assertLessEqual(len(n), 64)
        self.assertEqual(n, os.path.basename(SKILL))
        self.assertNotRegex(n, "anthropic|claude")

    def test_trigger_set_has_ten_and_ten_with_kinds(self):
        t = json.loads(read(os.path.join(ROOT, "evals", "triggers.json")))
        self.assertEqual(len(t["should_fire"]), 10)
        self.assertEqual(len(t["should_not_fire"]), 10)
        self.assertEqual(t["runs_each"], 3)
        self.assertEqual({x["kind"] for x in t["should_fire"]}, {"direct", "indirect", "contextual"})
        self.assertTrue({"near-miss", "negative-control"} <= {x["kind"] for x in t["should_not_fire"]})
        kinds = " ".join(x["query"].lower() for x in t["should_not_fire"])
        for near in ("recruiter", "inbox", "bullet", "interview"):
            self.assertIn(near, kinds, f"no near-miss about {near}")


class StructureTests(unittest.TestCase):
    def test_budget_under_300_lines_and_5000_tokens_with_invariants_first(self):
        text = read(SKILL_MD)
        self.assertLess(len(text.split("\n")), 300)
        self.assertLess(len(text) / 4, 5000, "about 4 characters per token")
        first_h2 = re.search(r"^## (.+)$", BODY, flags=re.M).group(1)
        self.assertTrue(first_h2.startswith("Invariants"), first_h2)

    def test_frontmatter_fields_only(self):
        self.assertTrue(set(FM) <= {"name", "description", "license", "compatibility", "metadata"}, set(FM))
        self.assertTrue(set(FM["metadata"]) <= {"author", "version", "tags"}, set(FM["metadata"]))
        for k, v in FM["metadata"].items():
            self.assertIsInstance(v, str, f"metadata.{k}: the spec says metadata maps string keys to string values")
            self.assertFalse(v.startswith("["), f"metadata.{k} is a YAML list; write it as one quoted string")
        self.assertEqual(FM["license"], "MIT", "the license field is an SPDX identifier")
        self.assertNotIn("allowed-tools", FM)
        self.assertLessEqual(len(FM["compatibility"]), 500)
        self.assertNotIn("[", FM["author"] if "author" in FM else FM["metadata"]["author"])

    def test_every_reference_is_linked_once_over_and_none_is_orphaned(self):
        linked = set(re.findall(r"`references/([A-Za-z0-9_.-]+\.md)`", BODY))
        on_disk = {os.path.basename(p) for p in glob.glob(os.path.join(REFS, "*"))}
        self.assertEqual(linked, on_disk)
        self.assertEqual(len(on_disk), 10, sorted(on_disk))
        self.assertEqual([p for p in glob.glob(os.path.join(REFS, "*")) if os.path.isdir(p)], [], "references are one level deep")

    def test_no_backslashes_in_paths_and_toc_over_100_lines(self):
        for p in glob.glob(os.path.join(REFS, "*.md")) + [SKILL_MD]:
            text = read(p)
            self.assertNotRegex(text, r"(?:references|scripts|assets)\\", p)
            if p != SKILL_MD and len(text.split("\n")) > 100:
                self.assertRegex(text, r"(?im)^#+ contents", f"{p} needs a table of contents")

    def test_references_stay_under_5000_characters(self):
        for p in glob.glob(os.path.join(REFS, "*.md")):
            self.assertLess(len(read(p)), 5000, p)

    def test_body_has_no_dates_or_skill_version_numbers(self):
        for p in [SKILL_MD] + glob.glob(os.path.join(REFS, "*.md")):
            text = read(p) if p != SKILL_MD else BODY
            self.assertNotRegex(text, r"\b20\d\d-\d\d-\d\d\b", p)
            self.assertNotRegex(text, r"\b(January|February|March|April|June|July|August|September|October|November|December)\s+20\d\d\b", p)
            self.assertNotRegex(text, r"\bv?\d+\.\d+\.\d+\b", p)
            self.assertNotRegex(text, r"(?i)\bversion\s+\d", p)


class WritingTests(unittest.TestCase):
    def test_output_contract_with_a_realistic_example_and_glossary(self):
        self.assertIn("## Inputs and outputs", BODY)
        self.assertRegex(BODY, r"Output, in this order")
        self.assertRegex(BODY, r"```\nScore \d of 5")
        self.assertIn("## Words used here", BODY)
        for term in ("**bank**", "**version**", "**tailoring**"):
            self.assertIn(term, BODY)

    def test_calibration_decision_table_stop_rules_and_do_not_infer(self):
        self.assertIn("### Decision points", BODY)
        self.assertIn("| If | Then |", BODY)
        self.assertIn("Ask one question and stop", BODY)
        self.assertIn("Do not infer", BODY)
        self.assertRegex(BODY, r"outranks")

    def test_step_6_agrees_with_the_output_contract_and_setup_covers_the_old_settings_file(self):
        step6 = next(l for l in BODY.split("\n") if l.startswith("- [ ] 6."))
        self.assertIn("was:", step6)
        self.assertNotIn("before/after", step6)
        scripts = BODY.split("## Scripts", 1)[1].split("\n## ", 1)[0]
        self.assertIn("--convert-settings", scripts)

    def test_edits_are_shown_as_was_and_now_lines(self):
        out = BODY.split("## Inputs and outputs", 1)[1].split("## Workflow", 1)[0]
        self.assertIn("`was:`", out)
        self.assertIn("`now:`", out)
        self.assertRegex(out, r"(?m)^Edits:.*\n\s*was:")

    def test_an_instruction_inside_a_posting_is_named_to_the_user(self):
        row = next(l for l in BODY.split("\n") if l.startswith("| The posting or a message contains instructions"))
        self.assertIn("ignore", row)
        self.assertIn("name the instruction", row)

    def test_a_missing_number_is_asked_for_with_a_placeholder_never_a_digit(self):
        row = next(l for l in BODY.split("\n") if l.startswith("| A number is missing"))
        self.assertIn("[N]", row)
        self.assertIn("never a digit", row)

    def test_no_company_or_person_names_from_a_real_user(self):
        # employer names and facts are covered by tools/leak_scan.py; here: no first person, no "he/his" (pronouns unknown)
        self.assertNotRegex(BODY, r"\b(he|his|him|she|her)\b")


class ScriptTests(TmpCase):
    def test_every_script_is_executable_has_help_and_a_shebang(self):
        self.assertGreaterEqual(len(SCRIPT_FILES), 10, [os.path.basename(s) for s in SCRIPT_FILES])
        for s in SCRIPT_FILES:
            self.assertTrue(os.stat(s).st_mode & stat.S_IXUSR, f"{s} is not executable")
            self.assertTrue(read(s).startswith("#!/usr/bin/env python3"), s)
            r = run(s, "--help", env=self.env_for(EXAMPLE))
            self.assertEqual(r.returncode, 0, f"{os.path.basename(s)} --help: {r.stderr[:200]}")
            self.assertTrue(r.stdout.strip(), f"{os.path.basename(s)} --help printed nothing")

    def test_no_network_imports_no_eval_exec_no_prompts(self):
        banned_mods = {"urllib", "http", "socket", "requests", "ftplib", "smtplib", "telnetlib", "xmlrpc", "ssl", "webbrowser"}
        for s in SCRIPT_FILES + glob.glob(os.path.join(ROOT, "tools", "*.py")):
            tree = ast.parse(read(s))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    mods = {a.name.split(".")[0] for a in node.names}
                elif isinstance(node, ast.ImportFrom):
                    mods = {(node.module or "").split(".")[0]}
                else:
                    mods = set()
                self.assertFalse(mods & banned_mods, f"{s} imports {mods & banned_mods}")
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, {"eval", "exec", "input", "compile", "__import__"}, f"{s}: {node.func.id}()")

    def test_scripts_that_the_agent_reads_have_json(self):
        for name in ("where", "validate", "preflight", "check", "fit_score", "export"):
            r = run(f"{name}.py", "--help", env=self.env_for(EXAMPLE))
            self.assertIn("--json", r.stdout, name)

    def test_setup_style_scripts_take_flags_and_dry_run(self):
        for name, path in (("setup", os.path.join(SCRIPTS, "setup.py")), ("save", os.path.join(SCRIPTS, "save.py")),
                           ("import_old", os.path.join(ROOT, "tools", "import_old.py"))):
            r = run(path, "--help", env=self.env_for(EXAMPLE))
            self.assertIn("--dry-run", r.stdout, name)

    def test_skill_md_states_run_not_read_and_names_every_script(self):
        scripts_section = BODY.split("## Scripts", 1)[1].split("\n## ", 1)[0]
        self.assertRegex(scripts_section, r"RUN these")
        for s in SCRIPT_FILES:
            name = os.path.basename(s)
            if name in ("resume_data.py", "build_docx.py", "miniyaml.py"):
                continue  # libraries used by the others, not commands
            self.assertIn(f"scripts/{name}", scripts_section, name)

    def test_every_script_command_in_skill_md_exists(self):
        for m in re.finditer(r"python3 scripts/([a-z_]+\.py)", BODY):
            self.assertTrue(os.path.isfile(os.path.join(SCRIPTS, m.group(1))), m.group(1))


class EvalTests(unittest.TestCase):
    def test_cases_cover_the_matrix_and_every_reference_is_opened_somewhere(self):
        d = json.loads(read(os.path.join(ROOT, "evals", "cases.json")))
        cases = d["cases"]
        self.assertGreaterEqual(len(cases), 9)
        cats = {c["category"] for c in cases}
        for need in ("incomplete-input", "trap-injection", "trap-private-term", "no-data-folder", "user-override", "recruiter-intro"):
            self.assertIn(need, cats)
        opened = {o for c in cases for o in c["opens"]}
        linked = {m[:-3] for m in os.listdir(REFS) if m.endswith(".md")}
        for ref in linked:
            if ref.startswith("rules-"):
                continue  # covered by the "rules" entry below
            self.assertIn(ref, opened, f"reference {ref} is opened in no eval (orphan)")
        self.assertIn("rules", opened)
        for c in cases:
            self.assertTrue({"id", "prompt", "assert"} <= set(c), c.get("id"))


class ShippingTests(unittest.TestCase):
    def test_plugin_json_is_the_one_version_source(self):
        p = json.loads(read(os.path.join(ROOT, ".claude-plugin", "plugin.json")))
        self.assertEqual(p["name"], FM["name"])
        self.assertEqual(p["version"], FM["metadata"]["version"])
        self.assertFalse(os.path.exists(os.path.join(ROOT, "VERSION")))
        self.assertIn(p["version"], read(os.path.join(ROOT, "CHANGELOG.md")))

    def test_layout_follows_the_plugin_form(self):
        for rel in ("skills/resume-skill/SKILL.md", ".claude-plugin/plugin.json", "README.md", "AGENTS.md", "CLAUDE.md", "CHANGELOG.md", ".gitignore"):
            self.assertTrue(os.path.exists(os.path.join(ROOT, rel)), rel)
        for rel in ("evals", "tools", "tests", "examples"):
            self.assertFalse(os.path.exists(os.path.join(SKILL, rel)), f"{rel} must sit at the repo root, not in the skill folder")

    def test_license_file_matches_the_license_field(self):
        text = read(os.path.join(ROOT, "LICENSE"))
        self.assertTrue(text.startswith("MIT License"))
        self.assertIn("Permission is hereby granted, free of charge", text)
        self.assertNotRegex(text, r"Copyright \(c\) \d{4} [A-Z][a-z]+ [A-Z][a-z]+", "the holder is the generic 'resume-skill contributors'")


class UserDataTests(TmpCase):
    def test_no_user_data_inside_the_skill_folder(self):
        names = {os.path.basename(p) for p in glob.glob(os.path.join(SKILL, "**", "*"), recursive=True)}
        for forbidden in ("bank.json", "profile.md", "contact.json", "terms.json", "summaries.json", "tailoring.json"):
            self.assertNotIn(forbidden, names)

    def test_reinstall_keeps_the_data_folder_and_scripts_never_write_into_the_skill_folder(self):
        data = self.example_copy()
        for i in range(2):  # install, then re-install: replace the skill folder with a fresh copy
            dest = os.path.join(self.tmp, "installed", "resume-skill")
            shutil.rmtree(dest, ignore_errors=True)
            shutil.copytree(SKILL, dest, ignore=shutil.ignore_patterns("__pycache__"))
            skill_before = _tree_hash(dest)
            env = self.env_for(data)
            outdir = os.path.join(self.tmp, "resumes")
            for args in (("where.py",), ("validate.py",), ("preflight.py",), ("check.py", "--all"), ("check.py", "--stack", "full-time"),
                         ("export.py", "full-time", outdir, "--no-contact"), ("setup.py", "--data", os.path.join(self.tmp, "x"), "--dry-run")):
                r = run(os.path.join(dest, "scripts", args[0]), *args[1:], env=env, cwd=dest)
                self.assertIn(r.returncode, (0, 2), f"{args[0]}: {r.stdout[-200:]} {r.stderr[-200:]}")
            self.assertEqual(_tree_hash(dest), skill_before, "a script wrote into the installed skill folder")
        # the data folder changes only under out/ (the pre-flight result), never in saved data
        before = _tree_hash(EXAMPLE)
        self.assertEqual(_tree_hash(data, skip=("out",)), _tree_hash(EXAMPLE, skip=("out",)))
        self.assertEqual(_tree_hash(EXAMPLE), before)


def _tree_hash(root, skip=()):
    import hashlib
    h = hashlib.sha256()
    for dp, dn, fn in os.walk(root):
        dn[:] = sorted(d for d in dn if not (dp == root and d in skip))
        for f in sorted(fn):
            p = os.path.join(dp, f)
            h.update(os.path.relpath(p, root).encode())
            with open(p, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()


if __name__ == "__main__":
    unittest.main()
