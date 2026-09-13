#!/usr/bin/env python3
"""
convert.py - Turn an English book (PDF/DOCX/EPUB/HTML/MD/TXT/...) into Markdown chunks.

Layout produced under <out_dir> (default: <input dir>/<stem>_roman_urdu):
    config.json                 run configuration and source metadata
    work/input.md               full-book Markdown
    work/chunkNNNN.md           source chunks (~chunk_size chars, split at structure)
    work/manifest.json          SHA-256 manifest of chunks (manifest.py)
    work/source_fingerprint.json identity of the source bytes this run was built from
    media/                      images extracted by pandoc (DOCX/EPUB/HTML)

The chunker and page-number detection are adapted from deusyu/translate-book
(MIT, Copyright (c) 2025 Rainman). See LICENSE.

Last line of stdout is a one-line JSON summary for the orchestrator.
"""

import argparse
import bisect
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import doctor  # noqa: E402
import manifest  # noqa: E402

SKILL_VERSION = "0.1.0"
DEFAULT_CHUNK_SIZE = 4500
PANDOC_INPUTS = {"docx", "epub", "html", "htm", "odt", "rtf", "fb2"}
PDF_METHODS = ("pdftotext", "pymupdf", "pypdf", "calibre")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def _atomic_write(path, text):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def default_out_dir(input_path):
    p = Path(input_path).resolve()
    return p.parent / f"{p.stem}_roman_urdu"


def input_format(input_path):
    return Path(input_path).suffix.lower().lstrip(".")


# ---------------------------------------------------------------------------
# Markdown cleanup
# ---------------------------------------------------------------------------

_ATTR_RE = re.compile(r"[ \t]*\{[#.][^}\n]*\}")           # {#id .class key=val}
_DIV_TAG_RE = re.compile(r"^\s*</?div[^>]*>\s*$", re.M)
_FENCE_DIV_RE = re.compile(r"^:::+.*$", re.M)


def clean_markdown(content):
    """Strip pandoc/Calibre artefacts that carry no meaning for translation."""
    content = content.replace("\u21a9\ufe0e", "").replace("\u21a9", "")
    content = content.replace("﻿", "").replace(" ", " ")
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    content = _FENCE_DIV_RE.sub("", content)
    content = _DIV_TAG_RE.sub("", content)
    content = re.sub(r"\(#calibre_link-\d+\)", "", content)
    content = re.sub(r"\[\*\*([^*]+)\*\*\]", r"**\1**", content)
    # Heading / span attribute blocks, e.g. "## Title {#sec .unnumbered}"
    content = "\n".join(_ATTR_RE.sub("", line) if not line.lstrip().startswith("```") else line
                        for line in content.split("\n"))
    # Trailing backslash hard-breaks pandoc emits for <br>
    content = re.sub(r"[ \t]*\\$", "", content, flags=re.M)
    # Empty links/anchors
    content = re.sub(r"\[\]\([^)]*\)", "", content)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip("\n") + "\n"


# ---------------------------------------------------------------------------
# Page-number detection (adapted from translate-book convert.py)
# ---------------------------------------------------------------------------

_PAGE_SEQUENCE_MIN_LENGTH = 4
_PAGE_SEQUENCE_MIN_RATIO = 0.5


def _detect_page_number_lines(lines):
    """Indices of standalone-digit lines forming a monotonic page-number sequence.

    Longest non-decreasing subsequence over standalone digits; outliers (years,
    chapter numbers, citation indices) stay off the spine and are preserved.
    """
    digit_indices, digit_values = [], []
    for i, line in enumerate(lines):
        s = line.strip()
        if s.isdigit():
            digit_indices.append(i)
            digit_values.append(int(s))
    n = len(digit_values)
    if n < _PAGE_SEQUENCE_MIN_LENGTH:
        return set()
    tails, tails_idx, parents = [], [], [-1] * n
    for i, v in enumerate(digit_values):
        pos = bisect.bisect_right(tails, v)
        if pos > 0:
            parents[i] = tails_idx[pos - 1]
        if pos == len(tails):
            tails.append(v)
            tails_idx.append(i)
        else:
            tails[pos] = v
            tails_idx[pos] = i
    lnds, cur = [], tails_idx[-1]
    while cur != -1:
        lnds.append(cur)
        cur = parents[cur]
    lnds.reverse()
    if len(lnds) < _PAGE_SEQUENCE_MIN_LENGTH or len(lnds) / n < _PAGE_SEQUENCE_MIN_RATIO:
        return set()
    return {digit_indices[i] for i in lnds}


def strip_page_numbers(content, aggressive=False):
    lines = content.split("\n")
    drop = _detect_page_number_lines(lines)
    out = []
    for i, line in enumerate(lines):
        if re.match(r"^\s*\d+\s*$", line) and (aggressive or i in drop):
            continue
        out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# PDF text extraction and reflow
# ---------------------------------------------------------------------------

def _extract_pdftotext(pdf_path):
    exe = doctor.find_binary("pdftotext")
    if not exe:
        raise RuntimeError("pdftotext not available")
    res = subprocess.run([exe, "-enc", "UTF-8", "-eol", "unix", str(pdf_path), "-"],
                         capture_output=True, text=True, timeout=600)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or "pdftotext failed")
    return res.stdout


def _extract_pymupdf(pdf_path):
    try:
        import fitz  # type: ignore
    except ImportError as e:
        raise RuntimeError("PyMuPDF (fitz) not installed") from e
    pages = []
    with fitz.open(str(pdf_path)) as doc:
        for page in doc:
            pages.append(page.get_text("text"))
    return "\f".join(pages)


def _extract_pypdf(pdf_path):
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError as e:
        raise RuntimeError("pypdf not installed") from e
    reader = PdfReader(str(pdf_path))
    return "\f".join((page.extract_text() or "") for page in reader.pages)


def _extract_calibre(pdf_path):
    exe = doctor.find_binary("ebook-convert")
    if not exe:
        raise RuntimeError("ebook-convert (Calibre) not available")
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        txt = os.path.join(tmp, "out.txt")
        res = subprocess.run([exe, str(pdf_path), txt], capture_output=True, text=True, timeout=1800)
        if res.returncode != 0 or not os.path.exists(txt):
            raise RuntimeError(res.stderr.strip() or "ebook-convert failed")
        return Path(txt).read_text(encoding="utf-8", errors="replace")


EXTRACTORS = {
    "pdftotext": _extract_pdftotext,
    "pymupdf": _extract_pymupdf,
    "pypdf": _extract_pypdf,
    "calibre": _extract_calibre,
}


def extract_pdf_text(pdf_path, method="auto"):
    """Return (text, method_used). Raises RuntimeError with install hints when none works."""
    order = list(PDF_METHODS) if method == "auto" else [method]
    available = doctor.find_pdf_extractors() if method == "auto" else order
    errors = []
    for name in order:
        if name not in available:
            continue
        try:
            text = EXTRACTORS[name](pdf_path)
            if text and text.strip():
                return text, name
            errors.append(f"{name}: produced no text (scanned/image-only PDF?)")
        except Exception as e:  # noqa: BLE001 - surface every failure
            errors.append(f"{name}: {e}")
    hints = doctor.INSTALL_HINTS
    matrix = "\n".join(f"  - {k}: {hints[k]}" for k in ("pdftotext", "pymupdf", "pypdf", "calibre"))
    detail = ("\n".join("  " + e for e in errors)) if errors else "  (no extractor installed)"
    raise RuntimeError(
        "Could not extract text from the PDF.\n" + detail +
        "\nInstall one of the following and re-run:\n" + matrix)


_SENTENCE_END = re.compile(r'[.!?:;"”’)\]۔؟]\d{0,2}\s*$')  # trailing digits = glued footnote marker
_FOOTNOTE_LINE = re.compile(r"^\d{1,3}\s+\S")
_LIST_LINE = re.compile(r"^(?:\d{1,3}[.)]|[-*•▪◦]|[a-z][.)]|[ivx]{1,4}[.)])\s+\S")
_ARABIC_CHARS = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
_QUOTE_START = re.compile(r'^["“‘\'«]')


def _is_arabic_line(s):
    letters = [ch for ch in s if ch.isalpha()]
    return bool(letters) and sum(1 for ch in letters if _ARABIC_CHARS.match(ch)) >= 0.6 * len(letters)


def _is_single_word_heading(s):
    """A lone capitalised word such as 'Introduction' or 'Conclusion'."""
    return bool(re.fullmatch(r"[A-Z][A-Za-z'\u2019-]{2,29}", s.strip()))


def _typical_width(lines):
    """Approximate full line width: 90th percentile of non-blank line lengths."""
    lens = sorted(len(l.strip()) for l in lines if l.strip())
    if not lens:
        return 80
    return max(40, lens[min(len(lens) - 1, int(len(lens) * 0.9))])


def _is_heading_candidate(line):
    s = line.strip()
    if not (3 <= len(s) <= 80) or _SENTENCE_END.search(s) or s.endswith(","):
        return False
    words = s.split()
    if len(words) > 12 or any(ch.isdigit() for ch in s[:1]) and len(words) == 1:
        return False
    if s.isupper() and any(c.isalpha() for c in s):
        return True
    caps = sum(1 for w in words if w[:1].isupper())
    return caps >= max(1, int(len(words) * 0.8)) and len(words) >= 2


def reflow_pdf_text(text, keep_page_numbers=False):
    """Turn extracted PDF text into paragraph-oriented Markdown.

    Drops repeated running headers/footers, monotonic page numbers, joins
    hard-wrapped lines, de-hyphenates, and promotes short title-like lines to
    ``##`` headings.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")
    pages = text.split("\f")
    # Running headers/footers: identical non-blank lines on >=30% of pages (needs >= 4 pages)
    repeated = set()
    if len(pages) >= 4:
        counts = {}
        for page in pages:
            seen = set()
            for line in page.split("\n"):
                s = re.sub(r"\s+", " ", line.strip())
                if s and not s.isdigit() and len(s) < 120:
                    seen.add(s)
            for s in seen:
                counts[s] = counts.get(s, 0) + 1
        repeated = {s for s, c in counts.items() if c >= max(2, 0.3 * len(pages))}

    lines = []
    for page in pages:
        for line in page.split("\n"):
            s = re.sub(r"\s+", " ", line.strip())
            if s in repeated:
                continue
            lines.append(line.rstrip())
        lines.append("")
    if not keep_page_numbers:
        lines = strip_page_numbers("\n".join(lines)).split("\n")

    # Join hard-wrapped lines into paragraphs. A line is a paragraph end when it
    # is clearly shorter than the page width and ends a sentence, when the next
    # line starts a list item / quotation / Arabic verse, or when it looks like
    # a heading following a completed paragraph.
    width = _typical_width(lines)
    short = 0.7 * width
    paragraphs, buf = [], []

    def flush():
        if buf:
            paragraphs.append(" ".join(buf))
            buf.clear()

    for line in lines:
        s = line.strip()
        if not s:
            flush()
            continue
        if buf:
            prev = buf[-1]
            prev_done = bool(_SENTENCE_END.search(prev))
            if prev.endswith("-") and len(prev) > 1 and prev[-2].isalpha() and s[:1].islower():
                buf[-1] = prev[:-1] + s
                continue
            if _is_arabic_line(s) or _is_arabic_line(prev):
                flush()
            elif _LIST_LINE.match(s) or (_FOOTNOTE_LINE.match(s) and prev_done):
                flush()
            elif _QUOTE_START.match(s) and prev.rstrip().endswith(":"):
                flush()
            elif prev_done and len(prev) < short:
                flush()
            elif _is_heading_candidate(s) and (prev_done or (len(buf) == 1 and _is_heading_candidate(prev))):
                flush()
        if _is_arabic_line(s):
            buf.append(s)
            flush()
            continue
        if not buf and len(s) < short and (_is_heading_candidate(s) or _is_single_word_heading(s)):
            # Peek: a heading is a short standalone line; keep it separate from the
            # following text by flushing immediately.
            buf.append(s)
            flush()
            continue
        buf.append(s)
    flush()

    out = []
    for para in paragraphs:
        if (_is_heading_candidate(para) or _is_single_word_heading(para)) and len(para.split()) <= 12:
            title = para if not para.isupper() else para.title()
            out.append(f"## {title}")
        else:
            out.append(para)
    return "\n\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Plain text / Markdown inputs
# ---------------------------------------------------------------------------

def txt_to_markdown(text):
    """Reflow a .txt file: blank-line separated paragraphs, hard wraps joined."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    paras = re.split(r"\n\s*\n", text)
    out = []
    for p in paras:
        lines = [l.strip() for l in p.split("\n") if l.strip()]
        if not lines:
            continue
        if len(lines) == 1 and _is_heading_candidate(lines[0]):
            out.append("## " + lines[0])
        else:
            out.append(" ".join(lines))
    return "\n\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Pandoc
# ---------------------------------------------------------------------------

def run_pandoc(args, timeout=600):
    exe = doctor.find_binary("pandoc")
    if not exe:
        raise RuntimeError("pandoc not found. " + doctor.INSTALL_HINTS["pandoc"])
    res = subprocess.run([exe] + args, capture_output=True, text=True, timeout=timeout)
    if res.returncode != 0:
        raise RuntimeError(f"pandoc failed: {res.stderr.strip()}")
    return res.stdout


def _meta_to_text(node):
    """Flatten a pandoc JSON metadata value to plain text."""
    if node is None:
        return ""
    t = node.get("t") if isinstance(node, dict) else None
    if t in ("MetaString",):
        return node["c"]
    if t in ("MetaInlines", "MetaBlocks"):
        return _inlines_to_text(node["c"])
    if t == "MetaList":
        return "; ".join(_meta_to_text(x) for x in node["c"] if _meta_to_text(x))
    if t == "MetaMap":
        return ", ".join(_meta_to_text(v) for v in node["c"].values())
    return ""


def _inlines_to_text(inlines):
    parts = []
    for x in inlines:
        if not isinstance(x, dict):
            continue
        t = x.get("t")
        if t in ("Str", "Code", "Math"):
            parts.append(x["c"] if isinstance(x["c"], str) else x["c"][-1])
        elif t in ("Space", "SoftBreak", "LineBreak"):
            parts.append(" ")
        elif t in ("Emph", "Strong", "SmallCaps", "Strikeout", "Underline", "Span", "Link", "Quoted", "Para", "Plain"):
            c = x["c"]
            inner = c[-1] if t in ("Span", "Link") else (c[1] if t == "Quoted" else c)
            if t == "Link":
                inner = c[1]
            parts.append(_inlines_to_text(inner if isinstance(inner, list) else []))
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def pandoc_metadata(input_path):
    try:
        raw = run_pandoc([str(input_path), "-t", "json"])
        meta = json.loads(raw).get("meta", {})
        return {"title": _meta_to_text(meta.get("title")), "author": _meta_to_text(meta.get("author"))}
    except Exception:  # noqa: BLE001
        return {"title": "", "author": ""}


def fallback_title(md_text, input_path):
    m = re.search(r"^#\s+(.+)$", md_text, re.M)
    if m:
        return m.group(1).strip()
    return Path(input_path).stem.replace("_", " ").replace("-", " ").strip()


# ---------------------------------------------------------------------------
# Structural chunking (adapted from translate-book convert.py)
# ---------------------------------------------------------------------------

def parse_structural_blocks(content):
    """Parse markdown into (text, type) blocks that must not be split."""
    blocks, lines, i = [], content.split("\n"), 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if s.startswith("```"):
            block = [line]
            i += 1
            while i < len(lines):
                block.append(lines[i])
                if lines[i].strip().startswith("```") and len(block) > 1:
                    i += 1
                    break
                i += 1
            blocks.append(("\n".join(block), "code_block"))
            continue
        if re.match(r"^#{1,6}\s", s):
            blocks.append((line, "heading"))
            i += 1
            continue
        if s.startswith(">"):
            block = [line]
            i += 1
            while i < len(lines) and lines[i].strip().startswith(">"):
                block.append(lines[i])
                i += 1
            blocks.append(("\n".join(block), "blockquote"))
            continue
        if s.startswith("|"):
            block = [line]
            i += 1
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1
            blocks.append(("\n".join(block), "table"))
            continue
        if re.match(r"^[-*+]\s", s) or re.match(r"^\d+[.)]\s", s):
            block = [line]
            i += 1
            while i < len(lines):
                t = lines[i].strip()
                if (re.match(r"^[-*+]\s", t) or re.match(r"^\d+[.)]\s", t) or (lines[i].startswith("  ") and t)
                        or (t == "" and i + 1 < len(lines)
                            and (re.match(r"^[-*+]\s", lines[i + 1].strip())
                                 or re.match(r"^\d+[.)]\s", lines[i + 1].strip())
                                 or lines[i + 1].startswith("  ")))):
                    block.append(lines[i])
                    i += 1
                else:
                    break
            blocks.append(("\n".join(block), "list"))
            continue
        if s.startswith("!["):
            blocks.append((line, "image"))
            i += 1
            continue
        if s == "":
            blocks.append((line, "paragraph"))
            i += 1
            continue
        block = [line]
        i += 1
        while i < len(lines):
            t = lines[i].strip()
            if (t == "" or t.startswith("```") or re.match(r"^#{1,6}\s", t) or t.startswith(">")
                    or t.startswith("|") or re.match(r"^[-*+]\s", t) or re.match(r"^\d+[.)]\s", t)
                    or t.startswith("![")):
                break
            block.append(lines[i])
            i += 1
        blocks.append(("\n".join(block), "paragraph"))
    return blocks


def _force_split_block(text, target_size):
    stripped = text.strip()
    fenced = stripped.startswith("```")
    if not fenced:
        paragraphs = re.split(r"\n\n+", text)
        if len(paragraphs) > 1:
            chunks, cur, size = [], [], 0
            for p in paragraphs:
                if size + len(p) > target_size and cur:
                    chunks.append("\n\n".join(cur))
                    cur, size = [p], len(p)
                else:
                    cur.append(p)
                    size += len(p)
            if cur:
                chunks.append("\n\n".join(cur))
            return chunks
    lines = text.split("\n")
    opener = ""
    if fenced:
        opener = lines[0]
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
    chunks, cur, size = [], [], 0
    for line in lines:
        if size + len(line) + 1 > target_size and cur:
            chunks.append("\n".join(cur))
            cur, size = [line], len(line) + 1
        else:
            cur.append(line)
            size += len(line) + 1
    if cur:
        chunks.append("\n".join(cur))
    if fenced:
        chunks = [f"{opener}\n{c}\n```" for c in chunks]
    return chunks


def merge_blocks_to_chunks(blocks, target_size=DEFAULT_CHUNK_SIZE):
    """Merge blocks into chunks near target_size, preferring heading boundaries."""
    chunks, cur, size = [], [], 0

    def flush():
        nonlocal cur, size
        if cur and "".join(cur).strip():
            chunks.append("\n".join(cur).strip("\n") + "\n")
        cur, size = [], 0

    for text, btype in blocks:
        n = len(text)
        if n > target_size * 2:
            flush()
            chunks.extend(c.strip("\n") + "\n" for c in _force_split_block(text, target_size))
            continue
        if btype == "heading" and size > 0:
            level = len(text) - len(text.lstrip("#"))
            # Chapter-level headings (# / ##) always start a new chunk; deeper
            # headings only when the current chunk is already reasonably full.
            if size > target_size * (0.25 if level <= 2 else 0.5):
                flush()
        if size + n > target_size and cur:
            flush()
        cur.append(text)
        size += n
    flush()
    # Fold small trailing fragments (e.g. a short closing section) into the
    # previous chunk so no chunk is a tiny orphan.
    merged = []
    for c in chunks:
        if merged and len(c) < target_size * 0.3 and len(merged[-1]) + len(c) <= target_size * 1.3:
            merged[-1] = merged[-1].rstrip("\n") + "\n\n" + c
        else:
            merged.append(c)
    return merged


def split_markdown(md_text, work_dir, target_size=DEFAULT_CHUNK_SIZE):
    """Write chunkNNNN.md files into work_dir; returns the filenames."""
    chunk_texts = merge_blocks_to_chunks(parse_structural_blocks(md_text), target_size)
    for old in glob.glob(os.path.join(work_dir, "chunk*.md")):
        os.remove(old)
    files = []
    for i, text in enumerate(chunk_texts, 1):
        name = f"chunk{i:04d}.md"
        Path(work_dir, name).write_text(text, encoding="utf-8")
        files.append(name)
    return files


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def to_markdown(input_path, out_dir, pdf_method="auto", keep_page_numbers=False):
    """Return (markdown_text, method, metadata)."""
    fmt = input_format(input_path)
    meta = {"title": "", "author": ""}
    if fmt == "pdf":
        raw, method = extract_pdf_text(input_path, pdf_method)
        md = reflow_pdf_text(raw, keep_page_numbers=keep_page_numbers)
    elif fmt in ("md", "markdown"):
        md, method = Path(input_path).read_text(encoding="utf-8", errors="replace"), "markdown"
        if doctor.find_binary("pandoc"):
            meta = pandoc_metadata(input_path)
    elif fmt == "txt":
        md, method = txt_to_markdown(Path(input_path).read_text(encoding="utf-8", errors="replace")), "text"
    elif fmt in PANDOC_INPUTS:
        media = Path(out_dir) / "media"
        md = run_pandoc([str(input_path), "-t", "gfm", "--wrap=none", "--markdown-headings=atx",
                         f"--extract-media={media}"])
        # pandoc writes absolute media paths; make them relative to out_dir
        md = md.replace(str(media), "media")
        method = "pandoc"
        meta = pandoc_metadata(input_path)
    else:
        raise RuntimeError(f"Unsupported input format '.{fmt}'. Supported: pdf, {', '.join(sorted(PANDOC_INPUTS))}, md, txt")
    md = clean_markdown(md)
    if not md.strip():
        raise RuntimeError("Conversion produced no text.")
    if not meta.get("title"):
        meta["title"] = fallback_title(md, input_path)
    return md, method, meta


def write_fingerprint(work_dir, input_path):
    data = {"input_file": str(Path(input_path).resolve()), "sha256": _sha256_file(input_path),
            "size": os.path.getsize(input_path)}
    _atomic_write(Path(work_dir) / "source_fingerprint.json", json.dumps(data, indent=2))
    return data


def check_fingerprint(work_dir, input_path, force=False):
    fp = Path(work_dir) / "source_fingerprint.json"
    if not fp.exists():
        return None
    try:
        old = json.loads(fp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if old.get("sha256") == _sha256_file(input_path):
        return old
    if force:
        return None
    raise RuntimeError(
        f"{work_dir} was created from different source bytes "
        f"(expected sha256 {old.get('sha256', '')[:12]}...). Delete the run directory, pass a fresh "
        f"--out-dir, or use --force to rebuild it.")


def write_config(out_dir, input_path, fmt, method, chunk_size, chunk_count, meta, existing=None):
    cfg = existing or {}
    cfg.update({
        "version": 1,
        "input_file": str(Path(input_path).resolve()),
        "input_format": fmt,
        "conversion_method": method,
        "chunk_size": chunk_size,
        "chunk_count": chunk_count,
        "source": {"title": meta.get("title", ""), "author": meta.get("author", ""), "language": "en"},
        "domain": cfg.get("domain", "auto"),
        "domain_detection": cfg.get("domain_detection"),
        "book": cfg.get("book") or {"title_ru": "", "subtitle_ru": "", "author": "", "translator": "", "publisher": ""},
        "created": cfg.get("created") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "skill_version": SKILL_VERSION,
    })
    _atomic_write(Path(out_dir) / "config.json", json.dumps(cfg, indent=2, ensure_ascii=False))
    return cfg


def load_config(out_dir):
    p = Path(out_dir) / "config.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def convert(input_path, out_dir=None, chunk_size=DEFAULT_CHUNK_SIZE, pdf_method="auto",
            keep_page_numbers=False, force=False):
    input_path = Path(input_path).resolve()
    if not input_path.is_file():
        raise RuntimeError(f"Input file not found: {input_path}")
    out_dir = Path(out_dir).resolve() if out_dir else default_out_dir(input_path)
    work_dir = out_dir / "work"
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(exist_ok=True)
    (out_dir / "media").mkdir(exist_ok=True)

    existing_cfg = load_config(out_dir)
    fp = check_fingerprint(work_dir, input_path, force=force)
    existing_chunks = sorted(os.path.basename(p) for p in glob.glob(str(work_dir / "chunk*.md")))
    if fp and existing_chunks and not force and existing_cfg and existing_cfg.get("chunk_size") == chunk_size:
        print(f"Reusing {len(existing_chunks)} existing chunks in {work_dir} (source unchanged)")
        cfg = existing_cfg
        summary = {"out_dir": str(out_dir), "chunk_count": len(existing_chunks),
                   "title": cfg["source"]["title"], "author": cfg["source"]["author"],
                   "method": cfg.get("conversion_method", ""), "reused": True}
        return cfg, summary

    fmt = input_format(input_path)
    md, method, meta = to_markdown(input_path, out_dir, pdf_method=pdf_method, keep_page_numbers=keep_page_numbers)
    input_md = work_dir / "input.md"
    _atomic_write(input_md, md)
    print(f"Converted {input_path.name} via {method}: {len(md)} chars -> {input_md}")

    # Existing outputs would no longer line up with new chunks.
    for old in glob.glob(str(work_dir / "output_chunk*.md")):
        os.remove(old)
    chunk_files = split_markdown(md, str(work_dir), chunk_size)
    print(f"Split into {len(chunk_files)} chunks (target {chunk_size} chars)")
    manifest.create_manifest(str(work_dir), chunk_files, str(input_md))
    write_fingerprint(work_dir, input_path)
    cfg = write_config(out_dir, input_path, fmt, method, chunk_size, len(chunk_files), meta,
                       existing=existing_cfg if not force else None)
    summary = {"out_dir": str(out_dir), "chunk_count": len(chunk_files), "title": meta["title"],
               "author": meta["author"], "method": method, "reused": False}
    return cfg, summary


def main(argv=None):
    parser = argparse.ArgumentParser(description="Convert a book into Markdown chunks for roman-urdu-book")
    parser.add_argument("input", help="Input file (pdf, docx, epub, html, md, txt, odt, rtf, fb2)")
    parser.add_argument("--out-dir", help="Run directory (default: <input dir>/<stem>_roman_urdu)")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE, help="Target chars per chunk")
    parser.add_argument("--pdf-method", choices=("auto",) + PDF_METHODS, default="auto")
    parser.add_argument("--keep-page-numbers", action="store_true", help="Do not drop page-number lines from PDFs")
    parser.add_argument("--force", action="store_true", help="Rebuild chunks even if the run dir exists")
    args = parser.parse_args(argv)
    try:
        _, summary = convert(args.input, args.out_dir, args.chunk_size, args.pdf_method,
                             args.keep_page_numbers, args.force)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
