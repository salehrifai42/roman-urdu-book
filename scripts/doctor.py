#!/usr/bin/env python3
"""
doctor.py - Report which converters and renderers are available for roman-urdu-book.

Exit code is always 0; the orchestrator reads the JSON (``--json``) and decides.
Shared discovery helpers (find_binary, has_module, find_chrome, ...) are imported
by convert.py and render_pdf.py so there is one source of truth for detection.
"""

import argparse
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys

SUPPORTED_INPUTS = ["pdf", "docx", "epub", "html", "htm", "md", "markdown", "txt", "odt", "rtf", "fb2"]
PANDOC_OUTPUTS = ["md", "html", "docx", "epub"]

INSTALL_HINTS = {
    "pandoc": "Install pandoc: macOS `brew install pandoc`; Debian/Ubuntu `sudo apt-get install pandoc`; "
              "Windows `choco install pandoc` or https://pandoc.org/installing.html",
    "pdftotext": "Install poppler for `pdftotext`: macOS `brew install poppler`; Debian/Ubuntu "
                 "`sudo apt-get install poppler-utils`; Windows: https://github.com/oschwartz10612/poppler-windows",
    "pymupdf": "`pip install pymupdf` (PyMuPDF, imported as `fitz`)",
    "pypdf": "`pip install pypdf`",
    "calibre": "Install Calibre so `ebook-convert` is on PATH: https://calibre-ebook.com/download",
    "chrome": "Install Google Chrome, Chromium, or Microsoft Edge (used headless to print book.html to PDF). "
              "Set ROMAN_URDU_CHROME=/path/to/binary to point at a custom location.",
    "wkhtmltopdf": "Install wkhtmltopdf: https://wkhtmltopdf.org/downloads.html",
    "weasyprint": "`pip install weasyprint` (needs Pango/Cairo system libraries)",
}


def find_binary(name):
    """Return the absolute path of an executable on PATH, or None."""
    return shutil.which(name)


def has_module(name):
    """True if a Python module can be imported (without importing it)."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError, AttributeError):
        return False


def _chrome_candidates():
    system = platform.system()
    home = os.path.expanduser("~")
    if system == "Darwin":
        apps = [
            "Google Chrome.app/Contents/MacOS/Google Chrome",
            "Chromium.app/Contents/MacOS/Chromium",
            "Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "Brave Browser.app/Contents/MacOS/Brave Browser",
        ]
        return [os.path.join(root, app) for root in ("/Applications", os.path.join(home, "Applications")) for app in apps]
    if system == "Windows":
        roots = [os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                 os.environ.get("LocalAppData", os.path.join(home, "AppData", "Local"))]
        rel = [r"Google\Chrome\Application\chrome.exe", r"Chromium\Application\chrome.exe",
               r"Microsoft\Edge\Application\msedge.exe", r"BraveSoftware\Brave-Browser\Application\brave.exe"]
        return [os.path.join(r, p) for r in roots if r for p in rel]
    return []


def find_chrome():
    """Locate a Chromium-based browser binary. Env ROMAN_URDU_CHROME wins."""
    env = os.environ.get("ROMAN_URDU_CHROME")
    if env and os.path.isfile(env):
        return env
    for cand in _chrome_candidates():
        if os.path.isfile(cand):
            return cand
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
                 "microsoft-edge", "microsoft-edge-stable", "brave-browser", "chrome"):
        path = find_binary(name)
        if path:
            return path
    return None


def find_pdf_extractors():
    """Ordered list of available PDF text extractors: pdftotext, pymupdf, pypdf, calibre."""
    found = []
    if find_binary("pdftotext"):
        found.append("pdftotext")
    if has_module("fitz"):
        found.append("pymupdf")
    if has_module("pypdf"):
        found.append("pypdf")
    if find_binary("ebook-convert"):
        found.append("calibre")
    return found


def find_pdf_renderers():
    """Ordered list of available HTML->PDF renderers as {kind, path} dicts."""
    found = []
    chrome = find_chrome()
    if chrome:
        found.append({"kind": "chrome", "path": chrome})
    wk = find_binary("wkhtmltopdf")
    if wk:
        found.append({"kind": "wkhtmltopdf", "path": wk})
    if has_module("weasyprint"):
        found.append({"kind": "weasyprint", "path": sys.executable})
    cal = find_binary("ebook-convert")
    if cal:
        found.append({"kind": "calibre", "path": cal})
    return found


def pandoc_info():
    path = find_binary("pandoc")
    if not path:
        return {"ok": False, "version": None, "path": None}
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=20).stdout
        first = out.splitlines()[0] if out else ""
        version = first.split()[1] if len(first.split()) > 1 else None
    except (OSError, subprocess.SubprocessError, IndexError):
        version = None
    return {"ok": True, "version": version, "path": path}


def report():
    pandoc = pandoc_info()
    extractors = find_pdf_extractors()
    renderers = find_pdf_renderers()
    supported_inputs = []
    if pandoc["ok"]:
        supported_inputs.extend(i for i in SUPPORTED_INPUTS if i != "pdf")
    else:
        supported_inputs.extend(["md", "markdown", "txt"])
    if extractors:
        supported_inputs.insert(0, "pdf")
    supported_outputs = ["md"]
    if pandoc["ok"]:
        supported_outputs = list(PANDOC_OUTPUTS)
    if renderers and pandoc["ok"]:
        supported_outputs.append("pdf")
    hints = {}
    if not pandoc["ok"]:
        hints["pandoc"] = INSTALL_HINTS["pandoc"]
    if not extractors:
        hints["pdf_input"] = "No PDF text extractor found. Install one of: " + " | ".join(
            INSTALL_HINTS[k] for k in ("pdftotext", "pymupdf", "pypdf", "calibre"))
    if not renderers:
        hints["pdf_output"] = "No HTML->PDF renderer found (book.pdf will be skipped). Install one of: " + " | ".join(
            INSTALL_HINTS[k] for k in ("chrome", "wkhtmltopdf", "weasyprint", "calibre"))
    return {
        "python": platform.python_version(),
        "platform": platform.system(),
        "pandoc": pandoc,
        "pdf_extractors": extractors,
        "pdf_renderers": renderers,
        "supported_inputs": supported_inputs,
        "supported_outputs": supported_outputs,
        "install_hints": hints,
    }


def _print_table(rep):
    def mark(ok):
        return "OK " if ok else "-- "
    print("roman-urdu-book doctor")
    print(f"  python           {rep['python']} ({rep['platform']})")
    print(f"  {mark(rep['pandoc']['ok'])}pandoc         {rep['pandoc'].get('version') or 'not found (required)'}")
    ex = rep["pdf_extractors"]
    print(f"  {mark(bool(ex))}PDF input      {', '.join(ex) if ex else 'no extractor (pdftotext / pymupdf / pypdf / calibre)'}")
    rd = rep["pdf_renderers"]
    print(f"  {mark(bool(rd))}PDF output     {', '.join(r['kind'] for r in rd) if rd else 'no renderer (chrome / wkhtmltopdf / weasyprint / calibre)'}")
    print(f"  inputs           {', '.join(rep['supported_inputs'])}")
    print(f"  outputs          {', '.join(rep['supported_outputs'])}")
    for key, hint in rep["install_hints"].items():
        print(f"  hint [{key}]: {hint}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Report available converters/renderers for roman-urdu-book")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)
    rep = report()
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        _print_table(rep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
