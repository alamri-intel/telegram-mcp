# Starter pack: security incidents

For users tracking cyber incidents, data leaks, vulnerabilities and actor
claims — for an organization, a sector or a region.

## Extra interview options

- **Focus** (multi-select): claims of intrusion or data theft · data leaks and
  dumps · ransomware victim posts · vulnerabilities and exploits · DDoS ·
  defacements · access or tool sales · scams and phishing aimed at a brand.
- **Scope of victims**: one organization · a sector (energy, finance,
  health, government, telecom, education, industrial) · a country or region ·
  anywhere.
- **Evidence bar**: any claim · claims with proof (sample, file list, size,
  screenshots) · only verified incidents.
- **Vulnerabilities**: exploited in the wild · public exploit released · any
  new advisory for listed products.

## Seed vocabulary

Translate and expand into the channels' languages (see
`../data/language-patterns.md`).

- Claims: hacked, breached, leaked, dumped, pwned, "claims responsibility",
  "we have access", "full database", "target down".
- Leaks: dump, database, records, "for sale", combolist, credentials, stealer
  logs, sample, GB/TB.
- Ransomware: ransomware, "new victim", encrypted, "data will be published",
  deadline, negotiation.
- Vulnerabilities: CVE-\d{4}-\d{4,}, zero-day / 0day, "exploited in the wild",
  "actively exploited", PoC, RCE, "pre-auth", KEV.
- Access sales: "initial access", RDP, VPN access, shell, admin panel.
- Identifiers: the victim's domains, brand names, ticker, local-language name.

## Typical noise

Generic DDoS claims with only a "check-host" link · reposts of old
operations · news articles about someone else's claim · recruitment and
channel promotion · political or war content with no cyber action · CVE feed
reposts and patch roundups with no exploitation signal · boasting with no
named target.

## Suggested rule groups

1. **Target names** — organizations, brands, domains, in every language.
2. **Geography** — countries and cities in scope (from `../data/country-names/`).
3. **Claim and leak vocabulary.**
4. **Vulnerability vocabulary and CVE ids** — its own rule; often high volume.

## Example criterion

> `targeted-claim` — A first-person claim by an actor of intrusion, data theft,
> leak, ransomware or defacement against a named organization in scope.
> Critical: proof attached and the victim is critical infrastructure. High:
> proof attached, other sectors. Medium: named victim, no proof. Excludes:
> DDoS-only claims, reposted or re-announced old operations, claims naming a
> country but no organization, news about another actor's claim.

Judge limits to mention: it sees one message at a time, so it can't know that
a fresh-looking claim recycles an old operation, and it does not verify
whether a claim is true.
