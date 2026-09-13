import contextlib
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import doctor  # noqa: E402


class DoctorTests(unittest.TestCase):
    def test_report_shape(self):
        rep = doctor.report()
        for key in ("python", "pandoc", "pdf_extractors", "pdf_renderers", "supported_inputs",
                    "supported_outputs", "install_hints"):
            self.assertIn(key, rep)
        self.assertIsInstance(rep["pandoc"]["ok"], bool)

    def test_missing_pandoc_hint(self):
        with mock.patch.object(doctor, "find_binary", return_value=None), \
             mock.patch.object(doctor, "has_module", return_value=False), \
             mock.patch.object(doctor, "find_chrome", return_value=None):
            rep = doctor.report()
        self.assertFalse(rep["pandoc"]["ok"])
        self.assertIn("pandoc", rep["install_hints"])
        self.assertIn("pdf_input", rep["install_hints"])
        self.assertIn("pdf_output", rep["install_hints"])
        self.assertEqual(rep["pdf_extractors"], [])
        self.assertNotIn("pdf", rep["supported_outputs"])

    def test_json_cli_never_raises(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = doctor.main(["--json"])
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertIn("pandoc", data)

    def test_find_chrome_env_override(self):
        with mock.patch.dict(os.environ, {"ROMAN_URDU_CHROME": sys.executable}):
            self.assertEqual(doctor.find_chrome(), sys.executable)

    def test_find_chrome_none(self):
        with mock.patch.dict(os.environ, {"ROMAN_URDU_CHROME": ""}), \
             mock.patch.object(doctor, "_chrome_candidates", return_value=[]), \
             mock.patch.object(doctor, "find_binary", return_value=None):
            self.assertIsNone(doctor.find_chrome())


if __name__ == "__main__":
    unittest.main()
