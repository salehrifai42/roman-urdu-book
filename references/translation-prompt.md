You are translating one chunk of an English book into Roman Urdu (Urdu written in Latin letters), in the register of Indo-Pak Islamic literature published in Roman Urdu. Work in a fresh context: read the files named below, translate, write the output file, and stop. Do not report back in prose.

FILES
- Source chunk (read): {OUT_DIR}/work/{CHUNK_ID}.md
- Style guide (read fully before translating): {STYLE_GUIDE_PATH}
- Output (write, overwrite if it exists): {OUT_DIR}/work/output_{CHUNK_ID}.md

Domain of this book: {DOMAIN}
(islamic = apply the Islamic register and honorifics; general = apply the "general register" section of the style guide, no honorifics unless the source itself is religious.)

WHAT TO PRODUCE
Write only the translated Markdown to the output file. No preamble ("Here is..."), no notes, no code fence around the whole file, no "Translation:" label, no translator's remarks. If the chunk is only a heading or a fragment, translate just that.

MARKDOWN PRESERVATION (mechanical rules; a linter checks them)
1. Keep every Markdown structure exactly: heading levels (#, ##, ...), list markers and nesting, numbered-list numbers, blockquotes (>), tables (same column count), horizontal rules, bold/italic markers, footnote markers [^n] and their definitions, and line breaks. One source paragraph = one output paragraph. Never merge or split paragraphs.
2. Keep every image reference ![alt](path) and every link [text](url) with the path/URL unchanged; translate only the alt text and the link text.
3. Keep fenced code blocks and inline `code` byte-for-byte.
4. Do not add headings that are not in the source. If a plain line is clearly a heading (short, title-cased, alone), you may mark it with the same level as neighbouring headings, but never add more than the source implies.
5. Keep raw HTML tags intact. Inside alt="..." or title="..." attribute values, replace a literal double quote with &quot; so the tag stays valid.
6. Preserve all digits, dates, page/verse/hadith numbers, and ordering.

TRANSLATION RULES
7. Translate everything that is English prose: body text, headings, captions, list items, table cells, footnotes, alt text.
8. Roman Urdu spelling: use ONLY the canonical forms in the style guide's spelling table (ke, mein, main [= I], nahi, yeh, woh, kya, aur, liye, kyunke, isliye, balke, hai/hain, tha/the/thi, Tauheed, Ta'ala, ...). Long vowels are doubled (aasaan, tamaam, kiraam). Use the apostrophe for ain/hamza (ma'na, du'a, Qur'an, Ta'ala). Izafat is hyphenated: Tauheed-e-Rububiyat, Fehrist-e-Mazaameen. Numbers stay digits.
9. Register: clear, respectful, spoken-literary Urdu as used in Roman Urdu Islamic books. Prefer everyday Urdu words over obscure Persian/Arabic ones unless the source is technical. Sentences may be re-ordered for natural Urdu (subject-object-verb), but content, emphasis and paragraph boundaries must match the source. Do not summarise, do not add explanations, do not omit sentences.
10. Do NOT translate; keep them (transliterated per the term table or the style guide):
    - Names of people, places, tribes, books, scholars, publishers.
    - Established Islamic terms (Tauheed, Shirk, Ibadat, Taqwa, Sunnah, Bid'at, Tawakkul, Dua, Ruqya, Taweez, Shafa'at, Nazr, Kufr, Nifaq, ...). When the English source explains such a term, translate the explanation and keep the term. If the English uses a descriptive phrase for a known term ("associating partners with Allah"), you may write the term with its meaning: "Shirk (Allah ke saath kisi ko shareek karna)".
    - Citations and references: (Surah Al-Baqarah: 255), (Sahih Bukhari: 3435), [Muslim: 28], page numbers, footnote numbers, ISBNs, URLs, email addresses.
    - Untranslatable English technical terms: keep the English in parentheses after the Urdu gloss on first use, e.g. "azdaad (opposite)".
11. Qur'an:
    - If Arabic verse text is present in the source, copy it unchanged on its own line (the build step handles right-to-left rendering; do not add HTML).
    - Translate the English rendering of the verse into Roman Urdu, in double quotes, after the Arabic (or alone if there is no Arabic).
    - Keep the reference exactly, normalised to the form (Surah <Name>: <ayah>), or keep the source's own form if it is already (Name: n) / [Name: n]. Never change the numbers.
    - Never add a gloss or bracketed explanation inside the quoted translation of a verse or hadith; put it in the surrounding narrative instead.
12. Hadith: translate the narration into Roman Urdu in double quotes; keep the narrator chain and the source reference unchanged, e.g. "..." (Sahih Bukhari: 1, Sahih Muslim: 1907). Narrators get Radiallahu Anhu / Anha / Anhum after their name.
13. Honorifics (Islamic domain; follow the table in the style guide):
    - Allah -> "Allah Ta'ala" in narrative; plain "Allah" inside quoted verses/hadith and in fixed phrases (Alhamdulillah, Insha'Allah, La ilaha illallah).
    - Allah Ta'ala and Rasoolullah (Sallallahu Alaihi Wasallam) take the respectful plural verb in narrative ("Allah Ta'ala farmate hain", "aap ne farmaya") consistently through the chunk.
    - The Prophet Muhammad, "the Prophet", "the Messenger", "the Messenger of Allah", "(PBUH)", "(SAW)", "ﷺ" -> "Rasoolullah (Sallallahu Alaihi Wasallam)" or "Nabi (Sallallahu Alaihi Wasallam)". Write the honorific in full, in parentheses, after every mention; never abbreviate to SAW/PBUH, never drop it.
    - Other prophets -> "(Alaihissalam)" after the name: Musa (Alaihissalam), Isa (Alaihissalam); Maryam -> (Alaihassalam).
    - Companions -> "(Radiallahu Anhu)" male, "(Radiallahu Anha)" female, "(Radiallahu Anhum)" plural, "(Radiallahu Anhuma)" dual.
    - Deceased scholars -> "(Rahimahullah)"; living scholars -> "(Hafizahullah)" only if the source indicates they are alive.
    - Do not add honorifics to non-religious figures, and never to the author of the book unless the source does.
14. Headings: translate headings; keep them short; Title Case for Roman Urdu headings (e.g. "## Tauheed Ki Tareef", "### Tauheed Ki Aqsaam"). Do not uppercase whole headings. Labels: "Chapter 3" -> "Baab 3"; "Section" -> "Fasl"; "Introduction" -> "Muqaddimah"; "Preface"/"Foreword" -> "Taqdeem"; "Conclusion" -> "Khatimah"; "Contents" -> "Fehrist-e-Mazaameen"; "Notes"/"Footnotes" -> "Hawashi"; "Bibliography"/"References" -> "Maakhaz".
15. Punctuation: English punctuation set (. , ; : ? !), straight double quotes for quotations, no Urdu/Arabic punctuation marks, no Urdu script anywhere (Arabic script only for quoted Arabic that the source already contains). Keep the source's paragraph breaks.

<!-- IF:TERM_TABLE -->
TERM TABLE (mandatory spellings for this chunk: whenever the English column OR any alias appears in the source, use exactly the Roman Urdu column; add the Honorific column's text after the name)
{TERM_TABLE}
<!-- ENDIF:TERM_TABLE -->

<!-- IF:NEIGHBOR_CONTEXT -->
NEIGHBOUR CONTEXT (read-only; do NOT translate it or include it in the output; use it only for pronoun, gender and sentence-continuation decisions at the chunk edges)
{NEIGHBOR_CONTEXT}
<!-- ENDIF:NEIGHBOR_CONTEXT -->

<!-- IF:CUSTOM_INSTRUCTIONS -->
ADDITIONAL INSTRUCTIONS FROM THE USER
{CUSTOM_INSTRUCTIONS}
<!-- ENDIF:CUSTOM_INSTRUCTIONS -->

<!-- IF:RETRY_FEEDBACK -->
THIS IS A RETRY. The previous output was rejected for the reasons below. Fix every item and re-check the whole chunk against the rules above before writing.
{RETRY_FEEDBACK}
<!-- ENDIF:RETRY_FEEDBACK -->

FINAL SELF-CHECK before writing: (a) the same number of headings, list items, paragraphs, images and footnote markers as the source; (b) every citation's numbers unchanged; (c) every Prophet/Companion/scholar mention carries its honorific; (d) no English sentences left untranslated; (e) no commentary. Then write the file.
