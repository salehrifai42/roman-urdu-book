"""Integrity checks for glossary/*.json and their sync with references/style-guide.md.

Self-contained: only json / re / pathlib / unittest, no imports from scripts/.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TERMS_PATH = ROOT / "glossary" / "islamic-terms.json"
RULES_PATH = ROOT / "glossary" / "spelling-rules.json"
STYLE_PATH = ROOT / "references" / "style-guide.md"

ALLOWED_CATEGORIES = {
    "aqeedah", "fiqh_ibadah", "names_of_allah", "prophet", "companion",
    "scholar", "book", "surah", "place", "phrase",
}
REQUIRED_TERM_KEYS = {"source", "aliases", "target", "category", "honorific"}
REQUIRED_RULE_KEYS = {"canonical", "reject", "safe_fix"}


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def rule_matches(rule, text):
    """Return True if `text` contains a rejected variant of `rule` (whole word, case-insensitive)."""
    if rule.get("regex"):
        return re.search(rule["regex"], text, re.IGNORECASE) is not None
    for variant in rule["reject"]:
        pattern = r"(?<![\w'])" + re.escape(variant) + r"(?![\w'])"
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


class TestIslamicTerms(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load(TERMS_PATH)
        cls.terms = cls.data["terms"]
        cls.honorific_ids = {h["id"] for h in cls.data["honorifics"]}

    def test_top_level_shape(self):
        self.assertEqual(self.data["version"], 1)
        self.assertEqual(self.data["name"], "islamic-terms")
        det = self.data["detection"]
        self.assertIn("min_distinct_terms", det)
        self.assertIn("min_hits_per_1000_words", det)
        self.assertTrue(det["strong_terms"])
        for h in self.data["honorifics"]:
            self.assertIn("id", h)
            self.assertIn("target", h)
            self.assertIsInstance(h.get("triggers", []), list)

    def test_term_count_and_surahs(self):
        self.assertGreaterEqual(len(self.terms), 250)
        surahs = [t for t in self.terms if t["category"] == "surah"]
        self.assertEqual(len(surahs), 114)
        numbers = {int(re.search(r"Surah (\d+)", t.get("note", "")).group(1)) for t in surahs}
        self.assertEqual(numbers, set(range(1, 115)))

    def test_term_keys_and_categories(self):
        for t in self.terms:
            missing = REQUIRED_TERM_KEYS - set(t)
            self.assertFalse(missing, "term %r missing %s" % (t.get("source"), missing))
            self.assertIn(t["category"], ALLOWED_CATEGORIES, t["source"])
            self.assertIsInstance(t["aliases"], list, t["source"])
            self.assertTrue(t["source"].strip(), "empty source")
            self.assertTrue(t["target"].strip(), "empty target for %r" % t["source"])
            if "gender" in t:
                self.assertIn(t["gender"], ("m", "f"), t["source"])

    def test_honorific_ids_exist(self):
        for t in self.terms:
            self.assertTrue(
                t["honorific"] == "" or t["honorific"] in self.honorific_ids,
                "term %r has unknown honorific %r" % (t["source"], t["honorific"]),
            )
        self.assertEqual(
            self.honorific_ids,
            {"allah", "prophet_muhammad", "other_prophets", "companion",
             "scholar_deceased", "scholar_living"},
        )

    def test_no_duplicate_surface_forms(self):
        seen = {}
        dups = []
        for t in self.terms:
            for surface in [t["source"]] + t["aliases"]:
                key = surface.strip().lower()
                if key in seen and seen[key] != t["source"]:
                    dups.append((surface, seen[key], t["source"]))
                seen.setdefault(key, t["source"])
        self.assertFalse(dups, "duplicate surfaces: %s" % dups)

    def test_targets_follow_spelling_rules(self):
        rules = [r for r in load(RULES_PATH)["rules"] if r["safe_fix"]]
        offenders = []
        for t in self.terms:
            for r in rules:
                if rule_matches(r, t["target"]):
                    offenders.append((t["source"], t["target"], r["canonical"]))
        self.assertFalse(offenders, "targets violating spelling rules: %s" % offenders)


class TestSpellingRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load(RULES_PATH)
        cls.rules = cls.data["rules"]
        cls.style = STYLE_PATH.read_text(encoding="utf-8")

    def test_shape(self):
        self.assertEqual(self.data["version"], 1)
        self.assertGreaterEqual(len(self.rules), 20)
        for r in self.rules:
            missing = REQUIRED_RULE_KEYS - set(r)
            self.assertFalse(missing, "rule %r missing %s" % (r.get("canonical"), missing))
            self.assertIsInstance(r["reject"], list)
            self.assertIsInstance(r["safe_fix"], bool)
            if r.get("regex"):
                re.compile(r["regex"])  # must be valid Python regex

    def test_canonicals_unique(self):
        canon = [r["canonical"].lower() for r in self.rules]
        self.assertEqual(len(canon), len(set(canon)))

    def test_main_never_rejected(self):
        for r in self.rules:
            self.assertNotIn("main", [v.lower() for v in r["reject"]], r["canonical"])
            if r.get("regex"):
                self.assertIsNone(re.search(r["regex"], "main", re.IGNORECASE),
                                  "regex of %r matches 'main'" % r["canonical"])

    def test_canonical_never_matches_its_own_rule(self):
        for r in self.rules:
            self.assertFalse(rule_matches(r, r["canonical"]),
                             "rule %r matches its own canonical form" % r["canonical"])

    def test_every_canonical_in_style_guide(self):
        missing = [r["canonical"] for r in self.rules
                   if "`%s`" % r["canonical"] not in self.style]
        self.assertFalse(missing, "canonicals absent from style-guide.md: %s" % missing)

    def test_style_guide_has_spelling_table(self):
        self.assertIn("| Meaning | Canonical | Rejected variants | Note |", self.style)
        self.assertLessEqual(len(self.style.splitlines()), 350)


if __name__ == "__main__":
    unittest.main()
