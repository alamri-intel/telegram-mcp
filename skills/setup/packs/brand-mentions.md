# Starter pack: brand and organization mentions

For users watching what is said about an organization, product, person or
brand — reputation, customer complaints, impersonation, fraud, press.

## Extra interview options

- **What matters** (multi-select): complaints and outages · impersonation and
  fake accounts · scams using the brand · leaks of internal material ·
  press and analyst coverage · competitor mentions · executive mentions.
- **Who**: the organization only · its products · named people · competitors.
- **Tone**: everything · only negative or risky · only high-reach posts.

## Seed vocabulary

- Every name form: legal name, short name, product names, old names,
  abbreviations, ticker, hashtags, official handles, domains.
- Local-language and transliterated forms; common misspellings of the name.
- Risk words: scam, fake, fraud, "official giveaway", refund, outage, down,
  leak, lawsuit, boycott.
- Impersonation markers: "support", "customer service", "verify your
  account", "claim your", lookalike domains.

## Typical noise

The brand's own official posts reposted · ads and sponsored posts · unrelated
uses of a name that is also an ordinary word · job postings by the company ·
stock price chatter (unless wanted).

## Suggested rule groups

1. **Names and handles** — every form, as `word` rules for short Latin
   names to avoid substring collisions.
2. **Domains and lookalikes** — the official domains and obvious variants.
3. **Risk vocabulary near the brand** — as a separate, broader rule.

## Example criterion

> `brand-risk` — A post about the organization or its products that signals
> risk: a scam or impersonation using its name, a customer-facing outage,
> leaked internal material, or a complaint gaining traction. High: active scam
> or impersonation. Medium: outage or leak. Low: individual complaint.
> Excludes: the organization's own posts and ads, neutral news mentions, job
> listings, unrelated uses of the name.
