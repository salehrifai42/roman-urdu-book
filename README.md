# roman-urdu-book

An agent skill for Claude Code and Codex that turns an English book into a Roman Urdu book.

Give it a PDF, DOCX, EPUB, HTML, Markdown or TXT file. It splits the book into chunks, translates every chunk with its own sub-agent, keeps terminology consistent with a glossary, checks spelling and structure with a linter, has reviewer agents spot-check the result, and builds the finished book as Markdown, HTML, DOCX, EPUB and PDF.

The output register is the Roman Urdu used by Indo-Pak Islamic publishers (the books on thewayofsalafiyyah.com are the reference), standardised to one spelling per word. Islamic books get the built-in glossary and honorific rules automatically. Other books are translated with the same spelling rules and no honorifics.

## How it works

```
Input (PDF / DOCX / EPUB / HTML / MD / TXT)
  |
  v
pandoc (or pdftotext / PyMuPDF / pypdf for PDF)  -->  work/input.md
  |
  v
Split into chunks  (work/chunk0001.md ...)   manifest.json tracks hashes
  |
  v
Detect domain (Islamic / general)  -->  seed glossary  -->  scan book for names
  |
  v
Parallel sub-agents (6 at a time, one fresh context per chunk)
  |   each reads: chunk + style guide + term table + neighbour context
  |   each writes: work/output_chunkNNNN.md
  v
Linter (spelling auto-fix, structure, citations, untranslated lines)  -->  retry bad chunks
  |
  v
Reviewer sub-agents on a 10% sample  -->  retry low-scoring chunks
  |
  v
Merge  -->  pandoc  -->  book.md / book.html / book.docx / book.epub
                    -->  Chrome headless (or wkhtmltopdf / weasyprint / Calibre)  -->  book.pdf
```

## What the output reads like

```
Rasoolullah (Sallallahu Alaihi Wasallam) ne farmaya: "Aamaal ka daromadaar niyyaton par hai."
(Sahih Bukhari: 1)

Tauheed ki teen aqsaam hain: Tauheed-e-Rububiyat, Tauheed-e-Uluhiyat aur Tauheed-e-Asma-wa-Sifaat.
Abu Hurairah (Radiallahu Anhu) se riwayat hai ke ...
```

## Install

Replace `salehrifai42` below with the GitHub account that hosts this repository.

### Claude Code

```bash
npx skills add salehrifai42/roman-urdu-book -a claude-code -g
```

Or clone it by hand:

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/salehrifai42/roman-urdu-book.git ~/.claude/skills/roman-urdu-book
```

### Codex

```bash
npx skills add salehrifai42/roman-urdu-book -a codex -g
```

Or:

```bash
mkdir -p ~/.agents/skills
git clone https://github.com/salehrifai42/roman-urdu-book.git ~/.agents/skills/roman-urdu-book
```

Restart the agent if the skill does not appear.

## Prerequisites

| Need | Required? | macOS | Ubuntu / Debian | pip |
|---|---|---|---|---|
| Python 3.10+ | yes | `brew install python` | `sudo apt-get install python3` | — |
| pandoc | yes | `brew install pandoc` | `sudo apt-get install pandoc` | — |
| PDF text extractor (one of) | only for PDF input | `brew install poppler` | `sudo apt-get install poppler-utils` | `pip install pymupdf` or `pip install pypdf` |
| PDF renderer (one of) | only for PDF output | Google Chrome, Chromium or Edge installed | `sudo apt-get install chromium` or `wkhtmltopdf` | `pip install weasyprint` |
| Calibre | no | optional fallback for PDF input and output | | |

Check what is installed:

```bash
python3 scripts/doctor.py
```

Missing optional tools only disable the formats that need them. The skill tells you what was skipped and how to install it.

## Quick start

In Claude Code or Codex, ask:

```text
translate /path/to/book.pdf to Roman Urdu
```

or use the slash command:

```text
/roman-urdu-book translate /path/to/book.epub to Roman Urdu
```

Useful additions to the request:

- "it is a general book" or "it is an Islamic book" (skips domain detection)
- "use 4 agents" (concurrency)
- "keep English technical terms in parentheses"
- "author is Shaikh Abdullah Al-Huwail, translator is Mariya Abdul Qadeer"
- "only html and pdf"
- "re-translate everything" (force)

## Outputs

Everything goes into `<book-name>_roman_urdu/` next to the input file:

| File | Description |
|---|---|
| `book.md` | Merged Roman Urdu Markdown with cover block and front matter |
| `book.html` | Standalone web version with cover page and a Fehrist-e-Mazaameen (contents) drawer |
| `book.docx` | Word document |
| `book.epub` | E-book with metadata and optional cover image |
| `book.pdf` | A5 print-ready PDF (skipped with a hint if no renderer is installed) |
| `work/` | Chunks, translated chunks, glossary, lint and review reports (kept for resuming) |
| `config.json` | Source metadata, detected domain, cover lines |

## Customising the style

| File | What it controls |
|---|---|
| `references/style-guide.md` | Spelling table, honorific table, citation formats, structural labels (Baab, Fasl, Muqaddimah...), general register, anti-patterns. Read by every translation sub-agent. |
| `glossary/spelling-rules.json` | Canonical spellings and rejected variants used by the linter's auto-fix. Keep in sync with the style guide; a unit test checks this. |
| `glossary/islamic-terms.json` | Built-in seed glossary (terms, prophets, companions, scholars, books, surah names, places, fixed phrases) and honorific rules. |
| `<book>_roman_urdu/work/glossary.json` | This book's glossary. Edit `target` or `honorific` values between runs. |

Edits do not change chunks that are already translated. To apply them, delete the affected `work/output_chunk*.md` files (or ask the skill to "re-translate everything"), then run the skill again.

## Quality controls

- One chunk per sub-agent with a fresh context, so long books never truncate.
- A term table is injected into every prompt, so names and terms are spelled the same in chunk 1 and chunk 90.
- Short read-only excerpts of the neighbouring chunks give each sub-agent pronoun and sentence-continuation context.
- The linter checks every chunk: same headings, lists, images, footnotes and citation numbers as the source; no untranslated English lines; no commentary; no Urdu script; canonical spellings (auto-fixed where safe); honorifics after every Prophet, Companion and scholar mention.
- Chunks with errors are retried once with the concrete findings in the prompt.
- Reviewer sub-agents score a 10% sample (minimum 3 chunks). Low scores trigger a retry; a pattern across the sample is reported to you before a full re-run.

## Resuming

Run the same request again and the skill skips chunks that already have output. Delete individual `work/output_chunkNNNN.md` files to redo just those. Delete `work/glossary.json` to rebuild the glossary. If the source file changed, use a new output directory.

## Troubleshooting

| Problem | What to do |
|---|---|
| `pandoc not found` | Install pandoc (see Prerequisites) and make sure it is on PATH. |
| `No PDF text extractor available` | Install poppler (`pdftotext`), or `pip install pymupdf`, or `pip install pypdf`, or Calibre. Or convert the PDF to EPUB/DOCX first. |
| `pdf: skipped` | Install Google Chrome/Chromium/Edge, `wkhtmltopdf`, `pip install weasyprint`, or Calibre, then re-run the build step. |
| Chrome hangs or complains about a profile in use | The skill starts Chrome with a temporary `--user-data-dir`; close other headless Chrome processes and retry. Set `ROMAN_URDU_CHROME=/path/to/chrome` to pick a specific binary. |
| Garbled or merged words from a PDF | Try `--pdf-method pymupdf` on `convert.py`, or supply an EPUB/DOCX of the same book. Scanned PDFs need OCR first. |
| Arabic shows as boxes in the PDF | Install an Arabic font such as Amiri or Noto Naskh Arabic. macOS ships Geeza Pro, which works. |
| `was created from different source bytes` | The output directory belongs to another file. Delete it or use a new `--out-dir`. |
| Footnotes appear inline | PDF input has no footnote structure; they stay where the text extractor found them. Prefer EPUB or DOCX input for books with many footnotes. |
| A chunk keeps failing lint | The report is in `work/lint_chunkNNNN.json`. Fix the source chunk formatting if the input is malformed, delete the output chunk, re-run. |

## Development

Unit tests need only the Python standard library:

```bash
python3 -m compileall scripts tests
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 scripts/doctor.py
python3 scripts/glossary.py validate --builtin glossary/islamic-terms.json
```

Offline end-to-end run (no LLM; uses the checked-in translated fixture):

```bash
mkdir -p tests/.artifacts && cd tests/.artifacts
python3 ../../scripts/convert.py ../baselines/tauheed-primer/tauheed-primer.md --out-dir tauheed-primer_roman_urdu
python3 ../../scripts/detect_domain.py tauheed-primer_roman_urdu
python3 ../../scripts/glossary.py seed tauheed-primer_roman_urdu
python3 ../../scripts/glossary.py extract-candidates tauheed-primer_roman_urdu
python3 ../../scripts/build_prompt.py tauheed-primer_roman_urdu chunk0001.md --kind translate | head -60
cp ../fixtures/output_chunk0001.md tauheed-primer_roman_urdu/work/
python3 ../../scripts/lint_roman_urdu.py tauheed-primer_roman_urdu --all --fix
python3 ../../scripts/build.py tauheed-primer_roman_urdu --title "Aasan Tauheed (Test)" --author "Test Author"
ls -la tauheed-primer_roman_urdu/
```

Full run through the skill:

```text
/roman-urdu-book translate tests/baselines/tauheed-primer/tauheed-primer.md to Roman Urdu
```

Generated files under `tests/.artifacts/` are ignored by git.

## Credits

- Pipeline architecture (chunk manifest, neighbour context, parallel sub-agents) adapted from [deusyu/translate-book](https://github.com/deusyu/translate-book) (MIT). See LICENSE for the notice.
- Style reference: the Roman Urdu books published at [thewayofsalafiyyah.com](https://thewayofsalafiyyah.com/category/books/).

## License

[MIT](LICENSE)
