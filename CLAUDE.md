# CLAUDE.md

## Project

roman-urdu-book is an agent skill for Claude Code and Codex that translates an English book (PDF/DOCX/EPUB/HTML/Markdown/TXT) into a Roman Urdu book using parallel sub-agents, a built-in Islamic-terms glossary, an editable style guide, a deterministic linter, and pandoc-based output (Markdown, HTML, DOCX, EPUB, PDF). The style reference is the Roman Urdu books published at thewayofsalafiyyah.com.

## Structure

- `SKILL.md` — skill definition; the orchestration steps the agent follows. Prompts are NOT here.
- `README.md` — user documentation.
- `LICENSE` — MIT plus third-party notice for code derived from deusyu/translate-book.
- `references/style-guide.md` — editable style guide: spelling table, honorifics, citations, structural labels, general register, anti-patterns. Read by every sub-agent.
- `references/translation-prompt.md` — sub-agent translation prompt template (`{PLACEHOLDERS}`, `<!-- IF:NAME -->` blocks).
- `references/reviewer-prompt.md` — reviewer sub-agent template.
- `references/glossary-prompt.md` — prompt for assigning Roman Urdu spellings to proper-noun candidates.
- `glossary/islamic-terms.json` — seed glossary (terms, prophets, companions, scholars, books, surahs, places, phrases), honorific rules, domain-detection thresholds.
- `glossary/spelling-rules.json` — canonical spellings and rejected variants; machine twin of the style-guide table.
- `scripts/doctor.py` — dependency report; shared binary/module discovery helpers.
- `scripts/convert.py` — any input → `work/input.md` → chunks, manifest, fingerprint, `config.json`.
- `scripts/manifest.py` — vendored from translate-book: chunk hashes and merge validation.
- `scripts/chunk_context.py` — vendored from translate-book: neighbouring chunk excerpts.
- `scripts/detect_domain.py` — Islamic vs general detection.
- `scripts/glossary.py` — seed / extract-candidates / add / count-frequencies / print-terms-for-chunk / validate / list.
- `scripts/build_prompt.py` — assembles the translate / retry / review prompt for one chunk.
- `scripts/lint_roman_urdu.py` — deterministic checker with `--fix` for safe spelling normalisation.
- `scripts/build.py` — merge chunks → `book.md` → HTML/DOCX/EPUB → PDF.
- `scripts/render_pdf.py` — HTML → PDF via Chrome headless, wkhtmltopdf, weasyprint or Calibre.
- `scripts/template.html`, `scripts/book.css` — pandoc HTML template and stylesheet (cover, TOC, print CSS, RTL Arabic).
- `tests/test_*.py` — stdlib unittest suites, one per script plus `test_glossary_data.py`.
- `tests/fixtures/output_chunk0001.md` — hand-written Roman Urdu translation of the baseline's first chunk.
- `tests/baselines/tauheed-primer/` — checked-in English sample book and `SOURCE.md` with expected outcomes.
- `tests/.artifacts/` — ignored full-pipeline outputs.
- `.github/workflows/ci.yml` — compileall + unittest on Python 3.11–3.13 with pandoc installed.

## Prerequisites

- Python 3.10+; unit tests need only the standard library (third-party imports are guarded).
- The full pipeline needs pandoc. PDF input needs one of pdftotext, PyMuPDF, pypdf, Calibre. PDF output needs one of Chrome/Chromium/Edge, wkhtmltopdf, weasyprint, Calibre. Missing optional tools skip a format; they never fail the run.

## Testing changes

```bash
python3 -m compileall scripts tests
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 scripts/doctor.py
```

Offline baseline run (no LLM), from `tests/.artifacts/`:

```bash
python3 ../../scripts/convert.py ../baselines/tauheed-primer/tauheed-primer.md --out-dir tauheed-primer_roman_urdu
python3 ../../scripts/detect_domain.py tauheed-primer_roman_urdu
python3 ../../scripts/glossary.py seed tauheed-primer_roman_urdu
cp ../fixtures/output_chunk0001.md tauheed-primer_roman_urdu/work/
python3 ../../scripts/lint_roman_urdu.py tauheed-primer_roman_urdu --all --fix
python3 ../../scripts/build.py tauheed-primer_roman_urdu --title "Aasan Tauheed (Test)" --author "Test Author"
```

Verify: lint reports 0 errors, `book.md` and `book.html` exist, DOCX/EPUB are valid zips, PDF is produced or reported as skipped.

## Conventions

- Script paths in SKILL.md use `{baseDir}`, never a hard-coded skill directory.
- SKILL.md frontmatter fields stay single-line.
- Sub-agent instructions are platform-neutral (Claude Code, Codex, OpenClaw).
- Run directories are `<stem>_roman_urdu/` with intermediates under `work/`; final artifacts use the canonical names `book.md`, `book.html`, `book.docx`, `book.epub`, `book.pdf`. `--export-name` adds copies, never replaces them.
- Chunk files are `work/chunkNNNN.md` and `work/output_chunkNNNN.md`; no other naming.
- Scripts are stdlib-only; optional third-party imports are guarded.
- `references/style-guide.md` and `glossary/spelling-rules.json` must agree; `tests/test_glossary_data.py` enforces it.
- A glossary surface form (source or alias) belongs to exactly one term.
- Canonical spellings: Tauheed, Ta'ala, ke, mein (in) / main (I), yeh, woh, nahi, Hadees, Sallallahu Alaihi Wasallam, Radiallahu Anhu, Rahimahullah, Alaihissalam. Izafat is hyphenated.

## Do not

- Do not add Calibre-only code paths; Calibre is an optional fallback.
- Do not hard-code skill install paths in SKILL.md or scripts.
- Do not add new required pip dependencies.
- Do not inline the translation, reviewer or glossary prompts into SKILL.md; they live in `references/`.
- Do not reintroduce translate-book's meta-merge / run_state loop without a measured need on real books.
- Do not let the linter rewrite `main` (it means "I"); only `mein` (in) has rejected variants.
- Do not emit Urdu script anywhere; only Arabic quoted from the source is allowed.
