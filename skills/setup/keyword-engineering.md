# Keyword engineering

How to turn the user's goal, names and example messages into rules that catch
everything they care about without flooding the judge. Work through the steps
in order. Most of this is your own work; involve the user only for judgment
calls.

## How matching works

Know the engine before writing patterns:

- Python `re`. Case-insensitive unless the rule sets `case_sensitive`.
- `substring` — the text appears anywhere, even inside a longer word.
- `word` — the text with `\b` on both sides. `\b` treats letters of every
  script as word characters, so it fails wherever a language attaches
  prefixes or suffixes to words (Arabic, Hebrew, Persian) — see below.
- `regex` — your pattern as written. Use it for alternations and variants.
- **No normalization.** Text is matched exactly as sent: letter variants,
  diacritics, stretched letters and look-alike characters all have to be
  covered by the pattern itself.
- Rules only see message text (including captions). Links count as text, so
  domains and URLs can be matched.

## 1. Discover the real vocabulary

People write differently from how requirements are phrased. Before drafting:

1. Read the messages collected in phase 4, and 50–100 more recent messages
   from the most relevant selected channels (`read_messages`).
2. List the words, abbreviations, hashtags, handles, emoji markers and
   recurring phrases that appear in the messages the user wanted — especially
   ones they never mentioned themselves.
3. For each key name or term, run `search_messages` and read what else appears
   around it. Co-occurring terms are often better signals than the obvious one.
4. Note the channels' own conventions: a fixed post format, a tag like
   `#breaking`, a template line such as "Victim:" or "Price:".

## 2. Expand every concept

Start from the seed vocabulary in the matching starter packs (`packs/`), and
for countries in scope take every language's name from
`data/country-names/<lang>.tsv`. Then, for each concept (a name, a topic, an
event type), build the full set of ways it is written:

- synonyms and near-synonyms; formal and informal terms;
- abbreviations, acronyms, codes and tickers, with and without dots;
- singular/plural and other grammatical forms — prefer a shared stem;
- common misspellings and alternate spellings;
- the name in every language and script the sources use, including
  transliterations in both directions and romanized chat-speak
  (e.g. Arabizi, which writes Arabic with Latin letters and digits);
- hashtags and handles (`#name`, `@name`), with and without separators;
- domains, URLs and identifier formats when relevant (a company domain, a
  country code domain, a ticket or ID pattern);
- deliberate obfuscation where the audience uses it: digits for letters
  (`h4ck`), inserted dots or spaces (`c.o.m.p.a.n.y`), look-alike letters from
  other scripts.

When the user chose **Widen coverage**, this is where it happens: propose the
extra variants and related terms as a multi-select, with a note on how much
volume each adds.

## 3. Language checks

Apply every section that matches a language in the sources. Ready-made,
tested patterns for these are in `data/language-patterns.md` — use them
rather than writing letter classes from scratch.

**Arabic**
- Attached prefixes: و ف ب ك ل and ال, alone or combined (وال، بال، فال،
  لل). `word` misses "والشركة" for "الشركة" — use `substring` or regex without
  `\b` for Arabic terms.
- Attached suffixes (ـه ـها ـهم ـي ـنا, plural ـون ـين ـات): match the stem.
- Letter variants — cover each with a character class:
  alef `[اأإآ]`, final ta marbuta `[ةه]`, final yeh `[يى]`, hamza seats
  `[ؤو]` and `[ئي]`, and Persian/Urdu forms `ی` for `ي` and `ک` for `ك` in
  some channels.
- Tatweel (ـ) can stretch any word: allow it with `ـ*` between letters for
  short, important names, or accept the small miss.
- Diacritics (tashkeel) are rare but possible in formal posts.
- Ambiguity: short words and place names that are also common words (عمان is
  Oman and Amman; الخبر is Khobar and "the news"). Prefer longer, specific
  forms, and let the criteria resolve what remains.

**Hebrew and Persian** — same prefix and letter-variant issues; handle them
the same way.

**Russian and other inflected languages** — match stems, not full words, so
all case endings are caught (e.g. a stem plus `\w*`).

**Chinese, Japanese and other languages without spaces** — word boundaries
don't exist; use `substring`.

**Mixed scripts** — English terms are often written in the local script, and
local names in Latin letters. Include both directions.

## 4. Remove false positives

Before testing, review each term for collisions:

- short tokens inside longer words — use `word` or `\b` for short Latin
  acronyms (`\bstc\b`, not `stc`);
- ordinary words that happen to be names;
- terms that are common in the user's channels for unrelated reasons (a
  sponsor's name in every post footer, a word in the channel's template);
- ambiguous names shared by other organizations, people or places.

Drop a term only if the criteria can't reasonably sort it out; otherwise keep
it for recall and note the ambiguity for phase 6.

## 5. Structure the rules

- Group terms into a few rules by concept — e.g. names, topic terms, event
  words, identifiers — typically 3 to 7 rules. One giant pattern can't be
  tested or tuned.
- Give each rule a short, descriptive name; it appears on every alert.
- Scope every rule with the `chat_ids` from phase 3, and `exclude_chat_ids`
  for known-noisy chats.
- Keep terms that are valuable but noisy in their own rule, so it can be
  switched off without losing the rest.

## 6. Test every rule

Run `preview_rule` for each rule, scoped with its `chat_ids`. A regex over
unscoped history also needs a `search_hint` (a plain word Telegram can search
for), because Telegram's server-side search can't run regex. Raise `scan` for
low-volume channels.

Read the results honestly:

- **`match_rate` above ~0.2** — very broad. Acceptable only if the criteria
  will filter it and the user's volume target allows it.
- **Zero matches** — usually a typo or a term nobody writes; go back to the
  discovered vocabulary.
- **`top_chats` dominated by one channel** — that channel will become most of
  their alerts; ask whether to exclude it.
- **Read the samples.** Count real hits against noise. Name the noise pattern
  and fix the term that caused it.

**Recall check — do not skip.** Every message the user marked "Alert me" in
phase 4 must be matched by at least one rule. Check each one against the
patterns. Any miss means a missing term or variant: add it and re-test.

Iterate until each rule is both quiet enough and misses nothing the user
wanted. Then summarize for the user, as phase 5 of the skill describes.
