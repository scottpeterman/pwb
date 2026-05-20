#!/usr/bin/env python3
"""
Peering Workbench — Consolidated ASN / WHOIS / PeeringDB / Looking Glass tool.

APIs used (all free, no keys required):
  • PeeringDB   — https://www.peeringdb.com/api/
  • RIPEstat    — https://stat.ripe.net/data/
  • RDAP        — https://rdap.arin.net/ (+ RIPE, APNIC auto-redirect)
  • Team Cymru  — DNS-based IP→ASN mapping

Requirements:
  pip install PyQt6 requests dnspython
"""

import sys, json, os, re, textwrap, socket, ipaddress
from datetime import datetime
from functools import partial
from pathlib import Path

from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QUrl, QSize, QTimer
)
from PyQt6.QtGui import (
    QAction, QFont, QColor, QIcon, QPalette, QKeySequence,
    QDesktopServices
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTabWidget, QLineEdit,
    QPushButton, QLabel, QTextEdit, QComboBox, QTextBrowser,
    QMenu, QToolBar, QStatusBar, QGroupBox, QFormLayout,
    QMessageBox, QProgressBar, QGridLayout, QFrame, QSizePolicy
)

import requests

# Optional: dns python for Team Cymru lookups
try:
    import dns.resolver
    HAS_DNSPYTHON = True
except ImportError:
    HAS_DNSPYTHON = False


# ─── Colour Palette (pyNetweaver: burgundy / cream / beige, ultra-flat) ──────
#
#   Primary      #752d46  burgundy         On-Primary    #ffffff
#   Secondary    #A56179  dusty rose       Tertiary      #8b6f47  accent brown
#   Background   #fefcf8  cream            Surface       #ffffff
#   On-Surface   #3d2914  deep brown       Outline       #d4b896  tan
#   Containers   #faf6f0 → #f7f1e8 → #f0e6d6 → #e7dcc9
#   Success      #146c2e  Error #ba1a1a    Warning #9c4a00

STYLESHEET = """
QMainWindow, QWidget {
    background-color: #fefcf8;
    color: #3d2914;
    font-family: "Roboto", "SF Pro Text", "Helvetica Neue", sans-serif;
    font-size: 13px;
}

QTabWidget::pane { border: 1px solid #f0e6d6; border-radius: 2px; }
QTabBar::tab {
    background: #f7f1e8; color: #5c3e2a; padding: 8px 18px;
    border: 1px solid #f0e6d6; border-bottom: none; border-radius: 2px 2px 0 0;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background: #ffffff; color: #752d46; border-bottom: 2px solid #752d46;
}
QTabBar::tab:hover { background: #faf6f0; }

QTableView {
    background-color: #ffffff; alternate-background-color: #faf6f0;
    gridline-color: #f0e6d6; selection-background-color: #f7f1e8;
    selection-color: #752d46;
    border: 1px solid #d4b896; border-radius: 2px;
}
QHeaderView::section {
    background-color: #f0e6d6; color: #3d2914; padding: 6px;
    border: none; border-right: 1px solid #d4b896; border-bottom: 1px solid #d4b896;
    font-weight: 500;
}

QLineEdit, QComboBox {
    background-color: #ffffff; border: 1px solid #d4b896; border-radius: 2px;
    padding: 6px 10px; color: #3d2914;
}
QLineEdit:focus, QComboBox:focus { border-color: #752d46; }

QPushButton {
    background-color: #752d46; color: #ffffff; border: none;
    border-radius: 2px; padding: 7px 16px; font-weight: 500;
}
QPushButton:hover { background-color: #A56179; }
QPushButton:pressed { background-color: #5c1e35; }
QPushButton:disabled { background-color: #e7dcc9; color: #9a8a74; }

QPushButton[cssClass="danger"] { background-color: #ba1a1a; color: #ffffff; }
QPushButton[cssClass="success"] { background-color: #146c2e; color: #ffffff; }

QTextEdit {
    background-color: #ffffff; border: 1px solid #d4b896; border-radius: 2px;
    padding: 8px; color: #3d2914;
    font-family: "SF Mono", "Menlo", "Consolas", monospace; font-size: 12px;
}

QGroupBox {
    border: 1px solid #d4b896; border-radius: 3px; margin-top: 12px;
    padding-top: 18px; font-weight: 500; color: #752d46;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }

QProgressBar {
    border: 1px solid #d4b896; border-radius: 2px; text-align: center;
    background: #f7f1e8; color: #3d2914; height: 18px;
}
QProgressBar::chunk { background-color: #752d46; border-radius: 1px; }

QSplitter::handle { background: #d4b896; width: 2px; }

QStatusBar { background: #f7f1e8; color: #5c3e2a; border-top: 1px solid #f0e6d6; }

QToolBar { background: #ffffff; border-bottom: 1px solid #f0e6d6; spacing: 6px; padding: 4px; }

QMenu { background: #ffffff; border: 1px solid #d4b896; border-radius: 2px; padding: 4px; }
QMenu::item { padding: 6px 24px; color: #3d2914; }
QMenu::item:selected { background: #f7f1e8; color: #752d46; }

QLabel#heading { font-size: 15px; font-weight: 500; color: #752d46; }
QLabel#subheading { font-size: 12px; color: #5c3e2a; }
QLabel#tag { background: #752d46; color: #ffffff; border-radius: 2px; padding: 2px 8px; font-size: 11px; }
QLabel#tagGreen { background: #a7f2bb; color: #002106; border-radius: 2px; padding: 2px 8px; font-size: 11px; }
QLabel#tagYellow { background: #ffdbcc; color: #331200; border-radius: 2px; padding: 2px 8px; font-size: 11px; }
QLabel#tagRed { background: #ffdad6; color: #410002; border-radius: 2px; padding: 2px 8px; font-size: 11px; }

QScrollBar:vertical {
    background: #faf6f0; width: 8px; margin: 0;
}
QScrollBar::handle:vertical {
    background: #d4b896; border-radius: 4px; min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #5c3e2a; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


# ─── API Helpers ──────────────────────────────────────────────────────────────

import time

PEERINGDB_BASE = "https://www.peeringdb.com/api"
RIPESTAT_BASE = "https://stat.ripe.net/data"

# Config directory — also used by AsnNameCache
_CONFIG_DIR = Path.home() / ".peering_workbench"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "PeeringWorkbench/0.1.0",
    "Accept": "application/json",
})

# Optional PeeringDB API key — load from config or environment.
# Raises anonymous limits (~300 req/min) to authenticated (~500 req/min)
# and avoids the strict identical-request throttle.
#   env:  PEERINGDB_API_KEY=your-key-here
#   file: ~/.peering_workbench/peeringdb_api_key
_pdb_api_key = os.environ.get("PEERINGDB_API_KEY", "").strip()
if not _pdb_api_key:
    _key_file = _CONFIG_DIR / "peeringdb_api_key"
    try:
        if _key_file.exists():
            _pdb_api_key = _key_file.read_text().strip()
    except Exception:
        pass


def _retry_get(url, params=None, headers=None, timeout=15, max_retries=3):
    """GET with retry on 429. Respects Retry-After header."""
    for attempt in range(max_retries):
        r = SESSION.get(url, params=params or {}, headers=headers,
                        timeout=timeout)
        if r.status_code != 429:
            r.raise_for_status()
            return r
        # 429 — parse Retry-After or use exponential backoff
        retry_after = r.headers.get("Retry-After")
        if retry_after:
            try:
                wait = min(int(retry_after), 60)  # cap at 60s
            except ValueError:
                wait = 2 ** attempt
        else:
            wait = 2 ** attempt
        if attempt < max_retries - 1:
            time.sleep(wait)
    # Final attempt failed — raise as usual
    r.raise_for_status()
    return r  # unreachable, but keeps linters happy


def pdb_get(endpoint, params=None):
    """PeeringDB API call with retry and optional API key."""
    headers = {}
    if _pdb_api_key:
        headers["Authorization"] = f"Api-Key {_pdb_api_key}"
    r = _retry_get(
        f"{PEERINGDB_BASE}/{endpoint}",
        params=params or {},
        headers=headers,
    )
    return r.json().get("data", [])


def ripestat_get(endpoint, params=None):
    """RIPEstat Data API call with retry."""
    url = f"{RIPESTAT_BASE}/{endpoint}/data.json"
    r = _retry_get(url, params=params or {})
    return r.json().get("data", {})


def rdap_autnum(asn):
    """RDAP lookup for an ASN (auto-redirects between RIRs)."""
    r = _retry_get(f"https://rdap.org/autnum/{asn}")
    return r.json()


def rdap_ip(ip):
    """RDAP lookup for an IP address."""
    r = _retry_get(f"https://rdap.org/ip/{ip}")
    return r.json()


def cymru_ip_to_asn(ip):
    """Team Cymru DNS-based IP→ASN mapping (IPv4 and IPv6)."""
    if not HAS_DNSPYTHON:
        return None
    try:
        addr = ipaddress.ip_address(ip)
        if isinstance(addr, ipaddress.IPv4Address):
            parts = ip.split(".")
            query = ".".join(reversed(parts)) + ".origin.asn.cymru.com"
        else:
            # IPv6: expand to full 32 hex nibbles, reverse, query origin6
            exploded = addr.exploded.replace(":", "")   # 32 hex chars
            query = ".".join(reversed(exploded)) + ".origin6.asn.cymru.com"

        answers = dns.resolver.resolve(query, "TXT")
        for rdata in answers:
            txt = rdata.to_text().strip('"')
            # Format: "ASN | prefix | CC | RIR | date"
            fields = [f.strip() for f in txt.split("|")]
            return {
                "asn": fields[0] if len(fields) > 0 else "",
                "prefix": fields[1] if len(fields) > 1 else "",
                "cc": fields[2] if len(fields) > 2 else "",
                "rir": fields[3] if len(fields) > 3 else "",
                "allocated": fields[4] if len(fields) > 4 else "",
            }
    except Exception:
        return None


# ─── ASN Name Cache ──────────────────────────────────────────────────────────
# Disk-backed cache at ~/.peering_workbench/asn_cache.json
# Resolves via PeeringDB API on miss, falls back to RIPEstat.

class AsnNameCache:
    """Thread-safe ASN→name resolver with persistent disk cache."""

    def __init__(self):
        self._cache_dir = _CONFIG_DIR
        self._cache_file = self._cache_dir / "asn_cache.json"
        self._names = {}   # str(asn) → name
        self._load()

    def _load(self):
        """Load cache from disk."""
        try:
            if self._cache_file.exists():
                with open(self._cache_file) as f:
                    self._names = json.load(f)
        except Exception:
            self._names = {}

    def _save(self):
        """Persist cache to disk."""
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            with open(self._cache_file, "w") as f:
                json.dump(self._names, f, indent=1)
        except Exception:
            pass

    def get(self, asn):
        """Return cached name or None."""
        return self._names.get(str(asn))

    def resolve(self, asn):
        """Resolve a single ASN to a name. Checks cache first, then APIs."""
        key = str(asn)
        if key in self._names:
            return self._names[key]

        name = self._fetch_name(key)
        if name:
            self._names[key] = name
            self._save()
        return name

    def resolve_batch(self, asn_list):
        """
        Resolve a list of ASNs. Only fetches those not already cached.
        Returns dict of asn→name for all resolved.
        """
        to_fetch = [str(a) for a in asn_list if str(a) not in self._names]
        if not to_fetch:
            return {str(a): self._names.get(str(a), "") for a in asn_list}

        for asn in to_fetch:
            name = self._fetch_name(asn)
            if name:
                self._names[asn] = name

        if to_fetch:
            self._save()

        return {str(a): self._names.get(str(a), "") for a in asn_list}

    def _fetch_name(self, asn):
        """Fetch ASN name from PeeringDB, fall back to RIPEstat."""
        # Try PeeringDB first (fast, structured)
        try:
            nets = pdb_get("net", {"asn": asn})
            if nets:
                return nets[0].get("name", "")
        except Exception:
            pass

        # Fallback: RIPEstat as-overview
        try:
            ov = ripestat_get("as-overview", {"resource": f"AS{asn}"})
            holder = ov.get("holder", "")
            if holder:
                return holder
        except Exception:
            pass

        return None

    @property
    def size(self):
        return len(self._names)


# Global instance — shared across workers
ASN_CACHE = AsnNameCache()


def fmt_as_path(as_path_str):
    """
    Format an AS path string with resolved names as HTML.
    Input:  "8218 6461 174 6169"
    Output: "8218 (Zayo-IPX) → 6461 (Zayo) → 174 (Cogent) → 6169 (Kentik)"
    Uses cached names; unknown ASNs show number only.
    """
    if not as_path_str or not as_path_str.strip():
        return ""
    hops = as_path_str.strip().split()
    parts = []
    seen = set()
    for asn in hops:
        if not asn.isdigit():
            parts.append(asn)
            continue
        # Deduplicate prepends for display
        if asn in seen:
            continue
        seen.add(asn)
        name = ASN_CACHE.get(asn)
        if name:
            # Truncate long names
            short = name[:20] + "…" if len(name) > 20 else name
            parts.append(
                f'<span style="color:#A56179;">{asn}</span>'
                f' <span style="color:#5c3e2a; font-size:10px;">({short})</span>'
            )
        else:
            parts.append(f'<span style="color:#A56179;">{asn}</span>')
    return ' → '.join(parts)


def fmt_asn_inline(asn):
    """Format a single ASN with its name inline. E.g. 'AS174 (Cogent)'."""
    key = str(asn)
    name = ASN_CACHE.get(key)
    if name:
        short = name[:25] + "…" if len(name) > 25 else name
        return f'<span style="color:#A56179;">AS{key}</span> ({short})'
    return f'<span style="color:#A56179;">AS{key}</span>'


class AsnBatchWorker(QThread):
    """Background thread that batch-resolves a set of ASNs."""
    finished = pyqtSignal(int)   # number resolved
    progress = pyqtSignal(str)

    def __init__(self, asn_set):
        super().__init__()
        self.asn_set = asn_set

    def run(self):
        to_resolve = [a for a in self.asn_set if ASN_CACHE.get(a) is None]
        if not to_resolve:
            self.finished.emit(0)
            return
        self.progress.emit(f"Resolving {len(to_resolve)} ASN names…")
        count = 0
        for i, asn in enumerate(to_resolve):
            name = ASN_CACHE.resolve(asn)
            if name:
                count += 1
            if (i + 1) % 5 == 0:
                self.progress.emit(f"Resolved {i+1}/{len(to_resolve)} ASNs…")
            # Courtesy delay to avoid triggering PeeringDB rate limits
            if i < len(to_resolve) - 1:
                time.sleep(0.15)
        self.finished.emit(count)


# ─── Worker Threads ───────────────────────────────────────────────────────────

class ApiWorker(QThread):
    """Generic async API worker. Emits (dict) on success, (str) on error."""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self._func = func
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            result = self._func(*self._args, **self._kwargs)
            self.finished.emit(result if isinstance(result, dict) else {"data": result})
        except Exception as e:
            self.error.emit(str(e))


class AsnLookupWorker(QThread):
    """Full ASN lookup: PeeringDB + RIPEstat + RDAP in one shot."""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, asn):
        super().__init__()
        self.asn = str(asn).strip().upper().replace("AS", "")

    def run(self):
        result = {"asn": self.asn}
        asn = self.asn

        # 1) PeeringDB net object
        self.progress.emit("Querying PeeringDB…")
        try:
            nets = pdb_get("net", {"asn": asn})
            if nets:
                result["peeringdb"] = nets[0]
                net_id = nets[0].get("id")
                # Grab IX connections
                try:
                    ixlans = pdb_get("netixlan", {"net_id": net_id})
                    result["peeringdb_ixlans"] = ixlans
                except Exception:
                    pass
                # Grab facility presence
                try:
                    facs = pdb_get("netfac", {"net_id": net_id})
                    result["peeringdb_facs"] = facs
                except Exception:
                    pass
        except Exception as e:
            result["peeringdb_error"] = str(e)

        # 2) RIPEstat — ASN overview
        self.progress.emit("Querying RIPEstat…")
        try:
            overview = ripestat_get("as-overview", {"resource": f"AS{asn}"})
            result["ripestat_overview"] = overview
        except Exception as e:
            result["ripestat_error"] = str(e)

        # 3) RIPEstat — announced prefixes
        self.progress.emit("Fetching announced prefixes…")
        try:
            prefixes = ripestat_get("announced-prefixes", {"resource": f"AS{asn}"})
            result["ripestat_prefixes"] = prefixes
        except Exception as e:
            pass

        # 4) RIPEstat — neighbours / upstreams
        self.progress.emit("Fetching ASN neighbours…")
        try:
            neighbours = ripestat_get("asn-neighbours", {"resource": f"AS{asn}"})
            result["ripestat_neighbours"] = neighbours
        except Exception as e:
            pass

        # 5) RDAP
        self.progress.emit("Querying RDAP…")
        try:
            rdap = rdap_autnum(asn)
            result["rdap"] = rdap
        except Exception as e:
            result["rdap_error"] = str(e)

        self.finished.emit(result)


class IpLookupWorker(QThread):
    """IP lookup: RDAP + Team Cymru + RIPEstat."""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, ip):
        super().__init__()
        self.ip = ip.strip()

    def run(self):
        result = {"ip": self.ip}
        ip = self.ip

        # Team Cymru
        self.progress.emit("Team Cymru DNS lookup…")
        cymru = cymru_ip_to_asn(ip)
        if cymru:
            result["cymru"] = cymru

        # RDAP IP
        self.progress.emit("RDAP IP lookup…")
        try:
            result["rdap"] = rdap_ip(ip)
        except Exception as e:
            result["rdap_error"] = str(e)

        # RIPEstat network info
        self.progress.emit("RIPEstat network info…")
        try:
            result["ripestat_prefix"] = ripestat_get("network-info", {"resource": ip})
        except Exception:
            pass

        # RIPEstat abuse contact
        try:
            result["ripestat_abuse"] = ripestat_get("abuse-contact-finder", {"resource": ip})
        except Exception:
            pass

        # RIPEstat geoloc
        try:
            result["ripestat_geoloc"] = ripestat_get("maxmind-geo-lite", {"resource": ip})
        except Exception:
            pass

        # RPKI validation — derive prefix + origin ASN from earlier results
        self.progress.emit("RPKI validation…")
        try:
            # Get prefix and ASN from Cymru or RIPEstat
            pfx = None
            origin_asn = None

            cymru = result.get("cymru", {})
            if cymru:
                pfx = cymru.get("prefix", "")
                origin_asn = cymru.get("asn", "")

            # Fallback to RIPEstat network-info
            if not pfx:
                ripe_pfx = result.get("ripestat_prefix", {})
                pfx = ripe_pfx.get("prefix", "")
                asns = ripe_pfx.get("asns", [])
                if asns and not origin_asn:
                    origin_asn = str(asns[0])

            if pfx and origin_asn:
                result["_derived_prefix"] = pfx
                result["_derived_asn"] = origin_asn
                rv = ripestat_get("rpki-validation", {
                    "resource": origin_asn, "prefix": pfx
                })
                rv["_queried_asn"] = origin_asn
                result["rpki"] = rv
        except Exception:
            pass

        self.finished.emit(result)


class PrefixLookupWorker(QThread):
    """Prefix lookup: RIPEstat BGP state, routing status, related objects."""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, prefix):
        super().__init__()
        self.prefix = prefix.strip()

    def run(self):
        result = {"prefix": self.prefix}
        pfx = self.prefix

        self.progress.emit("RIPEstat routing status…")
        try:
            result["routing_status"] = ripestat_get("routing-status", {"resource": pfx})
        except Exception:
            pass

        self.progress.emit("RIPEstat BGP state…")
        try:
            result["bgp_state"] = ripestat_get("bgp-state", {"resource": pfx})
        except Exception:
            pass

        self.progress.emit("RIPEstat prefix overview…")
        try:
            result["prefix_overview"] = ripestat_get("prefix-overview", {"resource": pfx})
        except Exception:
            pass

        self.progress.emit("RIPEstat related prefixes…")
        try:
            result["related"] = ripestat_get("related-prefixes", {"resource": pfx})
        except Exception:
            pass

        self.progress.emit("Looking glass (RIPEstat)…")
        try:
            result["looking_glass"] = ripestat_get("looking-glass", {"resource": pfx})
        except Exception:
            pass

        # RPKI validation — needs origin ASN from routing status
        self.progress.emit("RPKI validation…")
        try:
            origin_asns = []
            rs = result.get("routing_status", {})
            for o in rs.get("origins", []):
                if isinstance(o, dict):
                    origin_asns.append(str(o.get("asn", o.get("origin", ""))))
                else:
                    origin_asns.append(str(o))
            # Fallback to prefix-overview origins
            if not origin_asns:
                po = result.get("prefix_overview", {})
                for a in po.get("asns", []):
                    origin_asns.append(str(a.get("asn", "")))

            rpki_results = []
            for asn in origin_asns[:5]:  # cap to avoid flooding
                if not asn:
                    continue
                try:
                    rv = ripestat_get("rpki-validation", {
                        "resource": asn, "prefix": pfx
                    })
                    rv["_queried_asn"] = asn
                    rpki_results.append(rv)
                except Exception:
                    rpki_results.append({
                        "_queried_asn": asn, "status": "error"
                    })
            result["rpki"] = rpki_results
        except Exception:
            pass

        # IRR / prefix routing consistency
        self.progress.emit("IRR routing consistency…")
        try:
            result["irr_consistency"] = ripestat_get(
                "prefix-routing-consistency", {"resource": pfx}
            )
        except Exception:
            pass

        self.finished.emit(result)


class DnsLookupWorker(QThread):
    """DNS record lookup using dnspython."""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    # Record types to query — order matters for display
    RECORD_TYPES = ["A", "AAAA", "CNAME", "MX", "NS", "TXT", "SOA", "PTR", "CAA"]

    def __init__(self, hostname, record_types=None):
        super().__init__()
        self.hostname = hostname.strip().rstrip(".")
        self.record_types = record_types or self.RECORD_TYPES

    def run(self):
        if not HAS_DNSPYTHON:
            self.error.emit("dnspython is not installed (pip install dnspython)")
            return

        result = {"hostname": self.hostname, "records": {}}

        # Detect if input is an IP → do reverse (PTR) lookup
        is_reverse = False
        try:
            addr = ipaddress.ip_address(self.hostname)
            is_reverse = True
            result["reverse"] = True
            result["ptr_name"] = addr.reverse_pointer
        except ValueError:
            pass

        if is_reverse:
            self.progress.emit(f"Reverse DNS for {self.hostname}…")
            try:
                answers = dns.resolver.resolve(addr.reverse_pointer, "PTR")
                result["records"]["PTR"] = [rdata.to_text() for rdata in answers]
            except dns.resolver.NXDOMAIN:
                result["records"]["PTR"] = ["(NXDOMAIN — no PTR record)"]
            except dns.resolver.NoAnswer:
                result["records"]["PTR"] = ["(no PTR record)"]
            except Exception as e:
                result["records"]["PTR"] = [f"(error: {e})"]
        else:
            for rtype in self.record_types:
                self.progress.emit(f"Querying {rtype} for {self.hostname}…")
                try:
                    answers = dns.resolver.resolve(self.hostname, rtype)
                    records = []
                    for rdata in answers:
                        if rtype == "MX":
                            records.append(f"{rdata.preference}  {rdata.exchange}")
                        elif rtype == "SOA":
                            records.append(
                                f"mname={rdata.mname}  rname={rdata.rname}  "
                                f"serial={rdata.serial}  refresh={rdata.refresh}  "
                                f"retry={rdata.retry}  expire={rdata.expire}  "
                                f"minimum={rdata.minimum}"
                            )
                        else:
                            records.append(rdata.to_text())
                    if records:
                        result["records"][rtype] = records
                except dns.resolver.NXDOMAIN:
                    result["records"]["_nxdomain"] = True
                    break  # no point querying other types
                except dns.resolver.NoAnswer:
                    pass  # just skip — no records of this type
                except dns.resolver.NoNameservers:
                    result["records"][rtype] = ["(SERVFAIL)"]
                except Exception:
                    pass

        self.finished.emit(result)


def fmt_dns_result(data):
    """Format DNS lookup result as HTML."""
    lines = []
    hostname = data.get("hostname", "")
    is_reverse = data.get("reverse", False)

    if is_reverse:
        lines.append(f'<h3 style="color:#752d46;">🔎 Reverse DNS: {hostname}</h3>')
        ptr_name = data.get("ptr_name", "")
        lines.append(f'<p style="font-family:monospace; color:#5c3e2a;">Query: {ptr_name}</p>')
    else:
        lines.append(f'<h3 style="color:#752d46;">🔎 DNS Lookup: {hostname}</h3>')

    records = data.get("records", {})

    if records.get("_nxdomain"):
        lines.append(
            '<p style="color:#ba1a1a; font-weight:500;">'
            '✗ NXDOMAIN — this name does not exist</p>'
        )
        return "\n".join(lines)

    if not records:
        lines.append('<p style="color:#5c3e2a;">No records returned.</p>')
        return "\n".join(lines)

    for rtype, rdata_list in records.items():
        if rtype.startswith("_"):
            continue
        color = "#752d46" if rtype in ("A", "AAAA", "PTR") else "#A56179"
        lines.append(
            f'<h4 style="color:{color}; margin-bottom:2px;">{rtype}'
            f'<span style="color:#5c3e2a; font-size:11px; font-weight:normal;">'
            f'  ({len(rdata_list)} record{"s" if len(rdata_list) != 1 else ""})'
            f'</span></h4>'
        )
        lines.append(
            '<table cellpadding="3" style="font-family:monospace; font-size:12px; '
            'color:#3d2914; margin-bottom:8px;">'
        )
        for rd in rdata_list:
            lines.append(f'<tr><td>{rd}</td></tr>')
        lines.append('</table>')

    return "\n".join(lines)


# ─── Result Formatters ────────────────────────────────────────────────────────

def fmt_peeringdb(data):
    """Format PeeringDB net object as rich text."""
    if not data.get("peeringdb"):
        err = data.get("peeringdb_error", "Not found in PeeringDB")
        return f'<p style="color:#ba1a1a;">⚠ {err}</p>'

    n = data["peeringdb"]
    lines = []
    lines.append(f'<h3 style="color:#752d46;">🌐 {n.get("name", "?")} — AS{n.get("asn","")}</h3>')
    lines.append('<table cellpadding="4" style="color:#3d2914;">')

    fields = [
        ("Website", n.get("website", "")),
        ("IRR as-set", n.get("irr_as_set", "")),
        ("Info Type", n.get("info_type", "")),
        ("Info Traffic", n.get("info_traffic", "")),
        ("Info Ratio", n.get("info_ratio", "")),
        ("Info Scope", n.get("info_scope", "")),
        ("Peering Policy", n.get("policy_general", "")),
        ("Policy URL", n.get("policy_url", "")),
        ("IPv4 Prefixes", str(n.get("info_prefixes4", ""))),
        ("IPv6 Prefixes", str(n.get("info_prefixes6", ""))),
        ("NOC Email", n.get("noc_email", "") if n.get("noc_email") else "—"),
        ("Peering Email", n.get("policy_email", "") if n.get("policy_email") else "—"),
        ("Status", n.get("status", "")),
        ("Updated", n.get("updated", "")[:19] if n.get("updated") else ""),
    ]
    for label, val in fields:
        if val:
            if val.startswith("http"):
                val = f'<a style="color:#A56179;" href="{val}">{val}</a>'
            lines.append(f'<tr><td style="color:#5c3e2a;">{label}</td><td><b>{val}</b></td></tr>')
    lines.append('</table>')

    # IX list
    ixlans = data.get("peeringdb_ixlans", [])
    if ixlans:
        lines.append(f'<h4 style="color:#A56179;">Exchange Points ({len(ixlans)})</h4>')
        lines.append('<table cellpadding="3" style="color:#3d2914; font-size:12px;">')
        lines.append('<tr style="color:#5c3e2a;"><td>IX</td><td>IPv4</td><td>IPv6</td><td>Speed</td><td>Status</td></tr>')
        for ix in ixlans[:50]:
            name = ix.get("name", "")
            ip4 = ix.get("ipaddr4", "—")
            ip6 = ix.get("ipaddr6", "—")
            speed = ix.get("speed", 0)
            speed_str = f"{speed // 1000}G" if speed >= 1000 else f"{speed}M"
            status = ix.get("operational", True)
            status_str = '<span style="color:#146c2e;">●</span>' if status else '<span style="color:#ba1a1a;">●</span>'
            lines.append(f'<tr><td>{name}</td><td>{ip4}</td><td>{ip6}</td><td>{speed_str}</td><td>{status_str}</td></tr>')
        lines.append('</table>')

    # Facility list
    facs = data.get("peeringdb_facs", [])
    if facs:
        lines.append(f'<h4 style="color:#A56179;">Facilities ({len(facs)})</h4>')
        lines.append('<table cellpadding="3" style="color:#3d2914; font-size:12px;">')
        for f in facs[:30]:
            lines.append(f'<tr><td>{f.get("name","")}</td><td style="color:#5c3e2a;">{f.get("city","")}, {f.get("country","")}</td></tr>')
        lines.append('</table>')

    return "\n".join(lines)


def fmt_ripestat(data):
    """Format RIPEstat data as rich text."""
    lines = []
    ov = data.get("ripestat_overview", {})
    if ov:
        holder = ov.get("holder", "")
        block = ov.get("block", {})
        lines.append(f'<h3 style="color:#752d46;">📊 RIPEstat — AS{data.get("asn","")}</h3>')
        lines.append(f'<p><b>Holder:</b> {holder}</p>')
        if block:
            lines.append(f'<p><b>Block:</b> {block.get("resource","")} ({block.get("name","")}) — {block.get("desc","")}</p>')
        announced = ov.get("announced", False)
        color = "#146c2e" if announced else "#ba1a1a"
        lines.append(f'<p><b>Announced:</b> <span style="color:{color};">{"Yes" if announced else "No"}</span></p>')

    # Prefixes
    pfx_data = data.get("ripestat_prefixes", {})
    prefixes = pfx_data.get("prefixes", [])
    if prefixes:
        lines.append(f'<h4 style="color:#A56179;">Announced Prefixes ({len(prefixes)})</h4>')
        lines.append('<div style="font-size:12px; font-family:monospace; color:#3d2914;">')
        for p in prefixes[:100]:
            pfx = p.get("prefix", "")
            lines.append(f'  {pfx}<br>')
        if len(prefixes) > 100:
            lines.append(f'  <i style="color:#5c3e2a;">… and {len(prefixes)-100} more</i><br>')
        lines.append('</div>')

    # Neighbours
    nb_data = data.get("ripestat_neighbours", {})
    neighbours = nb_data.get("neighbours", [])
    if neighbours:
        ups = [n for n in neighbours if n.get("type") == "left"]
        downs = [n for n in neighbours if n.get("type") == "right"]
        if ups:
            lines.append(f'<h4 style="color:#A56179;">Upstreams ({len(ups)})</h4>')
            lines.append('<table cellpadding="2" style="color:#3d2914; font-size:12px;">')
            for n in ups[:20]:
                lines.append(f'<tr><td style="color:#A56179;">AS{n.get("asn","")}</td><td>{n.get("name","")}</td><td style="color:#5c3e2a;">power: {n.get("power","")}</td></tr>')
            lines.append('</table>')
        if downs:
            lines.append(f'<h4 style="color:#A56179;">Downstreams ({len(downs)})</h4>')
            lines.append('<table cellpadding="2" style="color:#3d2914; font-size:12px;">')
            for n in downs[:20]:
                lines.append(f'<tr><td style="color:#A56179;">AS{n.get("asn","")}</td><td>{n.get("name","")}</td></tr>')
            lines.append('</table>')

    if not lines:
        return '<p style="color:#5c3e2a;">No RIPEstat data available.</p>'
    return "\n".join(lines)


def fmt_rdap(data):
    """Format RDAP response as rich text."""
    rdap = data.get("rdap")
    if not rdap:
        err = data.get("rdap_error", "RDAP lookup failed")
        return f'<p style="color:#ba1a1a;">⚠ {err}</p>'

    lines = []
    lines.append(f'<h3 style="color:#752d46;">📋 RDAP / WHOIS</h3>')
    lines.append(f'<p><b>Handle:</b> {rdap.get("handle", "")}</p>')
    lines.append(f'<p><b>Name:</b> {rdap.get("name", "")}</p>')
    lines.append(f'<p><b>Type:</b> {rdap.get("type", "AUTNUM")}</p>')

    # Events (registration, last changed)
    events = rdap.get("events", [])
    if events:
        for ev in events:
            action = ev.get("eventAction", "")
            date = ev.get("eventDate", "")[:19]
            lines.append(f'<p style="color:#5c3e2a;">{action}: {date}</p>')

    # Entities (org, abuse, tech contacts)
    entities = rdap.get("entities", [])
    if entities:
        lines.append(f'<h4 style="color:#A56179;">Contacts</h4>')
        lines.append('<table cellpadding="3" style="color:#3d2914; font-size:12px;">')
        for ent in entities:
            handle = ent.get("handle", "")
            roles = ", ".join(ent.get("roles", []))
            # Try to extract name from vcard
            name = handle
            vcard = ent.get("vcardArray", [])
            if vcard and len(vcard) > 1:
                for field in vcard[1]:
                    if field[0] == "fn":
                        name = field[3] if len(field) > 3 else handle
                        break
            lines.append(f'<tr><td><b>{name}</b></td><td style="color:#5c3e2a;">{roles}</td><td>{handle}</td></tr>')
        lines.append('</table>')

    # Remarks
    remarks = rdap.get("remarks", [])
    for rem in remarks:
        title = rem.get("title", "")
        desc = "<br>".join(rem.get("description", []))
        if desc:
            lines.append(f'<p><b>{title}:</b><br><span style="color:#5c3e2a; font-size:12px;">{desc[:500]}</span></p>')

    return "\n".join(lines)


def fmt_ip_result(data):
    """Format IP lookup result."""
    lines = []
    ip = data.get("ip", "")
    lines.append(f'<h3 style="color:#752d46;">🔍 IP Lookup: {ip}</h3>')

    # Team Cymru
    cymru = data.get("cymru")
    if cymru:
        lines.append('<h4 style="color:#A56179;">Team Cymru</h4>')
        cymru_asn = cymru.get("asn", "")
        lines.append(f'<p><b>ASN:</b> {fmt_asn_inline(cymru_asn)} | '
                      f'<b>Prefix:</b> {cymru.get("prefix","")} | '
                      f'<b>CC:</b> {cymru.get("cc","")} | '
                      f'<b>RIR:</b> {cymru.get("rir","")}</p>')

    # RDAP
    rdap = data.get("rdap", {})
    if rdap:
        lines.append('<h4 style="color:#A56179;">RDAP</h4>')
        lines.append(f'<p><b>Name:</b> {rdap.get("name", "")} | <b>Handle:</b> {rdap.get("handle","")}</p>')
        cidr = rdap.get("cidr0_cidrs", [])
        if cidr:
            for c in cidr:
                lines.append(f'<p style="font-family:monospace;">{c.get("v4prefix","")}/{c.get("length","")}</p>')

    # RIPEstat
    pfx_info = data.get("ripestat_prefix", {})
    if pfx_info:
        lines.append(f'<p><b>Prefix:</b> {pfx_info.get("prefix","")} | <b>ASN(s):</b> {", ".join(str(a) for a in pfx_info.get("asns",[]))}</p>')

    abuse = data.get("ripestat_abuse", {})
    if abuse:
        contacts = abuse.get("abuse_contacts", [])
        if contacts:
            lines.append(f'<p><b>Abuse Contact:</b> {", ".join(contacts)}</p>')

    geoloc = data.get("ripestat_geoloc", {})
    located = geoloc.get("located_resources", [])
    if located:
        for loc in located[:3]:
            for l in loc.get("locations", []):
                lines.append(f'<p><b>Geo:</b> {l.get("city","")}, {l.get("country","")} ({l.get("latitude","")}, {l.get("longitude","")})</p>')

    # RPKI validation (if we derived a prefix + origin)
    rpki = data.get("rpki", {})
    derived_pfx = data.get("_derived_prefix", "")
    derived_asn = data.get("_derived_asn", "")
    if rpki:
        status = rpki.get("status", "unknown")
        if status == "valid":
            tag_style = 'background:#a7f2bb; color:#002106;'
            label = "✓ Valid"
        elif status == "invalid":
            tag_style = 'background:#ffdad6; color:#410002;'
            label = "✗ Invalid"
        elif status == "unknown":
            tag_style = 'background:#ffdbcc; color:#331200;'
            label = "? Not Found"
        else:
            tag_style = 'background:#f0e6d6; color:#3d2914;'
            label = status

        lines.append('<h4 style="color:#A56179;">RPKI Validation</h4>')
        lines.append(
            f'<p>Prefix {derived_pfx} / Origin AS{derived_asn}: '
            f'<span style="{tag_style} border-radius:2px; padding:2px 8px; '
            f'font-size:11px; font-weight:500;">{label}</span></p>'
        )
        roas = rpki.get("validating_roas", [])
        if roas:
            for roa in roas[:5]:
                roa_pfx = roa.get("prefix", "")
                roa_ml = roa.get("max_length", "")
                roa_origin = roa.get("origin", "")
                lines.append(
                    f'<p style="font-family:monospace; font-size:11px; color:#5c3e2a;">'
                    f'  ROA: {roa_pfx} max /{roa_ml} origin AS{roa_origin}</p>'
                )

    # Clickable link to full prefix lookup
    if derived_pfx:
        lines.append(
            f'<p style="margin-top:12px;">'
            f'<a href="action:prefix-lookup" style="color:#752d46; font-weight:500; '
            f'text-decoration:none; background:#f7f1e8; border:1px solid #d4b896; '
            f'border-radius:2px; padding:4px 12px;">'
            f'📡 Full Prefix Lookup: {derived_pfx} →</a></p>'
        )

    return "\n".join(lines)


def fmt_prefix_result(data):
    """Format prefix lookup result."""
    lines = []
    pfx = data.get("prefix", "")
    lines.append(f'<h3 style="color:#752d46;">📡 Prefix: {pfx}</h3>')

    # Routing status
    rs = data.get("routing_status", {})
    if rs:
        status = rs.get("announced", False)
        color = "#146c2e" if status else "#ba1a1a"
        lines.append(f'<p><b>Announced:</b> <span style="color:{color};">{"Yes" if status else "No"}</span></p>')
        origins = rs.get("origins", [])
        if origins:
            lines.append(f'<p><b>Origin AS:</b> {", ".join(fmt_asn_inline(o) for o in origins)}</p>')

    # Prefix overview
    po = data.get("prefix_overview", {})
    if po:
        asns = po.get("asns", [])
        if asns:
            lines.append('<h4 style="color:#A56179;">Origin ASNs</h4>')
            lines.append('<table cellpadding="3" style="color:#3d2914; font-size:12px;">')
            for a in asns:
                asn_num = a.get("asn", "")
                holder = a.get("holder", "")
                # Use PeeringDB name if we have it, else RIPEstat holder
                pdb_name = ASN_CACHE.get(str(asn_num))
                display = pdb_name or holder
                lines.append(f'<tr><td style="color:#A56179;">AS{asn_num}</td><td>{display}</td></tr>')
            lines.append('</table>')

    # Related prefixes
    rel = data.get("related", {})
    related_pfx = rel.get("prefixes", [])
    if related_pfx:
        lines.append(f'<h4 style="color:#A56179;">Related Prefixes ({len(related_pfx)})</h4>')
        lines.append('<table cellpadding="2" style="font-size:12px; font-family:monospace; color:#3d2914;">')
        for rp in related_pfx[:30]:
            p = rp.get("prefix", "")
            origin = rp.get("origin_asn", "")
            lines.append(f'<tr><td>{p}</td><td style="padding-left:12px;">{fmt_asn_inline(origin)}</td></tr>')
        lines.append('</table>')

    # Looking glass
    lg = data.get("looking_glass", {})
    rrcs = lg.get("rrcs", [])
    if rrcs:
        lines.append(f'<h4 style="color:#A56179;">Looking Glass ({len(rrcs)} RRCs)</h4>')
        lines.append('<table cellpadding="3" style="color:#3d2914; font-size:11px;">')
        lines.append('<tr style="color:#5c3e2a;"><td><b>RRC</b></td><td><b>Location</b></td><td><b>AS Path</b></td></tr>')
        for rrc in rrcs:
            rrc_name = rrc.get("rrc", "")
            loc = rrc.get("location", "")
            peers = rrc.get("peers", [])
            for peer in peers[:3]:
                as_path = peer.get("as_path", "")
                annotated = fmt_as_path(as_path)
                lines.append(
                    f'<tr><td style="color:#5c3e2a; white-space:nowrap;">{rrc_name}</td>'
                    f'<td style="white-space:nowrap;">{loc}</td>'
                    f'<td>{annotated}</td></tr>'
                )
        lines.append('</table>')

    # RPKI validation
    rpki_list = data.get("rpki", [])
    if rpki_list:
        lines.append('<h4 style="color:#A56179;">RPKI Validation</h4>')
        lines.append('<table cellpadding="4" style="color:#3d2914; font-size:12px;">')
        lines.append(
            '<tr style="color:#5c3e2a;">'
            '<td><b>Origin AS</b></td><td><b>Status</b></td>'
            '<td><b>ROAs</b></td></tr>'
        )
        for rv in rpki_list:
            asn = rv.get("_queried_asn", "?")
            status = rv.get("status", "unknown")
            # Colour-code the status
            if status == "valid":
                tag_style = 'background:#a7f2bb; color:#002106;'
                label = "✓ Valid"
            elif status == "invalid":
                tag_style = 'background:#ffdad6; color:#410002;'
                label = "✗ Invalid"
            elif status == "unknown":
                tag_style = 'background:#ffdbcc; color:#331200;'
                label = "? Not Found"
            else:
                tag_style = 'background:#f0e6d6; color:#3d2914;'
                label = status

            # Format validating ROAs
            roas = rv.get("validating_roas", [])
            roa_parts = []
            for roa in roas[:5]:
                roa_pfx = roa.get("prefix", "")
                roa_ml = roa.get("max_length", "")
                roa_origin = roa.get("origin", "")
                roa_validity = roa.get("validity", "")
                roa_parts.append(
                    f'{roa_pfx} max /{roa_ml} origin AS{roa_origin}'
                    f' <span style="font-size:10px; color:#5c3e2a;">({roa_validity})</span>'
                )
            roa_html = "<br>".join(roa_parts) if roa_parts else "—"

            lines.append(
                f'<tr>'
                f'<td>{fmt_asn_inline(asn)}</td>'
                f'<td><span style="{tag_style} border-radius:2px; padding:2px 8px; '
                f'font-size:11px; font-weight:500;">{label}</span></td>'
                f'<td style="font-family:monospace; font-size:11px;">{roa_html}</td>'
                f'</tr>'
            )
        lines.append('</table>')

    # IRR routing consistency
    irr = data.get("irr_consistency", {})
    irr_routes = irr.get("routes", [])
    if irr_routes:
        lines.append('<h4 style="color:#A56179;">IRR Route Objects</h4>')
        lines.append('<table cellpadding="4" style="color:#3d2914; font-size:12px;">')
        lines.append(
            '<tr style="color:#5c3e2a;">'
            '<td><b>Prefix</b></td><td><b>Origin</b></td>'
            '<td><b>IRR Sources</b></td><td><b>BGP Match</b></td></tr>'
        )
        for route in irr_routes:
            r_pfx = route.get("prefix", "")
            r_origin = route.get("origin", "")
            r_sources = route.get("irr_sources", "")
            if isinstance(r_sources, list):
                r_sources = ", ".join(r_sources)
            in_bgp = route.get("in_bgp", False)
            in_irr = route.get("in_irr", False)
            if in_bgp and in_irr:
                match_tag = '<span style="background:#a7f2bb; color:#002106; border-radius:2px; padding:2px 6px; font-size:11px;">BGP + IRR ✓</span>'
            elif in_bgp and not in_irr:
                match_tag = '<span style="background:#ffdad6; color:#410002; border-radius:2px; padding:2px 6px; font-size:11px;">BGP only — no IRR ✗</span>'
            elif in_irr and not in_bgp:
                match_tag = '<span style="background:#ffdbcc; color:#331200; border-radius:2px; padding:2px 6px; font-size:11px;">IRR only — not announced</span>'
            else:
                match_tag = '<span style="color:#5c3e2a;">—</span>'
            lines.append(
                f'<tr>'
                f'<td style="font-family:monospace;">{r_pfx}</td>'
                f'<td>{fmt_asn_inline(r_origin)}</td>'
                f'<td>{r_sources}</td>'
                f'<td>{match_tag}</td>'
                f'</tr>'
            )
        lines.append('</table>')
    elif "irr_consistency" in data:
        lines.append('<h4 style="color:#A56179;">IRR Route Objects</h4>')
        lines.append('<p style="color:#5c3e2a;">No route objects found for this prefix.</p>')

    return "\n".join(lines)


def _extract_asns_from_prefix(data):
    """Extract all unique ASN numbers from a prefix lookup result."""
    asns = set()

    # Origins from routing status
    rs = data.get("routing_status", {})
    for o in rs.get("origins", []):
        asns.add(str(o))

    # Origin ASNs from prefix overview
    po = data.get("prefix_overview", {})
    for a in po.get("asns", []):
        asns.add(str(a.get("asn", "")))

    # Related prefixes
    rel = data.get("related", {})
    for rp in rel.get("prefixes", []):
        asns.add(str(rp.get("origin_asn", "")))

    # AS paths from looking glass
    lg = data.get("looking_glass", {})
    for rrc in lg.get("rrcs", []):
        for peer in rrc.get("peers", []):
            path = peer.get("as_path", "")
            for hop in path.split():
                if hop.isdigit():
                    asns.add(hop)

    asns.discard("")
    return asns


# ─── Main Window ──────────────────────────────────────────────────────────────

class PeeringWorkbench(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("⚡ Peering Workbench")
        self.setMinimumSize(1280, 800)
        self._workers = []  # prevent GC

        self._build_ui()
        self.statusBar().showMessage(
            f"Ready — ASN cache: {ASN_CACHE.size} names"
        )

    # ── UI Construction ───────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(toolbar)

        logo = QLabel("  ⚡ Peering Workbench  ")
        logo.setStyleSheet("font-size: 16px; font-weight: bold; color: #752d46; padding: 4px;")
        toolbar.addWidget(logo)
        toolbar.addSeparator()

        # Quick-lookup bar in toolbar
        self._quick_input = QLineEdit()
        self._quick_input.setPlaceholderText("Quick lookup: ASN, IP, prefix, or hostname (e.g. 15169, 8.8.8.8, 2607:f8b0::1, 1.0.0.0/24, cloudflare.com)")
        self._quick_input.setMinimumWidth(400)
        self._quick_input.returnPressed.connect(self._quick_lookup)
        toolbar.addWidget(self._quick_input)

        self._quick_btn = QPushButton("Lookup")
        self._quick_btn.clicked.connect(self._quick_lookup)
        toolbar.addWidget(self._quick_btn)

        toolbar.addSeparator()

        pathviz_btn = QPushButton("🗺 AS-Path Viz")
        pathviz_btn.setToolTip("Visualise BGP AS-path between two IPs")
        pathviz_btn.clicked.connect(self._open_pathviz)
        toolbar.addWidget(pathviz_btn)

        # Spacer pushes help buttons to the right
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        help_btn = QPushButton("?")
        help_btn.setStyleSheet("padding: 4px 0px; font-size: 16px; min-width: 32px;")
        help_btn.setToolTip("Help")
        help_btn.clicked.connect(self._open_help)
        toolbar.addWidget(help_btn)

        # Main tabs
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        # Tab 0: ASN Lookup
        self._build_asn_tab()
        # Tab 1: IP Lookup
        self._build_ip_tab()
        # Tab 2: Prefix / Looking Glass
        self._build_prefix_tab()
        # Tab 3: DNS Lookup
        self._build_dns_tab()

        # Status bar
        self._progress = QProgressBar()
        self._progress.setMaximumWidth(200)
        self._progress.setMaximum(0)
        self._progress.setVisible(False)
        self.statusBar().addPermanentWidget(self._progress)

    def _build_asn_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Input
        input_row = QHBoxLayout()
        input_row.addWidget(QLabel("ASN:"))
        self._asn_input = QLineEdit()
        self._asn_input.setPlaceholderText("Enter ASN number (e.g. 15169)")
        self._asn_input.returnPressed.connect(self._do_asn_lookup)
        input_row.addWidget(self._asn_input)
        self._asn_btn = QPushButton("Lookup")
        self._asn_btn.clicked.connect(self._do_asn_lookup)
        input_row.addWidget(self._asn_btn)
        pdb_link = QPushButton("Open in PeeringDB ↗")
        pdb_link.clicked.connect(lambda: self._open_pdb(self._asn_input.text()))
        input_row.addWidget(pdb_link)
        he_link = QPushButton("Open in HE ↗")
        he_link.clicked.connect(lambda: self._open_he_asn(self._asn_input.text()))
        input_row.addWidget(he_link)
        layout.addLayout(input_row)

        # Results in sub-tabs
        self._asn_results = QTabWidget()
        self._asn_pdb_view = QTextEdit(); self._asn_pdb_view.setReadOnly(True)
        self._asn_ripe_view = QTextEdit(); self._asn_ripe_view.setReadOnly(True)
        self._asn_rdap_view = QTextEdit(); self._asn_rdap_view.setReadOnly(True)
        self._asn_raw_view = QTextEdit(); self._asn_raw_view.setReadOnly(True)

        self._asn_results.addTab(self._asn_pdb_view, "PeeringDB")
        self._asn_results.addTab(self._asn_ripe_view, "RIPEstat")
        self._asn_results.addTab(self._asn_rdap_view, "RDAP/WHOIS")
        self._asn_results.addTab(self._asn_raw_view, "Raw JSON")
        layout.addWidget(self._asn_results)

        self._tabs.addTab(tab, "🏷 ASN Lookup")

    def _build_ip_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        input_row = QHBoxLayout()
        input_row.addWidget(QLabel("IP:"))
        self._ip_input = QLineEdit()
        self._ip_input.setPlaceholderText("Enter IP address (e.g. 8.8.8.8 or 2607:f8b0:4001::1)")
        self._ip_input.returnPressed.connect(self._do_ip_lookup)
        input_row.addWidget(self._ip_input)
        self._ip_btn = QPushButton("Lookup")
        self._ip_btn.clicked.connect(self._do_ip_lookup)
        input_row.addWidget(self._ip_btn)
        layout.addLayout(input_row)

        self._ip_result_view = QTextBrowser()
        self._ip_result_view.setReadOnly(True)
        self._ip_result_view.setOpenLinks(False)
        self._ip_result_view.anchorClicked.connect(self._on_ip_link_clicked)
        layout.addWidget(self._ip_result_view)

        self._tabs.addTab(tab, "🌍 IP Lookup")

    def _build_prefix_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        input_row = QHBoxLayout()
        input_row.addWidget(QLabel("Prefix:"))
        self._pfx_input = QLineEdit()
        self._pfx_input.setPlaceholderText("Enter prefix (e.g. 1.0.0.0/24)")
        self._pfx_input.returnPressed.connect(self._do_prefix_lookup)
        input_row.addWidget(self._pfx_input)
        self._pfx_btn = QPushButton("Lookup")
        self._pfx_btn.clicked.connect(self._do_prefix_lookup)
        input_row.addWidget(self._pfx_btn)
        layout.addLayout(input_row)

        self._pfx_result_view = QTextEdit()
        self._pfx_result_view.setReadOnly(True)
        layout.addWidget(self._pfx_result_view)

        self._tabs.addTab(tab, "📡 Prefix / LG")

    def _build_dns_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        input_row = QHBoxLayout()
        input_row.addWidget(QLabel("Hostname / IP:"))
        self._dns_input = QLineEdit()
        self._dns_input.setPlaceholderText(
            "Enter hostname (e.g. cloudflare.com) or IP for reverse DNS"
        )
        self._dns_input.returnPressed.connect(self._do_dns_lookup)
        input_row.addWidget(self._dns_input)

        self._dns_type_combo = QComboBox()
        self._dns_type_combo.addItem("All Records")
        for rtype in DnsLookupWorker.RECORD_TYPES:
            self._dns_type_combo.addItem(rtype)
        self._dns_type_combo.setMinimumWidth(120)
        input_row.addWidget(self._dns_type_combo)

        self._dns_btn = QPushButton("Lookup")
        self._dns_btn.clicked.connect(self._do_dns_lookup)
        input_row.addWidget(self._dns_btn)
        layout.addLayout(input_row)

        self._dns_result_view = QTextEdit()
        self._dns_result_view.setReadOnly(True)
        layout.addWidget(self._dns_result_view)

        self._tabs.addTab(tab, "🔎 DNS Lookup")

    # ── DNS Actions ──────────────────────────────────────────────────────

    def _do_dns_lookup(self):
        hostname = self._dns_input.text().strip()
        if not hostname:
            return
        self._dns_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._dns_result_view.setHtml('<p style="color:#A56179;">Loading…</p>')

        selected = self._dns_type_combo.currentText()
        if selected == "All Records":
            record_types = None  # worker default — all types
        else:
            record_types = [selected]

        worker = DnsLookupWorker(hostname, record_types)
        worker.finished.connect(self._on_dns_result)
        worker.error.connect(
            lambda e: (
                self._dns_result_view.setHtml(
                    f'<p style="color:#ba1a1a;">Error: {e}</p>'
                ),
                self._dns_btn.setEnabled(True),
                self._progress.setVisible(False),
            )
        )
        worker.progress.connect(lambda msg: self.statusBar().showMessage(msg))
        self._workers.append(worker)
        worker.start()

    def _on_dns_result(self, data):
        self._dns_result_view.setHtml(fmt_dns_result(data))
        self._dns_btn.setEnabled(True)
        self._progress.setVisible(False)
        n_records = sum(
            len(v) for k, v in data.get("records", {}).items()
            if not k.startswith("_")
        )
        self.statusBar().showMessage(
            f"DNS lookup complete — {n_records} records for {data.get('hostname','')}"
        )

    # ── Actions ───────────────────────────────────────────────────────────

    def _open_pathviz(self):
        """Open the AS-Path Visualization window."""
        from .pathviz import PathVisualizationWindow
        win = PathVisualizationWindow(parent=self)
        win.setStyleSheet(STYLESHEET)
        win.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        win.show()

    def _open_help(self):
        """Open the Help dialog."""
        from .helpview import WorkbenchHelpDialog
        dlg = WorkbenchHelpDialog(parent=self)
        dlg.setStyleSheet(STYLESHEET)
        dlg.show()

    def _quick_lookup(self):
        text = self._quick_input.text().strip()
        if not text:
            return
        # Detect type
        if "/" in text:
            self._pfx_input.setText(text)
            self._tabs.setCurrentIndex(2)
            self._do_prefix_lookup()
        elif re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", text):
            self._ip_input.setText(text)
            self._tabs.setCurrentIndex(1)
            self._do_ip_lookup()
        elif ":" in text:
            # IPv6 address (bare, no prefix slash — that's caught above)
            self._ip_input.setText(text)
            self._tabs.setCurrentIndex(1)
            self._do_ip_lookup()
        else:
            asn = text.upper().replace("AS", "").strip()
            if asn.isdigit():
                self._asn_input.setText(asn)
                self._tabs.setCurrentIndex(0)
                self._do_asn_lookup()
            elif "." in text and not text[0].isdigit():
                # Looks like a domain name → DNS Lookup
                self._dns_input.setText(text)
                self._tabs.setCurrentIndex(3)
                self._do_dns_lookup()
            else:
                self.statusBar().showMessage(f"Could not determine type for: {text}")

    def _open_pdb(self, asn):
        asn = str(asn).strip().upper().replace("AS", "")
        if asn.isdigit():
            QDesktopServices.openUrl(QUrl(f"https://www.peeringdb.com/asn/{asn}"))

    def _open_he_asn(self, asn):
        """Open this ASN in HE BGP Toolkit in the default browser."""
        asn = str(asn).strip().upper().replace("AS", "")
        if asn.isdigit():
            QDesktopServices.openUrl(QUrl(f"https://bgp.he.net/AS{asn}"))

    # ── ASN Lookup ────────────────────────────────────────────────────────

    def _do_asn_lookup(self):
        asn = self._asn_input.text().strip().upper().replace("AS", "")
        if not asn.isdigit():
            self.statusBar().showMessage("Enter a valid ASN number")
            return

        self._asn_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._asn_pdb_view.setHtml('<p style="color:#A56179;">Loading…</p>')
        self._asn_ripe_view.setHtml('<p style="color:#A56179;">Loading…</p>')
        self._asn_rdap_view.setHtml('<p style="color:#A56179;">Loading…</p>')

        worker = AsnLookupWorker(asn)
        worker.finished.connect(self._on_asn_result)
        worker.error.connect(self._on_asn_error)
        worker.progress.connect(lambda msg: self.statusBar().showMessage(msg))
        self._workers.append(worker)
        worker.start()

    def _on_asn_result(self, data):
        self._asn_pdb_view.setHtml(fmt_peeringdb(data))
        self._asn_ripe_view.setHtml(fmt_ripestat(data))
        self._asn_rdap_view.setHtml(fmt_rdap(data))
        # Raw JSON (pretty)
        self._asn_raw_view.setPlainText(json.dumps(data, indent=2, default=str)[:50000])
        self._asn_btn.setEnabled(True)
        self._progress.setVisible(False)

        # Opportunistically cache the looked-up ASN name from PeeringDB
        pdb = data.get("peeringdb", {})
        asn = data.get("asn", "")
        if pdb and asn:
            name = pdb.get("name", "")
            if name and ASN_CACHE.get(str(asn)) is None:
                ASN_CACHE._names[str(asn)] = name
                ASN_CACHE._save()

        self.statusBar().showMessage(
            f"AS{asn} — lookup complete ({ASN_CACHE.size} ASNs cached)"
        )

    def _on_asn_error(self, err):
        self._asn_pdb_view.setHtml(f'<p style="color:#ba1a1a;">Error: {err}</p>')
        self._asn_btn.setEnabled(True)
        self._progress.setVisible(False)

    # ── IP Lookup ─────────────────────────────────────────────────────────

    def _do_ip_lookup(self):
        ip = self._ip_input.text().strip()
        if not ip:
            return
        self._ip_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._ip_result_view.setHtml('<p style="color:#A56179;">Loading…</p>')

        worker = IpLookupWorker(ip)
        worker.finished.connect(self._on_ip_result)
        worker.error.connect(lambda e: self._ip_result_view.setHtml(f'<p style="color:#ba1a1a;">Error: {e}</p>'))
        worker.progress.connect(lambda msg: self.statusBar().showMessage(msg))
        self._workers.append(worker)
        worker.start()

    def _on_ip_result(self, data):
        self._ip_result_view.setHtml(fmt_ip_result(data))
        self._ip_btn.setEnabled(True)
        self._progress.setVisible(False)
        self.statusBar().showMessage(f"IP {data.get('ip','')} lookup complete")

        # Store derived prefix for the "Full Prefix Lookup" link
        self._last_derived_prefix = data.get("_derived_prefix", "")

        # Resolve Cymru ASN name if unknown
        cymru = data.get("cymru", {})
        asn = cymru.get("asn", "")
        if asn and ASN_CACHE.get(str(asn)) is None:
            self._last_ip_data = data
            worker = AsnBatchWorker({str(asn)})
            worker.finished.connect(self._on_ip_asn_resolved)
            self._workers.append(worker)
            worker.start()

    def _on_ip_asn_resolved(self, count):
        data = getattr(self, "_last_ip_data", None)
        if data:
            self._ip_result_view.setHtml(fmt_ip_result(data))

    def _on_ip_link_clicked(self, url):
        """Handle clicks on links in the IP result view."""
        url_str = url.toString()
        if url_str == "action:prefix-lookup":
            pfx = getattr(self, "_last_derived_prefix", "")
            if pfx:
                self._pfx_input.setText(pfx)
                self._tabs.setCurrentIndex(2)
                self._do_prefix_lookup()
        else:
            # External link — open in browser
            QDesktopServices.openUrl(url)

    # ── Prefix Lookup ─────────────────────────────────────────────────────

    def _do_prefix_lookup(self):
        pfx = self._pfx_input.text().strip()
        if not pfx:
            return
        self._pfx_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._pfx_result_view.setHtml('<p style="color:#A56179;">Loading…</p>')

        worker = PrefixLookupWorker(pfx)
        worker.finished.connect(self._on_pfx_result)
        worker.error.connect(lambda e: self._pfx_result_view.setHtml(f'<p style="color:#ba1a1a;">Error: {e}</p>'))
        worker.progress.connect(lambda msg: self.statusBar().showMessage(msg))
        self._workers.append(worker)
        worker.start()

    def _on_pfx_result(self, data):
        # Render immediately with whatever names are already cached
        self._pfx_result_view.setHtml(fmt_prefix_result(data))
        self._pfx_btn.setEnabled(True)
        self._progress.setVisible(False)
        self.statusBar().showMessage(f"Prefix {data.get('prefix','')} lookup complete")

        # Extract all ASNs from result and batch-resolve unknowns
        asns = _extract_asns_from_prefix(data)
        unknown = {a for a in asns if ASN_CACHE.get(a) is None}
        if unknown:
            self._last_pfx_data = data
            self.statusBar().showMessage(
                f"Resolving {len(unknown)} ASN names…"
            )
            worker = AsnBatchWorker(unknown)
            worker.finished.connect(self._on_pfx_asn_resolved)
            worker.progress.connect(lambda msg: self.statusBar().showMessage(msg))
            self._workers.append(worker)
            worker.start()

    def _on_pfx_asn_resolved(self, count):
        """Re-render prefix view now that ASN names are cached."""
        data = getattr(self, "_last_pfx_data", None)
        if data:
            self._pfx_result_view.setHtml(fmt_prefix_result(data))
        self.statusBar().showMessage(
            f"Resolved {count} ASN names ({ASN_CACHE.size} cached)"
        )


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)

    # macOS specific
    if sys.platform == "darwin":
        app.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)

    window = PeeringWorkbench()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()