You are reviewing one chunk of a Roman Urdu book translation against its English source and the project's style guide. Work in a fresh context, write one JSON file, and stop. Do not edit the translation and do not report in prose.

FILES
- English source chunk (read): {OUT_DIR}/work/{CHUNK_ID}.md
- Roman Urdu output (read): {OUTPUT_PATH}
- Style guide (read fully): {STYLE_GUIDE_PATH}
- Review report (write): {REVIEW_PATH}

Domain of this book: {DOMAIN}

<!-- IF:TERM_TABLE -->
TERM TABLE that the translator was required to follow:
{TERM_TABLE}
<!-- ENDIF:TERM_TABLE -->

WHAT TO CHECK (read the source and the output side by side, paragraph by paragraph)
1. meaning: any sentence whose meaning differs from the source, or is ambiguous where the source is clear.
2. omission: any source sentence, clause, list item, footnote or citation missing from the output; any added content.
3. register: unnatural word-for-word English order, Hindi-leaning vocabulary (dharti, prem, ...), obscure words where the style guide asks for plain Urdu, or ALL-CAPS headings.
4. spelling: any spelling that is not the canonical form in the style guide's table (keh, wo, ye, nahin, Tawheed, Ta'aala, SAW, PBUH, ...), inconsistent transliteration of the same name, Urdu script leaking in.
5. honorific: a mention of the Prophet, another prophet, a Companion or a deceased scholar without the required honorific, an honorific on the wrong person, or an abbreviated honorific.
6. citation: Qur'an/hadith references whose numbers or names changed, or references dropped.
7. formatting: Markdown structure differing from the source (headings, lists, tables, images, footnotes, paragraph boundaries), commentary in the output, code fences added.

SCORING
- 5: publishable as is; at most cosmetic issues.
- 4: a few minor issues (spelling/register) that a light edit fixes; meaning fully intact.
- 3: several issues or one meaning/omission problem; needs re-translation of parts.
- 2: multiple meaning/omission problems or systematic spelling/honorific failure.
- 1: unusable (untranslated, truncated, wrong content).

OUTPUT
Write exactly this JSON object to the review report path (UTF-8, no Markdown fence):
{"score": <1-5>, "issues": [{"type": "meaning|omission|register|spelling|honorific|citation|formatting", "quote": "<short exact quote from the OUTPUT showing the problem>", "suggestion": "<the corrected Roman Urdu text or a one-line fix>"}], "summary": "<one line>"}
List at most 25 issues, most serious first. An empty issues list with score 5 is a valid result. Quote real text only; never invent problems.
