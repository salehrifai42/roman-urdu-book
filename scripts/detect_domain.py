#!/usr/bin/env python3
"""
detect_domain.py - Decide whether a converted book is Islamic (apply the Islamic
register, honorifics and built-in glossary) or general.

Usage:
    detect_domain.py <out_dir> [--domain islamic|general] [--glossary path] [--json]

Reads <out_dir>/work/input.md, counts word-boundary hits of every glossary term
(source + aliases) and of the glossary's ``detection.strong_terms``, applies the
thresholds in ``detection`` and writes ``domain`` / ``domain_detection`` into
<out_dir>/config.json. Prints a JSON summary. An explicit --domain wins.
"""

import argparse
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
DEFAULT_GLOSSARY = SKILL_ROOT / "glossary" / "islamic-terms.json"

FALLBACK_STRONG_TERMS = ["Allah", "Qur'an", "Quran", "hadith", "Prophet Muhammad", "Sunnah",
                         "Tawhid", "Tawheed", "Shirk", "Sahabah", "Companions of the Prophet",
                         "Messenger of Allah", "peace be upon him"]
DEFAULT_DETECTION = {"min_distinct_terms": 8, "min_hits_per_1000_words": 3.0,
                     "strong_min_hits_per_1000_words": 1.5, "strong_terms": FALLBACK_STRONG_TERMS}


def load_glossary(path):
    p = Path(path) if path else DEFAULT_GLOSSARY
    if not p.exists():
        return {"terms": [], "detection": dict(DEFAULT_DETECTION)}
    data = json.loads(p.read_text(encoding="utf-8"))
    det = dict(DEFAULT_DETECTION)
    det.update(data.get("detection") or {})
    data["detection"] = det
    return data


def surface_regex(surface):
    """Case-insensitive whole-word regex for a term surface (ASCII-safe boundaries)."""
    esc = re.escape(surface.strip())
    return re.compile(r"(?<![\w'])" + esc + r"(?![\w'])", re.IGNORECASE)


def count_term_hits(text, surfaces):
    """Return {surface: count} for surfaces that occur at least once."""
    hits = {}
    for s in surfaces:
        if not s:
            continue
        n = len(surface_regex(s).findall(text))
        if n:
            hits[s] = n
    return hits


def word_count(text):
    return max(1, len(re.findall(r"[A-Za-z\u0600-\u06FF']+", text)))


def analyse(text, glossary):
    det = glossary["detection"]
    term_surfaces = []
    for t in glossary.get("terms", []):
        term_surfaces.append(t.get("source", ""))
        term_surfaces.extend(t.get("aliases") or [])
    strong = det.get("strong_terms") or FALLBACK_STRONG_TERMS
    words = word_count(text)
    term_hits = count_term_hits(text, term_surfaces)
    strong_hits = count_term_hits(text, strong)
    total_hits = sum(term_hits.values()) + sum(v for k, v in strong_hits.items() if k not in term_hits)
    stats = {
        "word_count": words,
        "distinct_terms": len(term_hits),
        "total_hits": total_hits,
        "hits_per_1000_words": round(total_hits * 1000.0 / words, 3),
        "strong_term_hits": sum(strong_hits.values()),
        "strong_hits_per_1000_words": round(sum(strong_hits.values()) * 1000.0 / words, 3),
        "top_terms": sorted(term_hits.items(), key=lambda kv: -kv[1])[:15],
    }
    return stats


def decide(stats, det):
    """Return (domain, confidence)."""
    min_distinct = det.get("min_distinct_terms", 8)
    min_density = det.get("min_hits_per_1000_words", 3.0)
    strong_min = det.get("strong_min_hits_per_1000_words", 1.5)
    d, dens, sdens = stats["distinct_terms"], stats["hits_per_1000_words"], stats["strong_hits_per_1000_words"]
    islamic = (d >= min_distinct and dens >= min_density) or sdens >= strong_min
    # Low confidence when any deciding metric is within 20% of its threshold.
    near = (abs(d - min_distinct) <= max(1, 0.2 * min_distinct)
            or abs(dens - min_density) <= 0.2 * min_density
            or abs(sdens - strong_min) <= 0.2 * strong_min)
    if islamic and (d >= min_distinct * 1.5 and dens >= min_density * 1.5 or sdens >= strong_min * 2):
        confidence = "high"
    elif not islamic and d == 0 and sdens == 0:
        confidence = "high"
    else:
        confidence = "low" if near else "medium"
    return ("islamic" if islamic else "general"), confidence


def run(out_dir, domain_override=None, glossary_path=None):
    out_dir = Path(out_dir)
    input_md = out_dir / "work" / "input.md"
    if not input_md.exists():
        raise RuntimeError(f"Missing {input_md}; run convert.py first")
    glossary = load_glossary(glossary_path)
    text = input_md.read_text(encoding="utf-8", errors="replace")
    stats = analyse(text, glossary)
    domain, confidence = decide(stats, glossary["detection"])
    if domain_override in ("islamic", "general"):
        stats["auto_domain"] = domain
        domain, confidence = domain_override, "override"
    result = {"domain": domain, "confidence": confidence}
    result.update({k: v for k, v in stats.items() if k != "top_terms"})
    result["top_terms"] = stats["top_terms"]
    cfg_path = out_dir / "config.json"
    cfg = {}
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except ValueError:
            cfg = {}
    cfg["domain"] = domain
    cfg["domain_detection"] = result
    tmp = cfg_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(cfg_path)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Detect Islamic vs general domain for a converted book")
    parser.add_argument("out_dir")
    parser.add_argument("--domain", choices=("islamic", "general", "auto"), default=None)
    parser.add_argument("--glossary", help="Path to islamic-terms.json (default: skill glossary)")
    parser.add_argument("--json", action="store_true", help="(default) print JSON")
    args = parser.parse_args(argv)
    try:
        result = run(args.out_dir, None if args.domain == "auto" else args.domain, args.glossary)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
