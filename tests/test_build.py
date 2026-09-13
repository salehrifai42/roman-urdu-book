import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import build as B  # noqa: E402

PANDOC = shutil.which("pandoc")

CHUNK1 = """# Muqaddimah

Tamam tareefen Allah Ta'ala ke liye hain. Rasoolullah (Sallallahu Alaihi Wasallam) ne farmaya:

> "Amaal ka daromadaar niyyaton par hai." (Sahih Bukhari: 1)

قُلْ هُوَ اللَّهُ أَحَدٌ
اللَّهُ الصَّمَدُ

"Kahiye: Woh Allah ek hai." (Surah Al-Ikhlas: 1)

Lafz **بسم الله** se shuru karein.[^1]

[^1]: Yeh ek hashiya hai.
"""

CHUNK2 = """# Tauheed Ki Tareef

## Tauheed Ki Aqsaam

1. Tauheed-e-Rububiyat
2. Tauheed-e-Uluhiyat
"""


def make_run(d, outputs=None, with_manifest=True):
    work = Path(d) / "work"
    work.mkdir(parents=True, exist_ok=True)
    srcs = {"chunk0001.md": CHUNK1, "chunk0002.md": CHUNK2}
    outputs = outputs if outputs is not None else srcs
    for name, text in srcs.items():
        (work / name).write_text(text, encoding="utf-8")
    for name, text in outputs.items():
        (work / f"output_{name}").write_text(text, encoding="utf-8")
    if with_manifest:
        manifest = {
            "chunk_count": 2,
            "source_hash": "",
            "chunks": [
                {"id": "chunk0002", "order": 2, "source_file": "chunk0002.md", "source_hash": "", "output_file": "output_chunk0002.md"},
                {"id": "chunk0001", "order": 1, "source_file": "chunk0001.md", "source_hash": "", "output_file": "output_chunk0001.md"},
            ],
        }
        (work / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return work


class WrapArabicTests(unittest.TestCase):
    def test_whole_line_runs_become_block(self):
        md = "Intro\n\nقُلْ هُوَ اللَّهُ أَحَدٌ\nاللَّهُ الصَّمَدُ\n\nAfter\n"
        out = B.wrap_arabic_runs(md)
        self.assertIn('::: {.arabic-block dir="rtl" lang="ar"}\nقُلْ هُوَ اللَّهُ أَحَدٌ\nاللَّهُ الصَّمَدُ\n:::', out)
        self.assertTrue(out.startswith("Intro\n\n"))
        self.assertTrue(out.endswith("After\n"))

    def test_inline_runs_become_span(self):
        out = B.wrap_arabic_runs("Lafz بسم الله se shuru.")
        self.assertEqual(out, 'Lafz [بسم الله]{.arabic dir="rtl" lang="ar"} se shuru.')

    def test_latin_and_code_untouched(self):
        md = "Plain line.\n\n```\nقُلْ\n```\n\n- list با item\n"
        out = B.wrap_arabic_runs(md)
        self.assertIn("```\nقُلْ\n```", out)
        self.assertIn("Plain line.", out)
        self.assertIn('- list [با]{.arabic dir="rtl" lang="ar"} item', out)

    def test_idempotent(self):
        once = B.wrap_arabic_runs(CHUNK1)
        self.assertEqual(B.wrap_arabic_runs(once), once)


class FrontMatterTests(unittest.TestCase):
    def test_yaml_and_front_matter_block(self):
        fm = B.compose_front_matter('Aasan "Tauheed"', None, "Author", "Trans", "Pub", date="2026")
        self.assertTrue(fm.startswith("---\n"))
        self.assertIn('title: "Aasan \\"Tauheed\\""', fm)
        self.assertIn('subtitle: "Roman Urdu Tarjuma"', fm)
        self.assertIn("lang: ur-Latn", fm)
        self.assertIn("**Taleef:** Author", fm)
        self.assertIn("**Tarjuma:** Trans", fm)
        self.assertIn("::: {.front-matter}", fm)

    def test_no_front_matter_block_without_people(self):
        fm = B.compose_front_matter("T", "S")
        self.assertNotIn(".front-matter", fm)


class MergeTests(unittest.TestCase):
    def test_merge_in_manifest_order(self):
        with tempfile.TemporaryDirectory() as d:
            work = make_run(d)
            merged, errors = B.merge_chunks(str(work))
            self.assertEqual(errors, [])
            self.assertLess(merged.index("Muqaddimah"), merged.index("Tauheed Ki Tareef"))

    def test_blank_output_aborts(self):
        with tempfile.TemporaryDirectory() as d:
            work = make_run(d, outputs={"chunk0001.md": CHUNK1, "chunk0002.md": "  \n"})
            merged, errors = B.merge_chunks(str(work))
            self.assertIsNone(merged)
            self.assertTrue(errors)

    def test_missing_output_aborts_without_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            work = make_run(d, outputs={"chunk0001.md": CHUNK1}, with_manifest=False)
            merged, errors = B.merge_chunks(str(work))
            self.assertIsNone(merged)
            self.assertTrue(any("missing output" in e for e in errors))

    def test_image_parity(self):
        with tempfile.TemporaryDirectory() as d:
            src2 = CHUNK2 + "\n![Fig](media/a.png)\n"
            work = make_run(d, outputs={"chunk0001.md": CHUNK1, "chunk0002.md": CHUNK2})
            (work / "chunk0002.md").write_text(src2, encoding="utf-8")
            merged, errors = B.merge_chunks(str(work))
            self.assertIsNone(merged)
            self.assertTrue(any("image references diverge" in e for e in errors))

    def test_malformed_img_detected(self):
        errs = B.validate_chunk_images.__globals__["_scan_img_tags"]('<img alt="a "b" c" src="x.png">')[1]
        self.assertTrue(errs)


class BuildNoPandocTests(unittest.TestCase):
    def test_pandoc_missing_skips_formats_but_writes_md(self):
        with tempfile.TemporaryDirectory() as d:
            make_run(d)
            with mock.patch.object(B, "pandoc_path", return_value=None):
                result = B.build(d, "Title", author="A")
            self.assertIn("md", result["produced"])
            for fmt in ("html", "docx", "epub", "pdf"):
                self.assertIn(fmt, result["skipped"])
            self.assertTrue(Path(d, "book.md").exists())

    def test_missing_work_dir(self):
        with tempfile.TemporaryDirectory() as d:
            result = B.build(d, "Title")
            self.assertIn("error", result)


@unittest.skipUnless(PANDOC, "pandoc not installed")
class BuildWithPandocTests(unittest.TestCase):
    def test_full_build_without_pdf_renderer(self):
        with tempfile.TemporaryDirectory() as d:
            make_run(d)
            import render_pdf
            with mock.patch.object(render_pdf, "available_renderers", return_value=[]):
                result = B.build(d, "Aasan Tauheed", author="Shaikh Test", translator="Mutarjim Test",
                                 publisher="Maktaba Test", export_name="aasan-tauheed")
            self.assertEqual(result.get("error"), None)
            for fmt in ("md", "html", "docx", "epub"):
                self.assertIn(fmt, result["produced"], result)
            self.assertIn("pdf", result["skipped"])
            self.assertIn("renderer", result["skipped"]["pdf"])

            html = Path(d, "book.html").read_text(encoding="utf-8")
            self.assertIn('dir="rtl"', html)
            self.assertIn("Fehrist-e-Mazaameen", html)
            self.assertIn("Aasan Tauheed", html)
            self.assertIn('class="cover"', html)
            self.assertIn("Taleef:", html)
            self.assertIn("Mutarjim Test", html)
            self.assertIn('class="arabic-block"', html)
            self.assertIn('<span class="arabic"', html)
            self.assertIn("<style>", html)
            self.assertNotIn("$css_inline$", html)
            self.assertNotIn('<link rel="stylesheet"', html)
            self.assertIn(".front-matter { display: none; }", html)

            with zipfile.ZipFile(Path(d, "book.docx")) as z:
                self.assertIn("word/document.xml", z.namelist())
            with zipfile.ZipFile(Path(d, "book.epub")) as z:
                names = z.namelist()
                self.assertIn("META-INF/container.xml", names)
                self.assertTrue(any(n.endswith(".css") for n in names))

            self.assertTrue(Path(d, "aasan-tauheed.epub").exists())
            self.assertTrue(Path(d, "aasan-tauheed.html").exists())

            md = Path(d, "book.md").read_text(encoding="utf-8")
            self.assertTrue(md.startswith("---\n"))
            self.assertIn('::: {.arabic-block dir="rtl" lang="ar"}', md)

    def test_formats_subset_and_cli(self):
        with tempfile.TemporaryDirectory() as d:
            make_run(d)
            rc = B.main([d, "--title", "T", "--formats", "md,html", "--cleanup"])
            self.assertEqual(rc, 0)
            self.assertTrue(Path(d, "book.html").exists())
            self.assertFalse(Path(d, "book.docx").exists())
            self.assertFalse(Path(d, "work", "merged.md").exists())

    def test_cli_fails_on_blank_chunk(self):
        with tempfile.TemporaryDirectory() as d:
            make_run(d, outputs={"chunk0001.md": CHUNK1, "chunk0002.md": ""})
            rc = B.main([d, "--title", "T", "--formats", "md,html"])
            self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
