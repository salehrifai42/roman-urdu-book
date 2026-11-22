import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import convert  # noqa: E402
import pdf_layout  # noqa: E402

# A synthetic pdf2xml document: body font 20pt (id 3), citation font 18pt (id 2),
# chapter font 27pt bold (id 0), bold body font (id 5). Body line pitch is 23,
# paragraph gap is 44 (as Word exports it).
_HEAD = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE pdf2xml SYSTEM "pdf2xml.dtd">
<pdf2xml producer="poppler" version="26.09.0">
"""
_FONTS = """<fontspec id="0" size="27" family="TNR-Bold" color="#800000"/>
<fontspec id="2" size="18" family="TNR" color="#000000"/>
<fontspec id="3" size="20" family="TNR" color="#000000"/>
<fontspec id="5" size="20" family="TNR-Bold" color="#0000ff"/>
"""


def _t(top, text, font="3", left=135, width=650, height=23):
    return f'<text top="{top}" left="{left}" width="{width}" height="{height}" font="{font}">{text}</text>\n'


def _page(n, body):
    return f'<page number="{n}" position="absolute" top="0" left="0" height="1188" width="918">\n{body}</page>\n'


def build_doc():
    p1 = (_FONTS
          + _t(109, "<b>My Book Title</b>", font="0", width=474, height=30)
          + _t(180, "English Translation", font="0", width=300, height=30)
          + _t(240, "Book by Some Author", width=330)
          + _t(299, "<b>Contents</b>", font="0", width=103, height=30)
          + _t(351, "<b>Introduction</b>", font="5", width=110)
          + _t(395, "<b>First Chapter</b>", font="5", width=216)
          + _t(440, "<b>Second Chapter</b>", font="5", width=173)
          + _t(520, "<b>Introduction</b>", font="0", width=200, height=30)
          + _t(580, "Bismillah Ar-Rahman Ar-Rahim", width=300)
          + _t(624, "Praise be to Allah, Lord of the Worlds, Who has said in His book {…and stand before Allah with obedience} [Al-")
          + _t(647, "Baqarah 2:238] and has said concerning the prayer that it is heavy except for the humble ones.")
          + _t(691, "Knowing that Allah responds to prayers", width=323)
          + _t(735, "The Prophet said something long enough to fill a full line of text on the page here.")
          + _t(758, "It was reported by Al-Hakim, and Al-Albani agreed with him in Sifat As-Salah,", font="2", width=541, height=20)
          + _t(779, "p. 89).", font="2", width=51, height=20)
          + _t(823, "A second paragraph that runs to the bottom of the page and continues on the")
          + _t(1100, "[ Table of Contents ]", width=170))
    p2 = (_t(120, "next page without a break because the sentence had not ended.")
          + _t(164, "1. First item of a list", width=200)
          + _t(187, "2. Second item of a list", width=200)
          + _t(231, "<b>First Chapter</b>", font="0", width=300, height=30)
          + _t(275, "Body text of the first chapter, which is a sentence.")
          + _t(319, "Warding off distractions and things that adversely", font="0", width=600, height=30)
          + _t(353, "affect Khushu", font="0", width=200, height=30)
          + _t(400, "More body text here, a complete sentence.")
          + _t(1100, "[ Table of Contents ]", width=170))
    p3 = (_t(120, "<b>Second Chapter</b>", font="0", width=300, height=30)
          + _t(170, "Last body paragraph of the document.")
          + _t(1100, "[ Table of Contents ]", width=170))
    return _HEAD + _page(1, p1) + _page(2, p2) + _page(3, p3) + "</pdf2xml>\n"


class LayoutMarkdownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.md = pdf_layout.markdown_from_xml(build_doc())
        cls.lines = cls.md.split("\n")

    def test_size_headings_become_h2(self):
        for h in ("## Introduction", "## First Chapter", "## Second Chapter"):
            self.assertIn(h, self.lines)

    def test_wrapped_size_heading_is_merged(self):
        self.assertIn("## Warding off distractions and things that adversely affect Khushu", self.lines)

    def test_plain_lone_line_is_h3(self):
        self.assertIn("### Knowing that Allah responds to prayers", self.lines)

    def test_title_block_is_not_headings(self):
        self.assertIn("My Book Title", self.lines)
        self.assertIn("English Translation", self.lines)
        self.assertIn("Book by Some Author", self.lines)
        self.assertNotIn("## My Book Title", self.lines)
        self.assertNotIn("### Book by Some Author", self.lines)
        self.assertEqual(self.lines[0], "My Book Title")

    def test_basmala_is_not_a_heading(self):
        self.assertIn("Bismillah Ar-Rahman Ar-Rahim", self.lines)
        self.assertFalse(any(l.startswith("#") and "Bismillah" in l for l in self.lines))

    def test_source_contents_block_dropped(self):
        self.assertNotIn("Contents", self.md)
        # each chapter title appears once (its heading), not twice (heading + TOC entry)
        self.assertEqual(self.md.count("Introduction"), 1)
        self.assertEqual(self.md.count("First Chapter"), 1)
        self.assertEqual(self.md.count("Second Chapter"), 1)

    def test_article_hyphen_kept_without_space(self):
        self.assertIn("[Al-Baqarah 2:238]", self.md)

    def test_page_reference_not_split_as_list_item(self):
        self.assertIn("Sifat As-Salah, p. 89).", self.md)
        self.assertNotIn("\n\np. 89).", self.md)

    def test_paragraph_continues_across_page_break(self):
        self.assertIn("continues on the next page without a break", self.md)

    def test_list_items_stay_separate_and_are_not_headings(self):
        self.assertIn("1. First item of a list", self.lines)
        self.assertIn("2. Second item of a list", self.lines)
        self.assertFalse(any(l.startswith("#") and "item of a list" in l for l in self.lines))

    def test_navigation_footer_dropped(self):
        self.assertNotIn("Table of Contents", self.md)

    def test_paragraph_gap_splits_paragraphs(self):
        self.assertIn("humble ones.\n\n### Knowing", self.md)


# A second layout, modelled on a Darussalam-style booklet: 18pt body (id 18),
# chapter headings only slightly larger and bold (20pt, id 16), a larger Qur'an
# font (21pt, id 20), cover title sizes 36/27, a cover spread over pages 1-3 and
# a bold body-size "Index" with wrapped entries in a 15pt font (id 32).
_FONTS2 = """<fontspec id="3" size="36" family="Cambria" color="#000000"/>
<fontspec id="7" size="27" family="Cambria" color="#000000"/>
<fontspec id="11" size="19" family="Cambria" color="#000000"/>
<fontspec id="16" size="20" family="Cambria" color="#3b772f"/>
<fontspec id="18" size="18" family="Cambria" color="#000000"/>
<fontspec id="20" size="21" family="KFGQPC" color="#177600"/>
<fontspec id="32" size="15" family="Cambria" color="#000000"/>
"""
_BODY_LINE = "a line of body text that runs the full width of the page here"


def _body(top, n):
    return "".join(_t(top + 21 * i, _BODY_LINE + ("." if i == n - 1 else ""), font="18", left=60, width=395, height=21)
                   for i in range(n))


def build_booklet():
    p1 = (_FONTS2
          + _t(60, "The Beneficial Means", font="3", left=80, width=300, height=40)
          + _t(110, "To A Happy Life", font="3", left=80, width=300, height=40)
          + _t(200, "Shaykh Abdur-Rahman As-Sa'di", font="11", left=80, width=300, height=21)
          + _t(222, "(may Allah have mercy upon him)", font="11", left=80, width=300, height=21))
    p3 = (_t(60, "<b>The Beneficial Means To</b>", font="7", left=80, width=300, height=30)
          + _t(95, "<b>A Happy Life</b>", font="7", left=80, width=300, height=30)
          + _t(150, "\u064e", font="20", left=200, width=0, height=24))
    p4 = (_t(60, "<b>Introduction</b>", font="16", left=200, width=100, height=23)
          + _body(90, 4)
          + _t(200, "<b>Chapter: Faith and righteous deeds</b>", font="16", left=109, width=313, height=23)
          + _body(225, 3)
          + _t(300, "\u0645\u064e\u0646\u0652 \u0639\u064e\u0645\u0650\u0644\u064e", font="20", left=100, width=300, height=27)
          + _body(340, 3)
          + _t(420, "<b>Chapter: Engaging in any of the righteous </b>", font="16", left=82, width=372, height=23)
          + _t(442, "<b>deeds or useful knowledge</b>", font="16", left=150, width=200, height=23)
          + _body(470, 3))
    p5 = (_t(60, "<b>Index</b>", font="18", left=200, width=50, height=21)
          + _t(90, "Introduction.................. 2", font="32", left=81, width=372, height=18)
          + _t(110, "Chapter: Faith and righteous deeds ........ 3", font="32", left=81, width=372, height=18)
          + _t(130, "Chapter: Engaging in any of the righteous deeds or useful", font="32", left=81, width=372, height=18)
          + _t(150, "knowledge ......................... 9", font="32", left=81, width=372, height=18))
    return _HEAD + _page(1, p1) + _page(3, p3) + _page(4, p4) + _page(5, p5) + "</pdf2xml>\n"


class BookletLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.md = pdf_layout.markdown_from_xml(build_booklet())
        cls.headings = [l for l in cls.md.split("\n") if l.startswith("#")]

    def test_slightly_larger_bold_lines_are_chapter_headings(self):
        self.assertEqual(self.headings, [
            "## Introduction",
            "## Chapter: Faith and righteous deeds",
            "## Chapter: Engaging in any of the righteous deeds or useful knowledge",
        ])

    def test_cover_across_pages_is_not_headings(self):
        self.assertIn("The Beneficial Means To A Happy Life", self.md)
        self.assertNotIn("# The Beneficial", self.md)

    def test_arabic_font_size_is_not_a_heading_level(self):
        self.assertIn("\u0645\u064e\u0646\u0652", self.md)
        self.assertFalse(any("\u0645" in h for h in self.headings))

    def test_lone_vowel_mark_lines_dropped(self):
        self.assertNotIn("\n\u064e\n", self.md)

    def test_bold_index_with_wrapped_entries_dropped(self):
        self.assertNotIn("Index", self.md)
        self.assertNotIn("knowledge ....", self.md)


class DropArabicTests(unittest.TestCase):
    def test_arabic_paragraphs_become_one_marker_per_run(self):
        md = ("Intro text.\n\n\u0645\u064e\u0646\u0652 \u0639\u064e\u0645\u0650\u0644\u064e\n\n"
              "\u0641\u064e\u0644\u064e\u0646\u064f\u062d\u0652\u064a\u0650\u064a\u064e\u0646\u0651\u064e\u0647\u064f\n\n"
              "{Whoever does righteous deeds} [Surat an-Nahl: 97]\n\n"
              "The Prophet (\u0635\u0644\u0649 \u0627\u0644\u0644\u0647 \u0639\u0644\u064a\u0647 \u0648\u0633\u0644\u0645) said this sentence in English.\n")
        out = convert.drop_arabic_paragraphs(md)
        paras = out.strip().split("\n\n")
        self.assertEqual(paras[1], convert.ARABIC_PLACEHOLDER)
        self.assertEqual(paras[2], "{Whoever does righteous deeds} [Surat an-Nahl: 97]")
        self.assertEqual(len(paras), 4)
        self.assertIn("\u0635\u0644\u0649", paras[3])  # inline honorific kept


class ErrorAndFallbackTests(unittest.TestCase):
    def test_unparseable_xml_raises_runtime_error(self):
        with self.assertRaises(RuntimeError):
            pdf_layout.markdown_from_xml("<pdf2xml><page number='1'><text top='1' left='1' width='9' height='9' font='0'>x")

    def test_empty_document_raises_runtime_error(self):
        with self.assertRaises(RuntimeError):
            pdf_layout.markdown_from_xml(_HEAD + _page(1, _FONTS) + "</pdf2xml>")

    def test_convert_prefers_pdftohtml_and_skips_reflow(self):
        with mock.patch.dict(convert.EXTRACTORS, {"pdftohtml": lambda _: "## Heading\n\nBody para.\n"}), \
             mock.patch.object(convert.doctor, "find_pdf_extractors", return_value=["pdftohtml", "pdftotext"]):
            text, method = convert.extract_pdf_text("x.pdf", "auto")
        self.assertEqual(method, "pdftohtml")
        self.assertIn(method, convert.LAYOUT_METHODS)
        self.assertEqual(text, "## Heading\n\nBody para.\n")

    def test_convert_falls_back_to_pdftotext(self):
        def boom(_):
            raise RuntimeError("no layout")

        with mock.patch.dict(convert.EXTRACTORS, {"pdftohtml": boom, "pdftotext": lambda _: "Plain text\fpage 2"}), \
             mock.patch.object(convert.doctor, "find_pdf_extractors", return_value=["pdftohtml", "pdftotext"]):
            text, method = convert.extract_pdf_text("x.pdf", "auto")
        self.assertEqual(method, "pdftotext")
        self.assertNotIn(method, convert.LAYOUT_METHODS)

    def test_pdf_method_order(self):
        self.assertEqual(convert.PDF_METHODS[0], "pdftohtml")
        self.assertIn("pdftohtml", convert.EXTRACTORS)


if __name__ == "__main__":
    unittest.main()
