"""Regenerate skills/setup/data/country-names/ from Unicode CLDR.

    python3 scripts/build_country_names.py

Writes one tab-separated file per language: code, English name, local name.
Alternate CLDR names (short, variant) get their own lines. Arabic-script names
also get a line without diacritics, since messages rarely carry them.
"""

import json
import re
import unicodedata
import urllib.request
from pathlib import Path

CLDR = "https://raw.githubusercontent.com/unicode-org/cldr-json/main/cldr-json"
LANGUAGES = ["ar", "fa", "ur", "he", "ru", "uk", "tr", "fr", "es", "de", "pt",
             "it", "zh", "ja", "ko", "hi", "id"]
OUT = Path(__file__).resolve().parent.parent / "skills/setup/data/country-names"
COUNTRY = re.compile(r"^[A-Z]{2}(-alt-[a-z]+)?$")
NOT_COUNTRIES = {"EU", "EZ", "UN", "QO", "ZZ", "XA", "XB"}
ARABIC_MARKS = re.compile("[ً-ٰٟـ]")


def fetch(path: str) -> dict:
    with urllib.request.urlopen(f"{CLDR}/{path}") as response:
        return json.load(response)


def territories(lang: str) -> dict[str, str]:
    data = fetch(f"cldr-localenames-full/main/{lang}/territories.json")
    names = data["main"][lang]["localeDisplayNames"]["territories"]
    return {k: v for k, v in names.items()
            if COUNTRY.match(k) and k[:2] not in NOT_COUNTRIES}


def names_for(entries: dict[str, str], code: str) -> list[str]:
    found = [v for k, v in sorted(entries.items()) if k[:2] == code]
    out = []
    for name in found:
        for form in (name, ARABIC_MARKS.sub("", unicodedata.normalize("NFC", name))):
            if form not in out:
                out.append(form)
    return out


def main() -> None:
    version = fetch("cldr-core/package.json")["version"]
    english = territories("en")
    codes = sorted({k[:2] for k in english})
    OUT.mkdir(parents=True, exist_ok=True)
    for lang in ["en", *LANGUAGES]:
        local = english if lang == "en" else territories(lang)
        lines = [f"# Country names in '{lang}' from Unicode CLDR {version}. "
                 "Columns: code, English name, local name.\n"]
        for code in codes:
            en_name = english.get(code, code)
            for name in names_for(local, code):
                lines.append(f"{code}\t{en_name}\t{name}\n")
        (OUT / f"{lang}.tsv").write_text("".join(lines), encoding="utf-8")
        print(f"{lang}: {len(lines) - 1} names")


if __name__ == "__main__":
    main()
