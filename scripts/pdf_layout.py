#!/usr/bin/env python3
"""Layout-aware PDF -> Markdown via poppler's ``pdftohtml -xml``.

``pdftotext`` throws away the font size, weight and position of every line, so
sentence-case headings ("Knowing that Allah responds to prayers") become body
text and paragraph breaks have to be guessed from punctuation. ``pdftohtml``
ships in the same poppler package and emits one ``<text>`` element per line
fragment with ``top/left/width/height`` and a ``font`` id whose size is known.
This module turns that into Markdown:

- lines set in a font larger than the body font become headings (largest
  size -> ``##``, next -> ``###``, ...);
- bold body-size lines that stand alone become the next heading level;
- plain lines that stand alone (blank space above and below), are short,
  start with a capital and carry no sentence punctuation become the level
  below that;
- paragraph breaks come from vertical gaps larger than the body line pitch;
- running headers/footers, page numbers and the source's own contents block
  (when every entry matches a detected heading) are dropped.

Standard library only. ``pdf_to_markdown`` raises ``RuntimeError`` when
``pdftohtml`` is missing or its output is unusable, so callers can fall back to
``pdftotext``.
"""
from __future__ import annotations

import re
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass

# Same sentence/list/Arabic predicates as convert.py, kept local so this
# module has no import cycle with it.
_SENTENCE_END = re.compile(r'[.!?:;"”’)\]۔؟]\d{0,2}\s*$')
_LIST_LINE = re.compile(r"^(?:\d{1,3}[.)]|[-*•▪◦]|(?!p[.)]\s+\d)[a-z][.)]|[ivx]{1,4}[.)])\s+\S")  # not "p. 89"
_NUMBERED = re.compile(r"^\d{1,3}[.)]\s+")
_ARABIC_CHARS = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")
_QUOTE_START = re.compile(r'^["“‘\'«(\[]')
_CONTENTS_TITLE = re.compile(r"^(table\s+of\s+)?contents$|^index$|^fehrist", re.I)
_BRACKETED = re.compile(r"^\[.*\]$")
_BASMALA = re.compile(r"^(bismillah|in the name of allah)\b", re.I)
_CONTINUATION_START = re.compile(r"^[a-z0-9\)\]”’\",.;:]")
_EOL_HYPHEN = re.compile(r"[A-Za-z]-$")  # a word broken (or a compound split) at a line end
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

HEADING_SIZE_RATIO = 1.15   # font size / body size that makes a line a heading
PARA_GAP_RATIO = 1.35       # top-to-top gap / body pitch that starts a paragraph
SHORT_LINE_RATIO = 0.85     # width / text width below which a lone line can be a heading
SPACED_DOC_MIN_RATIO = 0.05 # share of body gaps > PARA_GAP_RATIO*pitch that proves paragraph spacing
MAX_HEADING_WORDS = 14
MAX_HEADING_LEVEL = 4
COVER_MAX_PAGES = 5          # a cover/title-page block never runs past this page


@dataclass
class Line:
    page: int
    top: float
    bottom: float
    left: float
    right: float
    size: float
    bold: bool
    text: str
    level: int = 0            # 0 = body, 2..4 = heading level
    kind: str = ""            # "size" | "bold" | "plain" for headings
    para_break_before: bool = False
    drop: bool = False

    @property
    def width(self):
        return self.right - self.left

    @property
    def words(self):
        return len(self.text.split())


# ---------------------------------------------------------------------------
# pdftohtml
# ---------------------------------------------------------------------------

def run_pdftohtml_xml(pdf_path, exe="pdftohtml", timeout=1800):
    """Return the ``pdftohtml -xml`` output as a UTF-8 string."""
    cmd = [exe, "-xml", "-i", "-q", "-enc", "UTF-8", "-stdout", str(pdf_path)]
    res = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if res.returncode != 0 or not res.stdout.strip():
        err = res.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(err or "pdftohtml produced no output")
    return res.stdout.decode("utf-8", "replace")


def _parse_xml(xml_text):
    try:
        return ET.fromstring(xml_text)
    except ET.ParseError:
        cleaned = _CONTROL_CHARS.sub("", xml_text)
        try:
            return ET.fromstring(cleaned)
        except ET.ParseError as e:
            raise RuntimeError(f"pdftohtml XML could not be parsed: {e}") from e


def _piece_text(el):
    return "".join(el.itertext())


def _has_tag(el, tag):
    return any(True for _ in el.iter(tag))


# ---------------------------------------------------------------------------
# Lines
# ---------------------------------------------------------------------------

def _group_pieces_into_lines(pieces):
    """pieces: list of dicts with top/left/width/height/size/bold/text (one page).

    Fragments whose vertical extents overlap by at least half the smaller
    height belong to the same line.
    """
    pieces = sorted(pieces, key=lambda p: (p["top"], p["left"]))
    lines = []
    for p in pieces:
        placed = False
        for ln in reversed(lines[-4:]):
            overlap = min(ln["bottom"], p["top"] + p["height"]) - max(ln["top"], p["top"])
            if overlap >= 0.5 * min(p["height"], ln["bottom"] - ln["top"]):
                ln["pieces"].append(p)
                ln["top"] = min(ln["top"], p["top"])
                ln["bottom"] = max(ln["bottom"], p["top"] + p["height"])
                placed = True
                break
        if not placed:
            lines.append({"top": p["top"], "bottom": p["top"] + p["height"], "pieces": [p]})
    return lines


def _line_from_group(page, group):
    parts = sorted(group["pieces"], key=lambda p: p["left"])
    text = ""
    prev = None
    for p in parts:
        t = p["text"]
        if prev is not None:
            gap = p["left"] - (prev["left"] + prev["width"])
            if gap > 2 and not text.endswith(" ") and not t.startswith(" "):
                text += " "
        text += t
        prev = p
    text = re.sub(r"\s+", " ", text).strip()
    weights = Counter()
    bold_chars = 0
    total = 0
    for p in parts:
        n = len(p["text"].strip())
        if not n:
            continue
        weights[p["size"]] += n
        total += n
        if p["bold"]:
            bold_chars += n
    size = weights.most_common(1)[0][0] if weights else 0
    return Line(page=page, top=group["top"], bottom=group["bottom"],
                left=min(p["left"] for p in parts),
                right=max(p["left"] + p["width"] for p in parts),
                size=size, bold=total > 0 and bold_chars >= 0.6 * total, text=text)


def parse_lines(root):
    """Return a list of Line objects in reading order (page, top, left)."""
    lines = []
    fonts = {}  # font ids are global; each spec is declared once, on the page that first uses it
    for page_el in root.iter("page"):
        page = int(page_el.get("number", "0") or 0)
        for fs in page_el.iter("fontspec"):
            try:
                fonts[fs.get("id")] = float(fs.get("size", "0"))
            except ValueError:
                fonts[fs.get("id")] = 0.0
        pieces = []
        for el in page_el.iter("text"):
            text = _piece_text(el)
            if not text.strip():
                continue
            try:
                top, left = float(el.get("top", "0")), float(el.get("left", "0"))
                width, height = float(el.get("width", "0")), float(el.get("height", "0"))
            except ValueError:
                continue
            size = fonts.get(el.get("font"), 0.0)
            pieces.append({"top": top, "left": left, "width": width, "height": height or size or 1.0,
                           "size": size, "bold": _has_tag(el, "b"), "text": text})
        for group in _group_pieces_into_lines(pieces):
            ln = _line_from_group(page, group)
            if ln.text:
                lines.append(ln)
    return lines


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def _body_size(lines):
    weights = Counter()
    for ln in lines:
        weights[ln.size] += len(ln.text)
    return weights.most_common(1)[0][0] if weights else 0.0


def _text_width(lines, body):
    widths = sorted(ln.width for ln in lines if ln.size == body and ln.width > 0)
    if not widths:
        widths = sorted(ln.width for ln in lines if ln.width > 0) or [1.0]
    return max(1.0, widths[min(len(widths) - 1, int(len(widths) * 0.9))])


def _body_pitch(lines, body):
    """Typical top-to-top distance between consecutive body lines on a page.

    The 20th percentile, not the median: in a document made of short paragraphs
    most gaps are paragraph gaps, and the median would swallow every break.
    """
    gaps = []
    for a, b in zip(lines, lines[1:]):
        if a.page == b.page and a.size == body and b.size == body:
            g = b.top - a.top
            if 0 < g < 3 * max(body, 1.0):
                gaps.append(g)
    if gaps:
        gaps.sort()
        return gaps[min(len(gaps) - 1, int(len(gaps) * 0.2))]
    return max(body, 1.0) * 1.2


# ---------------------------------------------------------------------------
# Noise: running headers/footers, page numbers, navigation links
# ---------------------------------------------------------------------------

def _norm(s):
    return re.sub(r"[^a-z0-9؀-ۿ]+", "", s.lower())


def mark_noise(lines):
    pages = {ln.page for ln in lines}
    n_pages = max(1, len(pages))
    per_page_texts = {}
    for ln in lines:
        per_page_texts.setdefault(ln.page, set()).add(_norm(ln.text))
    counts = Counter()
    for texts in per_page_texts.values():
        for t in texts:
            counts[t] += 1
    repeated_min = max(3, int(0.3 * n_pages + 0.999))
    first_last = {}
    for ln in lines:
        fl = first_last.setdefault(ln.page, [ln, ln])
        fl[1] = ln
    for ln in lines:
        key = _norm(ln.text)
        if not key or not any(ch.isalnum() for ch in ln.text):
            # Nothing but punctuation or stray Arabic vowel marks split off their letters.
            ln.drop = True
            continue
        if len(ln.text) < 120 and counts[key] >= repeated_min:
            ln.drop = True
        elif _BRACKETED.match(ln.text) and counts[key] >= 3:
            ln.drop = True
        elif re.fullmatch(r"[\divx]{1,4}", ln.text.strip(), re.I) and ln in first_last.get(ln.page, ()):
            ln.drop = True
    return [ln for ln in lines if not ln.drop]


# ---------------------------------------------------------------------------
# Headings and paragraphs
# ---------------------------------------------------------------------------

def _is_arabic(s):
    letters = [ch for ch in s if ch.isalpha()]
    return bool(letters) and sum(1 for ch in letters if _ARABIC_CHARS.match(ch)) >= 0.6 * len(letters)


def _heading_text_ok(text, allow_single_word=True):
    s = text.strip()
    if not s or _is_arabic(s) or s.endswith("-") or _QUOTE_START.match(s) or _BASMALA.match(s):
        return False
    words = s.split()
    if len(words) > MAX_HEADING_WORDS or len(s) > 140:
        return False
    if _SENTENCE_END.search(s) and not s.endswith(")"):
        return False
    if s.endswith(")") and s.count("(") == 0:
        return False
    body = _NUMBERED.sub("", s)
    if not body or not (body[0].isupper() or body[0].isdigit()):
        return False
    if len(words) == 1 and not (allow_single_word and re.fullmatch(r"\d*[.)]?\s*[A-Z][A-Za-z'’-]{2,29}", s)):
        return False
    return True


def _uses_paragraph_spacing(lines, body, pitch):
    """True when the PDF separates paragraphs with extra vertical space."""
    gaps = [b.top - a.top for a, b in zip(lines, lines[1:])
            if a.page == b.page and a.size == body and b.size == body and b.top > a.top]
    if not gaps:
        return False
    wide = sum(1 for g in gaps if g > PARA_GAP_RATIO * pitch)
    return wide >= SPACED_DOC_MIN_RATIO * len(gaps)


def _mark_paragraph_breaks(lines, body, pitch, text_width, spaced=None):
    if spaced is None:
        spaced = _uses_paragraph_spacing(lines, body, pitch)
    thresh = PARA_GAP_RATIO * pitch
    short = 0.7 * text_width
    prev = None
    for ln in lines:
        brk = prev is None
        if prev is not None:
            structural = (ln.level > 0 or prev.level > 0
                          or _is_arabic(ln.text) or _is_arabic(prev.text)
                          or bool(_LIST_LINE.match(ln.text))
                          or (_QUOTE_START.match(ln.text) and prev.text.rstrip().endswith(":")))
            if ln.page != prev.page:
                # A sentence that ended at the page bottom starts a new paragraph unless the
                # next page clearly continues it (lower-case, digit or closing punctuation).
                brk = structural or (bool(_SENTENCE_END.search(prev.text))
                                     and not _CONTINUATION_START.match(ln.text))
            else:
                gap = ln.top - prev.top
                brk = structural or gap > thresh
                if not brk and not spaced and _SENTENCE_END.search(prev.text) and prev.width < short:
                    brk = True  # unspaced PDFs: a short sentence-final line ends the paragraph
        ln.para_break_before = brk
        prev = ln


def _standalone_flags(lines):
    """True for lines that form a paragraph on their own."""
    flags = []
    for i, ln in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        alone = ln.para_break_before and (nxt is None or nxt.para_break_before)
        flags.append(alone)
    return flags


def classify_size_headings(lines, body, pitch, text_width):
    """Mark font-size headings, merge wrapped ones, and mark paragraph breaks."""
    latin_sizes = Counter(ln.size for ln in lines if not _is_arabic(ln.text))
    bold_sizes = Counter(ln.size for ln in lines if ln.bold and not _is_arabic(ln.text))
    # Sizes used only by Arabic (Qur'an/hadith fonts are often set larger) are not heading levels.
    large = sorted({s for s in latin_sizes if s >= HEADING_SIZE_RATIO * body}, reverse=True)
    # Slightly larger bold type (e.g. 20pt bold over an 18pt body) is a heading style too,
    # when that size is mostly bold; plain lines at that size stay body text.
    emphasis = sorted({s for s in latin_sizes if body < s < HEADING_SIZE_RATIO * body
                       and bold_sizes[s] >= 2 and bold_sizes[s] >= 0.6 * latin_sizes[s]}, reverse=True)
    size_level = {s: min(MAX_HEADING_LEVEL, 2 + i) for i, s in enumerate(large + emphasis)}
    for ln in lines:
        if ln.size in size_level and (ln.size not in emphasis or ln.bold):
            ln.level, ln.kind = size_level[ln.size], "size"
    # Merge consecutive same-size heading lines (wrapped titles); demote long ones.
    merged = []
    for ln in lines:
        prev = merged[-1] if merged else None
        if (prev is not None and ln.kind == "size" and prev.kind == "size" and ln.size == prev.size
                and ln.bold == prev.bold and ln.page == prev.page and ln.top - prev.top <= 2.2 * max(ln.bottom - ln.top, 1.0)):
            prev.text = f"{prev.text} {ln.text}"
            prev.bottom = max(prev.bottom, ln.bottom)
            prev.left, prev.right = min(prev.left, ln.left), max(prev.right, ln.right)
            continue
        merged.append(ln)
    for ln in merged:
        if ln.kind == "size" and (ln.words > 3 * MAX_HEADING_WORDS or _is_arabic(ln.text)
                                  or (ln.size in emphasis and _SENTENCE_END.search(ln.text)
                                      and not ln.text.rstrip().endswith(")"))):
            ln.level, ln.kind = 0, ""
    lines = merged
    _mark_paragraph_breaks(lines, body, pitch, text_width)
    return lines, size_level


def classify_lone_headings(lines, body, pitch, text_width, size_level):
    """Bold and plain stand-alone lines become headings below the size-based levels."""
    alone = _standalone_flags(lines)
    bold_level = (max(size_level.values()) + 1) if size_level else 2
    bold_level = min(bold_level, MAX_HEADING_LEVEL)
    any_bold = False
    for ln, is_alone in zip(lines, alone):
        if ln.level or not is_alone or not ln.bold or ln.size != body:
            continue
        if _heading_text_ok(ln.text):
            ln.level, ln.kind = bold_level, "bold"
            any_bold = True
    plain_level = min(MAX_HEADING_LEVEL, bold_level + 1 if any_bold else bold_level)
    for i, (ln, is_alone) in enumerate(zip(lines, alone)):
        if ln.level or not is_alone or ln.size != body or ln.width >= SHORT_LINE_RATIO * text_width:
            continue
        if not _heading_text_ok(ln.text):
            continue
        if _NUMBERED.match(ln.text):
            # A run of numbered lone lines is a list, not headings.
            neighbours = [lines[j] for j in (i - 1, i + 1) if 0 <= j < len(lines)]
            if any(_NUMBERED.match(n.text) and alone[lines.index(n)] for n in neighbours):
                continue
        ln.level, ln.kind = plain_level, "plain"
    # Re-run breaks so new headings separate from their neighbours.
    _mark_paragraph_breaks(lines, body, pitch, text_width)
    return lines


def demote_title_block(lines):
    """A run of two or more headings opening the book with no body text between them is the
    cover (title, subtitle, author line, often repeated on a title page): keep the text as
    paragraphs, not headings. The run may span the first few pages."""
    run = []
    for ln in lines:
        if ln.page > COVER_MAX_PAGES:
            break
        text = ln.text.rstrip()
        if ln.level:
            run.append(ln)
        elif _is_arabic(text) or (ln.words <= MAX_HEADING_WORDS
                                  and (not _SENTENCE_END.search(text) or text.endswith(")"))):
            run.append(ln)  # e.g. "Book by ...", "(may Allah have mercy upon him)"
        else:
            break
    # The last heading of the run opens the body ("Introduction"); everything before it is cover.
    last_heading = max((i for i, ln in enumerate(run) if ln.level), default=-1)
    cover = run[:last_heading] if last_heading > 0 else []
    if sum(1 for ln in cover if ln.kind == "size") >= 1 and len(cover) >= 2:
        for ln in cover:
            ln.level, ln.kind = 0, ""
            ln.para_break_before = True
    return lines


def normalise_levels(lines):
    """Close gaps in the heading levels so the top level in use is ``##``.

    After the cover is demoted, a book whose chapters sit at the third or fourth
    detected size would otherwise start at ``####`` and nest nothing under it.
    """
    used = sorted({ln.level for ln in lines if ln.level})
    remap = {lvl: min(MAX_HEADING_LEVEL, 2 + i) for i, lvl in enumerate(used)}
    for ln in lines:
        if ln.level:
            ln.level = remap[ln.level]
    return lines


def drop_source_contents(lines):
    """Remove the book's own table of contents when its entries match detected headings."""
    heading_keys = [_norm(ln.text) for ln in lines if ln.level]
    for i, ln in enumerate(lines):
        # The title may be a size heading or a bold body line ("Index" in bold body type).
        if not (ln.level or ln.bold) or not _CONTENTS_TITLE.match(ln.text.strip()):
            continue
        title_level = ln.level or MAX_HEADING_LEVEL
        block = []
        for j in range(i + 1, min(len(lines), i + 120)):
            cand = lines[j]
            if cand.kind == "size" and cand.level <= title_level:
                break
            block.append(cand)
        if not block:
            continue
        # A long entry wraps: a line without a page number joins a lower-case next line.
        entries, pending = [], ""
        for k, cand in enumerate(block):
            pending = f"{pending} {cand.text}".strip()
            nxt = block[k + 1].text if k + 1 < len(block) else ""
            if re.search(r"\d\s*$", cand.text) or not nxt[:1].islower():
                entries.append(pending)
                pending = ""
        if pending:
            entries.append(pending)
        matched = 0
        for entry in entries:
            key = _norm(re.sub(r"[\s.]*\d+\s*$", "", entry))
            if key and any(hk == key or hk.startswith(key) for hk in heading_keys if hk != _norm(ln.text)):
                matched += 1
        if matched >= 2 and matched >= 0.8 * len(entries):
            ln.drop = True
            for cand in block:
                cand.drop = True
    return [ln for ln in lines if not ln.drop]


def render_markdown(lines):
    out = []
    buf = []

    def flush():
        if buf:
            text = " ".join(buf)
            out.append(re.sub(r"\s+", " ", text).strip())
            buf.clear()

    for ln in lines:
        if ln.level:
            flush()
            title = ln.text.strip()
            if title.isupper() and any(c.isalpha() for c in title):
                title = title.title()
            out.append("#" * ln.level + " " + title)
            continue
        if ln.para_break_before:
            flush()
        if buf and _EOL_HYPHEN.search(buf[-1]) and ln.text[:1].islower():
            buf[-1] = buf[-1][:-1] + ln.text          # hyphenated word wrap: de-hyphenate
        elif buf and _EOL_HYPHEN.search(buf[-1]) and ln.text[:1].isupper():
            buf[-1] = buf[-1] + ln.text               # "Al-" + "Baqarah", "Abdul-" + "Rahman": keep the hyphen
        else:
            buf.append(ln.text)
    flush()
    return "\n\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def markdown_from_xml(xml_text):
    root = _parse_xml(xml_text)
    lines = parse_lines(root)
    if not lines:
        raise RuntimeError("pdftohtml found no text (scanned/image-only PDF?)")
    lines = mark_noise(lines)
    if not lines:
        raise RuntimeError("pdftohtml found only repeated header/footer text")
    body = _body_size(lines)
    text_width = _text_width(lines, body)
    pitch = _body_pitch(lines, body)
    lines, size_level = classify_size_headings(lines, body, pitch, text_width)
    lines = drop_source_contents(lines)
    lines = classify_lone_headings(lines, body, pitch, text_width, size_level)
    lines = demote_title_block(lines)
    lines = normalise_levels(lines)
    return render_markdown(lines)


def pdf_to_markdown(pdf_path, exe="pdftohtml"):
    return markdown_from_xml(run_pdftohtml_xml(pdf_path, exe=exe))


if __name__ == "__main__":  # pragma: no cover - manual check
    import sys
    sys.stdout.write(pdf_to_markdown(sys.argv[1]))
