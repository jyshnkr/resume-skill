"""The leak scanner (tools/leak_scan.py): finds planted facts, stays quiet on clean text, masks what it prints."""
import json, os, subprocess, sys, unittest
from helpers import ROOT, TmpCase, write

TOOL = os.path.join(ROOT, "tools", "leak_scan.py")


def scan(*args):
    return subprocess.run([sys.executable, "-B", TOOL, *args], capture_output=True, text=True, stdin=subprocess.DEVNULL)


class LeakScanTests(TmpCase):
    def source(self):
        d = os.path.join(self.tmp, "src")
        write(os.path.join(d, "private", "contact.json"), json.dumps({"name": "Quentin Marlowe", "phone": "(555) 019-7788",
              "links": [{"text": "quentin-marlowe.example.org", "href": "https://quentin-marlowe.example.org"}]}))
        write(os.path.join(d, "private", "terms.json"), json.dumps({"people": ["Ottoline Brandt"], "internal_codenames": ["Bluefin"]}))
        write(os.path.join(d, "bank.json"), json.dumps({"roles": ["zephyrcorp", "amazon"], "bullets": [
              {"id": "b001", "role": "zephyrcorp", "text": "Cut the nightly ledger close from nine hours to forty minutes by splitting the batch."}]}))
        return d

    def repo(self, body):
        d = os.path.join(self.tmp, "repo")
        write(os.path.join(d, "README.md"), body)
        return d

    def test_clean_repo_has_no_hits(self):
        r = scan("--from", self.source(), "--root", self.repo("A generic skill for resumes. Uses Amazon and AWS in examples.\n"))
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_planted_facts_are_found_and_masked(self):
        body = ("Written by Quentin Marlowe.\nCall 555-019-7788.\nSee quentin-marlowe.example.org\nWorked at ZephyrCorp.\n"
                "Thanks Ottoline.\nProject Bluefin shipped.\n"
                "We cut the nightly ledger close from nine hours to forty minutes by splitting.\n")
        r = scan("--from", self.source(), "--root", self.repo(body))
        self.assertEqual(r.returncode, 1)
        for kind in ("name", "phone digits", "contact link", "employer", "private person part", "internal name", "word run"):
            self.assertIn(kind, r.stdout)
        self.assertNotIn("Quentin", r.stdout)
        self.assertNotIn("ZephyrCorp", r.stdout)

    def test_the_license_holder_line_is_not_a_leak(self):
        d = self.repo("A generic skill for resumes.\n")
        write(os.path.join(d, "LICENSE"), "MIT License\n\nCopyright (c) 2026 Quentin Marlowe\n")
        r = scan("--from", self.source(), "--root", d)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_product_words_in_roles_are_not_employer_hits(self):
        r = scan("--from", self.source(), "--root", self.repo("Examples use Amazon SQS.\n"))
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_no_source_is_exit_2_not_a_pass(self):
        r = scan("--root", self.repo("x\n"))
        self.assertEqual(r.returncode, 2)
        r = scan("--from", os.path.join(self.tmp, "nowhere"), "--root", self.repo("x\n"))
        self.assertEqual(r.returncode, 2)


class RealRepoScan(unittest.TestCase):
    """Runs the real scan when RESUME_SKILL_LEAK_SOURCES (os.pathsep-separated data folders) is set; skipped in CI."""

    @unittest.skipUnless(os.environ.get("RESUME_SKILL_LEAK_SOURCES"), "no private source configured")
    def test_this_repo_has_none_of_the_users_facts(self):
        args = []
        for p in os.environ["RESUME_SKILL_LEAK_SOURCES"].split(os.pathsep):
            args += ["--from", p]
        r = scan(*args)
        self.assertEqual(r.returncode, 0, r.stdout)


if __name__ == "__main__":
    unittest.main()
