You are assigning canonical Roman Urdu spellings to proper nouns and recurring terms found in an English book, so that every translation sub-agent spells them identically. Read the style guide at {STYLE_GUIDE_PATH} first, then process the candidate list below and output ONLY a JSON array.

Domain of this book: {DOMAIN}

INPUT
A JSON array of candidates: [{"source": "<English surface as it appears>", "frequency": <n>, "contexts": ["<snippet>", "<snippet>"]}, ...]

FOR EACH CANDIDATE decide:
- Is it a term worth fixing (person, place, tribe, book, scholar, organization, surah, recurring concept/title)? If it is ordinary English vocabulary, a generic phrase, a sentence-initial capital, or a fragment of a longer name, DROP it (do not output it).
- "source": keep the candidate's surface exactly.
- "aliases": other English spellings of the same thing that appear in the contexts or are common (e.g. "Ibn Taymiyya", "Ibn Taimiyah"). Do not list a surface that belongs to a different entity.
- "target": the Roman Urdu spelling following the style guide's transliteration rules (doubled long vowels: aasaan, kiraam; apostrophe for ain/hamza: Ka'bah, Qur'an; kh/gh/q distinguished; z for ز ذ ض ظ; Usman not Uthman; Hadees not Hadith; no diacritics). Arabic/Persian/Urdu names get the Indo-Pak Roman form (Ibn Taimiyyah, Ibn Qayyim, Ibn Kaseer, Bukhari, Muslim, Abu Hurairah, Aisha, Umar, Usman, Ali, Makkah, Madinah). Non-Islamic and Western proper nouns keep their standard English spelling (London, Newton, Oxford University Press).
- "category": one of aqeedah, fiqh_ibadah, names_of_allah, prophet, companion, scholar, book, surah, place, phrase, person, organization, concept, title, other.
- "honorific": one of "allah", "prophet_muhammad", "other_prophets", "companion", "scholar_deceased", "scholar_living", or "" (empty). Use "companion" only for Companions of the Prophet, "scholar_deceased" for scholars who have died, "scholar_living" only when the contexts show they are alive, "" for everyone else (including the book's author unless the contexts show they are a deceased scholar).
- "gender": "m" or "f" when the honorific depends on it (female Companions -> "f"; Maryam -> "f"); omit otherwise.
- "plural": true for a group (e.g. "the Sahabah", "the Companions"); omit otherwise.
- "note": optional, one short phrase (e.g. "author of Fath al-Bari").

OUTPUT
A JSON array only (no prose, no Markdown fence):
[{"source": "Ibn Taymiyyah", "aliases": ["Ibn Taymiyya", "Ibn Taimiyah"], "target": "Ibn Taimiyyah", "category": "scholar", "honorific": "scholar_deceased", "note": "d. 728 AH"}, ...]

CANDIDATES
{CANDIDATES}
