# tauheed-primer baseline

Self-written English sample (no third-party text) used for the full-pipeline smoke test. It is deliberately under 4,000 characters so that `convert.py` produces exactly one chunk, and it exercises every feature the translation rules care about: a title, four `##` headings, an Arabic verse line with an English rendering and a Qur'an reference, a hadith with a Sahih Bukhari reference, a three-item numbered list, a footnote marker and definition, the Prophet with "(peace be upon him)", a companion (Abu Hurairah) and a scholar (Ibn Taymiyyah).

`tests/fixtures/output_chunk0001.md` is a hand-written Roman Urdu translation of this file and is the reference for what a good translation looks like. Offline tests copy it into `work/` so lint and build can run without an LLM.

## Expected outcomes

| Measured | Expected target | Drift indicator |
|---|---|---|
| `chunk_count` from `convert.py` | 1 | 2 or more means the chunker changed or the sample grew |
| `detect_domain.py` | `islamic`, confidence not `low` | `general` means detection thresholds or the glossary changed |
| `glossary.py seed` terms written | at least 12 | fewer means alias matching regressed |
| `lint_roman_urdu.py --all` on the fixture | 0 errors, 0 auto-fixes | any `E_*` means the linter or fixture drifted |
| `book.html` | contains `dir="rtl"` around the Arabic verse, a `Fehrist-e-Mazaameen` TOC and a cover section | missing RTL means `wrap_arabic_runs` regressed |
| Honorifics in the fixture | `(Sallallahu Alaihi Wasallam)` after all 4 Prophet mentions, `(Radiallahu Anhu)` after Abu Hurairah, `(Rahimahullah)` after Ibn Taimiyyah | a missing one is a fixture bug |
| Citations in the fixture | `(Surah Al-Ikhlas: 1)`, `(Sahih Bukhari: 1)`, `[^1]` all present and unchanged | any change fails `E_CITATION` |
