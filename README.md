# ⚡ pwb — Peering Workbench

A consolidated desktop tool for network engineers who are tired of juggling browser tabs between PeeringDB, WHOIS, looking glass sites, and RPKI validators. One app, one search bar, every lookup you need.

Built with PyQt6. All APIs are free and require no keys.

![PyPI](https://img.shields.io/pypi/v/pwb)
![Python](https://img.shields.io/pypi/pyversions/pwb)
![License](https://img.shields.io/pypi/l/pwb)

---

## Install

```bash
pip install pwb
```

For Team Cymru IP→ASN lookups and the DNS Lookup tab (recommended):

```bash
pip install pwb[cymru]
```

## Launch

```bash
python -m pwb
```

Or if installed via pip:

```bash
peering-workbench
```

---

## Features

### ⚡ Quick Lookup Bar

The toolbar input auto-detects what you type and routes to the right tab:

| Input | Detected as | Tab |
|---|---|---|
| `15169` or `AS15169` | ASN | ASN Lookup |
| `8.8.8.8` | IPv4 address | IP Lookup |
| `2607:f8b0:4001::1` | IPv6 address | IP Lookup |
| `1.0.0.0/24` or `2620:129::/44` | Prefix (v4/v6) | Prefix / LG |
| `cloudflare.com` | Hostname | DNS Lookup |

One search bar for everything. No mode switching, no tab hunting.

### 🏷 ASN Lookup

Enter any ASN — pulls **PeeringDB**, **RIPEstat**, and **RDAP** simultaneously in background threads. Sub-tabs for each data source plus raw JSON. One-click "Open in HE" jumps to the embedded HE tab for that ASN.

- IX presence with port speeds
- Facility list with cities
- Peering policy, NOC/policy email contacts
- Announced prefixes, upstream/downstream neighbors
- WHOIS registration, abuse contacts

![ASN / PeeringDB Lookup](https://raw.githubusercontent.com/scottpeterman/pwb/refs/heads/main/screenshots/peeringdb.png)

### 🌍 IP Lookup

Full context for any IPv4 or IPv6 address in a single view:

- **Team Cymru** DNS-based IP→ASN mapping with resolved network name (IPv4 and IPv6)
- **RDAP** network allocation and CIDR blocks
- **RIPEstat** geolocation, abuse contacts, prefix info
- **RPKI validation** — automatically derives the covering prefix and origin ASN, then checks ROA validity inline. You see whether the prefix is RPKI-valid without leaving the tab.
- **One-click prefix drill-down** — click the "Full Prefix Lookup" link to jump to the Prefix tab with the covering prefix pre-filled, launching the full lookup (RPKI, IRR, looking glass, related prefixes) in one click.

![IP Lookup](https://raw.githubusercontent.com/scottpeterman/pwb/refs/heads/main/screenshots/iplookup.png)

### 📡 Prefix / Looking Glass

Query any IPv4 or IPv6 prefix for routing status, origin AS, related/covering prefixes, and **RIPEstat looking glass** data from 25+ RIPE RRC route collectors worldwide — with **resolved AS-path names**.

Every ASN in every AS path is automatically resolved via PeeringDB and cached to disk. First lookup resolves names in the background; subsequent lookups render instantly from cache.

#### RPKI Validation

Each origin ASN is checked against the RPKI via RIPEstat's Routinator-backed validator. Results are color-coded:

- 🟢 **Valid** — a ROA exists and matches the prefix/origin/maxLength
- 🟡 **Not Found** — no ROA covers this prefix (RPKI-unknown)
- 🔴 **Invalid** — a ROA exists but the origin or prefix length doesn't match

Matching ROAs are displayed with their origin, prefix, and maxLength so you can immediately spot maxLength mismatches — the most common "everything looks right but traffic is dropping" RPKI issue.

#### IRR Route Object Consistency

Shows whether route/route6 objects exist in the IRR for the prefix, which registries they're in, and whether they match what's actually announced in BGP:

- **BGP + IRR ✓** — announced and registered (healthy)
- **BGP only — no IRR ✗** — announced but no route object (peers filtering on IRR will drop it)
- **IRR only — not announced** — registered but not in the BGP table (stale object)

This surfaces the kind of mismatch where RPKI is valid but a peer's IRR-based filters silently reject the prefix.

![Prefix / Looking Glass with RPKI and IRR](https://raw.githubusercontent.com/scottpeterman/pwb/refs/heads/main/screenshots/lookingglass.png)

### 🔎 DNS Lookup

General-purpose DNS record lookup powered by `dnspython`. Enter any hostname to query all record types at once, or select a specific type from the dropdown:

- **A / AAAA** — IPv4 and IPv6 addresses
- **CNAME** — canonical name aliases
- **MX** — mail exchangers with preference values
- **NS** — authoritative nameservers
- **TXT** — SPF, DKIM, verification records
- **SOA** — zone authority (serial, refresh, retry, expire)
- **PTR** — reverse DNS (auto-detected when you enter an IP instead of a hostname)
- **CAA** — certificate authority authorization

Enter an IP address and it automatically performs a reverse PTR lookup instead. Useful for identifying router hostnames from traceroute output.

### 💾 ASN Name Cache

Persistent disk cache at `~/.peering_workbench/asn_cache.json`. Grows automatically as you use the tool — after a few prefix lookups you'll have the entire tier-1/tier-2 transit universe cached. The file is portable: back it up, sync across machines, or seed it from other sources.

### 🔑 PeeringDB API Key (optional)

PeeringDB throttles anonymous API requests. If you hit `429 Too Many Requests` errors during heavy use, register for a free API key at [peeringdb.com](https://www.peeringdb.com/) and configure it one of two ways:

```bash
# Environment variable
export PEERINGDB_API_KEY=your-key-here

# Or save to config file
echo "your-key-here" > ~/.peering_workbench/peeringdb_api_key
```

Authenticated requests get significantly higher rate limits. The tool will also automatically retry on 429 responses with backoff, but an API key avoids the delays in the first place.

---

## APIs Used

All free, no API keys required.

| Source | What it provides |
|--------|-----------------|
| [PeeringDB](https://www.peeringdb.com/api/) | Network info, IX connections, facilities, peering policy, contacts |
| [RIPEstat](https://stat.ripe.net/data/) | ASN overview, announced prefixes, neighbors, looking glass (RRCs), RPKI validation, IRR routing consistency |
| [RDAP](https://rdap.org/) | Structured WHOIS replacement (auto-routes to ARIN/RIPE/APNIC) |
| [Team Cymru](https://www.team-cymru.com/ip-asn-mapping) | DNS-based IP→ASN mapping for IPv4 and IPv6 (requires `dnspython`) |

## Requirements

- Python 3.10+
- PyQt6
- requests
- dnspython (optional but recommended — enables Team Cymru lookups and the DNS Lookup tab)

## Development

```bash
git clone https://github.com/speterman/pwb.git
cd pwb
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,cymru]"
python -m pwb
```

## Publishing

```bash
python -m build
twine upload dist/*
```

## License

MIT — see [LICENSE](LICENSE).