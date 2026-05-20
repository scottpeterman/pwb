"""
pwb — Peering Workbench

Consolidated ASN / WHOIS / PeeringDB / Looking Glass desktop tool
for network engineers. Built with PyQt6 + WebEngine.

Usage:
    python -m pwb          # launch the GUI
    peering-workbench      # if installed via pip

APIs used (all free, no keys required):
    • PeeringDB   — https://www.peeringdb.com/api/
    • RIPEstat    — https://stat.ripe.net/data/
    • RDAP        — https://rdap.org/ (auto-routes to ARIN/RIPE/APNIC)
    • Team Cymru  — DNS-based IP→ASN mapping (requires dnspython)
    • HE BGP      — Embedded bgp.he.net via WebEngine
"""

__version__ = "0.2.0"
__author__ = "speterman"

from .workbench import main

__all__ = ["main", "__version__"]