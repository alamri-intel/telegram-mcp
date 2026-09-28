# Starter pack: deals and marketplaces

For users hunting specific items, prices or listings in buy-and-sell groups
and deal channels.

## Extra interview options

- **Items**: the exact products, models, sizes or categories wanted.
- **Price**: a ceiling, a discount threshold, or "any listing".
- **Condition and terms** (multi-select): new · used · refurbished · local
  pickup only · shipping OK.
- **Place**: cities or areas, if the market is local.

## Seed vocabulary

- Product names, model numbers, common abbreviations and misspellings, in
  every language the groups use (sellers often mix languages).
- Selling words: for sale, selling, WTS, "price", "negotiable", "OBO",
  "brand new", "sealed" — translated.
- Price formats: currency symbols and codes, `\d+\s?(k|K)`, local digits
  (see `../data/language-patterns.md`).

## Typical noise

"Wanted" and buying posts (unless wanted) · accessories for the item rather
than the item · repeated bumps of the same listing · shop ads · items above the
price limit.

## Suggested rule groups

1. **Items** — names and model numbers.
2. **Selling vocabulary**, only if item names alone are too broad.

## Example criterion

> `wanted-item-for-sale` — A listing offering one of the tracked items for
> sale, with a price at or below the user's limit, in the user's area or
> with shipping. High: well below the limit. Medium: at the limit. Excludes:
> buying requests, accessories, shop advertisements, reposted listings
> already seen.

Note for the judge: price limits in the criterion must name the currency.
