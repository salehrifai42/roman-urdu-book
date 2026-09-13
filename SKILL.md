---
name: roman-urdu-book
description: Translate an English book or long document (PDF/DOCX/EPUB/HTML/Markdown/TXT) into a Roman Urdu book using parallel sub-agents, a built-in Islamic-terms glossary, an editable style guide, a deterministic spelling/structure linter, and Markdown/HTML/DOCX/EPUB/PDF output. Use whenever the user asks to translate, convert, or render a book, chapter, or document into Roman Urdu / Romanised Urdu / "Urdu in English letters".
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent, AskUserQuestion
metadata: {"openclaw":{"requires":{"bins":["python3","pandoc"]},"homepage":"https://github.com/<gh-user>/roman-urdu-book"},"version":"0.1.0"}
---

# Roman Urdu Book

You are the orchestrator of a book-translation pipeline. You convert the input, build a glossary, hand every chunk to its own fresh-context sub-agent, lint and review the results, and build the final book files. You never translate text yourself in this context.

## Do not

- Never translate a chunk in the main context. Every chunk is translated by a sub-agent whose entire task is the prompt printed by `build_prompt.py`.
- Never hand-edit `work/output_chunkNNNN.md`. Fix a bad chunk only through a retry sub-agent (`--kind retry`).
- Never skip the lint step, and never build while `lint_summary.json` still reports errors.
- Never write Urdu (Arabic-script) text yourself, and never let the pipeline emit it. Only quoted Arabic that already exists in the source is allowed.
- Never overwrite an existing `work/glossary.json`; it may be hand-edited.

## Parameters

| Parameter | Required | Default | Notes |
|---|---|---|---|
| `file_path` | yes | — | PDF, DOCX, EPUB, HTML, Markdown, TXT, ODT, RTF |
| `out_dir` | no | `<dir of file>/<stem>_roman_urdu/` | Run directory; contains `work/`, `media/`, `book.*` |
| `domain` | no | `auto` | `auto`, `islamic`, `general` |
| `concurrency` | no | `6` | Sub-agents per batch |
| `chunk_size` | no | `4500` | Source characters per chunk |
| `title_ru`, `subtitle_ru` | no | derived | Roman Urdu title/subtitle for the cover |
| `author`, `translator`, `publisher` | no | derived / empty | Cover lines (Taleef, Tarjuma) |
| `cover` | no | — | Path to a cover image |
| `formats` | no | `md,html,docx,epub,pdf` | Any subset |
| `custom_instructions` | no | — | Free-text rules passed to every sub-agent |
| `force` | no | `false` | Re-translate chunks that already have output |

Ask the user only for `file_path` if it is missing. Everything else has a default or is derived.

## Run directory layout

```
<out_dir>/
  config.json                  source metadata, domain, book title/author lines
  work/chunkNNNN.md            source chunks (never edit)
  work/output_chunkNNNN.md     translated chunks (sub-agents only)
  work/manifest.json           chunk hashes
  work/glossary.json           per-book glossary (hand-editable)
  work/lint_chunkNNNN.json     linter report per chunk
  work/lint_summary.json       linter summary
  work/review_chunkNNNN.json   reviewer reports
  media/                       extracted images
  book.md book.html book.docx book.epub book.pdf
```

## Steps

### Step 0 — Check tools

```bash
python3 {baseDir}/scripts/doctor.py --json
```

Parse the JSON. If `pandoc.ok` is false, stop and show the user the `install_hints` for pandoc. If the input is a PDF and `pdf_extractors` is empty, stop and show the install hints for PDF extractors. Remember `pdf_renderers[0]` (may be absent; then the PDF format will be skipped later, which is fine).

### Step 1 — Collect parameters

Fill the Parameters table from the user's message. Derive `out_dir` from the file path if not given. Do not ask about optional parameters.

### Step 2 — Convert and chunk

```bash
python3 {baseDir}/scripts/convert.py "<file_path>" --out-dir "<out_dir>" --chunk-size <chunk_size>
```

The last line of stdout is a JSON summary: `{"chunk_count": N, "title": ..., "author": ..., "method": ...}`. Record it.

If the script aborts because the directory was created from different source bytes, tell the user to delete `<out_dir>` or pass a new `--out-dir`, then stop. If it exits with code 2 (no PDF extractor), show its install matrix and stop.

### Step 3 — Detect domain

```bash
python3 {baseDir}/scripts/detect_domain.py "<out_dir>" --json
```

Add `--domain <islamic|general>` if the user chose one. The output is `{"domain": ..., "confidence": ..., ...}`. If `confidence` is `low`, ask the user once: "Is this an Islamic/religious book (use Islamic terms and honorifics) or a general book?" and re-run with `--domain`.

### Step 4 — Build the per-book glossary

Skip this whole step if `<out_dir>/work/glossary.json` already exists.

1. Seed from the built-in glossary (only terms that occur in the book):

   ```bash
   python3 {baseDir}/scripts/glossary.py seed "<out_dir>"
   ```

2. Extract proper-noun candidates not yet covered:

   ```bash
   python3 {baseDir}/scripts/glossary.py extract-candidates "<out_dir>" --min-freq 2 --max 400 --json
   ```

3. Assign a Roman Urdu spelling to each candidate. If there are 120 or fewer, do it yourself following `{baseDir}/references/style-guide.md` (transliteration rules, honorific table). If there are more, spawn helper sub-agents in batches of 100 candidates each, using the prompt in `{baseDir}/references/glossary-prompt.md` with the candidate JSON pasted in. Each entry must have `source`, `target`, `category` (person, place, book, scholar, companion, prophet, organization, concept, title, other), `honorific` (an honorific id from the glossary or empty string), and optional `aliases`. Write the resolved list to `<out_dir>/work/candidates_resolved.json`.

4. Add, count, validate:

   ```bash
   python3 {baseDir}/scripts/glossary.py add "<out_dir>" --from-json "<out_dir>/work/candidates_resolved.json"
   python3 {baseDir}/scripts/glossary.py count-frequencies "<out_dir>"
   python3 {baseDir}/scripts/glossary.py validate "<out_dir>"
   ```

   If `add` rejects an entry for a surface-form collision, fix that entry (merge it as an alias of the existing term or rename it) and re-run.

### Step 5 — Plan the work queue

Use Glob on `<out_dir>/work/chunk*.md` (exclude `output_chunk*.md`). The queue is every chunk whose `work/output_chunkNNNN.md` is missing or blank. If `force` is set, the queue is every chunk.

### Step 6 — Translate in parallel

Process the queue in batches of `concurrency`. For each chunk in a batch:

```bash
python3 {baseDir}/scripts/build_prompt.py "<out_dir>" chunkNNNN.md --kind translate --custom-instructions "<custom_instructions>"
```

Omit `--custom-instructions` when there are none. Capture stdout.

Spawn one sub-agent per chunk whose entire task is the text printed by `build_prompt.py`. Use whatever sub-agent mechanism the runtime provides (the Agent tool, `sessions_spawn`, or equivalent). Launch all sub-agents of a batch together, wait for the whole batch to finish, then start the next batch. Each sub-agent reads its chunk and the style guide, writes `work/output_chunkNNNN.md`, and stops. Do not add instructions of your own to the prompt.

### Step 7 — Lint, retry, verify

After every batch:

```bash
python3 {baseDir}/scripts/lint_roman_urdu.py "<out_dir>" --chunks chunkNNNN chunkMMMM ... --fix --json
```

This applies safe spelling fixes in place and writes `work/lint_chunkNNNN.json` per chunk. For every chunk whose report contains any `E_*` error, spawn a retry sub-agent:

```bash
python3 {baseDir}/scripts/build_prompt.py "<out_dir>" chunkNNNN.md --kind retry --lint-report "<out_dir>/work/lint_chunkNNNN.json" --custom-instructions "<custom_instructions>"
```

Then lint that chunk again. A chunk gets at most 2 attempts (initial + 1 retry). If it still has errors, keep it and list it in the final report.

After all batches:

```bash
python3 {baseDir}/scripts/lint_roman_urdu.py "<out_dir>" --all --json
```

Read `work/lint_summary.json`. Every manifest chunk must have a non-blank output and there must be zero `E_*` errors before you continue. Missing or blank outputs go back to Step 6 as a new batch (they count toward the same 2-attempt limit).

### Step 8 — Quality review

Sample `max(3, ceil(0.10 × chunk_count))` chunks: the first, the last, and evenly spaced chunks between them. For each:

```bash
python3 {baseDir}/scripts/build_prompt.py "<out_dir>" chunkNNNN.md --kind review
```

Spawn one reviewer sub-agent per sampled chunk with that text as its whole task. Each writes `work/review_chunkNNNN.json` with `{"score": 1-5, "issues": [{"type": ..., "quote": ..., "suggestion": ...}]}`.

- Score 3 or lower: re-translate that chunk with `--kind retry --review-report "<out_dir>/work/review_chunkNNNN.json"`, then lint it again (Step 7 rules and the 2-attempt limit apply).
- If the same issue `type` appears in at least half of the sampled chunks, the problem is systematic. Tell the user what it is, add a one-line corrective instruction to `custom_instructions`, and ask whether to re-run all chunks with `force`. Do not re-run everything without asking.

### Step 9 — Title and front matter

Read `source.title` and `source.author` from `<out_dir>/config.json`. Decide:

- `title_ru`: translate English titles into Roman Urdu ("The Easy Book of Tawhid" → "Aasan Tauheed"; "How to Increase Taqwa" → "Taqwa Kaise Badhayen"). Keep Arabic-origin or Urdu titles transliterated per the style guide ("Kitab at-Tawhid" → "Kitab-ut-Tauheed"; "Stories of the Prophets" → "Qasas-ul-Ambiya"). Do not invent subtitles.
- `author`: spell the author's name per `work/glossary.json` if present there, otherwise per the style guide's transliteration rules ("Shaykh Abdullah ibn Ahmad al-Huwayl" → "Shaikh Abdullah bin Ahmad Al-Huwail").
- `translator`, `publisher`: only if the user gave them.

Prefer values the user supplied over derived ones.

### Step 10 — Build the book files

```bash
python3 {baseDir}/scripts/build.py "<out_dir>" --title "<title_ru>" --subtitle "<subtitle_ru>" --author "<author>" --translator "<translator>" --publisher "<publisher>" --cover "<cover>" --formats md,html,docx,epub,pdf --export-name "<slug>" --toc-depth 2
```

Omit flags whose value is empty. Add `--cleanup` only if the user asked for a clean directory. Add `--pdf-renderer <chrome|wkhtmltopdf|weasyprint|calibre>` only if the user asked for a specific renderer. A line like `pdf: skipped — <reason>` is not a failure; keep it for the report. A non-zero exit means the merge or HTML step failed; show the error and stop.

### Step 11 — Report

Tell the user, in this shape:

```
Roman Urdu book built: <out_dir>
Title: <title_ru>  |  Author: <author>
Chunks: <n> translated, <r> retried, <f> still flagged (list ids if any)
Lint: <e> errors, <w> warnings, <fixes> spelling auto-fixes applied
Review: <k> chunks sampled, scores <list>, systematic issues: <none | description>
Files:
  book.md    <size>
  book.html  <size>
  book.docx  <size>
  book.epub  <size>
  book.pdf   <size | skipped — reason + install hint>
Editable: references/style-guide.md, glossary/spelling-rules.json, glossary/islamic-terms.json (skill-wide);
          <out_dir>/work/glossary.json (this book). Re-run with force to apply changes.
```

## Resuming and re-running

- Re-running the skill on the same file with the same `out_dir` skips chunks that already have non-blank output. Only missing or blank chunks are translated.
- To re-translate everything, set `force`.
- To re-translate specific chunks, delete their `work/output_chunkNNNN.md` files and re-run.
- To rebuild the glossary from scratch, delete `work/glossary.json` and re-run.
- If only the title, author, cover, or formats changed, re-run Step 10 alone.
- A changed source file is detected by `work/source_fingerprint.json`; use a new `out_dir` or delete the old one.

## Customising

- `{baseDir}/references/style-guide.md` — the spelling table, honorific table, citation formats, structural labels, and the general (non-Islamic) register. Every sub-agent reads it.
- `{baseDir}/glossary/spelling-rules.json` — the machine-readable twin of the spelling table used by the linter's `--fix`. Keep it in sync with the style guide (a unit test enforces this).
- `{baseDir}/glossary/islamic-terms.json` — the built-in seed glossary and honorific rules.
- `<out_dir>/work/glossary.json` — this book's glossary. Edit `target` or `honorific` values between runs.

Edits do not touch chunks that are already translated. To apply them, delete the affected `work/output_chunk*.md` files or re-run with `force`, then rebuild.
