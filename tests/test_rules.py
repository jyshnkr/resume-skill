"""Rules registry (checked through seam 10): 67 rules, each with a `when` tag and a way it is enforced; generated files match."""
import importlib.util, json, os, re, subprocess, sys, unittest
from helpers import ROOT, SKILL, SCRIPTS

REGISTRY = os.path.join(SKILL, "assets", "rules", "registry.json")
WHEN = {"preflight", "posting", "tailoring", "final", "reading"}
ENFORCED = {"check", "build", "reading"}


def rules():
    with open(REGISTRY, encoding="utf-8") as f:
        return json.load(f)["rules"]


class RegistryTests(unittest.TestCase):
    def test_sixty_seven_rules_numbered_one_to_sixty_seven(self):
        self.assertEqual([r["n"] for r in rules()], list(range(1, 68)))

    def test_every_live_rule_has_when_text_and_enforcement(self):
        live = [r for r in rules() if r["status"] == "live"]
        self.assertEqual(len(live), 65)
        for r in live:
            self.assertIn(r["when"], WHEN, r["n"])
            self.assertIn(r["enforced"], ENFORCED, r["n"])
            self.assertGreater(len(r["text"]), 20, r["n"])

    def test_merged_rules_point_to_a_live_rule(self):
        by_n = {r["n"]: r for r in rules()}
        merged = [r for r in rules() if r["status"] == "merged"]
        self.assertEqual({r["n"] for r in merged}, {64, 65})
        for r in merged:
            self.assertEqual(by_n[r["into"]]["status"], "live")

    def test_build_rules_name_an_existing_script(self):
        for r in rules():
            if r.get("enforced") == "build":
                self.assertTrue(os.path.isfile(os.path.join(SCRIPTS, r["by"])), f"rule {r['n']} names {r.get('by')}")

    def test_no_personal_wording_in_the_registry(self):
        text = open(REGISTRY, encoding="utf-8").read()
        for word in ("Master", "Contract"):  # version names of the research source; employers are covered by tools/leak_scan.py
            self.assertNotIn(word, text)


class GeneratedFilesTests(unittest.TestCase):
    def test_generated_files_match_the_registry(self):
        r = subprocess.run([sys.executable, "-B", os.path.join(ROOT, "tools", "make_rules.py"), "--check"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_each_file_is_under_five_thousand_characters(self):
        for n in (1, 2, 3):
            p = os.path.join(SKILL, "references", f"rules-{n}.md")
            self.assertLess(len(open(p, encoding="utf-8").read()), 5000, p)

    def test_every_live_rule_appears_once_across_the_files(self):
        body = "".join(open(os.path.join(SKILL, "references", f"rules-{n}.md"), encoding="utf-8").read() for n in (1, 2, 3))
        for r in rules():
            self.assertEqual(len(re.findall(rf"^\*\*{r['n']}\*\*", body, flags=re.M)), 1, r["n"])


class CheckerCoversCheckRulesTests(unittest.TestCase):
    """Every rule marked `check` has at least one check in check.py that reports under that rule number (or through `via`)."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("check_mod", os.path.join(SCRIPTS, "check.py"))
        cls.check = importlib.util.module_from_spec(spec)
        sys.path.insert(0, SCRIPTS)
        spec.loader.exec_module(cls.check)

    def test_each_check_rule_is_reported_by_some_check(self):
        covered = {c["rule"] for c in self.check.CHECKS.values()}
        by_n = {r["n"]: r for r in rules()}
        for r in rules():
            if r.get("enforced") == "check":
                ok = r["n"] in covered or any(v in covered for v in r.get("via", []))
                self.assertTrue(ok, f"rule {r['n']} is marked check but no check reports it")

    def test_each_check_reports_a_known_live_check_rule(self):
        by_n = {r["n"]: r for r in rules()}
        for cid, c in self.check.CHECKS.items():
            self.assertIn(c["rule"], by_n, cid)
            self.assertEqual(by_n[c["rule"]]["status"], "live", cid)


if __name__ == "__main__":
    unittest.main()
