#!/usr/bin/env python3
"""
build.py - Merge translated chunks into book.md and build HTML / DOCX / EPUB / PDF.

Usage:
    build.py <out_dir> --title T [--subtitle S] [--author A] [--translator X]
             [--publisher P] [--cover img] [--formats md,html,docx,epub,pdf]
             [--export-name slug] [--toc-depth 2] [--cleanup]
             [--pdf-renderer auto|chrome|wkhtmltopdf|weasyprint|calibre] [--page-size A5]

Reads <out_dir>/work/output_chunkNNNN.md in manifest order, validates them,
wraps Arabic runs for right-to-left rendering, prepends front matter, writes
<out_dir>/book.md, then converts with pandoc. PDF uses render_pdf.py and is
skipped with a warning when no renderer is available.

Exit 0 when book.md and book.html were produced (other formats may be skipped).
The last stdout line is JSON: {"out_dir", "produced": {fmt: path}, "skipped": {fmt: reason}}.

Portions of the image validation are adapted from deusyu/translate-book
(MIT, Copyright (c) 2025 Rainman). See LICENSE.
"""

import argparse
import datetime as _dt
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
TEMPLATE_PATH = SCRIPT_DIR / "template.html"
CSS_PATH = SCRIPT_DIR / "book.css"

ALL_FORMATS = ("md", "html", "docx", "epub", "pdf")
DEFAULT_SUBTITLE = "Roman Urdu Tarjuma"

ARABIC_CHARS = "؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿"
ARABIC_RE = re.compile(f"[{ARABIC_CHARS}]")
# A run of Arabic script incl. combining marks, spaces and Arabic punctuation.
ARABIC_RUN_RE = re.compile(
    f"[{ARABIC_CHARS}](?:[{ARABIC_CHARS}\\sً-ٰٟۖ-ۭ٠-٩۰-۹]*[{ARABIC_CHARS}ً-ٰٟ٠-٩۰-۹])?"
)
# Whole line made of Arabic script, Arabic digits/punctuation and whitespace.
ARABIC_LINE_RE = re.compile(
    f"^[\\s{ARABIC_CHARS}ً-ٰٟۖ-ۭ٠-٩۰-۹؟،؛۔()\\[\\]{{}}«»\"'.,;:!?\\-–—*]+$"
)
FENCE_RE = re.compile(r"^\s*(```|~~~)")
SPAN_ALREADY_RE = re.compile(r"\[[^\]]*\]\{\.arabic[^}]*\}")


# =============================================================================
# Image structure validation (adapted from translate-book/merge_and_build.py)
# =============================================================================

_MD_IMG_RE = re.compile(r'(?<!\\)!\[[^\]]*\]\(\s*([^)\s]+)[^)]*\)')
_VALID_ATTR_NAME_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_:.\-]*$')


class _ImgTagCollector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.records = []

    def handle_starttag(self, tag, attrs):
        if tag == 'img':
            self.records.append((self.get_starttag_text(), list(attrs)))

    handle_startendtag = handle_starttag


def _scan_img_tags(text):
    src_counts = Counter()
    bad_attrs = []
    parser = _ImgTagCollector()
    try:
        parser.feed(text)
        parser.close()
    except Exception as e:  # pragma: no cover - defensive
        bad_attrs.append(('<unparseable input>', f'<parser error: {e}>'))
        return src_counts, bad_attrs
    for raw_tag, attrs in parser.records:
        for name, _ in attrs:
            if not _VALID_ATTR_NAME_RE.match(name):
                bad_attrs.append((raw_tag, name))
        for name, val in attrs:
            if name == 'src' and val:
                src_counts[val] += 1
    return src_counts, bad_attrs


def _scan_image_refs(text):
    html_srcs, bad_attrs = _scan_img_tags(text)
    md_srcs = Counter(_MD_IMG_RE.findall(text))
    return html_srcs, md_srcs, bad_attrs


def validate_chunk_images(work_dir):
    """Return a list of error strings for output chunks whose image
    references diverge from their source chunk."""
    work = Path(work_dir)
    errors = []
    for src_chunk in sorted(work.glob('chunk*.md')):
        if src_chunk.name.startswith('output_'):
            continue
        out_chunk = work / f'output_{src_chunk.name}'
        if not out_chunk.exists():
            continue
        src_html, src_md, src_bad = _scan_image_refs(src_chunk.read_text(encoding='utf-8'))
        out_html, out_md, out_bad = _scan_image_refs(out_chunk.read_text(encoding='utf-8'))
        new_bad = Counter(n for _, n in out_bad) - Counter(n for _, n in src_bad)
        for raw_tag, attr_name in out_bad:
            if new_bad.get(attr_name, 0) > 0:
                errors.append(
                    f"{out_chunk.name}: malformed <img> tag not present in source: {raw_tag} "
                    f"(attribute '{attr_name}'); replace inner quotes with &quot;"
                )
        if src_html != out_html or src_md != out_md:
            errors.append(
                f"{out_chunk.name}: image references diverge from {src_chunk.name} "
                f"(missing {sorted((src_md - out_md).elements()) + sorted((src_html - out_html).elements())}, "
                f"extra {sorted((out_md - src_md).elements()) + sorted((out_html - src_html).elements())})"
            )
    return errors


def check_generated_html_sanity(html_path):
    try:
        text = Path(html_path).read_text(encoding='utf-8')
    except OSError as e:
        return [f"cannot read {html_path}: {e}"]
    _, bad_attrs = _scan_img_tags(text)
    return [f"malformed <img> in {Path(html_path).name}: {raw} (attribute '{name}')" for raw, name in bad_attrs]


# =============================================================================
# Merge
# =============================================================================

def _read(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def ordered_outputs(work_dir):
    """Return (ok, [output paths in order], errors) using manifest.py when
    available, else a glob fallback."""
    errors = []
    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        import manifest as _manifest  # vendored from translate-book
    except ImportError:
        _manifest = None

    if _manifest is not None and os.path.isfile(os.path.join(work_dir, 'manifest.json')):
        ok, files, warnings = _manifest.validate_for_merge(work_dir)
        if not ok:
            return False, [], ["manifest validation failed (see messages above)"]
        if files is not None:
            return True, files, []

    files = []
    for src in sorted(glob.glob(os.path.join(work_dir, 'chunk*.md'))):
        name = os.path.basename(src)
        if name.startswith('output_'):
            continue
        out = os.path.join(work_dir, f'output_{name}')
        if not os.path.isfile(out):
            errors.append(f"missing output for {name}")
            continue
        try:
            text = _read(out)
        except (OSError, UnicodeDecodeError):
            errors.append(f"unreadable output {os.path.basename(out)}")
            continue
        if not text.strip():
            errors.append(f"blank output {os.path.basename(out)}")
            continue
        files.append(out)
    if not files and not errors:
        errors.append("no chunks found in work/")
    return (not errors), files, errors


def merge_chunks(work_dir):
    """Merge output chunks in order. Returns (text, errors)."""
    ok, files, errors = ordered_outputs(work_dir)
    if not ok:
        return None, errors
    img_errors = validate_chunk_images(work_dir)
    if img_errors:
        return None, img_errors
    parts = []
    for path in files:
        text = _read(path).strip('\n')
        if text.strip():
            parts.append(text)
    merged = "\n\n".join(parts).strip() + "\n"
    return merged, []


# =============================================================================
# Arabic (RTL) wrapping
# =============================================================================

def _wrap_inline(line):
    if SPAN_ALREADY_RE.search(line):
        return line
    def repl(m):
        return '[' + m.group(0) + ']{.arabic dir="rtl" lang="ar"}'
    return ARABIC_RUN_RE.sub(repl, line)


def wrap_arabic_runs(md):
    """Wrap Arabic-script text for RTL rendering.

    Whole-line Arabic (consecutive lines) becomes a fenced div
    ``::: {.arabic-block dir="rtl" lang="ar"}``; inline runs become bracketed
    spans ``[...]{.arabic dir="rtl" lang="ar"}``. Fenced code is untouched.
    """
    out = []
    block = []
    in_fence = False

    def flush():
        if block:
            out.append('::: {.arabic-block dir="rtl" lang="ar"}')
            out.extend(block)
            out.append(':::')
            block.clear()

    in_block = False
    for line in md.split('\n'):
        if FENCE_RE.match(line):
            flush()
            in_fence = not in_fence
            out.append(line)
            continue
        if not in_fence and line.lstrip().startswith('::: {.arabic-block'):
            flush()
            in_block = True
            out.append(line)
            continue
        if in_block:
            out.append(line)
            if line.strip() == ':::':
                in_block = False
            continue
        if in_fence or not ARABIC_RE.search(line):
            flush()
            out.append(line)
            continue
        stripped = line.strip()
        is_heading = stripped.startswith('#')
        is_list = re.match(r'^\s*(?:[-*+]|\d+[.)])\s+', line) is not None
        is_quote = stripped.startswith('>')
        if ARABIC_LINE_RE.match(line) and not (is_heading or is_list or is_quote) and not line.lstrip().startswith(':::'):
            block.append(stripped)
            continue
        flush()
        out.append(_wrap_inline(line))
    flush()
    return '\n'.join(out)


# =============================================================================
# Front matter
# =============================================================================

def _yaml_str(s):
    return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'


def compose_front_matter(title, subtitle=None, author=None, translator=None,
                         publisher=None, lang="ur-Latn", date=None, cover_image=None):
    """Return the YAML metadata block plus a visible front-matter section
    (used by DOCX/EPUB; hidden in HTML where the template renders a cover)."""
    subtitle = subtitle or DEFAULT_SUBTITLE
    date = date or _dt.date.today().strftime('%Y')
    lines = ['---', f'title: {_yaml_str(title)}', f'subtitle: {_yaml_str(subtitle)}']
    if author:
        lines.append(f'author: {_yaml_str(author)}')
    if translator:
        lines.append(f'translator: {_yaml_str(translator)}')
    if publisher:
        lines.append(f'publisher: {_yaml_str(publisher)}')
    if cover_image:
        lines.append(f'cover-image: {_yaml_str(cover_image)}')
    lines.append(f'lang: {lang}')
    lines.append(f'date: {_yaml_str(date)}')
    lines.append('---')
    lines.append('')
    fm = ['::: {.front-matter}']
    if author:
        fm.append(f'**Taleef:** {author}  ')
    if translator:
        fm.append(f'**Tarjuma:** {translator}  ')
    if publisher:
        fm.append(f'{publisher}  ')
    fm.append(':::')
    if len(fm) > 2:
        lines.extend(fm)
        lines.append('')
    return '\n'.join(lines)


# =============================================================================
# Pandoc
# =============================================================================

def pandoc_path():
    return shutil.which('pandoc')


def pandoc_supports(flag):
    try:
        out = subprocess.run([pandoc_path(), '--help'], capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return False
    return flag in out


def _run_pandoc(args, cwd):
    cmd = [pandoc_path()] + args
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or '').strip().splitlines()
        return False, ' | '.join(msg[-3:]) if msg else f'pandoc exit {proc.returncode}'
    return True, ''


def _template_with_css(tmpdir):
    """Write a copy of template.html with book.css inlined; returns path."""
    template = TEMPLATE_PATH.read_text(encoding='utf-8')
    css = CSS_PATH.read_text(encoding='utf-8').replace('$', '$$')
    template = template.replace('$css_inline$', css)
    p = Path(tmpdir) / 'template.html'
    p.write_text(template, encoding='utf-8')
    return str(p)


def build_html(out_dir, book_md, toc_depth, tmpdir):
    html_path = os.path.join(out_dir, 'book.html')
    template = _template_with_css(tmpdir)
    args = [
        'book.md', '-f', 'markdown+smart', '-t', 'html5', '--standalone',
        '--toc', f'--toc-depth={toc_depth}', '--template', template,
        '--resource-path', out_dir, '-o', html_path,
    ]
    ok, msg = _run_pandoc(args, out_dir)
    if not ok:
        return None, msg
    problems = check_generated_html_sanity(html_path)
    if problems:
        return None, '; '.join(problems)
    return html_path, ''


def build_docx(out_dir, toc_depth):
    docx_path = os.path.join(out_dir, 'book.docx')
    args = ['book.md', '-f', 'markdown+smart', '--toc', f'--toc-depth={toc_depth}',
            '--resource-path', out_dir, '-o', docx_path]
    ok, msg = _run_pandoc(args, out_dir)
    return (docx_path, '') if ok else (None, msg)


def build_epub(out_dir, toc_depth, cover=None):
    epub_path = os.path.join(out_dir, 'book.epub')
    args = ['book.md', '-f', 'markdown+smart', '--toc', f'--toc-depth={toc_depth}',
            '--css', str(CSS_PATH), '--metadata', 'lang=ur-Latn',
            '--resource-path', out_dir, '-o', epub_path]
    if pandoc_supports('--epub-title-page'):
        args.append('--epub-title-page=true')
    if cover:
        args.extend(['--epub-cover-image', cover])
    ok, msg = _run_pandoc(args, out_dir)
    return (epub_path, '') if ok else (None, msg)


def build_pdf(out_dir, html_path, renderer, page_size):
    pdf_path = os.path.join(out_dir, 'book.pdf')
    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        import render_pdf
    except ImportError as e:
        return None, f'render_pdf.py unavailable: {e}'
    ok, name, msg = render_pdf.render(html_path, pdf_path, preferred=renderer, page_size=page_size)
    if ok:
        return pdf_path, name
    return None, msg


# =============================================================================
# Driver
# =============================================================================

def build(out_dir, title, subtitle=None, author=None, translator=None, publisher=None,
          cover=None, formats=ALL_FORMATS, export_name=None, toc_depth=2,
          cleanup=False, pdf_renderer='auto', page_size='A5'):
    out_dir = str(Path(out_dir).resolve())
    work_dir = os.path.join(out_dir, 'work')
    produced, skipped = {}, {}
    formats = [f.strip().lower() for f in formats if f.strip()]

    if not os.path.isdir(work_dir):
        return {'out_dir': out_dir, 'produced': produced, 'skipped': skipped,
                'error': f'no work/ directory in {out_dir}'}

    merged, errors = merge_chunks(work_dir)
    if merged is None:
        for e in errors:
            print(f'ERROR: {e}')
        return {'out_dir': out_dir, 'produced': produced, 'skipped': skipped,
                'error': 'merge failed'}

    merged_path = os.path.join(work_dir, 'merged.md')
    with open(merged_path, 'w', encoding='utf-8') as f:
        f.write(merged)

    cover_rel = None
    if cover:
        if not os.path.isfile(cover):
            print(f'WARNING: cover image not found: {cover}')
        else:
            ext = Path(cover).suffix.lower() or '.jpg'
            cover_rel = f'cover{ext}'
            dest = os.path.join(out_dir, cover_rel)
            if os.path.abspath(cover) != os.path.abspath(dest):
                shutil.copyfile(cover, dest)

    body = wrap_arabic_runs(merged)
    front = compose_front_matter(title, subtitle, author, translator, publisher, cover_image=cover_rel)
    book_md = os.path.join(out_dir, 'book.md')
    with open(book_md, 'w', encoding='utf-8') as f:
        f.write(front + '\n' + body.rstrip('\n') + '\n')
    produced['md'] = book_md

    html_path = None
    if pandoc_path() is None:
        for fmt in ('html', 'docx', 'epub', 'pdf'):
            if fmt in formats:
                skipped[fmt] = 'pandoc not found (install from https://pandoc.org/)'
    else:
        with tempfile.TemporaryDirectory(prefix='roman-urdu-build-') as tmpdir:
            if 'html' in formats or 'pdf' in formats:
                html_path, msg = build_html(out_dir, book_md, toc_depth, tmpdir)
                if html_path:
                    if 'html' in formats:
                        produced['html'] = html_path
                else:
                    skipped['html'] = msg
            if 'docx' in formats:
                p, msg = build_docx(out_dir, toc_depth)
                if p:
                    produced['docx'] = p
                else:
                    skipped['docx'] = msg
            if 'epub' in formats:
                p, msg = build_epub(out_dir, toc_depth, cover=cover_rel and os.path.join(out_dir, cover_rel))
                if p:
                    produced['epub'] = p
                else:
                    skipped['epub'] = msg
            if 'pdf' in formats:
                if html_path:
                    p, msg = build_pdf(out_dir, html_path, pdf_renderer, page_size)
                    if p:
                        produced['pdf'] = p
                        produced['pdf_renderer'] = msg
                    else:
                        skipped['pdf'] = msg
                else:
                    skipped['pdf'] = 'HTML build failed, so PDF was not attempted'

    if export_name:
        slug = re.sub(r'[^A-Za-z0-9._-]+', '-', export_name).strip('-') or 'book'
        for fmt, path in list(produced.items()):
            if fmt == 'pdf_renderer':
                continue
            dest = os.path.join(out_dir, f'{slug}.{fmt}')
            shutil.copyfile(path, dest)
            produced[f'{fmt}_alias'] = dest

    if cleanup:
        for p in glob.glob(os.path.join(work_dir, 'lint_*.json')) + [merged_path]:
            try:
                os.remove(p)
            except OSError:
                pass

    return {'out_dir': out_dir, 'produced': produced, 'skipped': skipped}


def _print_table(result):
    print(f"Build results for {result['out_dir']}")
    for fmt in ALL_FORMATS:
        if fmt in result['produced']:
            path = result['produced'][fmt]
            size = os.path.getsize(path)
            extra = f" (via {result['produced']['pdf_renderer']})" if fmt == 'pdf' and 'pdf_renderer' in result['produced'] else ''
            print(f"  {fmt:5s} ok       {os.path.basename(path)}  {size:,} bytes{extra}")
        elif fmt in result['skipped']:
            print(f"  {fmt:5s} skipped  — {result['skipped'][fmt]}")
    if 'pdf' in result['skipped']:
        print("  hint: install Google Chrome/Chromium, wkhtmltopdf, weasyprint (pip) or Calibre to get a PDF")


def main(argv=None):
    ap = argparse.ArgumentParser(description='Merge chunks and build the Roman Urdu book')
    ap.add_argument('out_dir')
    ap.add_argument('--title', required=True)
    ap.add_argument('--subtitle')
    ap.add_argument('--author')
    ap.add_argument('--translator')
    ap.add_argument('--publisher')
    ap.add_argument('--cover')
    ap.add_argument('--formats', default=','.join(ALL_FORMATS))
    ap.add_argument('--export-name')
    ap.add_argument('--toc-depth', type=int, default=2)
    ap.add_argument('--cleanup', action='store_true')
    ap.add_argument('--pdf-renderer', default='auto',
                    choices=('auto', 'chrome', 'wkhtmltopdf', 'weasyprint', 'calibre'))
    ap.add_argument('--page-size', default='A5')
    args = ap.parse_args(argv)

    result = build(
        args.out_dir, args.title, args.subtitle, args.author, args.translator, args.publisher,
        cover=args.cover, formats=args.formats.split(','), export_name=args.export_name,
        toc_depth=args.toc_depth, cleanup=args.cleanup, pdf_renderer=args.pdf_renderer,
        page_size=args.page_size,
    )
    if result.get('error'):
        print(f"ERROR: {result['error']}")
        print(json.dumps(result, ensure_ascii=False))
        return 1
    _print_table(result)
    print(json.dumps(result, ensure_ascii=False))
    ok = 'md' in result['produced'] and ('html' in result['produced'] or 'html' not in args.formats.split(','))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
