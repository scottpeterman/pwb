#!/usr/bin/env python3
"""
Help and About dialogs for the Peering Workbench.
"""

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QFont, QDesktopServices
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextBrowser,
    QPushButton, QTabWidget, QWidget,
)


# ─── Metadata ─────────────────────────────────────────────────────────────────

APP_NAME = "Peering Workbench"
APP_VERSION = "0.2.0"
APP_AUTHOR = "Scott Peterman"
APP_GITHUB = "https://github.com/scottpeterman/pwb"
APP_LICENSE = "GPLv3"


# ─── Shared Styles ────────────────────────────────────────────────────────────

_BROWSER_CSS = """
    body {
        font-family: "Roboto", "SF Pro Text", "Helvetica Neue", sans-serif;
        font-size: 13px; color: #3d2914; line-height: 1.5;
        margin: 0; padding: 4px;
    }
    h2 { color: #752d46; font-size: 16px; margin: 12px 0 6px 0; }
    h3 { color: #A56179; font-size: 14px; margin: 10px 0 4px 0; }
    code {
        background: #f7f1e8; padding: 1px 5px; border-radius: 2px;
        font-family: "SF Mono", "Menlo", "Consolas", monospace;
        font-size: 12px;
    }
    a { color: #752d46; }
    .tag {
        display: inline-block; padding: 2px 8px; border-radius: 2px;
        font-size: 11px; font-weight: 500;
    }
    .tag-green { background: #a7f2bb; color: #002106; }
    .tag-yellow { background: #ffdbcc; color: #331200; }
    .tag-red { background: #ffdad6; color: #410002; }
    .note {
        background: #f7f1e8; border-left: 3px solid #d4b896;
        padding: 8px 12px; margin: 8px 0; font-size: 12px;
    }
    .important {
        background: #fef3f0; border-left: 3px solid #A56179;
        padding: 8px 12px; margin: 8px 0; font-size: 12px;
    }
    table {
        border-collapse: collapse; width: 100%; margin: 6px 0;
    }
    td, th {
        padding: 4px 8px; font-size: 12px; text-align: left;
        border-bottom: 1px solid #f0e6d6;
    }
    th { background: #f0e6d6; color: #5c3e2a; }
"""


def _wrap_html(body):
    return f'<html><head><style>{_BROWSER_CSS}</style></head><body>{body}</body></html>'


def _make_browser(html):
    browser = QTextBrowser()
    browser.setOpenExternalLinks(True)
    browser.setHtml(_wrap_html(html))
    browser.setStyleSheet(
        "QTextBrowser { border: none; background: #fefcf8; }"
    )
    return browser


# ─── About Dialog ─────────────────────────────────────────────────────────────

class AboutDialog(QDialog):
    """Application About dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        self.setFixedSize(480, 400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)

        # Logo / title
        title = QLabel(f"⚡ {APP_NAME}")
        title.setStyleSheet(
            "font-size: 22px; font-weight: bold; color: #752d46;"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        version = QLabel(f"Version {APP_VERSION}")
        version.setStyleSheet("font-size: 12px; color: #5c3e2a;")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

        layout.addSpacing(8)

        body = _make_browser(f"""
            <p style="text-align:center; color:#5c3e2a;">
            A consolidated desktop tool for network engineers who are tired
            of juggling browser tabs between PeeringDB, WHOIS, looking glass
            sites, and RPKI validators.</p>

            <h3>Author</h3>
            <p>{APP_AUTHOR}
            · <a href="{APP_GITHUB}">GitHub</a>
            · License: {APP_LICENSE}</p>

            <h3>Data Sources</h3>
            <table>
            <tr><th>Source</th><th>Provides</th></tr>
            <tr><td><a href="https://www.peeringdb.com/api/">PeeringDB</a></td>
                <td>Network info, IX/facility presence, peering policy</td></tr>
            <tr><td><a href="https://stat.ripe.net/data/">RIPEstat</a></td>
                <td>ASN overview, prefixes, neighbours, looking glass, RPKI</td></tr>
            <tr><td><a href="https://rdap.org/">RDAP</a></td>
                <td>Structured WHOIS (auto-routes to ARIN/RIPE/APNIC)</td></tr>
            <tr><td><a href="https://www.team-cymru.com/ip-asn-mapping">Team Cymru</a></td>
                <td>DNS-based IP→ASN mapping (IPv4 + IPv6)</td></tr>
            </table>

            <div class="note">
            All APIs are free and require no keys. PeeringDB optionally
            accepts an API key for higher rate limits — see the README.</div>

            <h3>Tech Stack</h3>
            <p>Python · PyQt6 · requests · dnspython</p>
        """)
        layout.addWidget(body)

        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.close)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)


# ─── Workbench Help Dialog ────────────────────────────────────────────────────

_HELP_QUICKLOOKUP = """
<h2>⚡ Quick Lookup Bar</h2>
<p>The toolbar input auto-detects what you type and routes to the correct tab:</p>
<table>
<tr><th>Input</th><th>Detected as</th><th>Tab</th></tr>
<tr><td><code>15169</code> or <code>AS15169</code></td><td>ASN</td><td>ASN Lookup</td></tr>
<tr><td><code>8.8.8.8</code></td><td>IPv4</td><td>IP Lookup</td></tr>
<tr><td><code>2607:f8b0:4001::1</code></td><td>IPv6</td><td>IP Lookup</td></tr>
<tr><td><code>1.0.0.0/24</code></td><td>Prefix</td><td>Prefix / LG</td></tr>
<tr><td><code>cloudflare.com</code></td><td>Hostname</td><td>DNS Lookup</td></tr>
</table>
<p>One search bar for everything — no mode switching needed.</p>
"""

_HELP_ASN = """
<h2>🏷 ASN Lookup</h2>
<p>Enter any ASN to pull data from three sources simultaneously:</p>

<h3>PeeringDB Tab</h3>
<p>Network name, website, peering policy (Open / Selective / Restrictive),
NOC and peering email contacts, traffic levels, IX connections with port
speeds, and facility presence with cities.</p>

<h3>RIPEstat Tab</h3>
<p>ASN holder and registration block, announced prefixes, and
upstream/downstream neighbours with <b>power scores</b> — a measure of how
prominently each neighbour relationship appears in the global routing table.</p>

<h3>RDAP/WHOIS Tab</h3>
<p>Registration handle, contacts (org, abuse, tech), registration and
last-changed dates, and any remarks attached to the ASN object.</p>

<h3>Raw JSON Tab</h3>
<p>The complete response from all APIs as pretty-printed JSON.
Useful for scripting or finding fields not shown in the formatted views.</p>

<div class="note">
<b>Tip:</b> Use "Open in PeeringDB ↗" or "Open in HE ↗" buttons to
jump to the full web views for deeper investigation.</div>
"""

_HELP_IP = """
<h2>🌍 IP Lookup</h2>
<p>Full context for any IPv4 or IPv6 address in a single view:</p>

<h3>Team Cymru</h3>
<p>DNS-based IP→ASN mapping. Returns the origin ASN, covering prefix,
country code, and RIR. Fast and lightweight.</p>

<h3>RDAP</h3>
<p>Network allocation details: netblock handle, CIDR ranges, registration info.</p>

<h3>RIPEstat</h3>
<p>Prefix info, abuse contact, and MaxMind-based geolocation
(city, country, coordinates).</p>

<h3>RPKI Validation</h3>
<p>Automatically derives the covering prefix and origin ASN, then checks
ROA validity inline:</p>
<p><span class="tag tag-green">✓ Valid</span> — ROA matches prefix/origin/maxLength</p>
<p><span class="tag tag-yellow">? Not Found</span> — no ROA covers this prefix</p>
<p><span class="tag tag-red">✗ Invalid</span> — ROA exists but doesn't match</p>

<div class="note">
<b>Tip:</b> Click the "Full Prefix Lookup" link at the bottom to jump
to the Prefix tab with the covering prefix pre-filled.</div>
"""

_HELP_PREFIX = """
<h2>📡 Prefix / Looking Glass</h2>
<p>Deep analysis of any IPv4 or IPv6 prefix:</p>

<h3>Routing Status</h3>
<p>Whether the prefix is announced in BGP, and which ASN(s) originate it.</p>

<h3>Looking Glass</h3>
<p>Real AS paths observed from 20+ RIPE Route Collector (RRC) vantage points
worldwide. Every ASN in every path is resolved to its name via PeeringDB.</p>

<h3>RPKI Validation</h3>
<p>Each origin ASN is checked against ROAs. Shows the matching ROAs with
prefix, maxLength, and origin — useful for spotting maxLength mismatches.</p>

<h3>IRR Routing Consistency</h3>
<p>Checks whether route objects exist in the IRR and whether they match BGP:</p>
<p><span class="tag tag-green">BGP + IRR ✓</span> — announced and registered (healthy)</p>
<p><span class="tag tag-red">BGP only — no IRR ✗</span> — peers filtering on IRR will drop it</p>
<p><span class="tag tag-yellow">IRR only</span> — registered but not announced (stale)</p>
"""

_HELP_DNS = """
<h2>🔎 DNS Lookup</h2>
<p>General-purpose DNS record lookup powered by <code>dnspython</code>.</p>

<p>Enter a hostname to query all record types at once, or pick a
specific type from the dropdown:
<b>A</b>, <b>AAAA</b>, <b>CNAME</b>, <b>MX</b>, <b>NS</b>,
<b>TXT</b>, <b>SOA</b>, <b>PTR</b>, <b>CAA</b>.</p>

<p>Enter an IP address instead of a hostname and it automatically
performs a <b>reverse PTR lookup</b> — useful for identifying router
hostnames from traceroute output.</p>
"""

_HELP_CACHE = """
<h2>💾 ASN Name Cache</h2>
<p>Persistent disk cache at <code>~/.peering_workbench/asn_cache.json</code>.</p>

<p>Grows automatically as you use the tool. After a few prefix lookups
you'll have the entire Tier 1 / Tier 2 transit universe cached and
AS paths will render with names instantly.</p>

<div class="note">
The cache file is portable — back it up, sync across machines, or
seed it from other sources. The status bar shows the current cache size.</div>
"""


class WorkbenchHelpDialog(QDialog):
    """Tabbed help dialog for the main Peering Workbench."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — Help")
        self.setMinimumSize(580, 520)
        self.resize(620, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        tabs = QTabWidget()
        tabs.addTab(_make_browser(_HELP_QUICKLOOKUP), "Quick Lookup")
        tabs.addTab(_make_browser(_HELP_ASN), "ASN")
        tabs.addTab(_make_browser(_HELP_IP), "IP")
        tabs.addTab(_make_browser(_HELP_PREFIX), "Prefix / LG")
        tabs.addTab(_make_browser(_HELP_DNS), "DNS")
        tabs.addTab(_make_browser(_HELP_CACHE), "Cache")
        layout.addWidget(tabs)

        btn_row = QHBoxLayout()
        about_btn = QPushButton("About")
        about_btn.clicked.connect(lambda: AboutDialog(self).exec())
        btn_row.addWidget(about_btn)
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)


# ─── Path Visualization Help Dialog ───────────────────────────────────────────

_HELP_PATHVIZ = """
<h2>🗺 AS-Path Visualization</h2>
<p>Traces the BGP-level path between two IP addresses and renders
it as an interactive directed graph.</p>

<h3>How It Works</h3>
<ol>
<li><b>IP Resolution</b> — each IP is mapped to its origin ASN and covering
prefix via Team Cymru, with RIPEstat and RDAP as fallbacks.</li>
<li><b>Looking Glass</b> — RIPEstat's looking glass data provides real AS
paths observed from 20+ RIPE Route Collector vantage points worldwide.
Forward paths (to the destination prefix) and reverse paths (to the
source prefix) are queried separately.</li>
<li><b>Neighbour Data</b> — the <code>asn-neighbours</code> API provides
upstream relationships and <b>power scores</b> for both endpoints.</li>
<li><b>Path Selection</b> — paths are filtered and trimmed to connect
source to destination. <b>Direct</b> paths contain the source ASN in
the looking glass data. <b>Inferred</b> paths are routed via a known
upstream. <b>Fallback</b> paths are the shortest observed routes.</li>
</ol>

<h3>Reading the Graph</h3>
<table>
<tr><th>Element</th><th>Meaning</th></tr>
<tr><td style="color:#1a873a;">■ Green node</td><td>Source ASN</td></tr>
<tr><td style="color:#752d46;">■ Burgundy node</td><td>Destination ASN</td></tr>
<tr><td style="color:#d4b896;">■ Tan node</td><td>Transit ASN</td></tr>
<tr><td style="color:#752d46;">━ Burgundy edge</td><td>Forward path (src → dst)</td></tr>
<tr><td style="color:#2d6b5a;">━ Teal edge</td><td>Reverse path (dst → src)</td></tr>
</table>
<p><b>Edge thickness</b> reflects the <b>power score</b> from the
asn-neighbours API — a measure of how prominently that peering
relationship appears in the global routing table. Thicker edges
represent stronger, more widely-visible links. Edges without a
known power score fall back to path-count-based thickness.</p>

<h3>Interaction</h3>
<p>
<b>Scroll</b> to zoom · <b>Drag</b> to pan ·
<b>Hover</b> a node or edge for details<br>
<b>Click an edge</b> to open a PeeringDB detail dialog showing
shared Internet Exchanges, facilities, port speeds, and peering
policy for those two ASNs.<br>
<b>Click a path</b> in the sidebar list to highlight it ·
use the <b>Visibility</b> checkboxes to toggle forward/reverse.</p>
"""

_HELP_PATHVIZ_LIMITS = """
<h2>⚠ Important Limitations</h2>

<div class="important">
<b>This is a model, not ground truth.</b><br>
The visualization shows <b>observed BGP control-plane paths</b> — real
routes announced to RIPE's route collectors. But it cannot show you
what actually happens to packets on the data plane.</div>

<h3>What We Can See</h3>
<p>Real AS paths from the global routing table, power scores reflecting
neighbour relationship strength, and PeeringDB data on shared IXes
and facilities.</p>

<h3>What We Cannot See</h3>
<table>
<tr><th>Factor</th><th>Impact</th></tr>
<tr><td><b>Local Preference</b></td>
    <td>The single most influential routing knob. An operator can
    override all other factors by setting LP. Completely invisible
    externally.</td></tr>
<tr><td><b>BGP Communities</b></td>
    <td>no-export, blackhole, transit-specific action communities
    reshape what gets advertised where. Requires access to router
    configs.</td></tr>
<tr><td><b>MED / Weight</b></td>
    <td>MED influences inbound preference between multiple links;
    Weight is entirely local. Both invisible.</td></tr>
<tr><td><b>Hot/Cold Potato</b></td>
    <td>Does the network hand off at the nearest exit or carry
    traffic across its backbone? Huge impact, zero visibility.</td></tr>
<tr><td><b>ECMP</b></td>
    <td>Traffic may be load-balanced across multiple paths
    simultaneously.</td></tr>
<tr><td><b>Private Peering</b></td>
    <td>Bilateral PNI between networks won't appear in public
    looking glass data.</td></tr>
</table>

<div class="note">
<b>Bottom line:</b> The graph shows which routes <em>exist</em> and
how strongly they're represented in the global table. This is valuable
for peering analysis and understanding connectivity options — but the
actual traffic engineering is a black box without access to the routers
themselves.</div>
"""


class PathVizHelpDialog(QDialog):
    """Tabbed help dialog for the AS-Path Visualization."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AS-Path Visualization — Help")
        self.setMinimumSize(580, 520)
        self.resize(620, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        tabs = QTabWidget()
        tabs.addTab(_make_browser(_HELP_PATHVIZ), "How It Works")
        tabs.addTab(_make_browser(_HELP_PATHVIZ_LIMITS), "Limitations")
        layout.addWidget(tabs)

        btn_row = QHBoxLayout()
        about_btn = QPushButton("About")
        about_btn.clicked.connect(lambda: AboutDialog(self).exec())
        btn_row.addWidget(about_btn)
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)