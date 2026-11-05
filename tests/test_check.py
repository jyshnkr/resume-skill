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

try:
    import PIL  # noqa: F401
    HAVE_PIL = True
except ImportError:
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
        self.assertEqual([p for p in pairs(r.stdout) if p[0] == "FAIL"], [], r.stdout)
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
