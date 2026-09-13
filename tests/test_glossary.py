import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import glossary  # noqa: E402

BUILTIN = {
    "version": 1,
    "honorifics": [
        {"id": "companion", "target": "(Radiallahu Anhu)", "female_target": "(Radiallahu Anha)", "plural_target": "(Radiallahu Anhum)"},
        {"id": "scholar_deceased", "target": "(Rahimahullah)"},
    ],
    "terms": [
        {"source": "Tawhid", "aliases": ["Tawheed"], "target": "Tauheed", "category": "aqeedah", "honorific": ""},
        {"source": "Abu Hurairah", "aliases": ["Abu Huraira"], "target": "Abu Hurairah", "category": "companion", "honorific": "companion"},
        {"source": "Aisha", "aliases": [], "target": "Aisha", "category": "companion", "honorific": "companion", "gender": "f"},
        {"source": "Sahih al-Bukhari", "aliases": ["Bukhari"], "target": "Sahih Bukhari", "category": "book", "honorific": ""},
        {"source": "Makkah", "aliases": ["Mecca"], "target": "Makkah", "category": "place", "honorific": ""},
        {"source": "cat", "aliases": [], "target": "billi", "category": "other", "honorific": ""},
        {"source": "Zakat", "aliases": [], "target": "Zakat", "category": "fiqh_ibadah", "honorific": ""},
    ],
}

TEXT = ("Tawheed is the right of Allah. Abu Huraira narrated in Bukhari that the Prophet went to Mecca. "
        "Ibn Taymiyyah wrote about it, and Ibn Taymiyyah was clear. The category of Bukharian scholars is large. "
        "Later, Ibn Taymiyyah repeated this. Shaykh Muhammad ibn Abdul Wahhab agreed. Shaykh Muhammad ibn Abdul Wahhab said so.")


class GlossaryTests(unittest.TestCase):
    def _run(self, tmp, domain="islamic", text=TEXT):
        out = Path(tmp) / "run"
        (out / "work").mkdir(parents=True)
        (out / "work" / "input.md").write_text(text, encoding="utf-8")
        (out / "work" / "chunk0001.md").write_text(text, encoding="utf-8")
        (out / "config.json").write_text(json.dumps({"domain": domain}), encoding="utf-8")
        b = Path(tmp) / "builtin.json"
        b.write_text(json.dumps(BUILTIN), encoding="utf-8")
        return out, b

    def test_seed_only_present_terms(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, b = self._run(tmp)
            with contextlib.redirect_stdout(io.StringIO()):
                data = glossary.cmd_seed(out, builtin=b)
            sources = {t["source"] for t in data["terms"]}
            self.assertEqual(sources, {"Tawhid", "Abu Hurairah", "Sahih al-Bukhari", "Makkah"})
            self.assertNotIn("cat", sources)  # "category" must not match
            self.assertEqual(len(data["honorifics"]), 2)
            self.assertEqual(data["domain"], "islamic")

    def test_seed_general_limits_categories(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, b = self._run(tmp, domain="general")
            with contextlib.redirect_stdout(io.StringIO()):
                data = glossary.cmd_seed(out, builtin=b)
            self.assertEqual({t["source"] for t in data["terms"]}, {"Sahih al-Bukhari", "Makkah"})

    def test_seed_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, b = self._run(tmp)
            with contextlib.redirect_stdout(io.StringIO()):
                glossary.cmd_seed(out, builtin=b)
                data = glossary.load(out)
                data["terms"][0]["target"] = "EDITED"
                glossary.save(out, data)
                glossary.cmd_seed(out, builtin=b)
            self.assertEqual(glossary.load(out)["terms"][0]["target"], "EDITED")

    def test_extract_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, b = self._run(tmp)
            with contextlib.redirect_stdout(io.StringIO()):
                glossary.cmd_seed(out, builtin=b)
            cands = glossary.cmd_extract_candidates(out, min_freq=2)
            names = [c["source"] for c in cands]
            self.assertIn("Ibn Taymiyyah", names)
            self.assertIn("Shaykh Muhammad ibn Abdul Wahhab", names)
            self.assertNotIn("Tawheed", names)   # covered by glossary
            self.assertNotIn("The", names)        # sentence-initial stopword
            self.assertNotIn("Later", names)      # sentence-initial only
            top = cands[0]
            self.assertEqual(top["source"], "Ibn Taymiyyah")
            self.assertEqual(top["frequency"], 3)
            self.assertTrue(top["contexts"])

    def test_add_rejects_collisions_and_validates(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, b = self._run(tmp)
            with contextlib.redirect_stdout(io.StringIO()):
                glossary.cmd_seed(out, builtin=b)
            new = Path(tmp) / "new.json"
            new.write_text(json.dumps([
                {"source": "Ibn Taymiyyah", "aliases": ["Ibn Taymiyya"], "target": "Ibn Taimiyyah", "category": "scholar", "honorific": "scholar_deceased"},
                {"source": "Mecca", "target": "Makkah", "category": "place", "honorific": ""},
                {"source": "Broken", "target": "x"},
            ]), encoding="utf-8")
            res = glossary.cmd_add(out, new)
            self.assertEqual(res["added"], 1)
            self.assertEqual(len(res["skipped"]), 1)
            self.assertEqual(len(res["errors"]), 1)
            self.assertEqual(glossary.validate_data(glossary.load(out)), [])

    def test_validate_detects_duplicate_surface_and_bad_honorific(self):
        data = json.loads(json.dumps(BUILTIN))
        data["terms"].append({"source": "Mecca", "target": "x", "category": "place", "honorific": "nope"})
        errs = glossary.validate_data(data)
        self.assertTrue(any("already belongs" in e for e in errs))
        self.assertTrue(any("unknown honorific" in e for e in errs))

    def test_print_terms_for_chunk_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, b = self._run(tmp)
            with contextlib.redirect_stdout(io.StringIO()):
                glossary.cmd_seed(out, builtin=b)
                glossary.cmd_count_frequencies(out)
            table = glossary.cmd_print_terms_for_chunk(out, "chunk0001.md")
            self.assertIn("| English | Aliases | Roman Urdu | Honorific | Note |", table)
            self.assertIn("| Abu Hurairah | Abu Huraira | Abu Hurairah | (Radiallahu Anhu) |", table)
            self.assertIn("| Sahih al-Bukhari | Bukhari | Sahih Bukhari |  |", table)
            # Zakat did not occur and has zero frequency -> not in table
            self.assertNotIn("Zakat", table)

    def test_print_terms_top_n_includes_frequent_absent_terms(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, b = self._run(tmp)
            with contextlib.redirect_stdout(io.StringIO()):
                glossary.cmd_seed(out, builtin=b)
                glossary.cmd_count_frequencies(out)
            (out / "work" / "chunk0002.md").write_text("Nothing relevant here.", encoding="utf-8")
            table = glossary.cmd_print_terms_for_chunk(out, "chunk0002.md")
            self.assertIn("Tawhid", table)  # top-N by frequency

    def test_female_honorific(self):
        term = {"source": "Aisha", "target": "Aisha", "honorific": "companion", "gender": "f"}
        self.assertEqual(glossary.honorific_text(term, BUILTIN["honorifics"]), "(Radiallahu Anha)")
        term["plural"] = True
        self.assertEqual(glossary.honorific_text(term, BUILTIN["honorifics"]), "(Radiallahu Anhum)")

    def test_no_glossary_prints_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, _ = self._run(tmp)
            self.assertEqual(glossary.cmd_print_terms_for_chunk(out, "chunk0001.md"), "")


if __name__ == "__main__":
    unittest.main()
