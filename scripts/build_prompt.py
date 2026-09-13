#!/usr/bin/env python3
"""
build_prompt.py - Assemble the full prompt for a translation / retry / review sub-agent.

Usage:
    build_prompt.py <out_dir> chunkNNNN.md --kind translate|retry|review
        [--custom-instructions "..."] [--lint-report path] [--review-report path]
        [--style-guide path] [--glossary-candidates path]

Templates live in <skill_root>/references/. Placeholders are {NAME}; optional
blocks are wrapped in <!-- IF:NAME --> ... <!-- ENDIF:NAME --> and removed
entirely when NAME resolves to an empty value. Prints the prompt to stdout.
"""

import argparse
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
REFERENCES = SKILL_ROOT / "references"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import chunk_context  # noqa: E402
import glossary  # noqa: E402

TEMPLATES = {
    "translate": REFERENCES / "translation-prompt.md",
    "retry": REFERENCES / "translation-prompt.md",
    "review": REFERENCES / "reviewer-prompt.md",
    "glossary": REFERENCES / "glossary-prompt.md",
}
_IF_BLOCK = re.compile(r"<!--\s*IF:([A-Z_]+)\s*-->(.*?)<!--\s*ENDIF:\1\s*-->\n?", re.S)


def render_template(template, values):
    """Substitute {PLACEHOLDER}s and drop IF blocks whose placeholder is empty."""
    def _block(m):
        name, body = m.group(1), m.group(2)
        if str(values.get(name, "") or "").strip():
            return body.strip("\n") + "\n"
        return ""
    text = _IF_BLOCK.sub(_block, template)
    for key, val in values.items():
        text = text.replace("{" + key + "}", str(val if val is not None else ""))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip("\n") + "\n"


def unresolved_placeholders(text):
    return sorted(set(re.findall(r"\{([A-Z_]{3,})\}", text)))


def _load_json(path):
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None


def format_lint_report(report):
    if not report:
        return ""
    lines = []
    for e in report.get("errors") or []:
        msg = e.get("message") or e.get("code") or ""
        detail = e.get("detail")
        lines.append(f"- ERROR {e.get('code', '')}: {msg}" + (f" — {detail}" if detail else ""))
    for w in report.get("warnings") or []:
        msg = w.get("message") or w.get("code") or ""
        detail = w.get("detail")
        lines.append(f"- warning {w.get('code', '')}: {msg}" + (f" — {detail}" if detail else ""))
    return ("Linter findings:\n" + "\n".join(lines)) if lines else ""


def format_review_report(report):
    if not report:
        return ""
    lines = [f"Reviewer score: {report.get('score', '?')}/5. {report.get('summary', '')}".strip()]
    for issue in report.get("issues") or []:
        q = issue.get("quote", "")
        s = issue.get("suggestion", "")
        lines.append(f"- {issue.get('type', 'issue')}: \"{q}\" -> {s}")
    return "\n".join(lines)


def build(out_dir, chunk_file, kind, custom_instructions="", lint_report=None, review_report=None,
          style_guide=None, candidates=None):
    out_dir = Path(out_dir).resolve()
    work = out_dir / "work"
    chunk_name = Path(chunk_file).name
    chunk_id = chunk_context.parse_chunk_name(chunk_name)[0]
    if not (work / chunk_name).exists() and kind != "glossary":
        raise RuntimeError(f"Chunk not found: {work / chunk_name}")
    template_path = TEMPLATES[kind]
    template = template_path.read_text(encoding="utf-8")
    cfg = glossary.load_config(out_dir)
    domain = cfg.get("domain") or "islamic"
    if domain == "auto":
        domain = "islamic"
    style_path = Path(style_guide).resolve() if style_guide else (REFERENCES / "style-guide.md")

    term_table = ""
    neighbor = ""
    if kind != "glossary":
        try:
            term_table = glossary.cmd_print_terms_for_chunk(out_dir, chunk_name)
        except RuntimeError:
            term_table = ""
        try:
            neighbor = chunk_context.format_for_prompt(chunk_context.get_neighbor_context(str(work), chunk_name))
        except (FileNotFoundError, ValueError):
            neighbor = ""

    feedback_parts = [format_lint_report(_load_json(lint_report)), format_review_report(_load_json(review_report))]
    retry_feedback = "\n\n".join(p for p in feedback_parts if p)
    if kind == "retry" and not retry_feedback:
        retry_feedback = "The previous output failed validation. Re-translate the whole chunk carefully."

    values = {
        "OUT_DIR": str(out_dir),
        "CHUNK_ID": chunk_id,
        "DOMAIN": domain,
        "STYLE_GUIDE_PATH": str(style_path),
        "TERM_TABLE": term_table,
        "NEIGHBOR_CONTEXT": neighbor,
        "CUSTOM_INSTRUCTIONS": custom_instructions or "",
        "RETRY_FEEDBACK": retry_feedback if kind == "retry" else "",
        "OUTPUT_PATH": str(work / f"output_{chunk_id}.md"),
        "REVIEW_PATH": str(work / f"review_{chunk_id}.json"),
        "CANDIDATES": json.dumps(candidates, ensure_ascii=False, indent=1) if candidates is not None else "",
    }
    return render_template(template, values)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Assemble a sub-agent prompt for roman-urdu-book")
    parser.add_argument("out_dir")
    parser.add_argument("chunk_file", help="chunkNNNN.md (any chunk for --kind glossary)")
    parser.add_argument("--kind", choices=("translate", "retry", "review", "glossary"), default="translate")
    parser.add_argument("--custom-instructions", default="")
    parser.add_argument("--lint-report")
    parser.add_argument("--review-report")
    parser.add_argument("--style-guide")
    parser.add_argument("--glossary-candidates", help="JSON file of candidates (for --kind glossary)")
    args = parser.parse_args(argv)
    try:
        candidates = _load_json(args.glossary_candidates) if args.glossary_candidates else None
        prompt = build(args.out_dir, args.chunk_file, args.kind, args.custom_instructions,
                       args.lint_report, args.review_report, args.style_guide, candidates)
    except (RuntimeError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    sys.stdout.write(prompt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
