import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import render_pdf as R  # noqa: E402


class FindChromeTests(unittest.TestCase):
    def test_env_override_wins(self):
        with tempfile.TemporaryDirectory() as d:
            fake = Path(d) / "mychrome"
            fake.write_text("#!/bin/sh\n")
            fake.chmod(0o755)
            with mock.patch.dict(os.environ, {"ROMAN_URDU_CHROME": str(fake)}):
                self.assertEqual(R.find_chrome(), str(fake))

    def test_mac_bundle_candidates(self):
        wanted = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ROMAN_URDU_CHROME", None)
            with mock.patch("platform.system", return_value="Darwin"), \
                 mock.patch("os.path.isfile", side_effect=lambda p: p == wanted), \
                 mock.patch("os.access", return_value=True), \
                 mock.patch("shutil.which", return_value=None):
                self.assertEqual(R.find_chrome(), wanted)

    def test_linux_binary_fallback(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ROMAN_URDU_CHROME", None)
            with mock.patch("platform.system", return_value="Linux"), \
                 mock.patch("os.path.isfile", return_value=False), \
                 mock.patch("shutil.which", side_effect=lambda n: "/usr/bin/chromium" if n == "chromium" else None):
                self.assertEqual(R.find_chrome(), "/usr/bin/chromium")

    def test_none_when_nothing_found(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ROMAN_URDU_CHROME", None)
            with mock.patch("platform.system", return_value="Linux"), \
                 mock.patch("os.path.isfile", return_value=False), \
                 mock.patch("shutil.which", return_value=None):
                self.assertIsNone(R.find_chrome())


class ChromeCommandTests(unittest.TestCase):
    def test_flags_present(self):
        with tempfile.TemporaryDirectory() as d:
            html = Path(d) / "book.html"
            html.write_text("<p>x</p>")
            cmd = R.chrome_command("/usr/bin/chrome", str(html), str(Path(d) / "book.pdf"), d)
            self.assertEqual(cmd[0], "/usr/bin/chrome")
            self.assertIn("--headless=new", cmd)
            self.assertTrue(any(a.startswith("--print-to-pdf=") for a in cmd))
            self.assertTrue(any(a.startswith("--user-data-dir=") for a in cmd))
            self.assertIn("--no-pdf-header-footer", cmd)
            self.assertTrue(cmd[-1].startswith("file://"))


class RenderTests(unittest.TestCase):
    def test_no_renderer_reports_skip(self):
        with tempfile.TemporaryDirectory() as d:
            html = Path(d) / "book.html"
            html.write_text("<p>x</p>")
            with mock.patch.object(R, "available_renderers", return_value=[]):
                ok, name, msg = R.render(str(html), str(Path(d) / "book.pdf"))
            self.assertFalse(ok)
            self.assertIsNone(name)
            self.assertIn("no PDF renderer", msg)

    def test_preferred_renderer_missing(self):
        with tempfile.TemporaryDirectory() as d:
            html = Path(d) / "book.html"
            html.write_text("<p>x</p>")
            with mock.patch.object(R, "available_renderers", return_value=[("chrome", "/x/chrome")]):
                ok, name, msg = R.render(str(html), str(Path(d) / "book.pdf"), preferred="wkhtmltopdf")
            self.assertFalse(ok)
            self.assertIn("wkhtmltopdf", msg)

    def test_fallback_order_and_magic_validation(self):
        with tempfile.TemporaryDirectory() as d:
            html = Path(d) / "book.html"
            html.write_text("<p>x</p>")
            pdf = Path(d) / "book.pdf"
            calls = []

            def fake_chrome(chrome, h, p, timeout=180):
                calls.append("chrome")
                Path(p).write_bytes(b"not a pdf")  # invalid -> must fall through
                return False, "bad"

            def fake_wk(exe, h, p, timeout=180, page_size="A5"):
                calls.append("wkhtmltopdf")
                Path(p).write_bytes(b"%PDF-1.4\n" + b"0" * 2048)
                return True, ""

            with mock.patch.object(R, "available_renderers", return_value=[("chrome", "/x"), ("wkhtmltopdf", "/y")]), \
                 mock.patch.object(R, "render_with_chrome", fake_chrome), \
                 mock.patch.object(R, "render_with_wkhtmltopdf", fake_wk):
                ok, name, msg = R.render(str(html), str(pdf))
            self.assertTrue(ok)
            self.assertEqual(name, "wkhtmltopdf")
            self.assertEqual(calls, ["chrome", "wkhtmltopdf"])

    def test_pdf_validation(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.pdf"
            p.write_bytes(b"%PDF-1.7\n" + b"x" * 10)
            self.assertFalse(R._pdf_is_valid(str(p)))  # too small
            p.write_bytes(b"%PDF-1.7\n" + b"x" * 2000)
            self.assertTrue(R._pdf_is_valid(str(p)))
            p.write_bytes(b"HTML" + b"x" * 2000)
            self.assertFalse(R._pdf_is_valid(str(p)))

    def test_missing_html(self):
        ok, name, msg = R.render("/nonexistent/book.html", "/tmp/x.pdf")
        self.assertFalse(ok)
        self.assertIn("HTML not found", msg)


if __name__ == "__main__":
    unittest.main()
