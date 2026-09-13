import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import lint_roman_urdu as L  # noqa: E402

RULES = [
    {"canonical": "ke", "reject": ["keh", "kay"], "safe_fix": True},
    {"canonical": "woh", "reject": ["wo", "vo"], "safe_fix": True},
    {"canonical": "Tauheed", "reject": ["Tawheed", "Tawhid"], "safe_fix": True, "case_insensitive": True},
    {"canonical": "Ta'ala", "reject": ["Ta'aala", "Taala"], "safe_fix": True},
    {
        "canonical": "Sallallahu Alaihi Wasallam",
        "reject": ["SAW", "PBUH"],
        "safe_fix": True,
        "regex": r"(?i)sall?all?ahu\s+ala[iy]h[ei]\s+wa\s*sall?am|\(\s*(?:SAW|SAWS|PBUH)\s*\)",
    },
    {"canonical": "Rahimahullah", "reject": ["Rahimullah"], "safe_fix": False},
]

GLOSSARY = {
    "version": 1,
    "domain": "islamic",
    "top_n": 25,
    "honorifics": [
        {"id": "prophet_muhammad", "target": "(Sallallahu Alaihi Wasallam)"},
        {"id": "companion", "target": "(Radiallahu Anhu)", "female_target": "(Radiallahu Anha)"},
        {"id": "scholar_deceased", "target": "(Rahimahullah)"},
    ],
    "terms": [
        {"source": "Abu Hurairah", "aliases": [], "target": "Abu Hurairah", "category": "companion", "honorific": "companion"},
        {"source": "Ibn Taymiyyah", "aliases": [], "target": "Ibn Taimiyyah", "category": "scholar", "honorific": "scholar_deceased"},
        {"source": "Sahih al-Bukhari", "aliases": ["Bukhari"], "target": "Sahih Bukhari", "category": "book", "honorific": ""},
    ],
}

SRC = """# Introduction

The Prophet (peace be upon him) said: "Actions are judged by intentions." (Sahih Bukhari: 1)

قُلْ هُوَ اللَّهُ أَحَدٌ

"Say: He is Allah, the One." (Surah Al-Ikhlas: 1)

- first
- second

See also 2:255 and the note.[^1] ![Figure](media/img1.png)

[^1]: A footnote.
"""

OUT = """# Muqaddimah

Rasoolullah (Sallallahu Alaihi Wasallam) ne farmaya: "Amaal ka daromadaar niyyaton par hai." (Sahih Bukhari: 1)

قُلْ هُوَ اللَّهُ أَحَدٌ

"Kahiye: Woh Allah ek hai." (Surah Al-Ikhlas: 1)

- pehla
- doosra

2:255 aur hashiya bhi dekhiye.[^1] ![Tasweer](media/img1.png)

[^1]: Ek hashiya.
"""


def rules():
    return [L._compile_rule(r) for r in RULES]


class ApplyFixesTests(unittest.TestCase):
    def test_case_preserving_fixes(self):
        text = "Keh woh keh raha tha. KEH nahi. wo gaya. Tawheed aur tawhid. Allah Ta'aala."
        fixed, counts = L.apply_fixes(text, rules())
        self.assertEqual(fixed, "Ke woh ke raha tha. KE nahi. woh gaya. Tauheed aur Tauheed. Allah Ta'ala.")
        self.assertEqual(counts["ke"], 3)
        self.assertEqual(counts["woh"], 1)
        self.assertEqual(counts["Tauheed"], 2)
        self.assertEqual(counts["Ta'ala"], 1)

    def test_main_untouched_and_no_partial_words(self):
        text = "main kehta hun ke woh sawal kare. Keh-kar."
        fixed, counts = L.apply_fixes(text, rules())
        self.assertIn("main kehta", fixed)
        self.assertIn("woh sawal", fixed)  # "sawal" must not become "woh..." etc
        self.assertEqual(fixed, "main kehta hun ke woh sawal kare. Ke-kar.")

    def test_abbreviation_keeps_parentheses(self):
        fixed, _ = L.apply_fixes("Nabi (SAW) aur Nabi (pbuh). Rasoolullah (sallallahu alaihe wa sallam).", rules())
        self.assertEqual(
            fixed,
            "Nabi (Sallallahu Alaihi Wasallam) aur Nabi (Sallallahu Alaihi Wasallam). "
            "Rasoolullah (Sallallahu Alaihi Wasallam).",
        )

    def test_protected_regions_untouched(self):
        text = "keh `keh` https://x.com/keh (Sahih Bukhari: keh 1)\n```\nkeh\n```\nkeh"
        fixed, counts = L.apply_fixes(text, rules())
        self.assertEqual(counts["ke"], 2)
        self.assertIn("`keh`", fixed)
        self.assertIn("https://x.com/keh", fixed)
        self.assertIn("(Sahih Bukhari: keh 1)", fixed)
        self.assertIn("```\nkeh\n```", fixed)

    def test_unsafe_rule_only_warns(self):
        fixed, counts = L.apply_fixes("Imam Malik Rahimullah", rules())
        self.assertEqual(fixed, "Imam Malik Rahimullah")
        self.assertEqual(counts, {})
        issues = L.find_spelling_issues(fixed, rules())
        self.assertIn("Rahimahullah", issues)

    def test_load_rules_falls_back_to_builtin(self):
        r = L.load_rules("/nonexistent/spelling-rules.json")
        self.assertTrue(any(x["canonical"] == "Tauheed" for x in r))

    def test_load_rules_from_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "rules.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"version": 1, "rules": RULES}, f)
            r = L.load_rules(p)
            self.assertEqual(len(r), len(RULES))


class LintPairTests(unittest.TestCase):
    def test_good_pair_passes(self):
        report, fixed = L.lint_pair(SRC, OUT, rules(), GLOSSARY, fix=True, chunk_id="chunk0001")
        self.assertEqual(report["errors"], [], report)
        self.assertEqual([w["code"] for w in report["warnings"]], [], report)
        self.assertEqual(fixed, OUT)
        self.assertGreater(report["ratio"], 0.5)

    def test_empty_output(self):
        report, _ = L.lint_pair(SRC, "   \n", rules(), GLOSSARY)
        self.assertEqual(report["errors"][0]["code"], "E_EMPTY")
        report, _ = L.lint_pair(SRC, None, rules(), GLOSSARY)
        self.assertEqual(report["errors"][0]["code"], "E_EMPTY")

    def test_commentary_detected(self):
        report, _ = L.lint_pair(SRC, "Here is the translation:\n\n" + OUT, rules(), GLOSSARY)
        self.assertIn("E_COMMENTARY", [e["code"] for e in report["errors"]])
        report, _ = L.lint_pair(SRC, "```markdown\n" + OUT + "```\n", rules(), GLOSSARY)
        self.assertIn("E_COMMENTARY", [e["code"] for e in report["errors"]])

    def test_removed_heading_is_structure_error(self):
        out = OUT.replace("# Muqaddimah\n", "Muqaddimah\n")
        report, _ = L.lint_pair(SRC, out, rules(), GLOSSARY)
        codes = [e["code"] for e in report["errors"]]
        self.assertIn("E_STRUCTURE", codes)
        self.assertTrue(any("heading" in e["message"] for e in report["errors"]))

    def test_missing_list_item_and_image(self):
        out = OUT.replace("- doosra\n", "").replace("![Tasweer](media/img1.png)", "")
        report, _ = L.lint_pair(SRC, out, rules(), GLOSSARY)
        msgs = " ".join(e["message"] for e in report["errors"])
        self.assertIn("list items", msgs)
        self.assertIn("image", msgs)

    def test_footnote_marker_missing(self):
        out = OUT.replace("[^1] ", " ").replace("[^1]: Ek hashiya.", "Ek hashiya.")
        report, _ = L.lint_pair(SRC, out, rules(), GLOSSARY)
        self.assertTrue(any("footnote" in e["message"] for e in report["errors"]))

    def test_changed_citation_number(self):
        out = OUT.replace("(Sahih Bukhari: 1)", "(Sahih Bukhari: 2)").replace("2:255", "2:256")
        report, _ = L.lint_pair(SRC, out, rules(), GLOSSARY)
        codes = [e["code"] for e in report["errors"]]
        self.assertEqual(codes.count("E_CITATION"), 2)

    def test_citation_name_variation_tolerated(self):
        out = OUT.replace("(Sahih Bukhari: 1)", "(Bukhari: 1)")
        report, _ = L.lint_pair(SRC, out, rules(), GLOSSARY)
        self.assertNotIn("E_CITATION", [e["code"] for e in report["errors"]])

    def test_untranslated_english_line(self):
        out = OUT.replace(
            "2:255 aur hashiya bhi dekhiye.[^1]",
            "See also 2:255 and this should be translated because it is very much english.[^1]",
        )
        report, _ = L.lint_pair(SRC, out, rules(), GLOSSARY)
        self.assertIn("E_UNTRANSLATED", [e["code"] for e in report["errors"]])

    def test_roman_urdu_not_flagged_as_english(self):
        line = "Yeh baat is liye ahem hai ke ham sab ko us par amal karna chahiye aur main bhi is mein shamil hun."
        self.assertEqual(L.check_untranslated(line), [])

    def test_arabic_parity(self):
        out = OUT.replace("قُلْ هُوَ اللَّهُ أَحَدٌ", "قُلْ")
        report, _ = L.lint_pair(SRC, out, rules(), GLOSSARY)
        self.assertTrue(any("Arabic" in e["message"] for e in report["errors"]))

    def test_urdu_script_warning(self):
        out = OUT.replace("ek hai", "ایک hai")
        report, _ = L.lint_pair(SRC, out, rules(), GLOSSARY)
        self.assertIn("W_URDU_SCRIPT", [w["code"] for w in report["warnings"]])

    def test_missing_honorific_warnings(self):
        out = OUT.replace("Rasoolullah (Sallallahu Alaihi Wasallam)", "Rasoolullah")
        out += "\nAbu Hurairah se riwayat hai. Ibn Taimiyyah farmate hain. Muhammad bin Abdul Wahhab ne likha.\n"
        report, _ = L.lint_pair(SRC, out, rules(), GLOSSARY)
        hon = [w for w in report["warnings"] if w["code"] == "W_HONORIFIC"]
        text = " ".join(w["message"] for w in hon)
        self.assertIn("Prophet", text)
        self.assertIn("Abu Hurairah", text)
        self.assertIn("Ibn Taimiyyah", text)
        # "Muhammad bin ..." must not be counted as the Prophet
        prophet = [w for w in hon if "Prophet" in w["message"]][0]
        self.assertEqual(prophet["message"].split(" ")[0], "1")

    def test_honorific_present_not_flagged(self):
        out = OUT + "\nAbu Hurairah (Radiallahu Anhu) se riwayat hai. Ibn Taimiyyah (Rahimahullah) farmate hain.\n"
        report, _ = L.lint_pair(SRC, out, rules(), GLOSSARY)
        self.assertEqual([w for w in report["warnings"] if w["code"] == "W_HONORIFIC"], [])

    def test_spelling_warning_without_fix_and_fix_applied(self):
        out = OUT.replace("Woh Allah", "Wo Allah")
        report, fixed = L.lint_pair(SRC, out, rules(), GLOSSARY, fix=False)
        self.assertIn("W_SPELLING", [w["code"] for w in report["warnings"]])
        report, fixed = L.lint_pair(SRC, out, rules(), GLOSSARY, fix=True)
        self.assertNotIn("W_SPELLING", [w["code"] for w in report["warnings"]])
        self.assertEqual(report["fixes"], {"woh": 1})
        self.assertIn("Woh Allah", fixed)

    def test_length_warning(self):
        report, _ = L.lint_pair(SRC, OUT + ("Lambi baat. " * 200), rules(), GLOSSARY)
        self.assertIn("W_LENGTH", [w["code"] for w in report["warnings"]])


class RunDirTests(unittest.TestCase):
    def _make_run(self, d):
        work = Path(d) / "work"
        work.mkdir()
        (work / "chunk0001.md").write_text(SRC, encoding="utf-8")
        (work / "chunk0002.md").write_text("## Two\n\nSecond part.\n", encoding="utf-8")
        (work / "output_chunk0001.md").write_text(OUT.replace("Woh Allah", "Wo Allah"), encoding="utf-8")
        (work / "output_chunk0002.md").write_text("## Doosra\n\nDoosra hissa.\n", encoding="utf-8")
        (work / "glossary.json").write_text(json.dumps(GLOSSARY), encoding="utf-8")
        manifest = {
            "chunk_count": 2,
            "source_hash": "",
            "chunks": [
                {"id": "chunk0002", "order": 2, "source_file": "chunk0002.md", "source_hash": "", "output_file": "output_chunk0002.md"},
                {"id": "chunk0001", "order": 1, "source_file": "chunk0001.md", "source_hash": "", "output_file": "output_chunk0001.md"},
            ],
        }
        (work / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        rules_path = Path(d) / "rules.json"
        rules_path.write_text(json.dumps({"version": 1, "rules": RULES}), encoding="utf-8")
        return work, rules_path

    def test_all_with_fix_writes_reports_and_fixes_file(self):
        with tempfile.TemporaryDirectory() as d:
            work, rules_path = self._make_run(d)
            rc = L.main([d, "--all", "--fix", "--json", "--rules", str(rules_path)])
            self.assertEqual(rc, 0)
            self.assertTrue((work / "lint_chunk0001.json").exists())
            self.assertTrue((work / "lint_chunk0002.json").exists())
            summary = json.loads((work / "lint_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["chunks"], 2)
            self.assertEqual(summary["errors"], 0)
            self.assertEqual(summary["fixes"], {"woh": 1})
            self.assertEqual(list(summary["per_chunk"].keys()), ["chunk0001", "chunk0002"])
            self.assertIn("Woh Allah", (work / "output_chunk0001.md").read_text(encoding="utf-8"))

    def test_error_exit_code_and_strict(self):
        with tempfile.TemporaryDirectory() as d:
            work, rules_path = self._make_run(d)
            (work / "output_chunk0002.md").write_text("", encoding="utf-8")
            rc = L.main([d, "--chunks", "chunk0002", "--rules", str(rules_path)])
            self.assertEqual(rc, 1)
            rc = L.main([d, "--chunks", "chunk0001", "--rules", str(rules_path)])
            self.assertEqual(rc, 0)  # only a spelling warning
            rc = L.main([d, "--chunks", "chunk0001", "--strict", "--rules", str(rules_path)])
            self.assertEqual(rc, 1)

    def test_single_file_mode(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "s.md"
            out = Path(d) / "o.md"
            src.write_text(SRC, encoding="utf-8")
            out.write_text(OUT.replace("Woh Allah", "Wo Allah"), encoding="utf-8")
            rules_path = Path(d) / "rules.json"
            rules_path.write_text(json.dumps({"version": 1, "rules": RULES}), encoding="utf-8")
            rc = L.main(["--file", str(out), "--source", str(src), "--fix", "--json", "--rules", str(rules_path)])
            self.assertEqual(rc, 0)
            self.assertIn("Woh Allah", out.read_text(encoding="utf-8"))

    def test_missing_work_dir(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(L.main([d, "--all"]), 2)


if __name__ == "__main__":
    unittest.main()
