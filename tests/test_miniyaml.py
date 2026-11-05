"""The built-in YAML reader and writer used for settings.yaml (standard library only, a small subset of YAML)."""
import json, os, sys, unittest
from helpers import SCRIPTS, SKILL

sys.path.insert(0, SCRIPTS)
import miniyaml as y  # noqa: E402


class ScalarTests(unittest.TestCase):
    def test_plain_scalars(self):
        d = y.loads("a: null\nb: ~\nc:\nd: true\ne: false\nf: 42\ng: -3\nh: 0.5\ni: hello world\nj: 70\n")
        self.assertEqual(d, {"a": None, "b": None, "c": None, "d": True, "e": False, "f": 42, "g": -3, "h": 0.5, "i": "hello world", "j": 70})

    def test_quoted_strings(self):
        d = y.loads('a: "tab\\there"\nb: \'it\'\'s\'\nc: \'(?i)\\bcleared\\b\'\nd: ""\ne: "5"\nf: "true"\n')
        self.assertEqual(d, {"a": "tab\there", "b": "it's", "c": "(?i)\\bcleared\\b", "d": "", "e": "5", "f": "true"})

    def test_double_quoted_unknown_escape_says_use_single_quotes(self):
        with self.assertRaises(ValueError) as cm:
            y.loads('a: "\\d+"\n')
        self.assertIn("single quotes", str(cm.exception))
        self.assertIn("line 1", str(cm.exception))

    def test_hash_rules(self):
        d = y.loads("a: C# and F#   # a trailing comment\nb: 'keep # this'\n# full line\nc: x\n")
        self.assertEqual(d, {"a": "C# and F#", "b": "keep # this", "c": "x"})


class ApostropheTests(unittest.TestCase):
    """An apostrophe inside a plain word is not a quote: a trailing comment after it must still be dropped."""

    def test_apostrophe_in_a_plain_value_then_a_comment(self):
        self.assertEqual(y.loads("location: Austin's Finest   # my city\n"), {"location": "Austin's Finest"})
        self.assertEqual(y.loads("a: don't # note\n"), {"a": "don't"})

    def test_apostrophes_inside_flow_lists(self):
        self.assertEqual(y.loads("a: [it's, fine, b's]  # c\n"), {"a": ["it's", "fine", "b's"]})

    def test_real_quotes_still_work_with_comments(self):
        self.assertEqual(y.loads("a: 'keep # this'  # drop this\nb: \"x # y\"  # z\nc: ['p, q', r]\n"),
                         {"a": "keep # this", "b": "x # y", "c": ["p, q", "r"]})

    def test_a_key_with_an_apostrophe_and_a_colon_in_the_value(self):
        self.assertEqual(y.loads("note: it's: fine # c\n"), {"note": "it's: fine"})


class StructureTests(unittest.TestCase):
    def test_nested_mappings_with_string_keys(self):
        d = y.loads("fit:\n  weights:\n    required: 70\n    preferred: 30\n  legend:\n    5: 90\n    4: 75\n")
        self.assertEqual(d, {"fit": {"weights": {"required": 70, "preferred": 30}, "legend": {"5": 90, "4": 75}}})

    def test_lists_flow_block_and_empty(self):
        d = y.loads('a: [x, "b, c", 3]\nb: []\nc: {}\nd:\n  - one\n  - two words\n  - 3\ne:\n- same\n- indent\n')
        self.assertEqual(d, {"a": ["x", "b, c", 3], "b": [], "c": {}, "d": ["one", "two words", 3], "e": ["same", "indent"]})

    def test_list_of_mappings(self):
        text = "rules:\n  - pattern: '(?i)\\bcleared\\b'\n    say: passed the review\n    rule: 15\n  - pattern: other\n    say: x\n    rule: 3\n"
        self.assertEqual(y.loads(text), {"rules": [{"pattern": "(?i)\\bcleared\\b", "say": "passed the review", "rule": 15},
                                                  {"pattern": "other", "say": "x", "rule": 3}]})

    def test_flow_mapping_inline(self):
        self.assertEqual(y.loads("a: {x: 1, y: two}\n"), {"a": {"x": 1, "y": "two"}})

    def test_comments_are_collected_by_key_path(self):
        c = {}
        y.loads("# header line\n\n# about fit\nfit:\n  # about weights\n  # second line\n  weights:\n    required: 70\n", comments=c)
        self.assertEqual(c[()], ["header line"])
        self.assertEqual(c[("fit",)], ["about fit"])
        self.assertEqual(c[("fit", "weights")], ["about weights", "second line"])

    def test_errors_name_the_line(self):
        for text, needle in (("a:\n\tb: 1\n", "tab"), ("a: 1\n  b: 2\n", "line 2"), ("a: 1\na: 2\n", "duplicate"), ("- x\ny: 1\n", "line 2")):
            with self.assertRaises(ValueError) as cm:
                y.loads(text)
            self.assertIn(needle, str(cm.exception), text)


class WriterTests(unittest.TestCase):
    SAMPLE = {"a": None, "b": True, "c": 5, "d": 0.5, "e": "plain words", "f": "5", "g": "null", "h": "true", "i": "", "j": "(?i)\\bx\\b",
              "k": ["x", "y z", "a, b"], "l": [], "m": {}, "n": {"o": {"p": [1, 2]}, "q": "it's"},
              "r": [{"pattern": "(?i)\\bcleared\\b", "say": "passed", "rule": 15}], "s": {"5": 90, "4": 75}, "t": "has: colon", "u": "# hash", "v": "- dash"}

    def test_round_trip(self):
        self.assertEqual(y.loads(y.dumps(self.SAMPLE)), self.SAMPLE)

    def test_comments_go_above_their_keys(self):
        text = y.dumps({"fit": {"weights": {"required": 70}}, "x": 1}, comments={(): ["top"], ("fit",): ["about fit"], ("fit", "weights"): ["w1", "w2"]})
        self.assertTrue(text.startswith("# top\n"))
        self.assertIn("# about fit\nfit:\n", text)
        self.assertIn("  # w1\n  # w2\n  weights:\n", text)
        self.assertEqual(y.loads(text), {"fit": {"weights": {"required": 70}}, "x": 1})

    def test_key_order_is_kept(self):
        self.assertEqual(list(y.loads(y.dumps({"z": 1, "a": 2, "m": 3}))), ["z", "a", "m"])


class ShippedDefaultsTests(unittest.TestCase):
    def test_the_shipped_defaults_survive_a_yaml_round_trip(self):
        d = y.load(os.path.join(SKILL, "assets", "defaults", "settings.yaml"))
        self.assertEqual(y.loads(y.dumps(d)), d)


if __name__ == "__main__":
    unittest.main()
