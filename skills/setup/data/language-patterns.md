# Language pattern building blocks

Tested regex pieces for `regex` rules (Python `re`, case-insensitive). Copy
them, then run `preview_rule` on the result — never skip the test.

## Arabic

| Need | Pattern | Matches |
|---|---|---|
| Any alef form | `[اأإآ]` | أرامكو · ارامكو |
| Final ta marbuta | `[ةه]` | السعودية · السعوديه |
| Final yeh | `[يى]` | مستشفي · مستشفى |
| Yeh / kaf incl. Persian forms | `[يیى]` · `[كک]` | سعودي · سعودی — الكويت · الکویت |
| Hamza seats | `[وؤ]` · `[يئ]` | مؤسسة · موسسة — رئيس · ريس |
| Optional vowel marks after a letter | `[ً-ٰٟ]?` | عُمان · عمان |
| Any digit, Latin or Arabic-Indic or Persian | `[0-9٠-٩۰-۹]` | ٢٠٢٦ · 2026 |

**Whole word with clitic prefixes.** `word` rules miss Arabic words with
attached prefixes (و ف ب ك ل ال لل). Use this template, putting the stem where
`STEM` is:

```
(?<![؀-ۿ])(?:[وفبكل]?(?:ال)?|لل)?STEM[؀-ۿ]*
```

It starts at a word boundary, allows the prefixes, and allows suffixes.
Tested: `سعودي[ةه]?` as the stem matches والسعودية · بالسعودية · للسعودية ·
السعوديه · السعودي, and does not match مسعودي or مسعود. With `عُ?مان` it
matches سلطنة عمان and وعُمان but not سلمان.

Write the stem **without** a leading ال; the template adds it.

**Arabizi** (Arabic in Latin letters and digits, common in informal chats):
2 = ء, 3 = ع, 5 = خ, 6 = ط, 7 = ح, 8 = غ, 9 = ق or ص. For example
`s3oud` or `el 7a2` — add Arabizi spellings of key names when the channels are
informal.

## Persian

Persian text often joins word parts with a zero-width non-joiner (U+200C).
Allow it where a space could be: `[\s‌]*`. Tested: `عربستان[\s‌]*سعود[يیى]`
matches عربستان سعودی and عربستان‌سعودي. Use the Arabic letter classes above
for yeh and kaf.

## Hebrew

Prefix letters ו ה ב כ ל מ ש attach to words, up to two at a time:

```
(?<![֐-׿])[והבכלמש]{0,2}STEM
```

Tested with `ישראל`: matches בישראל and וישראל, not אישראל. Final letter
forms (ך ם ן ף ץ) replace the normal ones at the end of a word — match the stem
before the final letter.

## Russian and Ukrainian

Words change endings by case, so match the stem: `(?<!\w)STEM\w*`. Tested:
`(?<!\w)сауд\w*` matches Саудовской. Russian `ё` is often written `е` — use
`[её]`. Ukrainian uses і, ї, є where Russian uses и, и, е; include both
spellings of names that appear in both languages.

## Turkish

No special handling: case-insensitive rules already match İ, I, i and ı.

## Chinese, Japanese, Korean

No spaces between words in Chinese and Japanese, so `\b` is meaningless; use
`substring`. Include both Simplified and Traditional Chinese forms of names
when the sources may use either.

## Obfuscated Latin text

People dodging filters swap letters for look-alikes and add separators.

- Letter classes: a `[a4@]` · e `[e3]` · i `[i1!|]` · o `[o0]` · s `[s5$]` · t `[t7]`
- Optional separator between letters: `[\W_]?`
- Tested: `h[\W_]?[a4@][\W_]?[c\(k][\W_]?k` matches h4ck, H.A.C.K and h@ck.

Use this only for a few key terms; it makes patterns slower to read and test.

## Country names in other languages

`country-names/<language>.tsv` lists every country's name in 18 languages
(from Unicode CLDR, with vowel-free Arabic forms added). Look up the rows for
the countries in scope and use those names as seeds — then add the shorter
everyday forms people actually write (CLDR gives formal names:
"المملكة العربية السعودية", while posts say "السعودية"), and run them through
the templates above.
