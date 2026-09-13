#!/usr/bin/env python3
"""
lint_roman_urdu.py - Deterministic checker for translated Roman Urdu chunks.

Compares each output_chunkNNNN.md against its source chunkNNNN.md and reports
structural, citation, commentary and untranslated-text ERRORS, plus spelling,
honorific, Urdu-script and length WARNINGS. With --fix, safe spelling
normalisations from glossary/spelling-rules.json are applied in place.

Usage:
    lint_roman_urdu.py <out_dir> (--all | --chunks chunk0001 chunk0002 ...)
                       [--fix] [--json] [--strict] [--rules path]
    lint_roman_urdu.py --file OUT.md --source SRC.md [--fix] [--json] [--rules path]

Exit code: 1 if any error (or any warning with --strict), else 0.

Report shape (per chunk):
    {"chunk_id": "chunk0001", "errors": [{"code", "message", "detail"?}],
     "warnings": [...], "fixes": {canonical: count}, "ratio": 1.23}
"""

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RULES_PATH = SKILL_ROOT / "glossary" / "spelling-rules.json"

ARABIC_CHARS = "؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿"
ARABIC_RE = re.compile(f"[{ARABIC_CHARS}]")
ARABIC_RUN_RE = re.compile(f"[{ARABIC_CHARS}][{ARABIC_CHARS}\\sً-ٰٟ]*")

FENCE_RE = re.compile(r"^\s*(```|~~~)")
HEADING_RE = re.compile(r"^(#{1,6})\s+\S")
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\S")
BLOCKQUOTE_RE = re.compile(r"^\s*>")
TABLE_ROW_RE = re.compile(r"^\s*\|")
IMAGE_RE = re.compile(r"(?<!\\)!\[[^\]]*\]\(\s*([^)\s]+)[^)]*\)")
LINK_RE = re.compile(r"(?<!!)(?<!\\)\[[^\]]*\]\(\s*([^)\s]+)[^)]*\)")
FOOTNOTE_MARK_RE = re.compile(r"\[\^[^\]\s]+\]")
URL_RE = re.compile(r"(?:https?://|www\.)\S+")
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
CITATION_PAREN_RE = re.compile(r"[\(\[][^()\[\]\n]*?:\s*[^()\[\]\n]*?\d[^()\[\]\n]*[\)\]]")
NUM_REF_RE = re.compile(r"\b\d+[:/]\d+\b")
NAMED_REF_RE = re.compile(r"\(([A-Za-z][A-Za-z\s\-'.]*):\s*(\d+[\d,\s]*)\)")
WORD_RE = re.compile(r"[A-Za-z']+")

HONORIFIC_SUBJECT_RE = re.compile(r"\b(Rasoolullah|Nabi|Huzoor|Muhammad)\b")
SAW_RE = re.compile(r"sallallahu\s+alaihi\s+wasallam", re.IGNORECASE)
COMMENTARY_START_RE = re.compile(
    r"^(Here\b|Sure\b|Translation\b|Below\b|Note:|Okay\b|Certainly\b|Of course\b)",
    re.IGNORECASE,
)

# English function/content words that are NOT Roman Urdu homographs. Words
# such as "is", "the", "so", "to", "do", "ho", "me", "main", "us", "un", "in",
# "on", "or", "no", "he", "be", "an", "ham", "hum", "ki", "ka", "ko", "se",
# "na", "par", "per", "sab", "kar", "jo", "jab", "tab", "ab", "ye", "wo",
# "aur", "bhi", "phir", "tak", "hi", "bas", "mat", "log" are deliberately absent.
ENGLISH_STOPLIST = frozenset(
    """
    and of with from which their there would should because about between
    through without these those been have has will they them into than when
    what where whom also only very this that were are not but his her its our
    your who how why some any each other more most such upon after before
    while during then was for by at as it if can could all one two many must
    may might shall does did done being over under again never always every
    both either neither whether however therefore thus hence among against
    toward towards within until since although though unless whereas said
    says made make makes people person things thing way ways know knows knew
    known seen come came went gone got give gave given take took taken here
    """.split()
)

BUILTIN_RULES = [
    {"canonical": "ke", "reject": ["keh", "kay"], "safe_fix": True},
    {"canonical": "mein", "reject": ["mei", "mn"], "safe_fix": True},
    {"canonical": "nahi", "reject": ["nahin", "nahee", "nai", "nhi"], "safe_fix": True},
    {"canonical": "yeh", "reject": ["ye"], "safe_fix": True},
    {"canonical": "woh", "reject": ["wo", "vo", "voh"], "safe_fix": True},
    {"canonical": "Tauheed", "reject": ["Tawheed", "Tavheed", "Tauhid", "Tawhid"], "safe_fix": True, "case_insensitive": True},
    {"canonical": "Ta'ala", "reject": ["Ta'aala", "Taala", "Ta'alaa", "Ta'aalaa"], "safe_fix": True, "case_insensitive": True},
    {
        "canonical": "Sallallahu Alaihi Wasallam",
        "reject": ["Sallallahu alaihe wa sallam", "SAW", "SAWS", "PBUH"],
        "safe_fix": True,
        "regex": r"(?i)sall?all?ahu\s+ala[iy]h[ei]\s+wa\s*sall?am|\(\s*(?:SAW|SAWS|PBUH|S\.A\.W\.?)\s*\)",
    },
    {
        "canonical": "Radiallahu Anhu",
        "reject": ["Raziallahu anhu", "raziyallahu anhu"],
        "safe_fix": True,
        "regex": r"(?i)ra[dz]i?y?all?ahu\s+anhu\b",
    },
    {"canonical": "Rahimahullah", "reject": ["Rahimullah", "rahmatullah alaih"], "safe_fix": False},
]


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

def _compile_rule(rule):
    r = dict(rule)
    if r.get("regex"):
        r["_pattern"] = re.compile(r["regex"])
    else:
        rejects = [re.escape(v) for v in r.get("reject", []) if v]
        if not rejects:
            r["_pattern"] = None
        else:
            # Longest first so multi-word variants win over their prefixes.
            rejects.sort(key=len, reverse=True)
            flags = re.IGNORECASE  # whole-word, any case; case is preserved on replace
            r["_pattern"] = re.compile(r"(?<![\w'])(?:" + "|".join(rejects) + r")(?![\w'])", flags)
    r.setdefault("safe_fix", False)
    return r


def load_rules(path=None):
    """Load spelling rules from JSON. Falls back to BUILTIN_RULES when the
    file is missing or unreadable."""
    candidates = [path] if path else [DEFAULT_RULES_PATH]
    for p in candidates:
        if p and os.path.isfile(str(p)):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                rules = data.get("rules", data if isinstance(data, list) else [])
                return [_compile_rule(r) for r in rules if r.get("canonical")]
            except (OSError, ValueError) as e:
                print(f"WARNING: could not load rules from {p}: {e}; using built-in rules", file=sys.stderr)
                break
    return [_compile_rule(r) for r in BUILTIN_RULES]


def _protected_spans(text):
    """Spans (start, end) that spelling fixes must not touch."""
    spans = []
    # fenced code blocks
    pos = 0
    lines = text.split("\n")
    in_fence = False
    fence_start = 0
    offset = 0
    for line in lines:
        if FENCE_RE.match(line):
            if not in_fence:
                in_fence = True
                fence_start = offset
            else:
                in_fence = False
                spans.append((fence_start, offset + len(line)))
        offset += len(line) + 1
    if in_fence:
        spans.append((fence_start, len(text)))
    for rx in (INLINE_CODE_RE, URL_RE, ARABIC_RUN_RE, CITATION_PAREN_RE):
        for m in rx.finditer(text):
            spans.append((m.start(), m.end()))
    spans.sort()
    return spans


def _in_spans(pos, spans):
    for s, e in spans:
        if s <= pos < e:
            return True
        if s > pos:
            break
    return False


def _preserve_case(matched, canonical):
    if len(matched) > 1 and matched.isupper() and matched.isalpha():
        return canonical.upper()
    if matched[:1].isupper():
        return canonical[:1].upper() + canonical[1:]
    if canonical[:1].isupper():
        # Proper terms (Tauheed, Ta'ala, honorifics) stay capitalised.
        return canonical
    return canonical


def _iter_rule_matches(text, rules, spans):
    for rule in rules:
        pat = rule.get("_pattern")
        if pat is None:
            continue
        for m in pat.finditer(text):
            if _in_spans(m.start(), spans):
                continue
            if m.group(0).lower() == rule["canonical"].lower():
                continue
            yield rule, m


def apply_fixes(text, rules):
    """Apply safe spelling fixes. Returns (new_text, {canonical: count})."""
    spans = _protected_spans(text)
    counts = Counter()
    edits = []
    for rule, m in _iter_rule_matches(text, rules, spans):
        if not rule.get("safe_fix"):
            continue
        matched = m.group(0)
        repl = _preserve_case(matched, rule["canonical"])
        if matched.startswith("(") and matched.endswith(")") and not rule["canonical"].startswith("("):
            repl = f"({repl})"
        edits.append((m.start(), m.end(), repl, rule["canonical"]))
    # Apply non-overlapping edits from the end.
    edits.sort(key=lambda e: e[0])
    filtered = []
    last_end = -1
    for e in edits:
        if e[0] < last_end:
            continue
        filtered.append(e)
        last_end = e[1]
    out = text
    for s, e, repl, canonical in reversed(filtered):
        out = out[:s] + repl + out[e:]
        counts[canonical] += 1
    return out, dict(counts)


def find_spelling_issues(text, rules):
    """Remaining reject-variant hits: {canonical: {variant: count}}."""
    spans = _protected_spans(text)
    issues = {}
    for rule, m in _iter_rule_matches(text, rules, spans):
        issues.setdefault(rule["canonical"], Counter())[m.group(0)] += 1
    return {k: dict(v) for k, v in issues.items()}


# ---------------------------------------------------------------------------
# Structure helpers
# ---------------------------------------------------------------------------

def _split_code(text):
    """Return (prose_lines, fence_count) with fenced-code contents removed."""
    prose = []
    fences = 0
    in_fence = False
    for line in text.split("\n"):
        if FENCE_RE.match(line):
            fences += 1
            in_fence = not in_fence
            continue
        if not in_fence:
            prose.append(line)
    return prose, fences


def _features(text):
    prose, fences = _split_code(text)
    joined = "\n".join(prose)
    return {
        "headings": [len(m.group(1)) for m in (HEADING_RE.match(l) for l in prose) if m],
        "list_items": sum(1 for l in prose if LIST_ITEM_RE.match(l)),
        "blockquotes": sum(1 for l in prose if BLOCKQUOTE_RE.match(l)),
        "table_rows": sum(1 for l in prose if TABLE_ROW_RE.match(l)),
        "fences": fences,
        "images": Counter(IMAGE_RE.findall(joined)),
        "links": Counter(LINK_RE.findall(joined)),
        "footnotes": set(FOOTNOTE_MARK_RE.findall(joined)),
        "arabic_chars": len(ARABIC_RE.findall(text)),
    }


def check_structure(src, out):
    errors = []
    a, b = _features(src), _features(out)
    if a["headings"] != b["headings"]:
        errors.append({
            "code": "E_STRUCTURE",
            "message": f"heading count/levels differ: source {a['headings']} vs output {b['headings']}",
        })
    for key, label in (
        ("list_items", "list items"),
        ("blockquotes", "blockquote lines"),
        ("table_rows", "table rows"),
        ("fences", "fenced code fences"),
    ):
        if a[key] != b[key]:
            errors.append({
                "code": "E_STRUCTURE",
                "message": f"{label} differ: source {a[key]} vs output {b[key]}",
            })
    if a["images"] != b["images"]:
        errors.append({
            "code": "E_STRUCTURE",
            "message": "image references differ",
            "detail": {
                "missing": sorted((a["images"] - b["images"]).elements()),
                "extra": sorted((b["images"] - a["images"]).elements()),
            },
        })
    if a["links"] != b["links"]:
        errors.append({
            "code": "E_STRUCTURE",
            "message": "link URLs differ",
            "detail": {
                "missing": sorted((a["links"] - b["links"]).elements()),
                "extra": sorted((b["links"] - a["links"]).elements()),
            },
        })
    if a["footnotes"] != b["footnotes"]:
        errors.append({
            "code": "E_STRUCTURE",
            "message": "footnote markers differ",
            "detail": {
                "missing": sorted(a["footnotes"] - b["footnotes"]),
                "extra": sorted(b["footnotes"] - a["footnotes"]),
            },
        })
    if a["arabic_chars"] > 0:
        lo, hi = a["arabic_chars"] * 0.9, a["arabic_chars"] * 1.1
        if not (lo <= b["arabic_chars"] <= hi):
            errors.append({
                "code": "E_STRUCTURE",
                "message": f"Arabic text length differs: source {a['arabic_chars']} chars vs output {b['arabic_chars']} (must be within ±10%)",
            })
    return errors


def _norm_ws(s):
    return re.sub(r"\s+", " ", s).strip()


def check_citations(src, out):
    errors = []
    out_lower = _norm_ws(out).lower()
    missing_nums = []
    for tok in sorted(set(NUM_REF_RE.findall(src))):
        if tok not in out:
            missing_nums.append(tok)
    if missing_nums:
        errors.append({
            "code": "E_CITATION",
            "message": "verse/hadith number references missing from output",
            "detail": missing_nums,
        })
    missing_refs = []
    for m in NAMED_REF_RE.finditer(src):
        full = _norm_ws(m.group(0)).lower()
        if full in out_lower:
            continue
        name_words = [w for w in re.findall(r"[A-Za-z']+", m.group(1)) if len(w) > 2]
        key = name_words[-1].lower() if name_words else ""
        nums = re.findall(r"\d+", m.group(2))
        if key and all(
            re.search(re.escape(key) + r"[^()\n]{0,40}?(?<!\d)" + re.escape(n) + r"(?!\d)", out_lower)
            for n in nums
        ):
            continue
        missing_refs.append(_norm_ws(m.group(0)))
    if missing_refs:
        errors.append({
            "code": "E_CITATION",
            "message": "source references not preserved in output",
            "detail": sorted(set(missing_refs)),
        })
    return errors


def check_commentary(src, out):
    errors = []
    stripped = out.lstrip()
    first_line = stripped.split("\n", 1)[0] if stripped else ""
    if COMMENTARY_START_RE.match(first_line):
        errors.append({
            "code": "E_COMMENTARY",
            "message": "output starts with commentary instead of the translation",
            "detail": first_line[:120],
        })
    if stripped.startswith("```") and not src.lstrip().startswith("```"):
        errors.append({
            "code": "E_COMMENTARY",
            "message": "output is wrapped in a code fence that the source does not have",
        })
    if "[translator's note" in out.lower() and "[translator's note" not in src.lower():
        errors.append({
            "code": "E_COMMENTARY",
            "message": "output contains a translator's note not present in the source",
        })
    return errors


def _is_skippable_line(line):
    s = line.strip()
    if not s:
        return True
    if URL_RE.search(s) or ARABIC_RE.search(s):
        return True
    if CITATION_PAREN_RE.fullmatch(s):
        return True
    if s.startswith("![") or s.startswith("|"):
        return True
    return False


def check_untranslated(out):
    errors = []
    prose, _ = _split_code(out)
    hits = []
    for line in prose:
        if _is_skippable_line(line):
            continue
        # strip inline code and links' URLs
        clean = INLINE_CODE_RE.sub(" ", line)
        clean = re.sub(r"\]\([^)]*\)", "]", clean)
        tokens = [t.lower().strip("'") for t in WORD_RE.findall(clean)]
        tokens = [t for t in tokens if t]
        if len(tokens) < 8:
            continue
        eng = sum(1 for t in tokens if t in ENGLISH_STOPLIST)
        if eng / len(tokens) >= 0.30:
            hits.append(line.strip()[:160])
    if hits:
        errors.append({
            "code": "E_UNTRANSLATED",
            "message": f"{len(hits)} line(s) look like untranslated English",
            "detail": hits[:10],
        })
    return errors


def _honorific_forms(glossary):
    """Map honorific id -> list of plain-text forms (without parentheses)."""
    forms = {}
    for h in (glossary or {}).get("honorifics", []) or []:
        hid = h.get("id")
        if not hid:
            continue
        vals = []
        for key in ("target", "female_target", "plural_target", "dual_target"):
            v = h.get(key)
            if v:
                vals.append(v.strip("() ").lower())
        forms[hid] = vals
    return forms


def check_honorifics(out, glossary=None):
    warnings = []
    prose, _ = _split_code(out)
    text = "\n".join(l for l in prose if not ARABIC_RE.search(l))

    # Pattern A: the Prophet's names without Sallallahu Alaihi Wasallam.
    misses = []
    for m in HONORIFIC_SUBJECT_RE.finditer(text):
        after = text[m.end():m.end() + 40]
        before = text[max(0, m.start() - 12):m.start()]
        if m.group(1) == "Muhammad":
            if re.match(r"\s+(?:bin|ibn|b\.|ibne|ibn-e)\b", after, re.IGNORECASE):
                continue
            if re.search(r"\b(?:bin|ibn|ibne|ibn-e|b\.)\s*$", before, re.IGNORECASE):
                continue
        if SAW_RE.search(after):
            continue
        snippet = text[max(0, m.start() - 20):m.end() + 30].replace("\n", " ")
        misses.append(snippet.strip())
    if misses:
        warnings.append({
            "code": "W_HONORIFIC",
            "message": f"{len(misses)} mention(s) of the Prophet without 'Sallallahu Alaihi Wasallam'",
            "detail": misses[:5],
        })

    # Pattern B: glossary terms whose honorific is required.
    forms = _honorific_forms(glossary)
    lower = text.lower()
    for term in (glossary or {}).get("terms", []) or []:
        hid = term.get("honorific")
        target = term.get("target")
        if not hid or not target or hid not in forms:
            continue
        expected = forms[hid]
        if not expected:
            continue
        pat = re.compile(r"(?<![\w'])" + re.escape(target.lower()) + r"(?![\w'])")
        term_misses = []
        for m in pat.finditer(lower):
            if _in_spans(m.start(), [(c.start(), c.end()) for c in CITATION_PAREN_RE.finditer(text)]):
                continue
            after = lower[m.end():m.end() + 30]
            if any(f in after for f in expected):
                continue
            term_misses.append(text[max(0, m.start() - 15):m.end() + 30].replace("\n", " ").strip())
        if term_misses:
            warnings.append({
                "code": "W_HONORIFIC",
                "message": f"'{target}' appears {len(term_misses)} time(s) without ({expected[0]})",
                "detail": term_misses[:3],
            })
    return warnings


def _arabic_words(text):
    words = set()
    for run in ARABIC_RUN_RE.findall(text):
        for w in run.split():
            w = w.strip()
            if w:
                words.add(w)
    return words


def check_urdu_script(src, out):
    warnings = []
    src_words = _arabic_words(src)
    extra = sorted(w for w in _arabic_words(out) if w not in src_words)
    if extra:
        warnings.append({
            "code": "W_URDU_SCRIPT",
            "message": f"{len(extra)} Arabic/Urdu-script word(s) in output not present in source",
            "detail": extra[:10],
        })
    return warnings


def check_length(src, out):
    s = len(src.strip())
    o = len(out.strip())
    ratio = (o / s) if s else 0.0
    if s == 0:
        return [], ratio
    lo, hi = (0.5, 4.0) if s < 200 else (0.9, 2.3)
    if ratio < lo or ratio > hi:
        return [{
            "code": "W_LENGTH",
            "message": f"output/source length ratio {ratio:.2f} outside [{lo}, {hi}]",
        }], ratio
    return [], ratio


def lint_pair(src_text, out_text, rules, glossary=None, fix=False, chunk_id=""):
    """Lint one (source, output) pair. Returns (report, fixed_text)."""
    report = {"chunk_id": chunk_id, "errors": [], "warnings": [], "fixes": {}, "ratio": 0.0}
    if out_text is None or not out_text.strip():
        report["errors"].append({"code": "E_EMPTY", "message": "output is empty or missing"})
        return report, out_text
    fixed = out_text
    if fix:
        fixed, counts = apply_fixes(out_text, rules)
        report["fixes"] = counts
    report["errors"].extend(check_commentary(src_text, fixed))
    report["errors"].extend(check_structure(src_text, fixed))
    report["errors"].extend(check_citations(src_text, fixed))
    report["errors"].extend(check_untranslated(fixed))
    issues = find_spelling_issues(fixed, rules)
    if issues:
        report["warnings"].append({
            "code": "W_SPELLING",
            "message": "non-canonical spellings" + (" remain" if fix else " found (run with --fix)"),
            "detail": issues,
        })
    report["warnings"].extend(check_honorifics(fixed, glossary))
    report["warnings"].extend(check_urdu_script(src_text, fixed))
    length_warnings, ratio = check_length(src_text, fixed)
    report["warnings"].extend(length_warnings)
    report["ratio"] = round(ratio, 3)
    return report, fixed


# ---------------------------------------------------------------------------
# Run-directory driver
# ---------------------------------------------------------------------------

def _read(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None


def _load_glossary(work_dir):
    p = os.path.join(work_dir, "glossary.json")
    if os.path.isfile(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None
    return None


def discover_chunk_ids(work_dir):
    manifest = os.path.join(work_dir, "manifest.json")
    if os.path.isfile(manifest):
        try:
            with open(manifest, "r", encoding="utf-8") as f:
                data = json.load(f)
            ids = [c["id"] for c in sorted(data.get("chunks", []), key=lambda c: c.get("order", 0))]
            if ids:
                return ids
        except (OSError, ValueError, KeyError):
            pass
    ids = []
    for p in sorted(glob.glob(os.path.join(work_dir, "chunk*.md"))):
        name = os.path.basename(p)
        if name.startswith("output_"):
            continue
        ids.append(os.path.splitext(name)[0])
    return ids


def lint_run_dir(out_dir, chunk_ids=None, fix=False, rules=None, strict=False):
    work_dir = os.path.join(out_dir, "work")
    if not os.path.isdir(work_dir):
        raise FileNotFoundError(f"no work/ directory in {out_dir}")
    rules = rules if rules is not None else load_rules()
    glossary = _load_glossary(work_dir)
    ids = chunk_ids or discover_chunk_ids(work_dir)
    reports = {}
    total_fixes = Counter()
    for cid in ids:
        cid = cid[:-3] if cid.endswith(".md") else cid
        src = _read(os.path.join(work_dir, f"{cid}.md"))
        out_path = os.path.join(work_dir, f"output_{cid}.md")
        out = _read(out_path)
        if src is None:
            report = {"chunk_id": cid, "errors": [{"code": "E_EMPTY", "message": f"source chunk {cid}.md not found"}],
                      "warnings": [], "fixes": {}, "ratio": 0.0}
        else:
            report, fixed = lint_pair(src, out, rules, glossary, fix=fix, chunk_id=cid)
            if fix and fixed is not None and fixed != out:
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(fixed)
        reports[cid] = report
        total_fixes.update(report.get("fixes", {}))
        with open(os.path.join(work_dir, f"lint_{cid}.json"), "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
    summary = {
        "chunks": len(reports),
        "errors": sum(len(r["errors"]) for r in reports.values()),
        "warnings": sum(len(r["warnings"]) for r in reports.values()),
        "fixes": dict(total_fixes),
        "strict": strict,
        "per_chunk": {
            cid: {"errors": len(r["errors"]), "warnings": len(r["warnings"]), "ratio": r["ratio"]}
            for cid, r in reports.items()
        },
        "chunks_with_errors": [cid for cid, r in reports.items() if r["errors"]],
    }
    with open(os.path.join(work_dir, "lint_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    return summary, reports


def _print_human(reports, summary):
    for cid, r in reports.items():
        status = "ERROR" if r["errors"] else ("warn" if r["warnings"] else "ok")
        print(f"[{status}] {cid}  ratio={r['ratio']}  fixes={sum(r['fixes'].values())}")
        for e in r["errors"]:
            print(f"    E {e['code']}: {e['message']}")
            if e.get("detail"):
                print(f"        {json.dumps(e['detail'], ensure_ascii=False)[:300]}")
        for w in r["warnings"]:
            print(f"    W {w['code']}: {w['message']}")
            if w.get("detail"):
                print(f"        {json.dumps(w['detail'], ensure_ascii=False)[:300]}")
    print(
        f"\nSummary: {summary['chunks']} chunk(s), {summary['errors']} error(s), "
        f"{summary['warnings']} warning(s), {sum(summary['fixes'].values())} spelling fix(es)"
    )


def main(argv=None):
    ap = argparse.ArgumentParser(description="Lint Roman Urdu translation chunks")
    ap.add_argument("out_dir", nargs="?", help="run directory containing work/")
    ap.add_argument("--all", action="store_true", help="lint every chunk in the manifest")
    ap.add_argument("--chunks", nargs="+", help="chunk ids to lint (chunk0001 ...)")
    ap.add_argument("--file", help="single output file to lint")
    ap.add_argument("--source", help="source chunk for --file")
    ap.add_argument("--fix", action="store_true", help="apply safe spelling fixes in place")
    ap.add_argument("--json", action="store_true", help="print JSON instead of text")
    ap.add_argument("--strict", action="store_true", help="treat warnings as failures")
    ap.add_argument("--rules", help="path to spelling-rules.json")
    ap.add_argument("--glossary", help="path to glossary.json (single-file mode)")
    args = ap.parse_args(argv)

    rules = load_rules(args.rules)

    if args.file:
        if not args.source:
            ap.error("--file requires --source")
        src = _read(args.source)
        out = _read(args.file)
        if src is None:
            print(f"ERROR: cannot read {args.source}", file=sys.stderr)
            return 2
        glossary = None
        if args.glossary and os.path.isfile(args.glossary):
            with open(args.glossary, "r", encoding="utf-8") as f:
                glossary = json.load(f)
        report, fixed = lint_pair(src, out, rules, glossary, fix=args.fix, chunk_id=Path(args.file).stem)
        if args.fix and fixed is not None and fixed != out:
            with open(args.file, "w", encoding="utf-8") as f:
                f.write(fixed)
        summary = {
            "chunks": 1, "errors": len(report["errors"]), "warnings": len(report["warnings"]),
            "fixes": report["fixes"], "strict": args.strict,
            "per_chunk": {report["chunk_id"]: {"errors": len(report["errors"]), "warnings": len(report["warnings"]), "ratio": report["ratio"]}},
            "chunks_with_errors": [report["chunk_id"]] if report["errors"] else [],
        }
        reports = {report["chunk_id"]: report}
    else:
        if not args.out_dir:
            ap.error("out_dir is required unless --file is used")
        if not args.all and not args.chunks:
            ap.error("specify --all or --chunks")
        try:
            summary, reports = lint_run_dir(
                args.out_dir, chunk_ids=None if args.all else args.chunks,
                fix=args.fix, rules=rules, strict=args.strict,
            )
        except FileNotFoundError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2

    if args.json:
        print(json.dumps({"summary": summary, "reports": reports}, indent=2, ensure_ascii=False))
    else:
        _print_human(reports, summary)

    if summary["errors"] > 0:
        return 1
    if args.strict and summary["warnings"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
