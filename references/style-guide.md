# Roman Urdu Style Guide

This is the single source of truth for how translated books must read. Sub-agents read it before translating; the linter enforces the spelling table below through `glossary/spelling-rules.json`. Edit this file (and the JSON twin) to change house style.

## 1. Purpose and register

Roman Urdu here means Urdu written in Latin letters, in the register of Indo-Pak Islamic books printed in Roman Urdu (the reference collection is the books at thewayofsalafiyyah.com, for example "Aasan Tauheed" and "Taqwa Kaise Badhaya Jayen"). The reader is an Urdu speaker who reads Latin script comfortably but may not read Urdu or Arabic script.

Voice: clear, respectful, spoken-literary Urdu. Prefer everyday Urdu words over obscure Persian or Arabic vocabulary unless the source is technical. Sentences may be re-ordered into natural Urdu (subject, object, verb), but content, emphasis and paragraph boundaries must match the source. Never summarise, never add explanations, never omit a sentence.

One spelling per word. The reference scans mix `mein/main`, `ke/keh`, `Tauheed/Tawheed`; we do not. No Urdu script appears anywhere except quoted Arabic (Qur'an, hadith, du'a) copied from the source.

A sample of the target register, taken from the introduction of "Aasan Tauheed" and normalised to our spellings:

> Tamam tareefen Allah Rabbul Aalameen ke liye hain, aur rehmaten aur salaam hon Khatim-ul-Ambiya, hamare Nabi Muhammad (Sallallahu Alaihi Wasallam) par, aur un ki aal aur un ke ashaab par. Is ke baad: yeh nafa bakhsh intikhab, jame masail aur chuninda fawaid hain, jinhen Tauheed ke baab mein jama kiya gaya hai, jis Tauheed ke baghair Allah Ta'ala koi bhi amal qubool nahi karte.

> Rasoolullah (Sallallahu Alaihi Wasallam) ne farmaya: "Islam ki bunyaad paanch cheezon par hai: is baat ki gawahi dena ke Allah Ta'ala ke siwa koi mabood-e-barhaq nahi aur Muhammad (Sallallahu Alaihi Wasallam) Allah ke Rasool hain, Namaz qaim karna, Zakat dena, Ramzan ke roze rakhna aur Baitullah ka Hajj karna." (Sahih Bukhari: 8, Sahih Muslim: 16)

> Tauheed ki teen aqsaam hain: 1. Tauheed-e-Rububiyat, 2. Tauheed-e-Uluhiyat, 3. Tauheed-e-Asma wa Sifaat.

## 2. Canonical spelling table

Use only the Canonical column. The linter auto-fixes the rejected variants marked safe in `spelling-rules.json` and warns about the rest.

| Meaning | Canonical | Rejected variants | Note |
|---|---|---|---|
| in | `mein` | mei, mn, mayn | never confuse with `main` |
| I | `main` | mai | `main` is never rewritten |
| that / of | `ke` | keh, kay | conjunction and postposition are both `ke`; `keh` stays only as the verb stem (keh dijiye, keh kar, keh diya) |
| is | `hai` | hay, hei, hy | |
| are | `hain` | hen, hayn, hein | |
| was (m.) | `tha` | thaa | |
| was (f.) | `thi` | thee | plural f. `theen` |
| were | `the` | thay | |
| not | `nahi` | nahin, nahee, nai, nhi | |
| this / these | `yeh` | ye, yah | |
| that / those / he / she | `woh` | wo, vo, voh | |
| what | `kya` | kia | `kiya` means "did" |
| and | `aur` | our, or | |
| for | `liye` | liay, liey, lye | always `ke liye`, two words |
| because | `kyunke` | kyunki, kyun ke, kyonke | one word |
| therefore | `isliye` | is liye, isliay | one word |
| but rather | `balke` | balkeh, balkay | |
| with | `saath` | sath | |
| like / such as | `jaise` | jese, jaisay | |
| also | `bhi` | bhee | |
| should | `chahiye` | chahye, chahiay | |
| people | `log` / `logon` | logo, logo'n | |
| Allah's exaltation | `Ta'ala` | Ta'aala, Taala, Ta'alaa | always `Allah Ta'ala` in narrative |
| monotheism | `Tauheed` | Tawheed, Tavheed, Tauhid, Tawhid | keep Tawakkul, Tawassul, Tauba unchanged |
| associating partners | `Shirk` | Shirq | |
| worship | `Ibadat` | Ibaadat, Ibadah | |
| Qur'an | `Qur'an` | Quran, Koran, Qur'aan | |
| hadith | `Hadees` | Hadith, Hadis, Hadeeth | plural `Ahadees` |
| Prophet | `Nabi` | Nabee | |
| Messenger | `Rasool` | Rasul | `Rasoolullah` is one word |
| prayer | `Namaz` | Namaaz, Nimaz | `Salah` only if the source stresses the Arabic |
| supplication | `Dua` | Du'a, Duaa | |
| fasting | `Roza` | Rozah, Rauza | |
| Paradise / Hell | `Jannat` / `Jahannam` | Jannah, Jahanum | |
| Day of Judgement | `Qiyamat` | Qiyamah, Qayamat | |
| Hereafter | `Aakhirat` | Akhirat, Akhirah | |
| this world | `Duniya` | Dunya, Dunia | |
| faith | `Imaan` | Iman, Eman | |
| piety | `Taqwa` | Taqwaa | |
| innovation | `Bid'at` | Bidah, Bid'ah | |
| scholar / scholars | `Aalim` / `Ulama` | Alim, Ulema | |
| companions | `Sahaba` | Sahabah | `Sahaba-e-Kiraam` in honorific context |
| Ramadan | `Ramzan` | Ramadan, Ramazan | |
| the Prophet's honorific | `Sallallahu Alaihi Wasallam` | SAW, PBUH, Sallallahu alaihe wa sallam | in full, in parentheses |
| companion honorific (m.) | `Radiallahu Anhu` | RA, Raziallahu anhu | |
| companion honorific (f.) | `Radiallahu Anha` | Raziallahu anha | |
| companions honorific (pl.) | `Radiallahu Anhum` | Raziallahu anhum | |
| two companions | `Radiallahu Anhuma` | Raziallahu anhuma | |
| deceased scholar | `Rahimahullah` | RH, Rahimullah | plural `Rahimahumullah` |
| prophet honorific | `Alaihissalam` | AS, alaihi salam | Maryam takes `Alaihassalam` |
| Messenger of Allah | `Rasoolullah` | Rasulullah, Rasool Allah | one word |

Frequent words, spelled once and always: `kaise`, `kyun`, `kahan`, `kab`, `jab`, `tab`, `phir`, `lekin`, `magar`, `agar`, `taake`, `zaroor`, `bilkul`, `hamesha`, `kabhi`, `sirf`, `sab`, `har`, `kuch`, `bahut`, `zyada`, `kam`, `achha`, `bura`, `sahih`, `ghalat`, `haqq`, `baatil`, `ilm`, `amal`, `niyat`, `rehmat`, `maghfirat`, `gunah`, `neki`, `sabr`, `shukr`, `tawakkul`, `koshish`, `zindagi`, `maut`, `insaan`, `bande`, `deen`, `dunya` is wrong (use `Duniya`), `waqt`, `baat`, `cheez`, `tarah`, `wajah`, `maqsad`, `matlab`, `misaal`, `daleel`, `farmaya`, `farmate hain`, `kaha`, `poocha`, `jawab diya`.

Transliteration rules:

- Long vowels are doubled: `aasaan`, `tamaam`, `kiraam`, `deen`, `qubool`. Short vowels single: `kitab`, `sabr`.
- `ai` for the ے diphthong (`hai`, `kaise`, `paisa`); `au` for the و diphthong (`aur`, `Tauheed`, `mauqa`).
- Apostrophe for ع and ء: `ma'na`, `du'a` inside compounds (but the standalone word is `Dua`), `Ka'bah`, `Ta'ala`, `nafa'`.
- Keep `kh`, `gh`, `q` distinct: `khauf`, `ghalat`, `qabool`. Use `z` for ز, ذ, ض, ظ: `zulm`, `zikr`, `Ramzan`, `zaahir`. Use `s` for ث: `Usman`, `Hadees`, `Ibn Kaseer`.
- No diacritics, macrons or digits-for-letters (no `3ain`, no `7`).
- Izafat is hyphenated: `Tauheed-e-Rububiyat`, `Fehrist-e-Mazaameen`, `Sahaba-e-Kiraam`, `Ahl-e-Sunnat`.
- Arabic definite article in names keeps its hyphen: `Al-Bukhari`, `Ibn Taimiyyah`, `Abdur Rahman bin Auf`. Use `bin` in Roman Urdu names (`Umar bin Khattab`), not `ibn`.
- Numbers are digits. Hijri years take `H`: `1424 H`.

### Verb forms and agreement

- Future and auxiliary endings are joined to the verb: `hoga`, `hogi`, `honge`, `marega`, `karega`, `karenge`, `jayega`, `sakega`. Never `ho ga`, `mare ga`, `kar sakte hain` stays as is (only `ga/gi/ge` is joined).
- Allah Ta'ala and Rasoolullah (Sallallahu Alaihi Wasallam) take the respectful plural in narrative: `Allah Ta'ala farmate hain`, `Allah Ta'ala ne paida kiya`, `Rasoolullah (Sallallahu Alaihi Wasallam) farmate hain`, `aap ne farmaya`. Keep this consistent through the whole book; do not switch between `farmata hai` and `farmate hain`.
- Inside a quoted verse or hadith translation the wording follows the text itself (`"Woh Allah ek hai."`), so singular forms there are correct.
- Use one spelling for a word throughout a chunk (`dikhaawa` everywhere, not `dikhawa` in one line and `dikhaawe` in the next).

## 3. Honorifics

| Subject | English triggers | Roman Urdu form | Placement |
|---|---|---|---|
| Allah | God, Allah, the Almighty, (SWT) | `Allah Ta'ala` | Narrative text. Plain `Allah` inside quoted verses/hadith and in fixed phrases (Alhamdulillah, Insha'Allah, La ilaha illallah). `Subhanahu wa Ta'ala` only when the source stresses it. |
| The Prophet Muhammad | the Prophet, the Messenger (of Allah), PBUH, SAW, ﷺ, peace be upon him | `Rasoolullah (Sallallahu Alaihi Wasallam)`, `Nabi (Sallallahu Alaihi Wasallam)`, `Aap (Sallallahu Alaihi Wasallam)`, `Muhammad (Sallallahu Alaihi Wasallam)` | After every mention, in full, in parentheses. Never SAW/PBUH, never dropped. |
| Other prophets | Prophet Musa, Moses (AS), upon him be peace | `Musa (Alaihissalam)`, `Isa (Alaihissalam)`; Maryam: `(Alaihassalam)`; group: `Ambiya-e-Kiraam (Alaihimussalam)` | After the name, every mention. |
| Companions | (RA), may Allah be pleased with him/her/them | `(Radiallahu Anhu)` m., `(Radiallahu Anha)` f., `(Radiallahu Anhuma)` two, `(Radiallahu Anhum)` group, `(Radiallahu Anhunna)` women | After the name, every mention. Hadith narrators included. |
| Deceased scholars and righteous people | rahimahullah, may Allah have mercy on him | `(Rahimahullah)`, plural `(Rahimahumullah)` | After the name. |
| Living scholars | hafizahullah, may Allah preserve him | `(Hafizahullah)` | Only if the source indicates the scholar is living. |

Rules: honorifics are written exactly as shown, capitalised, in parentheses, after every mention. They are not added inside Arabic quotations, to non-religious figures, or to the book's author unless the source does so. Never double an honorific ("Rasoolullah (Sallallahu Alaihi Wasallam) (Sallallahu Alaihi Wasallam)" is wrong).

## 4. Citations

- Qur'an: Arabic text (if present in the source) on its own line, then the Roman Urdu translation in double quotes, then the reference: `(Surah Al-Baqarah: 255)`. If the source already uses `(Name: n)` or `[Name: n]`, keep its form. Surah names use the canonical Roman spellings from `glossary/islamic-terms.json` (category `surah`). Never change the numbers.
- Hadith: translation in double quotes, then narrator and source unchanged: `(Sahih Bukhari: 3435, Sahih Muslim: 28)`, `(Sunan Tirmizi: 3505)`, `(Sunan Abu Dawood: 4607)`, `(Sunan Ibn Majah: 43)`, `(Musnad Ahmad: 22/128)`. Gradings stay transliterated: `Sahih`, `Hasan`, `Zaeef`, `Mauzu`.
- Book, page and volume references, footnote numbers, ISBNs, URLs and email addresses are copied exactly.
- Narrators: "Abu Hurairah (Radiallahu Anhu) se riwayat hai ke Rasoolullah (Sallallahu Alaihi Wasallam) ne farmaya: "..."".

- Never insert a gloss or explanation inside a quoted verse or hadith translation. `"Keh dijiye: Woh Allah ek hai." (Surah Al-Ikhlas: 1)` is right; `"Keh dijiye: Woh Allah ek (Al-Ahad) hai."` is wrong. Put any gloss in the narrative sentence before or after the quotation.

## 5. Punctuation, numbers and layout

- English punctuation set only: `. , ; : ? !`. Straight double quotes for quotations. No Urdu or Arabic punctuation marks (no `۔` or `،`).
- Digits always (`5 cheezen`, `3 aqsaam`), Hijri dates as `1424 H`, Gregorian as in the source.
- Arabic text on its own line, followed by the quoted Roman Urdu translation on the next line. The build step renders Arabic right-to-left; do not add HTML.
- Lists, tables, blockquotes, images and footnotes mirror the source exactly. Headings are Title Case, never ALL CAPS: `## Tauheed Ki Tareef`, `### Tauheed Ki Aqsaam`.
- One source paragraph becomes one output paragraph.

## 6. Front-matter and structural labels

| English | Roman Urdu |
|---|---|
| Author / Written by | `Taleef` |
| Translation | `Tarjuma` (cover line: `Roman Urdu Tarjuma`) |
| Translator | `Mutarjim` |
| Foreword / Preface | `Taqdeem` |
| Publisher's note | `Arz-e-Nashir` |
| Introduction | `Muqaddimah` |
| Preamble | `Tamheed` |
| Contents / Table of contents | `Fehrist-e-Mazaameen` |
| Chapter | `Baab` (`Baab 3`) |
| Section | `Fasl` |
| Conclusion | `Khatimah` |
| Notes / Footnotes | `Hawashi` |
| References / Bibliography | `Maakhaz` |
| Appendix | `Zameema` |
| Glossary | `Farhang` |

## 7. General (non-Islamic) register

The same spelling table and transliteration rules apply. Differences:

- No religious honorifics are added; only those present in the source are kept.
- Technical or untranslatable English terms are kept in English in parentheses on first use after the Urdu gloss: `azdaad (opposite)`, `mutawaazi computing (parallel computing)`.
- Proper nouns keep their common English spelling (London, Newton, Shakespeare) unless an Urdu form is standard in Urdu newspapers (`Misr`, `Hindustan`, `Amreeka`, `Bartaniya`). When unsure, keep the English form.
- Contents label is `Fehrist`; "Chapter" is still `Baab`; "Part" is `Hissa`.
- Keep the author's tone: a novel stays narrative and informal, a textbook stays plain and precise.

## 8. Anti-patterns

| Wrong | Right | Why |
|---|---|---|
| `Rasoolullah SAW ne farmaya` | `Rasoolullah (Sallallahu Alaihi Wasallam) ne farmaya` | honorific abbreviated |
| `Nabi ne farmaya` | `Nabi (Sallallahu Alaihi Wasallam) ne farmaya` | honorific dropped |
| `Allah ne kaha` (narrative) | `Allah Ta'ala ne farmaya` | missing Ta'ala and respectful verb |
| `dharti`, `prem`, `dharam`, `ishwar` | `zameen`, `muhabbat`, `deen`, `Allah Ta'ala` | Hindi-leaning vocabulary |
| `Tawheed`, `Tawhid` | `Tauheed` | non-canonical spelling |
| `keh`, `wo`, `ye`, `nahin`, `main` (for "in") | `ke`, `woh`, `yeh`, `nahi`, `mein` | non-canonical spelling |
| `Sahih Bukhari mein hai ke...` (reference moved into prose) | `"..." (Sahih Bukhari: 1)` | citation format changed |
| `Say: He is Allah, the One.` left in English | `"Keh dijiye: Woh Allah ek hai."` | untranslated sentence |
| `Tauheed ki teen qismein hain: Rububiyat, Uluhiyat, Asma.` (list collapsed) | keep the numbered list with three items | structure changed |
| `[Translator's note: ...]` | nothing | commentary added |
| Urdu script in the output (`توحید`) | `Tauheed` | script leak |
| `Al-hamdu lillahi rabbil alameen` translated as `Sab tareef Allah ki` inside a fixed phrase | keep `Alhamdulillah` and translate only the explanation | fixed phrase translated |
