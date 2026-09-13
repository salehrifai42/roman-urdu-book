import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import detect_domain  # noqa: E402

MINI_GLOSSARY = {
    "detection": {"min_distinct_terms": 3, "min_hits_per_1000_words": 3.0,
                  "strong_min_hits_per_1000_words": 1.5,
                  "strong_terms": ["Allah", "Qur'an", "hadith", "Prophet Muhammad", "Sunnah"]},
    "terms": [
        {"source": "Tawhid", "aliases": ["Tawheed"], "target": "Tauheed", "category": "aqeedah", "honorific": ""},
        {"source": "Shirk", "aliases": [], "target": "Shirk", "category": "aqeedah", "honorific": ""},
        {"source": "Abu Hurairah", "aliases": ["Abu Huraira"], "target": "Abu Hurairah", "category": "companion", "honorific": "companion"},
        {"source": "prayer", "aliases": ["Salah"], "target": "Namaz", "category": "fiqh_ibadah", "honorific": ""},
        {"source": "cat", "aliases": [], "target": "billi", "category": "other", "honorific": ""},
    ],
}

ISLAMIC = ("Tawhid is the foundation of Islam. Allah commanded the Prophet Muhammad to call to Tawheed and to warn "
           "against Shirk. Abu Hurairah narrated a hadith about prayer. The Qur'an and the Sunnah explain Salah. " * 3)
GENERAL = ("The category of small mammals includes the domestic animal known for hunting mice. Economic policy in the "
           "nineteenth century shaped the railway industry across Europe and North America. " * 5)


class DetectDomainTests(unittest.TestCase):
    def _setup(self, tmp, text, glossary=MINI_GLOSSARY):
        out = Path(tmp) / "run"
        (out / "work").mkdir(parents=True)
        (out / "work" / "input.md").write_text(text, encoding="utf-8")
        (out / "config.json").write_text(json.dumps({"domain": "auto"}), encoding="utf-8")
        gpath = Path(tmp) / "g.json"
        gpath.write_text(json.dumps(glossary), encoding="utf-8")
        return out, gpath

    def test_islamic_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, g = self._setup(tmp, ISLAMIC)
            res = detect_domain.run(out, glossary_path=g)
            self.assertEqual(res["domain"], "islamic")
            cfg = json.loads((out / "config.json").read_text())
            self.assertEqual(cfg["domain"], "islamic")
            self.assertEqual(cfg["domain_detection"]["domain"], "islamic")

    def test_general_text_and_word_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, g = self._setup(tmp, GENERAL)
            res = detect_domain.run(out, glossary_path=g)
            self.assertEqual(res["domain"], "general")
            self.assertEqual(res["distinct_terms"], 0)  # "category" must not match "cat"
            self.assertEqual(res["confidence"], "high")

    def test_override_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, g = self._setup(tmp, GENERAL)
            res = detect_domain.run(out, domain_override="islamic", glossary_path=g)
            self.assertEqual(res["domain"], "islamic")
            self.assertEqual(res["confidence"], "override")
            self.assertEqual(res["auto_domain"], "general")

    def test_low_confidence_near_threshold(self):
        stats = {"distinct_terms": 3, "hits_per_1000_words": 3.1, "strong_hits_per_1000_words": 0.0}
        domain, conf = detect_domain.decide(stats, MINI_GLOSSARY["detection"])
        self.assertEqual(domain, "islamic")
        self.assertEqual(conf, "low")

    def test_missing_glossary_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, _ = self._setup(tmp, ISLAMIC)
            res = detect_domain.run(out, glossary_path=Path(tmp) / "nope.json")
            self.assertEqual(res["domain"], "islamic")

    def test_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, g = self._setup(tmp, ISLAMIC)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = detect_domain.main([str(out), "--glossary", str(g)])
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(buf.getvalue())["domain"], "islamic")


if __name__ == "__main__":
    unittest.main()
