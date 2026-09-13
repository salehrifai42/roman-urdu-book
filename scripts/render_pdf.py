#!/usr/bin/env python3
"""
render_pdf.py - Render a standalone book.html to PDF using the first available
renderer: Chrome/Chromium headless, wkhtmltopdf, weasyprint, or Calibre.

Usage:
    render_pdf.py <book.html> -o <book.pdf> [--renderer auto|chrome|wkhtmltopdf|weasyprint|calibre]
                  [--page-size A5] [--timeout 180]

Library use:
    from render_pdf import render
    ok, renderer, message = render("book.html", "book.pdf")

Stdlib only. Renderer discovery is self-contained (no import of doctor.py).
"""

import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RENDERERS = ("chrome", "wkhtmltopdf", "weasyprint", "calibre")

INSTALL_HINTS = {
    "chrome": "Google Chrome / Chromium / Microsoft Edge / Brave (https://www.google.com/chrome/)",
    "wkhtmltopdf": "wkhtmltopdf (https://wkhtmltopdf.org/ or `brew install --cask wkhtmltopdf`)",
    "weasyprint": "weasyprint (`pip install weasyprint`)",
    "calibre": "Calibre ebook-convert (https://calibre-ebook.com/)",
}

_MAC_BUNDLES = (
    ("Google Chrome.app", "Google Chrome"),
    ("Chromium.app", "Chromium"),
    ("Microsoft Edge.app", "Microsoft Edge"),
    ("Brave Browser.app", "Brave Browser"),
    ("Google Chrome Canary.app", "Google Chrome Canary"),
)

_LINUX_BINARIES = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "microsoft-edge",
    "microsoft-edge-stable",
    "brave-browser",
)


def _windows_candidates():
    roots = [
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("LocalAppData"),
    ]
    rel = (
        r"Google\Chrome\Application\chrome.exe",
        r"Chromium\Application\chrome.exe",
        r"Microsoft\Edge\Application\msedge.exe",
        r"BraveSoftware\Brave-Browser\Application\brave.exe",
    )
    out = []
    for root in roots:
        if not root:
            continue
        for r in rel:
            out.append(os.path.join(root, r))
    return out


def find_chrome():
    """Return the path to a Chrome-family binary, or None.

    Honours the ROMAN_URDU_CHROME environment variable first.
    """
    env = os.environ.get("ROMAN_URDU_CHROME")
    if env:
        if os.path.isfile(env) and os.access(env, os.X_OK):
            return env
        found = shutil.which(env)
        if found:
            return found

    system = platform.system()
    candidates = []
    if system == "Darwin":
        for base in ("/Applications", os.path.expanduser("~/Applications")):
            for bundle, binary in _MAC_BUNDLES:
                candidates.append(os.path.join(base, bundle, "Contents", "MacOS", binary))
    elif system == "Windows":
        candidates.extend(_windows_candidates())

    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path

    for name in _LINUX_BINARIES + ("chrome", "msedge"):
        found = shutil.which(name)
        if found:
            return found
    return None


def find_wkhtmltopdf():
    return shutil.which("wkhtmltopdf")


def find_weasyprint():
    """Return a command prefix (list) to invoke weasyprint, or None."""
    exe = shutil.which("weasyprint")
    if exe:
        return [exe]
    try:
        import importlib.util

        if importlib.util.find_spec("weasyprint") is not None:
            return [sys.executable, "-m", "weasyprint"]
    except Exception:
        pass
    return None


def find_calibre():
    exe = shutil.which("ebook-convert")
    if exe:
        return exe
    mac = "/Applications/calibre.app/Contents/MacOS/ebook-convert"
    if os.path.isfile(mac) and os.access(mac, os.X_OK):
        return mac
    return None


def available_renderers():
    """Return an ordered list of (name, path_or_cmd) for renderers found."""
    out = []
    chrome = find_chrome()
    if chrome:
        out.append(("chrome", chrome))
    wk = find_wkhtmltopdf()
    if wk:
        out.append(("wkhtmltopdf", wk))
    wp = find_weasyprint()
    if wp:
        out.append(("weasyprint", wp))
    cal = find_calibre()
    if cal:
        out.append(("calibre", cal))
    return out


def _pdf_is_valid(pdf_path):
    try:
        p = Path(pdf_path)
        if not p.is_file() or p.stat().st_size <= 1024:
            return False
        with open(p, "rb") as f:
            return f.read(5) == b"%PDF-"
    except OSError:
        return False


def _run(cmd, timeout):
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s"
    except OSError as e:
        return False, f"could not run {cmd[0]}: {e}"
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip().splitlines()
        tail = " | ".join(err[-3:]) if err else f"exit code {proc.returncode}"
        return False, tail
    return True, ""


def chrome_command(chrome, html_path, pdf_path, user_data_dir):
    """Build the headless Chrome argument list (pure; used by tests)."""
    html_url = Path(html_path).resolve().as_uri()
    cmd = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={user_data_dir}",
        "--no-pdf-header-footer",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=5000",
        f"--print-to-pdf={Path(pdf_path).resolve()}",
    ]
    if platform.system() == "Linux" and hasattr(os, "geteuid") and os.geteuid() == 0:
        cmd.append("--no-sandbox")
    cmd.append(html_url)
    return cmd


def render_with_chrome(chrome, html_path, pdf_path, timeout=180):
    with tempfile.TemporaryDirectory(prefix="roman-urdu-chrome-") as tmp:
        cmd = chrome_command(chrome, html_path, pdf_path, tmp)
        ok, msg = _run(cmd, timeout)
    # Chrome sometimes exits non-zero after writing a good PDF; trust the file.
    if _pdf_is_valid(pdf_path):
        return True, ""
    return False, msg or "no PDF written"


def render_with_wkhtmltopdf(exe, html_path, pdf_path, timeout=180, page_size="A5"):
    cmd = [
        exe,
        "--enable-local-file-access",
        "--page-size", page_size,
        "--margin-top", "18mm", "--margin-bottom", "18mm",
        "--margin-left", "16mm", "--margin-right", "16mm",
        "--encoding", "utf-8",
        "--quiet",
        str(Path(html_path).resolve()),
        str(Path(pdf_path).resolve()),
    ]
    ok, msg = _run(cmd, timeout)
    if _pdf_is_valid(pdf_path):
        return True, ""
    return False, msg or "no PDF written"


def render_with_weasyprint(cmd_prefix, html_path, pdf_path, timeout=180):
    cmd = list(cmd_prefix) + [str(Path(html_path).resolve()), str(Path(pdf_path).resolve())]
    ok, msg = _run(cmd, timeout)
    if _pdf_is_valid(pdf_path):
        return True, ""
    return False, msg or "no PDF written"


def render_with_calibre(exe, html_path, pdf_path, timeout=180, page_size="A5"):
    cmd = [
        exe,
        str(Path(html_path).resolve()),
        str(Path(pdf_path).resolve()),
        "--paper-size", page_size.lower(),
        "--pdf-page-numbers",
    ]
    ok, msg = _run(cmd, timeout)
    if _pdf_is_valid(pdf_path):
        return True, ""
    return False, msg or "no PDF written"


def render(html_path, pdf_path, preferred="auto", page_size="A5", timeout=180):
    """Render html_path to pdf_path.

    Returns (ok, renderer_name_or_None, message). When ok is False, message
    explains why (missing renderers, or the last renderer's error).
    """
    html_path = str(html_path)
    pdf_path = str(pdf_path)
    if not os.path.isfile(html_path):
        return False, None, f"HTML not found: {html_path}"

    found = available_renderers()
    if preferred and preferred != "auto":
        found = [f for f in found if f[0] == preferred]
        if not found:
            return False, None, (
                f"renderer '{preferred}' not found; install {INSTALL_HINTS.get(preferred, preferred)}"
            )
    if not found:
        hints = "; ".join(INSTALL_HINTS[r] for r in RENDERERS)
        return False, None, f"no PDF renderer found. Install one of: {hints}"

    errors = []
    for name, target in found:
        try:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
        except OSError:
            pass
        if name == "chrome":
            ok, msg = render_with_chrome(target, html_path, pdf_path, timeout)
        elif name == "wkhtmltopdf":
            ok, msg = render_with_wkhtmltopdf(target, html_path, pdf_path, timeout, page_size)
        elif name == "weasyprint":
            ok, msg = render_with_weasyprint(target, html_path, pdf_path, timeout)
        else:
            ok, msg = render_with_calibre(target, html_path, pdf_path, timeout, page_size)
        if ok:
            return True, name, ""
        errors.append(f"{name}: {msg}")
    return False, None, "all renderers failed — " + "; ".join(errors)


def main(argv=None):
    import argparse

    ap = argparse.ArgumentParser(description="Render book.html to PDF")
    ap.add_argument("html", help="standalone HTML file")
    ap.add_argument("-o", "--output", required=True, help="output PDF path")
    ap.add_argument("--renderer", default="auto", choices=("auto",) + RENDERERS)
    ap.add_argument("--page-size", default="A5")
    ap.add_argument("--timeout", type=int, default=180)
    args = ap.parse_args(argv)

    ok, name, msg = render(args.html, args.output, args.renderer, args.page_size, args.timeout)
    if ok:
        size = os.path.getsize(args.output)
        print(f"pdf: {args.output} ({size} bytes, via {name})")
        return 0
    print(f"pdf: skipped — {msg}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
