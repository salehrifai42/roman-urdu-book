#!/usr/bin/env python3
"""
glossary.py - Per-book glossary for consistent Roman Urdu terminology.

work/glossary.json schema (version 1):
    {"version": 1, "domain": "islamic|general", "top_n": 25,
     "terms": [{"source", "aliases": [], "target", "category", "honorific": "<id>|''",
                "gender"?: "m|f", "plural"?: bool, "note"?: str, "frequency"?: int}],
     "honorifics": [{"id", "target", "female_target"?, "plural_target"?, "dual_target"?, ...}]}

Subcommands:
    seed <out_dir> [--builtin path] [--force]
    extract-candidates <out_dir> [--min-freq 2] [--max 400] [--json]
    add <out_dir> --from-json file
    count-frequencies <out_dir>
    print-terms-for-chunk <out_dir> chunkNNNN.md [--top-n 25] [--max-terms 60]
    validate (<out_dir> | --builtin path)
    list <out_dir> [--category cat]

Term matching uses whole-word, case-insensitive regexes so "cat" never matches
"category". A surface form (source or alias) may belong to only one term.
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, OrderedDict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
DEFAULT_BUILTIN = SKILL_ROOT / "glossary" / "islamic-terms.json"
GENERAL_SEED_CATEGORIES = {"place", "book", "phrase"}
REQUIRED_TERM_KEYS = ("source", "target", "category", "honorific")
VALID_CATEGORIES = {"aqeedah", "fiqh_ibadah", "names_of_allah", "prophet", "companion", "scholar", "book",
                    "surah", "place", "phrase", "person", "organization", "concept", "title", "other"}

STOPWORDS = set("""
a an the and or but if then else of in on at to for from by with without about into onto over under
between among through during before after above below up down out off again further once here there
when where why how all any both each few more most other some such no nor not only own same so than
too very can will just should now this that these those is are was were be been being have has had
having do does did doing would could may might must shall i you he she it we they me him her us them
my your his its our their mine yours hers ours theirs what which who whom whose am as also because
until while unless although though since however therefore thus hence moreover whereas yet
chapter section part book page volume introduction conclusion preface foreword contents notes index
appendix figure table example note first second third one two three four five six seven eight nine ten
monday tuesday wednesday thursday friday saturday sunday january february march april may june july
august september october november december god lord
""".split())
CONNECTORS = {"al", "al-", "ibn", "bin", "bint", "abu", "abd", "of", "ul", "ud", "ad", "as", "an", "ar",
              "el", "de", "the", "and", "&"}


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------

def glossary_path(out_dir):
    return Path(out_dir) / "work" / "glossary.json"


def load(out_dir):
    p = glossary_path(out_dir)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def save(out_dir, data):
    p = glossary_path(out_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def load_builtin(path=None):
    p = Path(path) if path else DEFAULT_BUILTIN
    if not p.exists():
        raise RuntimeError(f"Built-in glossary not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def load_config(out_dir):
    p = Path(out_dir) / "config.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {}


def read_input(out_dir):
    p = Path(out_dir) / "work" / "input.md"
    if not p.exists():
        raise RuntimeError(f"Missing {p}; run convert.py first")
    return p.read_text(encoding="utf-8", errors="replace")


def source_chunks(out_dir):
    work = Path(out_dir) / "work"
    return sorted(p for p in work.glob("chunk*.md") if not p.name.startswith("output_"))


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

_REGEX_CACHE = {}


def surface_regex(surface):
    key = surface.strip().lower()
    rx = _REGEX_CACHE.get(key)
    if rx is None:
        rx = re.compile(r"(?<![\w'])" + re.escape(surface.strip()) + r"(?![\w'])", re.IGNORECASE)
        _REGEX_CACHE[key] = rx
    return rx


def surfaces_of(term):
    return [term.get("source", "")] + list(term.get("aliases") or [])


def count_in_text(text, surface):
    if not surface or not surface.strip():
        return 0
    return len(surface_regex(surface).findall(text))


def term_occurs(text, term):
    return any(count_in_text(text, s) for s in surfaces_of(term))


def term_frequency(text, term):
    return sum(count_in_text(text, s) for s in surfaces_of(term))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_data(data, strict_categories=False):
    """Return a list of error strings (empty = valid)."""
    errors = []
    if not isinstance(data, dict) or not isinstance(data.get("terms"), list):
        return ["glossary must be an object with a 'terms' list"]
    honorific_ids = {h.get("id") for h in data.get("honorifics") or []}
    seen = {}
    for i, t in enumerate(data["terms"]):
        where = f"terms[{i}] ({t.get('source', '?')})"
        for k in REQUIRED_TERM_KEYS:
            if k not in t:
                errors.append(f"{where}: missing key '{k}'")
        if not str(t.get("source", "")).strip():
            errors.append(f"{where}: empty source")
        if not str(t.get("target", "")).strip():
            errors.append(f"{where}: empty target")
        if t.get("honorific") and honorific_ids and t["honorific"] not in honorific_ids:
            errors.append(f"{where}: unknown honorific id '{t['honorific']}'")
        if strict_categories and t.get("category") not in VALID_CATEGORIES:
            errors.append(f"{where}: unknown category '{t.get('category')}'")
        if t.get("aliases") is not None and not isinstance(t["aliases"], list):
            errors.append(f"{where}: aliases must be a list")
        for s in surfaces_of(t):
            key = s.strip().lower()
            if not key:
                continue
            if key in seen and seen[key] != i:
                errors.append(f"{where}: surface '{s}' already belongs to '{data['terms'][seen[key]]['source']}'")
            seen.setdefault(key, i)
    return errors


def surface_index(data):
    idx = {}
    for i, t in enumerate(data.get("terms", [])):
        for s in surfaces_of(t):
            if s.strip():
                idx[s.strip().lower()] = i
    return idx


# ---------------------------------------------------------------------------
# Honorific rendering
# ---------------------------------------------------------------------------

def honorific_text(term, honorifics):
    hid = term.get("honorific") or ""
    if not hid:
        return ""
    h = next((x for x in honorifics if x.get("id") == hid), None)
    if not h:
        return ""
    if term.get("plural") and h.get("plural_target"):
        return h["plural_target"]
    if term.get("gender") == "f" and h.get("female_target"):
        return h["female_target"]
    return h.get("target", "")


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_seed(out_dir, builtin=None, force=False):
    p = glossary_path(out_dir)
    if p.exists() and not force:
        print(f"{p} already exists; keeping it (use --force to rebuild)")
        return load(out_dir)
    data = load_builtin(builtin)
    text = read_input(out_dir)
    cfg = load_config(out_dir)
    domain = cfg.get("domain") or "islamic"
    if domain not in ("islamic", "general"):
        domain = "islamic"
    terms = []
    for t in data.get("terms", []):
        if domain == "general" and t.get("category") not in GENERAL_SEED_CATEGORIES:
            continue
        freq = term_frequency(text, t)
        if freq:
            nt = OrderedDict((k, v) for k, v in t.items())
            nt["frequency"] = freq
            terms.append(nt)
    glossary = OrderedDict([
        ("version", 1), ("domain", domain), ("top_n", 25),
        ("terms", terms), ("honorifics", data.get("honorifics") or []),
    ])
    save(out_dir, glossary)
    print(f"Seeded {len(terms)} terms ({domain}) -> {p}")
    return glossary


HONORIFIC_SUBJECT_WORDS = {"allah", "god", "prophet", "messenger", "lord", "creator", "almighty", "prophets"}

_CAP_TOKEN = re.compile(r"[A-Z][A-Za-z'\u2019\-]*")
_TOKEN = re.compile(r"[A-Za-z][A-Za-z'\u2019\-]*|[.!?,;:()\[\]\"\u201c\u201d]")  # punctuation breaks phrases


def _candidate_ngrams(sentence_tokens):
    """Yield capitalised n-grams (1-4 words, connectors allowed) with position flags."""
    toks = sentence_tokens
    n = len(toks)
    i = 0
    while i < n:
        w = toks[i]
        if _CAP_TOKEN.fullmatch(w) and w.lower() not in STOPWORDS:
            j = i
            phrase = [w]
            last_cap = i
            while j + 1 < n and len(phrase) < 6:
                nxt = toks[j + 1]
                if _CAP_TOKEN.fullmatch(nxt) and nxt.lower() not in STOPWORDS:
                    phrase.append(nxt)
                    last_cap = j + 1
                    j += 1
                elif nxt.lower() in CONNECTORS and j + 2 < n and _CAP_TOKEN.fullmatch(toks[j + 2]):
                    phrase.append(nxt)
                    j += 1
                else:
                    break
            phrase = phrase[: last_cap - i + 1]
            # emit longest phrase and its single first word
            yield " ".join(phrase), i == 0
            if len(phrase) > 1:
                yield phrase[0], i == 0
            i = last_cap + 1
        else:
            i += 1


def cmd_extract_candidates(out_dir, min_freq=2, max_items=400):
    text = read_input(out_dir)
    data = load(out_dir) or {"terms": []}
    covered = surface_index(data)
    # Words handled by honorific rules (Allah, the Prophet, ...) are not glossary candidates.
    covered = set(covered) | HONORIFIC_SUBJECT_WORDS | {
        t.lower() for h in (data.get("honorifics") or []) for t in (h.get("triggers") or [])}
    # Strip code/urls/citation parentheses
    clean = re.sub(r"```.*?```", " ", text, flags=re.S)
    clean = re.sub(r"https?://\S+", " ", clean)
    clean = re.sub(r"^#{1,6}\s+", "", clean, flags=re.M)
    sentences = re.split(r"(?<=[.!?])\s+|\n+", clean)
    freq = Counter()
    non_initial = Counter()
    contexts = {}
    for sent in sentences:
        toks = _TOKEN.findall(sent)
        if not toks:
            continue
        for phrase, initial in _candidate_ngrams(toks):
            key = phrase
            freq[key] += 1
            if not initial:
                non_initial[key] += 1
            if len(contexts.setdefault(key, [])) < 2:
                snippet = sent.strip()
                m = re.search(re.escape(phrase), snippet)
                if m:
                    start = max(0, m.start() - 60)
                    snippet = snippet[start:m.end() + 60]
                contexts[key].append(re.sub(r"\s+", " ", snippet)[:160])
    results = []
    for phrase, n in freq.items():
        if n < min_freq:
            continue
        # Single capitalised words seen only at sentence starts are just capitalisation.
        if " " not in phrase and non_initial[phrase] == 0:
            continue
        if phrase.lower() in covered:
            continue
        if all(w.lower() in STOPWORDS or w.lower() in CONNECTORS for w in phrase.split()):
            continue
        # skip single words that are also sub-parts of a more frequent longer phrase
        results.append({"source": phrase, "frequency": n, "contexts": contexts.get(phrase, [])})
    results.sort(key=lambda r: (-r["frequency"], r["source"]))
    return results[:max_items]


def cmd_add(out_dir, from_json):
    data = load(out_dir)
    if data is None:
        raise RuntimeError("No work/glossary.json; run `glossary.py seed` first")
    new_terms = json.loads(Path(from_json).read_text(encoding="utf-8"))
    if isinstance(new_terms, dict) and "terms" in new_terms:
        new_terms = new_terms["terms"]
    if not isinstance(new_terms, list):
        raise RuntimeError("--from-json must contain a JSON array of term objects")
    idx = surface_index(data)
    added, skipped, errors = 0, [], []
    for i, t in enumerate(new_terms):
        missing = [k for k in REQUIRED_TERM_KEYS if k not in t]
        if missing:
            errors.append(f"entry {i} ({t.get('source', '?')}): missing {missing}")
            continue
        if not str(t["source"]).strip() or not str(t["target"]).strip():
            errors.append(f"entry {i}: empty source/target")
            continue
        entry = OrderedDict()
        entry["source"] = str(t["source"]).strip()
        entry["aliases"] = [str(a).strip() for a in (t.get("aliases") or []) if str(a).strip()]
        entry["target"] = str(t["target"]).strip()
        entry["category"] = str(t.get("category") or "other")
        entry["honorific"] = str(t.get("honorific") or "")
        for opt in ("gender", "plural", "note"):
            if t.get(opt):
                entry[opt] = t[opt]
        collision = [s for s in surfaces_of(entry) if s.lower() in idx]
        if collision:
            owner = data["terms"][idx[collision[0].lower()]]["source"]
            skipped.append(f"{entry['source']}: surface '{collision[0]}' already belongs to '{owner}'")
            continue
        data["terms"].append(entry)
        for s in surfaces_of(entry):
            idx[s.lower()] = len(data["terms"]) - 1
        added += 1
    errs = validate_data(data)
    if errs:
        raise RuntimeError("glossary invalid after add: " + "; ".join(errs))
    save(out_dir, data)
    return {"added": added, "skipped": skipped, "errors": errors, "total": len(data["terms"])}


def cmd_count_frequencies(out_dir):
    data = load(out_dir)
    if data is None:
        raise RuntimeError("No work/glossary.json")
    text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in source_chunks(out_dir))
    if not text:
        text = read_input(out_dir)
    for t in data["terms"]:
        t["frequency"] = term_frequency(text, t)
    save(out_dir, data)
    return {t["source"]: t["frequency"] for t in data["terms"]}


def select_terms_for_chunk(data, chunk_text, top_n=None, max_terms=60):
    top_n = data.get("top_n", 25) if top_n is None else top_n
    terms = data.get("terms", [])
    local = [t for t in terms if term_occurs(chunk_text, t)]
    by_freq = sorted(terms, key=lambda t: -(t.get("frequency") or 0))
    top = [t for t in by_freq[:top_n] if (t.get("frequency") or 0) > 0]
    chosen, seen = [], set()
    for t in local + top:
        key = t["source"].lower()
        if key not in seen:
            seen.add(key)
            chosen.append(t)
    return chosen[:max_terms]


def _cell(s):
    return str(s or "").replace("|", "\\|").replace("\n", " ")


def format_term_table(terms, honorifics):
    if not terms:
        return ""
    lines = ["| English | Aliases | Roman Urdu | Honorific | Note |", "|---|---|---|---|---|"]
    for t in terms:
        lines.append("| {} | {} | {} | {} | {} |".format(
            _cell(t["source"]), _cell(", ".join(t.get("aliases") or [])), _cell(t["target"]),
            _cell(honorific_text(t, honorifics)), _cell(t.get("note") or t.get("category") or "")))
    return "\n".join(lines)


def cmd_print_terms_for_chunk(out_dir, chunk_file, top_n=None, max_terms=60):
    data = load(out_dir)
    if data is None:
        return ""
    chunk_path = Path(out_dir) / "work" / os.path.basename(chunk_file)
    if not chunk_path.exists():
        raise RuntimeError(f"Chunk not found: {chunk_path}")
    text = chunk_path.read_text(encoding="utf-8", errors="replace")
    terms = select_terms_for_chunk(data, text, top_n=top_n, max_terms=max_terms)
    return format_term_table(terms, data.get("honorifics") or [])


def cmd_validate(out_dir=None, builtin=None):
    if builtin:
        data = load_builtin(builtin)
        return validate_data(data, strict_categories=True)
    data = load(out_dir)
    if data is None:
        return ["No work/glossary.json"]
    return validate_data(data)


def cmd_list(out_dir, category=None):
    data = load(out_dir) or {"terms": []}
    rows = [t for t in data["terms"] if not category or t.get("category") == category]
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description="Per-book glossary management for roman-urdu-book")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("seed"); p.add_argument("out_dir"); p.add_argument("--builtin"); p.add_argument("--force", action="store_true")
    p = sub.add_parser("extract-candidates"); p.add_argument("out_dir"); p.add_argument("--min-freq", type=int, default=2)
    p.add_argument("--max", type=int, default=400); p.add_argument("--json", action="store_true")
    p = sub.add_parser("add"); p.add_argument("out_dir"); p.add_argument("--from-json", required=True)
    p = sub.add_parser("count-frequencies"); p.add_argument("out_dir")
    p = sub.add_parser("print-terms-for-chunk"); p.add_argument("out_dir"); p.add_argument("chunk_file")
    p.add_argument("--top-n", type=int, default=None); p.add_argument("--max-terms", type=int, default=60)
    p = sub.add_parser("validate"); p.add_argument("out_dir", nargs="?"); p.add_argument("--builtin")
    p = sub.add_parser("list"); p.add_argument("out_dir"); p.add_argument("--category")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "seed":
            cmd_seed(args.out_dir, args.builtin, args.force)
        elif args.cmd == "extract-candidates":
            res = cmd_extract_candidates(args.out_dir, args.min_freq, args.max)
            print(json.dumps(res, ensure_ascii=False, indent=None if args.json else 2))
        elif args.cmd == "add":
            res = cmd_add(args.out_dir, args.from_json)
            print(json.dumps(res, ensure_ascii=False))
            if res["errors"]:
                return 1
        elif args.cmd == "count-frequencies":
            res = cmd_count_frequencies(args.out_dir)
            print(json.dumps(res, ensure_ascii=False))
        elif args.cmd == "print-terms-for-chunk":
            table = cmd_print_terms_for_chunk(args.out_dir, args.chunk_file, args.top_n, args.max_terms)
            if table:
                print(table)
        elif args.cmd == "validate":
            if not args.out_dir and not args.builtin:
                parser.error("validate needs <out_dir> or --builtin path")
            errs = cmd_validate(args.out_dir, args.builtin)
            if errs:
                for e in errs:
                    print(f"ERROR: {e}")
                return 1
            print("glossary OK")
        elif args.cmd == "list":
            for t in cmd_list(args.out_dir, args.category):
                print(f"{t['source']} -> {t['target']} [{t.get('category', '')}] {t.get('honorific', '')}")
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
