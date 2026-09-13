# Baselines

Checked-in English sample inputs for full-pipeline testing. Each book lives in its own folder with a `SOURCE.md` that records what the pipeline is expected to produce (chunk count, detected domain, glossary seeds, lint result, output files) and what a drift looks like.

- `tauheed-primer/` — a short self-written Islamic primer with a heading, an Arabic verse with its English rendering and reference, a hadith citation, a list, a footnote, and mentions of the Prophet, a Companion and a scholar. Small enough to be a single chunk.

Run baselines from `tests/.artifacts/` so generated `*_roman_urdu/` directories stay out of the repo root (see README.md "Development").
