# Starter pack: regional news and events

For users following events in a country, city or region — breaking news,
security events, protests, disasters, policy changes.

## Extra interview options

- **Event types** (multi-select): breaking news · security or military
  events · protests and unrest · disasters and accidents · policy and
  regulation · economy and markets · infrastructure disruptions.
- **Geography**: which countries, regions and cities — and whether events
  *involving* them elsewhere count.
- **Source bar**: first-hand reports only · reputable outlets · anything,
  clearly labeled.

## Seed vocabulary

- Place names from `../data/country-names/` in every language in scope, plus
  cities, regions, landmarks and their everyday short forms.
- Event words: explosion, attack, strike, protest, arrest, flood, fire,
  earthquake, outage, evacuation, "breaking", "urgent" — translated.
- Channel markers: 🔴, "عاجل", "срочно", "BREAKING" — use what the channels use.

## Typical noise

Opinion and commentary · reposts of the same event across channels · old
footage recirculated · anniversaries and commemorations · ads · coverage of
other regions that only mentions the place in passing.

## Suggested rule groups

1. **Places** — one rule per language script if the list is long.
2. **Event vocabulary.**
3. **Channel urgency markers** — only if the channels use them consistently.

## Example criterion

> `local-breaking` — A first report of a significant event happening in the
> region in scope: a security incident, disaster, major disruption or
> significant official decision, with a specific place and time. High: people
> harmed or critical services disrupted. Medium: other significant events.
> Excludes: commentary, reposts of already-reported events, old footage,
> events elsewhere that merely mention the region.
