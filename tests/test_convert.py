import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import convert  # noqa: E402

HAS_PANDOC = shutil.which("pandoc") is not None


class CleanMarkdownTests(unittest.TestCase):
    def test_strips_attrs_divs_fences_and_breaks(self):
        src = "﻿# Title {#sec .unnumbered}\n\n::: {.note}\n<div>\nText here\\\n</div>\n:::\n\n\n\nMore"
        out = convert.clean_markdown(src)
        self.assertEqual(out, "# Title\n\nText here\n\nMore\n")

    def test_keeps_code_fence_braces(self):
        src = "```js\nconst x = {a: 1}\n```\n"
        self.assertIn("{a: 1}", convert.clean_markdown(src))


class ReflowPdfTests(unittest.TestCase):
    def test_joins_wrapped_lines_and_dehyphenates(self):
        raw = "This is a sen-\ntence that wraps\nacross lines.\n\nNext para."
        out = convert.reflow_pdf_text(raw)
        self.assertIn("This is a sentence that wraps across lines.", out)
        self.assertIn("Next para.", out)

    def test_drops_running_headers_and_page_numbers(self):
        pages = []
        for i in range(1, 7):
            pages.append(f"Book Title Header\n\nBody text of page {i} ends here.\n\n{i}\n")
        out = convert.reflow_pdf_text("\f".join(pages))
        self.assertNotIn("Book Title Header", out)
        self.assertIn("Body text of page 3 ends here.", out)
        self.assertNotIn("\n\n3\n", out)

    def test_keeps_years_and_footnote_lines(self):
        raw = "Something happened.\n\n1984\n\nThen more text.\n\n12 See the earlier discussion.\n"
        out = convert.reflow_pdf_text(raw)
        self.assertIn("1984", out)
        self.assertIn("12 See the earlier discussion.", out)

    def test_promotes_caps_heading(self):
        raw = "THE MEANING OF TAWHID\n\nTawhid means singling out Allah in worship."
        out = convert.reflow_pdf_text(raw)
        self.assertIn("## The Meaning Of Tawhid", out)

    def test_keep_page_numbers_flag(self):
        pages = [f"Text {i}.\n\n{i}\n" for i in range(1, 7)]
        out = convert.reflow_pdf_text("\f".join(pages), keep_page_numbers=True)
        self.assertIn("\n4\n", out + "\n")


class TxtTests(unittest.TestCase):
    def test_txt_to_markdown_reflows_paragraphs(self):
        out = convert.txt_to_markdown("Chapter One\n\nline a\nline b\n\nline c\n")
        self.assertEqual(out, "## Chapter One\n\nline a line b\n\nline c\n")


class ChunkerTests(unittest.TestCase):
    def test_splits_at_headings_and_respects_target(self):
        paras = "\n\n".join(["Paragraph " + str(i) + " " + "x" * 200 for i in range(10)])
        md = "# A\n\n" + paras + "\n\n# B\n\n" + paras
        chunks = convert.merge_blocks_to_chunks(convert.parse_structural_blocks(md), target_size=1000)
        self.assertGreater(len(chunks), 2)
        for c in chunks:
            self.assertLessEqual(len(c), 2100)
        self.assertTrue(any(c.startswith("# B") for c in chunks))
        self.assertEqual("".join(chunks).count("Paragraph"), 20)

    def test_small_doc_single_chunk(self):
        md = "# T\n\nshort\n"
        chunks = convert.merge_blocks_to_chunks(convert.parse_structural_blocks(md), 4500)
        self.assertEqual(len(chunks), 1)

    def test_oversized_block_force_split(self):
        big = "```\n" + "\n".join("line %d" % i for i in range(3000)) + "\n```"
        chunks = convert.merge_blocks_to_chunks(convert.parse_structural_blocks(big), 1000)
        self.assertGreater(len(chunks), 5)
        for c in chunks:
            self.assertTrue(c.startswith("```"))
            self.assertTrue(c.rstrip().endswith("```"))

    def test_list_and_table_blocks_not_split(self):
        md = "Intro\n\n- a\n- b\n- c\n\n| h1 | h2 |\n|---|---|\n| 1 | 2 |\n"
        blocks = convert.parse_structural_blocks(md)
        types = [b for _, b in blocks]
        self.assertIn("list", types)
        self.assertIn("table", types)


class PageNumberTests(unittest.TestCase):
    def test_monotonic_sequence_detected_outliers_kept(self):
        lines = ["a", "1", "b", "2", "c", "1984", "d", "3", "e", "4", "f", "5"]
        drop = convert._detect_page_number_lines(lines)
        self.assertEqual(sorted(lines[i] for i in drop), ["1", "2", "3", "4", "5"])


class ConvertRunTests(unittest.TestCase):
    def _run(self, tmp, name="book.md", content="# Sample Book\n\nOne.\n\n## Two\n\nTwo text.\n", **kw):
        src = Path(tmp) / name
        src.write_text(content, encoding="utf-8")
        out_dir = Path(tmp) / "run"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cfg, summary = convert.convert(str(src), str(out_dir), **kw)
        return src, out_dir, cfg, summary

    def test_markdown_run_layout_and_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, out_dir, cfg, summary = self._run(tmp)
            self.assertTrue((out_dir / "work" / "chunk0001.md").exists())
            self.assertTrue((out_dir / "work" / "manifest.json").exists())
            self.assertTrue((out_dir / "work" / "source_fingerprint.json").exists())
            self.assertTrue((out_dir / "media").is_dir())
            data = json.loads((out_dir / "config.json").read_text())
            for key in ("version", "input_file", "input_format", "conversion_method", "chunk_size",
                        "chunk_count", "source", "domain", "domain_detection", "book", "created", "skill_version"):
                self.assertIn(key, data)
            self.assertEqual(data["source"]["title"], "Sample Book")
            self.assertEqual(data["domain"], "auto")
            self.assertEqual(summary["chunk_count"], 1)

    def test_txt_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, out_dir, cfg, _ = self._run(tmp, name="b.txt", content="Title Here\n\npara one\nline two\n")
            self.assertEqual(cfg["conversion_method"], "text")
            self.assertIn("para one line two", (out_dir / "work" / "input.md").read_text())

    def test_rerun_reuses_chunks_and_fingerprint_mismatch_aborts(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, out_dir, _, s1 = self._run(tmp)
            (out_dir / "work" / "output_chunk0001.md").write_text("done", encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                _, s2 = convert.convert(str(src), str(out_dir))
            self.assertTrue(s2["reused"])
            self.assertTrue((out_dir / "work" / "output_chunk0001.md").exists())
            src.write_text("# Changed\n\nDifferent bytes.\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                with contextlib.redirect_stdout(io.StringIO()):
                    convert.convert(str(src), str(out_dir))
            with contextlib.redirect_stdout(io.StringIO()):
                cfg, s3 = convert.convert(str(src), str(out_dir), force=True)
            self.assertFalse(s3["reused"])
            self.assertEqual(cfg["source"]["title"], "Changed")

    def test_cli_last_line_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "x.md"
            src.write_text("# X\n\ntext\n", encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = convert.main([str(src), "--out-dir", str(Path(tmp) / "r")])
            self.assertEqual(rc, 0)
            last = buf.getvalue().strip().splitlines()[-1]
            self.assertEqual(json.loads(last)["title"], "X")

    def test_unsupported_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "x.xyz"
            src.write_text("hi", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                convert.convert(str(src), str(Path(tmp) / "r"))


class PdfFallbackTests(unittest.TestCase):
    def test_extractor_order_and_fallback(self):
        calls = []

        def fail(_):
            calls.append("pdftotext")
            raise RuntimeError("boom")

        def ok(_):
            calls.append("pymupdf")
            return "Hello\fWorld"

        with mock.patch.dict(convert.EXTRACTORS, {"pdftotext": fail, "pymupdf": ok}), \
             mock.patch.object(convert.doctor, "find_pdf_extractors", return_value=["pdftotext", "pymupdf"]):
            text, method = convert.extract_pdf_text("x.pdf", "auto")
        self.assertEqual(method, "pymupdf")
        self.assertEqual(calls, ["pdftotext", "pymupdf"])

    def test_no_extractor_error_mentions_install(self):
        with mock.patch.object(convert.doctor, "find_pdf_extractors", return_value=[]):
            with self.assertRaises(RuntimeError) as ctx:
                convert.extract_pdf_text("x.pdf", "auto")
        self.assertIn("pip install pypdf", str(ctx.exception))

    def test_pdf_cli_exit_2_without_extractor(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "x.pdf"
            src.write_bytes(b"%PDF-1.4 fake")
            with mock.patch.object(convert.doctor, "find_pdf_extractors", return_value=[]):
                err = io.StringIO()
                with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                    rc = convert.main([str(src), "--out-dir", str(Path(tmp) / "r")])
            self.assertEqual(rc, 2)
            self.assertIn("Install one of", err.getvalue())


@unittest.skipUnless(HAS_PANDOC, "pandoc not installed")
class PandocRoundTripTests(unittest.TestCase):
    def test_docx_roundtrip(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            md = Path(tmp) / "s.md"
            md.write_text("---\ntitle: Round Trip\nauthor: Some Author\n---\n\n# Heading One\n\nBody *text* here.\n\n- item a\n- item b\n", encoding="utf-8")
            docx = Path(tmp) / "s.docx"
            subprocess.run(["pandoc", str(md), "-o", str(docx)], check=True)
            with contextlib.redirect_stdout(io.StringIO()):
                cfg, summary = convert.convert(str(docx), str(Path(tmp) / "r"))
            text = (Path(tmp) / "r" / "work" / "input.md").read_text()
            self.assertIn("# Heading One", text)
            self.assertIn("- item a", text)
            self.assertEqual(cfg["source"]["title"], "Round Trip")
            self.assertEqual(cfg["source"]["author"], "Some Author")
            self.assertEqual(cfg["conversion_method"], "pandoc")


if __name__ == "__main__":
    unittest.main()
