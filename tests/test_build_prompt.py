import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import build_prompt  # noqa: E402
import glossary  # noqa: E402

BUILTIN = {
    "honorifics": [{"id": "companion", "target": "(Radiallahu Anhu)"}],
    "terms": [{"source": "Abu Hurairah", "aliases": [], "target": "Abu Hurairah", "category": "companion", "honorific": "companion"}],
}


class RenderTemplateTests(unittest.TestCase):
    def test_if_blocks_removed_when_empty(self):
        tpl = "A\n<!-- IF:X -->\nblock {X}\n<!-- ENDIF:X -->\nB {Y}\n"
        self.assertEqual(build_prompt.render_template(tpl, {"X": "", "Y": "y"}), "A\nB y\n")
        self.assertEqual(build_prompt.render_template(tpl, {"X": "val", "Y": "y"}), "A\nblock val\nB y\n")


class BuildTests(unittest.TestCase):
    def _run(self, tmp):
        out = Path(tmp) / "run"
        (out / "work").mkdir(parents=True)
        (out / "work" / "input.md").write_text("Abu Hurairah said. More.", encoding="utf-8")
        (out / "work" / "chunk0001.md").write_text("Abu Hurairah said.", encoding="utf-8")
        (out / "work" / "chunk0002.md").write_text("More text follows here.", encoding="utf-8")
        (out / "config.json").write_text(json.dumps({"domain": "islamic"}), encoding="utf-8")
        b = Path(tmp) / "b.json"
        b.write_text(json.dumps(BUILTIN), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            glossary.cmd_seed(out, builtin=b)
            glossary.cmd_count_frequencies(out)
        return out

    def test_translate_prompt_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._run(tmp)
            p = build_prompt.build(out, "chunk0001.md", "translate", custom_instructions="Keep it short.")
            self.assertEqual(build_prompt.unresolved_placeholders(p), [])
            self.assertIn(str(out / "work" / "chunk0001.md"), p)
            self.assertIn(str(out / "work" / "output_chunk0001.md"), p)
            self.assertIn("| Abu Hurairah |", p)
            self.assertIn("(Radiallahu Anhu)", p)
            self.assertIn("Next chunk excerpt", p)
            self.assertIn("Keep it short.", p)
            self.assertNotIn("THIS IS A RETRY", p)
            self.assertIn("Domain of this book: islamic", p)

    def test_empty_blocks_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._run(tmp)
            (out / "work" / "glossary.json").unlink()
            (out / "work" / "chunk0002.md").unlink()
            p = build_prompt.build(out, "chunk0001.md", "translate")
            self.assertNotIn("TERM TABLE", p)
            self.assertNotIn("NEIGHBOUR CONTEXT", p)
            self.assertNotIn("ADDITIONAL INSTRUCTIONS", p)
            self.assertNotIn("<!-- IF", p)
            self.assertEqual(build_prompt.unresolved_placeholders(p), [])

    def test_retry_embeds_lint_and_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._run(tmp)
            lint = out / "work" / "lint_chunk0001.json"
            lint.write_text(json.dumps({"chunk_id": "chunk0001", "errors": [{"code": "E_CITATION", "message": "Missing (Sahih Bukhari: 1)"}],
                                        "warnings": [{"code": "W_SPELLING", "message": "keh -> ke"}]}), encoding="utf-8")
            rev = out / "work" / "review_chunk0001.json"
            rev.write_text(json.dumps({"score": 2, "issues": [{"type": "honorific", "quote": "Nabi ne", "suggestion": "Nabi (Sallallahu Alaihi Wasallam) ne"}], "summary": "weak"}), encoding="utf-8")
            p = build_prompt.build(out, "chunk0001.md", "retry", lint_report=lint, review_report=rev)
            self.assertIn("THIS IS A RETRY", p)
            self.assertIn("E_CITATION", p)
            self.assertIn("keh -> ke", p)
            self.assertIn("Reviewer score: 2/5", p)
            self.assertIn("Nabi (Sallallahu Alaihi Wasallam) ne", p)

    def test_review_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._run(tmp)
            p = build_prompt.build(out, "chunk0001.md", "review")
            self.assertIn(str(out / "work" / "review_chunk0001.json"), p)
            self.assertIn("SCORING", p)
            self.assertEqual(build_prompt.unresolved_placeholders(p), [])

    def test_glossary_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._run(tmp)
            p = build_prompt.build(out, "chunk0001.md", "glossary", candidates=[{"source": "Ibn X", "frequency": 2, "contexts": []}])
            self.assertIn('"source": "Ibn X"', p)
            self.assertEqual(build_prompt.unresolved_placeholders(p), [])

    def test_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._run(tmp)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = build_prompt.main([str(out), "chunk0001.md", "--kind", "translate"])
            self.assertEqual(rc, 0)
            self.assertIn("FINAL SELF-CHECK", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
