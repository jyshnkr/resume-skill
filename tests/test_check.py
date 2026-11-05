"""Seam 3-4: check.py, the bullet / summary / document checker. Tests run the script as a user would (command line in, lines and exit code out).

Part 1: the port. The 17 recorded runs of the old checker (tests/fixtures/old-checker-goldens.json) must give the same exit code and the
same set of (level, rule) pairs; every value the old file hard-coded is now read from the data folder (one test each, listed below).
Part 2: the Wave 1 checks, driven by tests/fixtures/checks.json.

Hard-coded spots made data-driven (one test each):
 1 KEPT repeats -> bank rows' allowed_repeats      7 WORDS/CHARS/TEXT_PT/indent/wrap lines -> settings limits.*
 2 salted hashes + --hash-terms -> private/terms   8 summary opening regex + sentence count + lines -> settings summary.* / limits.*
 3 JARGON regex -> bullets.jargon                  9 RETIRED -> summary.retired_wording
 4 AWS list -> bullets.aws_services               10 beta/gamma stage words -> terms.stage_words
 5 'cleared' -> bullets.phrase_replacements       11 --all: bank + version names -> data folder
 6 BANNED/IRREGULAR/NOT_PAST/STOP -> bullets.*    12 wording that named the owner ('his') -> neutral
"""
import importlib.util, json, os, re, sys, unittest
from helpers import TmpCase, run, write, EXAMPLE, FIXTURES, SCRIPTS

try:  # Pillow plus the Liberation Serif font (found by name, or in the current folder)
    from PIL import ImageFont
    ImageFont.truetype("LiberationSerif-Regular.ttf", 11)
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False

LINE = re.compile(r"^\s+(FAIL|WARN|NOTE|INFO) rule (\d+): ", re.M)
GOOD = "Cut nightly report runtime from 6 hours to 40 minutes by rewriting the AWS Glue job as partitioned Parquet reads and adding retry-safe checkpoints."


def pairs(stdout):
    return [(m.group(1), int(m.group(2))) for m in LINE.finditer(stdout)]


def source():
    with open(os.path.join(SCRIPTS, "check.py"), encoding="utf-8") as f:
        return f.read()


# The AWS service names the old checker knew. The shared sample settings also list ECS, EKS, RDS and others, so golden g10
# ("Amazon ECS on Fargate") would pass there; the goldens run with exactly the old list.
OLD_AWS = ["Lambda", "DynamoDB", "S3", "Glue", "CloudWatch", "Step Functions", "SQS", "SNS", "Secrets Manager", "SSM", "Athena", "API Gateway",
           "Route 53", "Cognito", "CloudFront", "KMS", "IAM", "EventBridge", "AppConfig", "Lake Formation", "Kinesis", "Fargate", "X-Ray"]


def load_fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)


class CheckCase(TmpCase):
    def chk(self, *args, data=EXAMPLE):
        return run("check.py", *args, env=self.env_for(data))

    def bullet(self, text, leads="", data=EXAMPLE):
        return self.chk("--leads", leads, text, data=data)

    def edit(self, data, rel, fn):
        p = os.path.join(data, rel)
        d = self.jload(p)
        fn(d)
        write(p, json.dumps(d, indent=2))

    def setting(self, data, section, key, value):
        self.edit(data, "settings.json", lambda d: d[section].__setitem__(key, value))


class GoldenTests(CheckCase):
    """The old checker's recorded output on 17 made-up inputs, same verdict and same problems (rule numbers replace the old wording)."""

    def test_every_golden_gives_the_old_exit_code_and_problems(self):
        d = self.example_copy()
        self.setting(d, "bullets", "aws_services", OLD_AWS)
        for g in load_fixture("old-checker-goldens.json"):
            with self.subTest(g["id"]):
                args = ["--summary", g["text"]] if g.get("flag") == "--summary" else ["--leads", g.get("leads", ""), g["text"]]
                r = self.chk(*args, data=d)
                got = pairs(r.stdout)
                want = [tuple(p) for p in g["expect"]]
                if HAVE_PIL:  # the goldens were recorded without Pillow; measured wrap lines and the short-last-line note differ
                    got = [p for p, ln in zip(got, [l for l in r.stdout.splitlines() if LINE.match(l)]) if "wrap:" not in ln and p[1] != 60]
                    want = [p for p in want if p not in (("NOTE", 4), ("NOTE", 23))]
                self.assertEqual(r.returncode, g["exit"], r.stdout + r.stderr)
                self.assertEqual(sorted(got), sorted(want), r.stdout)

    def test_header_line_keeps_the_old_form(self):
        r = self.bullet(GOOD)
        self.assertTrue(r.stdout.startswith("OK 24w 146c :: Cut nightly report runtime from 6 hours to 40 minutes by rewriting the AWS Glue "), r.stdout)

    def test_result_line_is_a_plain_sentence_naming_the_rule(self):
        r = self.bullet("Cut report runtime 80% by tuning queries.")
        self.assertIn("    FAIL rule 4: 7 words; the limit is 20 to 30.\n", r.stdout)

    def test_help_prints_the_docstring_and_exits_0(self):
        r = self.chk("--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("Exit 0", r.stdout)


class DataDrivenTests(CheckCase):
    # 1
    def test_allowed_repeats_come_from_the_bank_row(self):
        b002 = next(b for b in self.jload(EXAMPLE, "bank.json")["bullets"] if b["id"] == "b002")
        r = self.bullet(b002["text"])  # queues / queue is allowed by the sample row b002
        self.assertEqual((r.returncode, [p for p in pairs(r.stdout) if p[1] == 6]), (0, []), r.stdout)
        d = self.example_copy()
        self.edit(d, "bank.json", lambda bk: [x.__setitem__("allowed_repeats", []) for x in bk["bullets"]])
        r = self.bullet(b002["text"], data=d)
        self.assertEqual((r.returncode, ("WARN", 6) in pairs(r.stdout)), (2, True), r.stdout)

    # 2
    def test_private_names_come_from_terms_json_not_from_hashes(self):
        text = GOOD.replace("nightly report", "Orion report")
        d = self.example_copy()
        self.assertNotIn(("FAIL", 16), pairs(self.bullet(text, data=d).stdout))  # Orion is not in the sample terms
        self.edit(d, "private/terms.json", lambda t: t.__setitem__("internal_codenames", ["Orion"]))
        self.assertIn(("FAIL", 16), pairs(self.bullet(text, data=d).stdout))
        falcon = GOOD.replace("nightly report", "Project Falcon report")
        self.assertNotIn(("FAIL", 16), pairs(self.bullet(falcon, data=d).stdout))  # no longer listed
        src = source()
        for gone in ("pbkdf2", "_HASHED", "--hash-terms", "JDFC_ROOT"):
            self.assertNotIn(gone, src)

    def test_no_data_folder_runs_with_defaults_and_says_names_were_not_checked(self):
        r = run("check.py", "--leads", "", GOOD, env=self.base_env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.count("NOTE rule 16: no data folder found, private names were not checked"), 1, r.stdout)
        r = run("check.py", "--leads", "", "Cut report runtime 80% by tuning queries.", env=self.base_env)
        self.assertEqual(r.returncode, 1)  # default limits still apply

    def test_private_patterns_from_terms_json_fail_without_echoing_the_match(self):
        d = self.example_copy()
        self.edit(d, "private/terms.json", lambda t: t.__setitem__("patterns", ["[unclosed", r"Zeta\d+"]))  # the bad regex is skipped
        text = GOOD.replace("nightly report", "Zeta42 report")
        r = self.bullet(text, data=d)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("    FAIL rule 16: private pattern matched: Ze...", r.stdout)
        self.assertNotIn("Zeta42", [l for l in r.stdout.splitlines() if "private pattern" in l][0])
        self.assertNotIn("Traceback", r.stderr)
        self.assertNotIn("private pattern", self.bullet(GOOD, data=d).stdout)
        s = self.chk("--summary", "Senior engineer with 8+ years of experience in cloud systems. Cut report runtime in half. Led the Zeta7 releases.", data=d)
        self.assertIn("FAIL rule 16: private pattern matched: Ze...", s.stdout)

    # 3
    def test_jargon_list_comes_from_settings(self):
        d = self.example_copy()
        text = GOOD.replace("Parquet reads", "FooBar reads")
        self.assertNotIn(("FAIL", 9), pairs(self.bullet(text, data=d).stdout))
        self.setting(d, "bullets", "jargon", ["FooBar", "@PreAuthorize", "cy.intercept"])
        self.assertIn(("FAIL", 9), pairs(self.bullet(text, data=d).stdout))
        for odd in ("@PreAuthorize", "cy.intercept"):  # names that start or end with a symbol
            self.assertIn(("FAIL", 9), pairs(self.bullet(GOOD.replace("Parquet reads", odd + " reads"), data=d).stdout), odd)
        self.assertNotIn(("FAIL", 9), pairs(self.bullet(GOOD.replace("Parquet reads", "cyXintercept reads"), data=d).stdout))  # the dot is escaped
        self.assertNotIn(("FAIL", 9), pairs(self.bullet(GOOD.replace("Parquet reads", "ParDo reads"), data=d).stdout))  # not listed any more

    # 4
    def test_aws_service_list_comes_from_settings(self):
        text = GOOD.replace("AWS Glue job", "Widget job")
        d = self.example_copy()
        self.assertNotIn(("FAIL", 8), pairs(self.bullet(text, data=d).stdout))
        self.setting(d, "bullets", "aws_services", ["Widget"])
        self.assertIn(("FAIL", 8), pairs(self.bullet(text, data=d).stdout))
        self.assertNotIn(("FAIL", 8), pairs(self.bullet(GOOD.replace("AWS Glue job", "Lambda job"), data=d).stdout))

    # 5
    def test_phrase_replacements_come_from_settings(self):
        text = GOOD.replace("Cut nightly", "Cleared nightly")
        self.assertIn(("FAIL", 15), pairs(self.bullet(text).stdout))
        d = self.example_copy()
        self.setting(d, "bullets", "phrase_replacements", [{"pattern": r"(?i)\bwidgets?\b", "say": "components", "rule": 15}])
        self.assertNotIn(("FAIL", 15), pairs(self.bullet(text, data=d).stdout))
        r = self.bullet(GOOD.replace("Parquet reads", "Widget reads"), data=d)
        self.assertIn(("FAIL", 15), pairs(r.stdout))
        self.assertIn("say 'components'", r.stdout)

    # 6
    def test_lead_word_lists_come_from_settings(self):
        d = self.example_copy()
        banned = GOOD.replace("Cut nightly", "Reorganized nightly")
        self.assertNotIn(("FAIL", 3), pairs(self.bullet(banned, data=d).stdout))
        self.setting(d, "bullets", "banned_leads", ["reorganized"])
        self.assertIn(("FAIL", 3), pairs(self.bullet(banned, data=d).stdout))
        flung = GOOD.replace("Cut nightly", "Flung nightly")  # irregular past tense
        self.assertIn(("FAIL", 3), pairs(self.bullet(flung).stdout))
        self.setting(d, "bullets", "irregular_past", ["flung"])
        self.assertNotIn(("FAIL", 3), pairs(self.bullet(flung, data=d).stdout))
        shred = GOOD.replace("Cut nightly", "Shred nightly")  # ends in 'ed' but is present tense
        self.assertNotIn(("FAIL", 3), pairs(self.bullet(shred).stdout))
        self.setting(d, "bullets", "not_past", ["shred"])
        self.assertIn(("FAIL", 3), pairs(self.bullet(shred, data=d).stdout))

    def test_stop_words_come_from_settings(self):
        text = GOOD.replace("runtime from", "overall runtime from").replace("retry-safe", "overall retry-safe")
        self.assertIn(("FAIL", 6), pairs(self.bullet(text).stdout))
        d = self.example_copy()
        self.setting(d, "bullets", "stop_words", ["overall", "a", "the", "by", "from", "to", "of", "as", "and"])
        self.assertNotIn(("FAIL", 6), pairs(self.bullet(text, data=d).stdout))

    # 7
    def test_word_and_character_limits_come_from_settings(self):
        d = self.example_copy()
        short = "Cut report runtime 80% by tuning queries."
        self.assertIn(("FAIL", 4), pairs(self.bullet(short).stdout))
        self.setting(d, "limits", "words", [5, 9])
        self.assertNotIn(("FAIL", 4), pairs(self.bullet(short, data=d).stdout))
        self.setting(d, "limits", "chars", 30)
        r = self.bullet(short, data=d)
        self.assertIn("FAIL rule 4: 40 characters; the limit is 30.", r.stdout)

    @unittest.skipUnless(HAVE_PIL, "needs Pillow and Liberation Serif")
    def test_wrap_limits_come_from_settings(self):
        d = self.example_copy()
        self.setting(d, "limits", "bullet_lines", [3, 4])
        self.assertIn(("FAIL", 4), [p for p in pairs(self.bullet(GOOD, data=d).stdout) if p[0] == "FAIL"])

    # 8
    def test_summary_opening_and_sentence_count_come_from_settings(self):
        s = "Senior Software Engineer with 8+ years of experience in cloud backend systems. Cut report runtime from 6 hours to 40 minutes. Led zero-downtime releases for 4 teams."
        r = self.chk("--summary", s)
        self.assertNotIn("FAIL rule 23: sentence", r.stdout)
        self.assertNotIn("FAIL rule 23: 3 sentences", r.stdout)
        self.assertNotIn("FAIL rule 24", r.stdout)
        d = self.example_copy()
        self.setting(d, "summary", "opening_pattern", r"^Staff Engineer with \d+ years")
        r = self.chk("--summary", s, data=d)
        self.assertIn("FAIL rule 23: sentence 1 does not open as required", r.stdout)
        self.setting(d, "limits", "summary_sentences", 2)
        r = self.chk("--summary", s, data=d)
        self.assertIn("FAIL rule 23: 3 sentences; the summary needs 2.", r.stdout)

    @unittest.skipUnless(HAVE_PIL, "needs Pillow and Liberation Serif")
    def test_summary_lines_come_from_settings(self):
        d = self.example_copy()
        self.setting(d, "limits", "summary_lines", 9)
        r = self.chk("--summary", "Senior Software Engineer with 8+ years of experience in cloud backend systems. Cut report runtime. Led releases.", data=d)
        self.assertIn(("FAIL", 23), pairs(r.stdout))

    # 9
    def test_retired_wording_comes_from_settings(self):
        s = "Senior Software Engineer with 8+ years of experience in cloud backend systems. Cut report runtime in half. Led releases for Old Phrase teams."
        self.assertNotIn(("FAIL", 25), pairs(self.chk("--summary", s).stdout))
        d = self.example_copy()
        self.setting(d, "summary", "retired_wording", ["Old Phrase", r"\b9\d%"])
        self.assertIn(("FAIL", 25), pairs(self.chk("--summary", s, data=d).stdout))

    # 10
    def test_stage_words_come_from_terms_json(self):
        beta = GOOD.replace("nightly report", "beta stage report")
        self.assertIn(("FAIL", 16), pairs(self.bullet(beta).stdout))
        d = self.example_copy()
        self.edit(d, "private/terms.json", lambda t: t.__setitem__("stage_words", ["alpha"]))
        self.assertNotIn(("FAIL", 16), pairs(self.bullet(beta, data=d).stdout))
        self.assertIn(("FAIL", 16), pairs(self.bullet(GOOD.replace("nightly report", "alpha stage report"), data=d).stdout))
        self.edit(d, "private/terms.json", lambda t: t.__setitem__("stage_words", []))
        self.assertNotIn(("FAIL", 16), pairs(self.bullet(beta, data=d).stdout))
        self.assertNotIn(("NOTE", 16), pairs(self.bullet(beta, data=d).stdout))

    # 11
    def test_all_reads_bank_and_version_names_from_the_data_folder(self):
        r = self.chk("--all")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("## b001 (contract) exit=0", r.stdout)  # first version name in sorted order that holds the bullet
        self.assertIn("## b010 (contract) exit=0", r.stdout)
        d = self.example_copy()
        os.remove(os.path.join(d, "versions", "contract.json"))
        r = self.chk("--all", data=d)
        self.assertIn("## b001 (full-time) exit=0", r.stdout)
        self.assertIn("## b011 (none)", r.stdout)  # in no remaining version
        d = self.example_copy("data2")  # leads of the other bullets in the same version
        self.edit(d, "bank.json", lambda bk: bk["bullets"][1].__setitem__("lead", "Cut"))
        r = self.chk("--all", data=d)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertRegex(r.stdout, r"## b001 \(contract\) exit=1\n(?:.*\n)*?\s+FAIL rule 3: lead 'Cut' is already used")

    def test_all_needs_a_data_folder(self):
        r = run("check.py", "--all", env=self.base_env)
        self.assertEqual(r.returncode, 1)
        self.assertIn("--all needs a data folder", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    # 12
    def test_messages_do_not_name_the_owner(self):
        out = ""
        for g in load_fixture("old-checker-goldens.json"):
            args = ["--summary", g["text"]] if g.get("flag") == "--summary" else ["--leads", g.get("leads", ""), g["text"]]
            out += self.chk(*args).stdout
        for word in (" his ", "Amazon stage"):
            self.assertNotIn(word, out)
        src = source()
        for word in ("Senior Software Engineer", "AppSec", "Change log"):
            self.assertNotIn(word, src)


def checker_module():
    spec = importlib.util.spec_from_file_location("check_under_test", os.path.join(SCRIPTS, "check.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, SCRIPTS)
    spec.loader.exec_module(mod)
    return mod


WAVE1 = {"first_person", "vague_size", "number_word", "vague_ing", "em_dash", "mixed_endings", "passive", "robot_phrase", "short_last_line"}


class Wave1Tests(CheckCase):
    """k36: one test walks tests/fixtures/checks.json. A fixture names the rule and check, the text, and the (level, rule) lines it must
    and must not produce."""

    def fixtures(self):
        return load_fixture("checks.json")

    def run_fixture(self, fx):
        if fx["kind"] == "document":
            path = os.path.join(self.tmp, "doc.txt")
            write(path, fx["text"] + "\n")
            return self.chk("--document-file", path)
        if fx["kind"] == "summary":
            return self.chk("--summary", fx["text"])
        return self.bullet(fx["text"], fx.get("leads", ""))

    def test_every_fixture_gives_its_lines(self):
        for i, fx in enumerate(self.fixtures()):
            if fx.get("needs_pillow") and not HAVE_PIL:
                continue
            with self.subTest("%s #%d" % (fx["check"], i)):
                r = self.run_fixture(fx)
                got = pairs(r.stdout)
                for want in fx["expect"]:
                    self.assertIn(tuple(want), got, r.stdout)
                for no in fx["must_not"]:
                    self.assertNotIn(tuple(no), got, r.stdout)

    def test_each_wave1_check_has_a_failing_and_a_passing_fixture(self):
        checks = checker_module().CHECKS
        fixtures = self.fixtures()
        for cid in sorted(WAVE1):
            mine = [f for f in fixtures if f["check"] == cid]
            with self.subTest(cid):
                self.assertIn(cid, checks)
                self.assertTrue([f for f in mine if f["expect"]], "no failing fixture")
                self.assertTrue([f for f in mine if not f["expect"] and f["must_not"]], "no passing fixture")
                for f in mine:
                    self.assertEqual(f["rule"], checks[cid]["rule"])

    def test_checks_table_is_complete_and_plain(self):
        checks = checker_module().CHECKS
        for cid, c in checks.items():
            with self.subTest(cid):
                self.assertEqual(sorted(c), ["doc", "level", "rule", "when"])
                self.assertIn(c["level"], ("FAIL", "WARN", "NOTE"))
                self.assertIn(c["when"], ("bullet", "summary", "document"))
                self.assertIsInstance(c["rule"], int)
                self.assertTrue(c["doc"].endswith("."))
        for cid in WAVE1 | {"stack_coverage"}:
            self.assertIn(cid, checks)


class SettingsDrivenWave1Tests(CheckCase):
    def test_vague_ing_verbs_come_from_settings(self):
        text = GOOD.replace("checkpoints.", "checkpoints, polishing the reporting experience.").replace("and adding retry-safe checkpoints,", "and retry-safe checkpoints,")
        self.assertNotIn(("WARN", 19), pairs(self.bullet(text).stdout))
        d = self.example_copy()
        self.setting(d, "checks", "vague_ing_verbs", ["polishing"])
        self.assertIn(("WARN", 19), pairs(self.bullet(text, data=d).stdout))

    def test_robot_phrases_extra_and_ignore_come_from_settings(self):
        d = self.example_copy()
        extra = GOOD.replace("retry-safe", "turnkey")
        self.assertNotIn(("WARN", 18), pairs(self.bullet(extra, data=d).stdout))
        self.setting(d, "checks", "robot_phrases_extra", ["turnkey"])
        self.assertIn(("WARN", 18), pairs(self.bullet(extra, data=d).stdout))
        robust = GOOD.replace("retry-safe", "robust")
        self.assertIn(("WARN", 18), pairs(self.bullet(robust, data=d).stdout))
        self.setting(d, "checks", "robot_phrases_ignore", ["robust"])
        self.assertNotIn(("WARN", 18), pairs(self.bullet(robust, data=d).stdout))

    def test_a_weak_lead_is_reported_once_by_the_lead_check(self):
        r = self.bullet("Helped " + GOOD[len("Cut "):])
        self.assertIn(("FAIL", 3), pairs(r.stdout))
        self.assertNotIn(("WARN", 18), pairs(r.stdout))

    @unittest.skipUnless(HAVE_PIL, "needs Pillow and Liberation Serif")
    def test_short_last_line_share_comes_from_settings(self):
        d = self.example_copy()
        self.assertIn(("NOTE", 60), pairs(self.bullet(GOOD, data=d).stdout))  # about 34% of the width
        self.setting(d, "checks", "short_last_line_pct", 20)
        self.assertNotIn(("NOTE", 60), pairs(self.bullet(GOOD, data=d).stdout))

    @unittest.skipUnless(HAVE_PIL, "needs Pillow and Liberation Serif")
    def test_short_last_lines_print_as_one_line_per_run_naming_the_bullets(self):
        pre = run("preflight.py", "--json", env=self.env_for(EXAMPLE))  # preflight keeps each finding on its own bullet
        bullets = json.loads(pre.stdout)["bullets"]
        short = [i for i, v in bullets.items() if any(f["check"] == "short_last_line" for f in v["findings"])]
        self.assertTrue(short)
        r = self.chk("--all")
        lines = [l for l in r.stdout.splitlines() if "rule 60" in l]
        self.assertEqual(lines, ["    NOTE rule 60: %d of 12 bullets end on a short last line: %s" % (len(short), ", ".join(short))])
        r = self.chk("--resume", "full-time")
        lines = [l for l in r.stdout.splitlines() if "rule 60" in l]
        self.assertEqual(len(lines), 1, r.stdout)
        self.assertRegex(lines[0], r"NOTE rule 60: \d+ of 10 bullets end on a short last line: b001, ")
        r = self.bullet(GOOD)  # one text run: the same single line, naming the bullet by its first word
        self.assertIn("NOTE rule 60: 1 of 1 bullets end on a short last line: Cut", r.stdout)

    @unittest.skipUnless(HAVE_PIL, "needs Pillow and Liberation Serif")
    def test_no_short_last_line_means_no_line(self):
        d = self.example_copy()
        self.setting(d, "checks", "short_last_line_pct", 10)
        self.assertNotIn("rule 60", self.chk("--all", data=d).stdout)

    def test_without_pillow_the_short_last_line_check_is_not_run_and_exit_is_unaffected(self):
        if HAVE_PIL:
            self.skipTest("Pillow present")
        r = self.bullet(GOOD)
        self.assertEqual(r.returncode, 0)
        self.assertNotIn(("NOTE", 60), pairs(r.stdout))


def fails_without_wrap(stdout):
    """FAIL lines other than the measured-wrap ones (the sample summaries print on 3 lines, the default wants 4; only with Pillow)."""
    return [l for l in stdout.splitlines() if l.strip().startswith("FAIL rule") and "wrap:" not in l]


class DocumentTests(CheckCase):
    def test_json_is_a_list_of_results_with_findings(self):
        r = self.chk("--json", "--leads", "", "Reduced report runtime 80% by tuning queries.", GOOD)
        self.assertEqual(r.returncode, 1)
        out = json.loads(r.stdout)
        self.assertEqual([o["status"] for o in out][:2], ["FAIL", "OK"])  # with Pillow a third, document result carries the short-last-line note
        self.assertEqual(sorted(out[0]), ["chars", "findings", "status", "text", "words"])
        self.assertEqual((out[0]["words"], out[0]["chars"]), (7, 44))
        f = out[0]["findings"][0]
        self.assertEqual((f["level"], f["rule"], f["check"]), ("FAIL", 4, "words"))
        self.assertEqual(f["message"], "7 words; the limit is 20 to 30.")

    def test_json_without_a_data_folder_carries_the_note_in_each_result(self):
        r = run("check.py", "--json", GOOD, env=self.base_env)
        out = json.loads(r.stdout)
        self.assertIn(("NOTE", 16, "no_data_folder"), [(f["level"], f["rule"], f["check"]) for f in out[0]["findings"]])

    def test_a_clean_sample_resume_passes(self):
        for target in ("full-time", "contract", "tailoring:acme-backend"):
            with self.subTest(target):
                r = self.chk("--resume", target)
                self.assertEqual(fails_without_wrap(r.stdout), [], r.stdout)
                if not HAVE_PIL: self.assertEqual(r.returncode, 0, r.stdout)
                if not HAVE_PIL: self.assertNotIn("document", r.stdout)  # with Pillow the one short-last-line note is printed there

    def test_resume_checks_leads_across_the_whole_resume_and_the_document(self):
        d = self.example_copy()
        self.edit(d, "bank.json", lambda bk: [bk["bullets"][1].__setitem__("text", bk["bullets"][1]["text"].replace("queue aged", "queue \u2014 aged"))])
        r = self.chk("--resume", "full-time", data=d)
        if not HAVE_PIL: self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("WARN rule 19: 1 em dash in the document", r.stdout)

    def test_resume_needs_a_data_folder_and_a_known_name(self):
        r = run("check.py", "--resume", "full-time", env=self.base_env)
        self.assertEqual(r.returncode, 1)
        self.assertIn("--resume needs a data folder", r.stderr)
        r = self.chk("--resume", "nope")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no version named", r.stderr)

    def test_document_file_reads_bullets_and_a_summary_line(self):
        f = os.path.join(self.tmp, "doc.txt")
        write(f, "SUMMARY: Senior engineer with 8+ years of experience in cloud systems. Cut report runtime in half. Led releases for 4 teams.\n" + GOOD + "\n" + GOOD.replace("Cut", "Reduced", 1) + "\n")
        r = self.chk("--document-file", f)
        self.assertEqual(fails_without_wrap(r.stdout), [], r.stdout)
        if not HAVE_PIL:
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertEqual(r.stdout.count("\n    "), 3)  # one wrap note per item, nothing else
        r = self.chk("--document-file", os.path.join(self.tmp, "gone.txt"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("error: cannot read", r.stderr)

    def test_unknown_option_is_a_one_line_error(self):
        r = self.chk("--nope")
        self.assertEqual(r.returncode, 1)
        self.assertIn("error: unknown option --nope", r.stderr)
        self.assertNotIn("Traceback", r.stderr)


class StackTests(CheckCase):
    """k39 against the sample data: b001 tech lists Python, which its text does not name."""

    def test_lists_terms_the_bullet_does_not_name_and_summarises_shared_ones(self):
        r = self.chk("--stack", "full-time")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("b001: Cut nightly shipment-report runtime", r.stdout)
        self.assertIn("    NOTE rule 67: not named in this bullet: Python.\n", r.stdout)
        self.assertIn("not named in this bullet: Python, AWS Lambda.", r.stdout)  # b002: language first
        self.assertIn("not named in this bullet: Java, Spring Boot, PostgreSQL.", r.stdout)  # b006
        self.assertIn("NOTE rule 67: Java: used in 5 bullets, named in 0.", r.stdout)
        self.assertIn("NOTE rule 67: Python: used in 3 bullets, named in 1.", r.stdout)
        self.assertNotIn("AWS Lambda: used", r.stdout)  # one bullet only
        self.assertNotIn("FAIL", r.stdout)
        self.assertNotIn("WARN", r.stdout)

    def test_works_on_a_tailoring_and_never_fails(self):
        r = self.chk("--stack", "tailoring:acme-backend")
        self.assertEqual(r.returncode, 0)
        self.assertIn("NOTE rule 67:", r.stdout)

    def test_a_vendor_prefix_is_optional_in_the_text(self):
        d = self.example_copy()
        self.edit(d, "bank.json", lambda bk: bk["bullets"][1].__setitem__("tech", ["Amazon SQS"]))  # text says 'Amazon SQS'
        self.edit(d, "bank.json", lambda bk: bk["bullets"][0].__setitem__("tech", ["AWS Parquet"]))  # text says 'Parquet'
        r = self.chk("--stack", "full-time", data=d)
        self.assertNotIn("b001: Cut nightly shipment-report runtime from 6 hours to 40 minutes by rewriting the AWS Glue job as partitioned Parquet reads and adding retry-safe checkpoints.\n    NOTE", r.stdout)
        self.assertIn("NOTE rule 67: Java: used in", r.stdout)

    def test_json(self):
        out = json.loads(self.chk("--stack", "full-time", "--json").stdout)
        self.assertEqual(out[0]["findings"][0]["check"], "stack_coverage")

    def test_needs_a_data_folder(self):
        r = run("check.py", "--stack", "full-time", env=self.base_env)
        self.assertEqual(r.returncode, 1)
        self.assertIn("--stack needs a data folder", r.stderr)


class AllJsonTests(CheckCase):
    def test_all_honours_json(self):
        r = self.chk("--all", "--json")
        self.assertEqual(r.returncode, 0, r.stdout)
        out = json.loads(r.stdout)
        self.assertEqual([o["id"] for o in out], ["b%03d" % i for i in range(1, 13)])
        o = out[0]
        self.assertEqual((o["version"], o["status"], o["exit"]), ("contract", "OK", 0))
        self.assertEqual(sorted(o), ["chars", "exit", "findings", "id", "status", "text", "version", "words"])
        self.assertEqual(next(x for x in out if x["id"] == "b012")["findings"][0]["check"], "no_metric")

    def test_all_json_exit_follows_the_worst_bullet(self):
        d = self.example_copy()
        self.edit(d, "bank.json", lambda bk: bk["bullets"][2].__setitem__("text", "x"))
        r = self.chk("--all", "--json", data=d)
        self.assertEqual(r.returncode, 1)
        out = json.loads(r.stdout)
        self.assertEqual((out[2]["status"], out[2]["exit"], out[2]["version"]), ("FAIL", 1, "contract"))

    def test_all_text_form_is_unchanged(self):
        r = self.chk("--all")
        self.assertTrue(r.stdout.startswith("## b001 (contract) exit=0\n"))


class PagesTests(CheckCase):
    def pdf(self, n):
        p = os.path.join(self.tmp, "r%d.pdf" % n)
        with open(p, "wb") as f:
            f.write(b"%PDF-1.4\n" + b"".join(b"<< /Type /Page >>\n" for _ in range(n)) + b"%%EOF\n")
        return p

    def test_pages_within_the_cap(self):
        r = self.chk("--pages", "2", self.pdf(2))
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("INFO rule 32: pages: 2 (cap 2)", r.stdout)

    def test_pages_over_the_cap_fail(self):
        r = self.chk("--pages", "2", self.pdf(3))
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("FAIL rule 32: pages: 3 (cap 2)", r.stdout)

    def test_unreadable_page_count_is_a_note_and_exits_2(self):
        docx = os.path.join(self.tmp, "r.docx")
        write(docx, "not a real docx")
        env = {**self.env_for(EXAMPLE), "PATH": "/usr/bin:/bin"}  # no soffice on the path
        r = run("check.py", "--pages", "2", docx, env=env)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("NOTE rule 32: pages: not checked (no PDF renderer)", r.stdout)
        r = self.chk("--pages", "2", os.path.join(self.tmp, "missing.pdf"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("NOTE rule 32: pages: not checked (no such file)", r.stdout)


if __name__ == "__main__":
    unittest.main()
