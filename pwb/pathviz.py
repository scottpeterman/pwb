#!/usr/bin/env python3
"""
AS-Path Visualization — trace BGP-level paths between two IPs.

Data pipeline:
  1. Team Cymru / RIPEstat / RDAP → resolve both IPs to ASN + prefix
  2. RIPEstat looking-glass → forward AS paths to dest, reverse to source
  3. RIPEstat asn-neighbours → upstreams + power scores for both ASNs
  4. ASN name cache → human labels for every hop

The result is a directed graph laid out left (source) → right (destination).
Forward paths are drawn in burgundy (left→right), reverse paths in teal
(right→left) to expose BGP asymmetry. Edge thickness reflects the
power score from asn-neighbours when available, falling back to path count.
"""

import math, re, time
from collections import defaultdict

from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QRectF, QPointF, QLineF, QTimer,
)
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QFontMetrics,
    QPainterPath, QPainterPathStroker, QPolygonF, QLinearGradient, QWheelEvent,
)
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLineEdit, QPushButton, QLabel, QGraphicsScene, QGraphicsView,
    QGraphicsItem, QGraphicsRectItem, QGraphicsPathItem,
    QListWidget, QListWidgetItem, QGroupBox, QFormLayout,
    QStatusBar, QProgressBar, QSizePolicy, QToolBar,
    QGraphicsDropShadowEffect, QCheckBox, QTextBrowser, QDialog,
)

from .workbench import (
    cymru_ip_to_asn, ripestat_get, rdap_ip, pdb_get,
    ASN_CACHE, AsnBatchWorker, STYLESHEET,
)


# ─── Colours (matches workbench palette) ─────────────────────────────────────

C_PRIMARY    = QColor("#752d46")
C_SECONDARY  = QColor("#A56179")
C_BACKGROUND = QColor("#fefcf8")
C_SURFACE    = QColor("#ffffff")
C_ON_SURFACE = QColor("#3d2914")
C_OUTLINE    = QColor("#d4b896")
C_CONTAINER1 = QColor("#faf6f0")
C_CONTAINER2 = QColor("#f7f1e8")
C_CONTAINER3 = QColor("#f0e6d6")
C_SUCCESS    = QColor("#146c2e")
C_ERROR      = QColor("#ba1a1a")
C_WARNING    = QColor("#9c4a00")

C_EDGE_DIM      = QColor("#d4b896")
C_EDGE_FWD      = QColor("#752d46")   # burgundy — forward
C_EDGE_REV      = QColor("#2d6b5a")   # teal — reverse
C_EDGE_FWD_DIM  = QColor("#d4b8b8")   # muted burgundy
C_EDGE_REV_DIM  = QColor("#b8d4cc")   # muted teal
C_SRC_ACCENT    = QColor("#1a873a")
C_DST_ACCENT    = QColor("#752d46")

NODE_W = 160
NODE_H = 52
LAYER_GAP = 220
VERT_GAP = 72


# ─── Worker Thread ────────────────────────────────────────────────────────────

class PathTraceWorker(QThread):
    """Background thread: resolve IPs → build AS-path graph data."""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, src_ip, dst_ip):
        super().__init__()
        self.src_ip = src_ip.strip()
        self.dst_ip = dst_ip.strip()

    def run(self):
        result = {"src_ip": self.src_ip, "dst_ip": self.dst_ip}

        # ── Phase 1: Resolve IPs → ASN + prefix ─────────────────────────
        self.progress.emit("Resolving source IP…")
        src_info = self._resolve_ip(self.src_ip)
        if not src_info:
            self.error.emit(
                f"Could not resolve source IP {self.src_ip} to an ASN.\n"
                "Make sure it's a publicly-routable address."
            )
            return
        result["src_asn"] = src_info["asn"]
        result["src_prefix"] = src_info["prefix"]

        self.progress.emit("Resolving destination IP…")
        dst_info = self._resolve_ip(self.dst_ip)
        if not dst_info:
            self.error.emit(
                f"Could not resolve destination IP {self.dst_ip} to an ASN.\n"
                "Make sure it's a publicly-routable address."
            )
            return
        result["dst_asn"] = dst_info["asn"]
        result["dst_prefix"] = dst_info["prefix"]

        src_asn = result["src_asn"]
        dst_asn = result["dst_asn"]

        if src_asn == dst_asn:
            result["same_asn"] = True
            result["forward_paths"] = [[src_asn]]
            result["reverse_paths"] = []
            result["power_scores"] = {}
            self.finished.emit(result)
            return

        # ── Phase 2: Looking-glass paths (forward + reverse) ─────────────

        # 2a) Forward — paths toward destination prefix
        self.progress.emit(f"Fetching forward paths to {result['dst_prefix']}…")
        fwd_raw = self._fetch_lg_paths(result["dst_prefix"])
        result["fwd_raw_count"] = len(fwd_raw)

        # 2b) Reverse — paths toward source prefix
        self.progress.emit(f"Fetching reverse paths to {result['src_prefix']}…")
        rev_raw = self._fetch_lg_paths(result["src_prefix"])
        result["rev_raw_count"] = len(rev_raw)

        # ── Phase 3: Neighbours + power scores ───────────────────────────
        power_scores = {}  # (asn_a, asn_b) → power  (bidirectional key)

        self.progress.emit(f"Fetching neighbours for AS{src_asn}…")
        src_upstreams = set()
        try:
            nb = ripestat_get("asn-neighbours", {"resource": f"AS{src_asn}"})
            for n in nb.get("neighbours", []):
                nasn = str(n.get("asn", ""))
                power = n.get("power", 0)
                if n.get("type") == "left":
                    src_upstreams.add(nasn)
                # Store power in both directions for lookup
                if nasn and power:
                    power_scores[(src_asn, nasn)] = power
                    power_scores[(nasn, src_asn)] = power
        except Exception:
            pass
        result["src_upstreams"] = src_upstreams

        self.progress.emit(f"Fetching neighbours for AS{dst_asn}…")
        dst_upstreams = set()
        try:
            nb = ripestat_get("asn-neighbours", {"resource": f"AS{dst_asn}"})
            for n in nb.get("neighbours", []):
                nasn = str(n.get("asn", ""))
                power = n.get("power", 0)
                if n.get("type") == "left":
                    dst_upstreams.add(nasn)
                if nasn and power:
                    power_scores[(dst_asn, nasn)] = power
                    power_scores[(nasn, dst_asn)] = power
        except Exception:
            pass
        result["dst_upstreams"] = dst_upstreams
        result["power_scores"] = power_scores

        # ── Phase 4: Select & trim forward paths ─────────────────────────
        self.progress.emit("Analysing forward paths…")
        result["forward_paths"] = self._select_paths(
            fwd_raw, src_asn, dst_asn, src_upstreams,
        )
        result["fwd_path_type"] = (
            "direct" if any(src_asn in p for p in fwd_raw) else
            "inferred" if result["forward_paths"] else "none"
        )

        # ── Phase 4b: Select & trim reverse paths ────────────────────────
        self.progress.emit("Analysing reverse paths…")
        # Reverse: paths toward src_prefix. We look for dst_asn in these
        # paths and extract dst_asn → … → src_asn.
        rev_selected = self._select_paths(
            rev_raw, dst_asn, src_asn, dst_upstreams,
        )
        # These are in dst→…→src order, which is what we want for reverse
        result["reverse_paths"] = rev_selected
        result["rev_path_type"] = (
            "direct" if any(dst_asn in p for p in rev_raw) else
            "inferred" if rev_selected else "none"
        )

        # ── Phase 5: Batch-resolve ASN names ──────────────────────────────
        all_asns = set()
        for p in result["forward_paths"]:
            all_asns.update(p)
        for p in result["reverse_paths"]:
            all_asns.update(p)
        all_asns.discard("")

        unknown = {a for a in all_asns if ASN_CACHE.get(a) is None}
        if unknown:
            self.progress.emit(f"Resolving {len(unknown)} ASN names…")
            for i, asn in enumerate(unknown):
                ASN_CACHE.resolve(asn)
                if (i + 1) % 5 == 0:
                    self.progress.emit(f"Resolved {i+1}/{len(unknown)} ASNs…")
                if i < len(unknown) - 1:
                    time.sleep(0.15)

        self.progress.emit("Done.")
        self.finished.emit(result)

    # ── Helpers ───────────────────────────────────────────────────────────

    def _resolve_ip(self, ip):
        """
        Resolve an IP to {"asn": str, "prefix": str} using multiple sources.
        Tries Team Cymru first, then RIPEstat network-info, then RDAP.
        """
        asn = prefix = ""

        # 1) Team Cymru DNS (fastest)
        try:
            cymru = cymru_ip_to_asn(ip)
            if cymru:
                asn = cymru.get("asn", "").split()[0]
                prefix = cymru.get("prefix", "")
        except Exception:
            pass

        if asn and prefix:
            return {"asn": asn, "prefix": prefix}

        # 2) RIPEstat network-info
        self.progress.emit(f"Cymru failed for {ip}, trying RIPEstat…")
        try:
            net = ripestat_get("network-info", {"resource": ip})
            if net:
                prefix = net.get("prefix", "") or prefix
                asns = net.get("asns", [])
                if asns and not asn:
                    asn = str(asns[0])
        except Exception:
            pass

        if asn and prefix:
            return {"asn": asn, "prefix": prefix}

        # 3) RDAP (last resort)
        self.progress.emit(f"RIPEstat incomplete for {ip}, trying RDAP…")
        try:
            rdap = rdap_ip(ip)
            if rdap and not prefix:
                cidrs = rdap.get("cidr0_cidrs", [])
                if cidrs:
                    c = cidrs[0]
                    v4 = c.get("v4prefix", "")
                    v6 = c.get("v6prefix", "")
                    length = c.get("length", "")
                    if v4:
                        prefix = f"{v4}/{length}"
                    elif v6:
                        prefix = f"{v6}/{length}"
        except Exception:
            pass

        if asn:
            return {"asn": asn, "prefix": prefix or f"{ip}/32"}
        return None

    def _fetch_lg_paths(self, prefix):
        """Fetch looking-glass AS paths for a prefix, deduplicate prepends."""
        raw_paths = []
        try:
            lg = ripestat_get("looking-glass", {"resource": prefix})
            for rrc in lg.get("rrcs", []):
                for peer in rrc.get("peers", []):
                    path_str = peer.get("as_path", "").strip()
                    if path_str:
                        hops = path_str.split()
                        deduped = []
                        for h in hops:
                            if h.isdigit() and (not deduped or deduped[-1] != h):
                                deduped.append(h)
                        if deduped:
                            raw_paths.append(deduped)
        except Exception:
            pass
        return raw_paths

    def _select_paths(self, raw_paths, from_asn, to_asn, from_upstreams):
        """
        From raw LG paths, select and trim those connecting from_asn → to_asn.
        Returns deduplicated list of paths.
        """
        direct = []
        inferred = []

        for path in raw_paths:
            if from_asn in path:
                idx = path.index(from_asn)
                trimmed = path[idx:]
                if trimmed not in direct:
                    direct.append(trimmed)
            else:
                for i, hop in enumerate(path):
                    if hop in from_upstreams:
                        trimmed = [from_asn] + path[i:]
                        if trimmed not in inferred:
                            inferred.append(trimmed)
                        break

        selected = direct if direct else inferred
        if not selected:
            seen = set()
            fallback = []
            for path in raw_paths:
                key = tuple(path)
                if key not in seen:
                    seen.add(key)
                    fallback.append([from_asn] + path)
            fallback.sort(key=len)
            selected = fallback[:12]

        # Deduplicate
        unique = []
        seen_tuples = set()
        for p in selected:
            t = tuple(p)
            if t not in seen_tuples:
                seen_tuples.add(t)
                unique.append(p)
        return unique[:20]


# ─── Link Detail Worker ───────────────────────────────────────────────────────

class LinkDetailWorker(QThread):
    """Background thread: query PeeringDB for shared IXes and facilities."""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, asn_a, asn_b):
        super().__init__()
        self.asn_a = str(asn_a)
        self.asn_b = str(asn_b)

    def run(self):
        result = {"asn_a": self.asn_a, "asn_b": self.asn_b}

        # Fetch net objects to get net_id
        def _get_net_id(asn):
            try:
                nets = pdb_get("net", {"asn": asn})
                if nets:
                    return nets[0].get("id"), nets[0]
            except Exception:
                pass
            return None, None

        net_id_a, net_a = _get_net_id(self.asn_a)
        net_id_b, net_b = _get_net_id(self.asn_b)

        result["net_a"] = net_a
        result["net_b"] = net_b

        if not net_id_a or not net_id_b:
            result["error"] = "One or both ASNs not found in PeeringDB"
            self.finished.emit(result)
            return

        # Fetch IX connections
        try:
            ix_a = pdb_get("netixlan", {"net_id": net_id_a})
            ix_b = pdb_get("netixlan", {"net_id": net_id_b})
        except Exception as e:
            result["error"] = f"IX query failed: {e}"
            self.finished.emit(result)
            return

        # Find common IXes
        ix_ids_a = {ix.get("ix_id"): ix for ix in ix_a}
        ix_ids_b = {ix.get("ix_id"): ix for ix in ix_b}
        common_ix_ids = set(ix_ids_a.keys()) & set(ix_ids_b.keys())

        common_ixes = []
        for ix_id in common_ix_ids:
            a = ix_ids_a[ix_id]
            b = ix_ids_b[ix_id]
            common_ixes.append({
                "name": a.get("name", ""),
                "ix_id": ix_id,
                "a_ipv4": a.get("ipaddr4", ""),
                "a_ipv6": a.get("ipaddr6", ""),
                "a_speed": a.get("speed", 0),
                "b_ipv4": b.get("ipaddr4", ""),
                "b_ipv6": b.get("ipaddr6", ""),
                "b_speed": b.get("speed", 0),
            })
        common_ixes.sort(key=lambda x: x["name"])
        result["common_ixes"] = common_ixes
        result["ix_count_a"] = len(ix_a)
        result["ix_count_b"] = len(ix_b)

        # Fetch facility presence
        try:
            fac_a = pdb_get("netfac", {"net_id": net_id_a})
            fac_b = pdb_get("netfac", {"net_id": net_id_b})
        except Exception:
            fac_a, fac_b = [], []

        fac_ids_a = {f.get("fac_id"): f for f in fac_a}
        fac_ids_b = {f.get("fac_id"): f for f in fac_b}
        common_fac_ids = set(fac_ids_a.keys()) & set(fac_ids_b.keys())

        common_facs = []
        for fac_id in common_fac_ids:
            a = fac_ids_a[fac_id]
            common_facs.append({
                "name": a.get("name", ""),
                "city": a.get("city", ""),
                "country": a.get("country", ""),
            })
        common_facs.sort(key=lambda x: x["name"])
        result["common_facs"] = common_facs
        result["fac_count_a"] = len(fac_a)
        result["fac_count_b"] = len(fac_b)

        # Peering policy info
        for label, net in [("policy_a", net_a), ("policy_b", net_b)]:
            if net:
                result[label] = {
                    "general": net.get("policy_general", ""),
                    "url": net.get("policy_url", ""),
                    "email": net.get("policy_email", ""),
                }

        self.finished.emit(result)


# ─── Link Detail Dialog ───────────────────────────────────────────────────────

class LinkDetailDialog(QDialog):
    """Modal dialog showing PeeringDB overlap between two ASNs."""

    def __init__(self, edge_item, parent=None):
        super().__init__(parent)
        self.edge_item = edge_item
        self._worker = None

        asn_a = edge_item.src_node.asn
        asn_b = edge_item.dst_node.asn
        self.asn_a = asn_a
        self.asn_b = asn_b
        name_a = ASN_CACHE.get(asn_a) or ""
        name_b = ASN_CACHE.get(asn_b) or ""

        self.setWindowTitle(f"AS{asn_a} ↔ AS{asn_b}")
        self.setMinimumSize(520, 420)
        self.resize(560, 500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header
        header = QLabel(f"AS{asn_a} ↔ AS{asn_b}")
        header.setStyleSheet(
            "font-size:18px; font-weight:bold; color:#752d46;"
        )
        layout.addWidget(header)

        subtitle_parts = []
        if name_a:
            subtitle_parts.append(name_a)
        subtitle_parts.append("↔")
        if name_b:
            subtitle_parts.append(name_b)
        subtitle = QLabel(" ".join(subtitle_parts))
        subtitle.setStyleSheet("font-size:12px; color:#5c3e2a;")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # Immediate stats
        direction = "← Reverse" if edge_item.is_reverse else "→ Forward"
        power_str = f"Power: {edge_item.power}" if edge_item.power else "No power score"
        stats = QLabel(
            f"{direction}  ·  Paths: {edge_item.weight}  ·  "
            f"{power_str}  ·  Thickness: {edge_item.thickness:.1f}px"
        )
        stats.setStyleSheet(
            "font-size:11px; color:#3d2914; background:#f7f1e8;"
            "border-radius:3px; padding:6px 10px;"
        )
        layout.addWidget(stats)

        # Spinner
        self._spinner = QProgressBar()
        self._spinner.setMaximum(0)  # indeterminate
        self._spinner.setTextVisible(True)
        self._spinner.setFormat("Querying PeeringDB…")
        self._spinner.setStyleSheet(
            "QProgressBar { border: 1px solid #d4b896; border-radius: 2px;"
            "  text-align: center; background: #faf6f0; color: #5c3e2a;"
            "  height: 24px; }"
            "QProgressBar::chunk { background-color: #752d46; }"
        )
        layout.addWidget(self._spinner)

        # Results browser
        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        self._browser.setStyleSheet(
            "QTextBrowser { border: 1px solid #d4b896; border-radius: 3px;"
            "  padding: 8px; font-size: 12px; }"
        )
        self._browser.setVisible(False)
        layout.addWidget(self._browser)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.close)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        # Start the worker
        self._worker = LinkDetailWorker(asn_a, asn_b)
        self._worker.finished.connect(self._on_result)
        self._worker.start()

    def _on_result(self, data):
        self._spinner.setVisible(False)
        self._browser.setVisible(True)

        asn_a = data["asn_a"]
        asn_b = data["asn_b"]
        name_a = ASN_CACHE.get(asn_a) or asn_a
        name_b = ASN_CACHE.get(asn_b) or asn_b

        lines = []

        if data.get("error"):
            lines.append(
                f'<p style="color:#ba1a1a;">{data["error"]}</p>'
            )
            self._browser.setHtml("\n".join(lines))
            return

        # Peering policies
        lines.append('<table cellpadding="4" style="width:100%; font-size:12px;">')
        for label, key in [
            (f"AS{asn_a}", "policy_a"),
            (f"AS{asn_b}", "policy_b"),
        ]:
            pol = data.get(key, {})
            if pol and pol.get("general"):
                policy = pol["general"]
                color = (
                    "#146c2e" if policy == "Open" else
                    "#9c4a00" if policy == "Selective" else
                    "#ba1a1a" if policy in ("Restrictive", "No") else
                    "#3d2914"
                )
                url = pol.get("url", "")
                email = pol.get("email", "")
                extras = ""
                if url:
                    extras += (
                        f' · <a style="color:#A56179;" href="{url}">policy</a>'
                    )
                if email:
                    extras += (
                        f' · <a style="color:#A56179;" '
                        f'href="mailto:{email}">{email}</a>'
                    )
                lines.append(
                    f'<tr><td style="color:#5c3e2a;">{label}</td>'
                    f'<td><span style="color:{color}; font-weight:600;">'
                    f'{policy}</span>{extras}</td></tr>'
                )
        lines.append('</table>')

        # Common IXes
        common_ixes = data.get("common_ixes", [])
        ix_a = data.get("ix_count_a", 0)
        ix_b = data.get("ix_count_b", 0)

        lines.append('<hr style="border:none; border-top:1px solid #f0e6d6;">')

        if common_ixes:
            lines.append(
                f'<h4 style="color:#752d46; margin:6px 0 4px 0;">'
                f'Shared Internet Exchanges — {len(common_ixes)}'
                f'<span style="font-weight:normal; font-size:11px; color:#5c3e2a;">'
                f'  (AS{asn_a}: {ix_a} total · AS{asn_b}: {ix_b} total)'
                f'</span></h4>'
            )
            lines.append(
                '<table cellpadding="3" cellspacing="0" '
                'style="width:100%; font-size:11px; color:#3d2914; '
                'border-collapse:collapse;">'
                '<tr style="background:#f0e6d6; color:#5c3e2a;">'
                f'<td><b>Exchange</b></td>'
                f'<td style="text-align:right;"><b>AS{asn_a}</b></td>'
                f'<td style="text-align:right;"><b>AS{asn_b}</b></td>'
                '</tr>'
            )
            for i, ix in enumerate(common_ixes):
                sp_a = ix["a_speed"]
                sp_b = ix["b_speed"]
                sp_a_str = f"{sp_a // 1000}G" if sp_a >= 1000 else f"{sp_a}M"
                sp_b_str = f"{sp_b // 1000}G" if sp_b >= 1000 else f"{sp_b}M"
                bg = "#faf6f0" if i % 2 else "#ffffff"
                lines.append(
                    f'<tr style="background:{bg};">'
                    f'<td>{ix["name"]}</td>'
                    f'<td style="text-align:right; font-family:monospace;">'
                    f'{sp_a_str}</td>'
                    f'<td style="text-align:right; font-family:monospace;">'
                    f'{sp_b_str}</td></tr>'
                )
            lines.append('</table>')
        else:
            lines.append(
                f'<h4 style="color:#752d46; margin:6px 0 4px 0;">'
                f'Shared Internet Exchanges — None</h4>'
                f'<p style="font-size:11px; color:#5c3e2a;">'
                f'No common IXes. AS{asn_a} is at {ix_a} IXes, '
                f'AS{asn_b} is at {ix_b}.</p>'
            )

        # Common facilities
        common_facs = data.get("common_facs", [])
        fac_a = data.get("fac_count_a", 0)
        fac_b = data.get("fac_count_b", 0)

        lines.append('<hr style="border:none; border-top:1px solid #f0e6d6;">')

        if common_facs:
            lines.append(
                f'<h4 style="color:#752d46; margin:6px 0 4px 0;">'
                f'Shared Facilities — {len(common_facs)}'
                f'<span style="font-weight:normal; font-size:11px; color:#5c3e2a;">'
                f'  (AS{asn_a}: {fac_a} · AS{asn_b}: {fac_b})'
                f'</span></h4>'
            )
            lines.append(
                '<table cellpadding="3" cellspacing="0" '
                'style="width:100%; font-size:11px; color:#3d2914; '
                'border-collapse:collapse;">'
                '<tr style="background:#f0e6d6; color:#5c3e2a;">'
                '<td><b>Facility</b></td><td><b>Location</b></td></tr>'
            )
            for i, fac in enumerate(common_facs):
                loc = (
                    f'{fac["city"]}, {fac["country"]}' if fac["city"]
                    else fac["country"]
                )
                bg = "#faf6f0" if i % 2 else "#ffffff"
                lines.append(
                    f'<tr style="background:{bg};">'
                    f'<td>{fac["name"]}</td>'
                    f'<td style="color:#5c3e2a;">{loc}</td></tr>'
                )
            lines.append('</table>')
        else:
            lines.append(
                f'<h4 style="color:#752d46; margin:6px 0 4px 0;">'
                f'Shared Facilities — None</h4>'
                f'<p style="font-size:11px; color:#5c3e2a;">'
                f'No common facilities ({fac_a}/{fac_b}).</p>'
            )

        self._browser.setHtml("\n".join(lines))

        # Auto-resize to fit content if needed
        doc_height = self._browser.document().size().height()
        if doc_height > 300:
            self.resize(self.width(), min(int(doc_height + 200), 800))


# ─── Graph Building ───────────────────────────────────────────────────────────

def _power_to_thickness(power):
    """Map a power score (1–300+) to an edge thickness (1.5–7.0)."""
    if not power or power <= 0:
        return 1.5
    return min(1.5 + math.log2(max(power, 1)) * 0.7, 7.0)


def build_graph(forward_paths, reverse_paths, src_asn, dst_asn, power_scores=None):
    """
    Build a layered directed graph from forward and reverse AS paths.

    Returns:
        nodes:  dict  asn → {asn, name, layer, x, y, is_src, is_dst, path_count}
        fwd_edges: list [{src, dst, weight, power, thickness, path_indices}]
        rev_edges: list [{src, dst, weight, power, thickness, path_indices}]
        layers: dict layer_num → [asn, …]
    """
    power_scores = power_scores or {}
    rev_as_fwd = [list(reversed(rp)) for rp in reverse_paths]
    all_paths = forward_paths + rev_as_fwd

    if not all_paths:
        return {}, [], [], {}

    # ── Assign layers ────────────────────────────────────────────────────
    # Forward-path positions take priority so the left→right layout
    # reflects the natural src→dst direction. Reverse-only nodes get
    # their positions from the reversed reverse paths as fallback.
    fwd_positions = defaultdict(list)
    for path in forward_paths:
        for i, asn in enumerate(path):
            fwd_positions[asn].append(i)

    rev_positions = defaultdict(list)
    for path in rev_as_fwd:
        for i, asn in enumerate(path):
            rev_positions[asn].append(i)

    asn_layer = {}
    all_asns = set(fwd_positions.keys()) | set(rev_positions.keys())
    for asn in all_asns:
        positions = fwd_positions[asn] if fwd_positions[asn] else rev_positions[asn]
        asn_layer[asn] = round(sorted(positions)[len(positions) // 2])

    # Force endpoints
    if src_asn in asn_layer:
        asn_layer[src_asn] = 0
    max_layer = max(asn_layer.values()) if asn_layer else 0
    if dst_asn in asn_layer and dst_asn != src_asn:
        asn_layer[dst_asn] = max(max_layer, asn_layer[dst_asn])

    max_layer = max(asn_layer.values()) if asn_layer else 0

    # ── Build layer lists ────────────────────────────────────────────────
    layers = defaultdict(list)
    for asn, layer in asn_layer.items():
        layers[layer].append(asn)

    # ── Barycenter ordering ──────────────────────────────────────────────
    adj = defaultdict(set)
    for path in all_paths:
        for i in range(len(path) - 1):
            adj[path[i]].add(path[i + 1])
            adj[path[i + 1]].add(path[i])

    layer_pos = {}
    for layer_num in sorted(layers.keys()):
        for i, asn in enumerate(layers[layer_num]):
            layer_pos[asn] = i

    for _ in range(3):
        for layer_num in sorted(layers.keys()):
            bary = {}
            for asn in layers[layer_num]:
                neighbors = [
                    layer_pos[n] for n in adj[asn]
                    if n in layer_pos and asn_layer.get(n) != layer_num
                ]
                bary[asn] = (
                    sum(neighbors) / len(neighbors) if neighbors
                    else layer_pos.get(asn, 0)
                )
            layers[layer_num].sort(key=lambda a: bary.get(a, 0))
            for i, asn in enumerate(layers[layer_num]):
                layer_pos[asn] = i

    # ── Compute coordinates ──────────────────────────────────────────────
    nodes = {}
    for layer_num in sorted(layers.keys()):
        layer_asns = layers[layer_num]
        layer_height = len(layer_asns) * (NODE_H + VERT_GAP) - VERT_GAP
        start_y = -layer_height / 2
        for i, asn in enumerate(layer_asns):
            name = ASN_CACHE.get(asn) or ""
            x = layer_num * LAYER_GAP
            y = start_y + i * (NODE_H + VERT_GAP)
            path_count = len(fwd_positions.get(asn, [])) + len(rev_positions.get(asn, []))
            nodes[asn] = {
                "asn": asn, "name": name, "layer": layer_num,
                "x": x, "y": y,
                "is_src": asn == src_asn, "is_dst": asn == dst_asn,
                "path_count": path_count,
            }

    # ── Build edges ──────────────────────────────────────────────────────
    def _make_edges(paths):
        counter = defaultdict(lambda: {"weight": 0, "path_indices": []})
        for pi, path in enumerate(paths):
            for i in range(len(path) - 1):
                key = (path[i], path[i + 1])
                counter[key]["weight"] += 1
                counter[key]["path_indices"].append(pi)

        edges = []
        for (a, b), info in counter.items():
            power = power_scores.get((a, b), 0)
            thickness = (
                _power_to_thickness(power) if power
                else min(1.5 + info["weight"] * 0.6, 5.0)
            )
            edges.append({
                "src": a, "dst": b,
                "weight": info["weight"],
                "power": power,
                "thickness": thickness,
                "path_indices": info["path_indices"],
            })
        return edges

    fwd_edges = _make_edges(forward_paths)
    rev_edges = _make_edges(reverse_paths)

    return nodes, fwd_edges, rev_edges, dict(layers)


# ─── QGraphicsItems ───────────────────────────────────────────────────────────

class AsnNodeItem(QGraphicsRectItem):
    """Visual node for a single ASN in the graph."""

    def __init__(self, asn, name, is_src=False, is_dst=False, path_count=1):
        super().__init__(0, 0, NODE_W, NODE_H)
        self.asn = asn
        self.asn_name = name
        self.is_src = is_src
        self.is_dst = is_dst
        self.path_count = path_count
        self._highlighted = False

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)

        tip = f"AS{asn}"
        if name:
            tip += f"\n{name}"
        tip += f"\nAppears in {path_count} path{'s' if path_count != 1 else ''}"
        self.setToolTip(tip)

    @property
    def center(self):
        r = self.sceneBoundingRect()
        return QPointF(r.center().x(), r.center().y())

    @property
    def right_port(self):
        r = self.sceneBoundingRect()
        return QPointF(r.right(), r.center().y())

    @property
    def left_port(self):
        r = self.sceneBoundingRect()
        return QPointF(r.left(), r.center().y())

    def set_highlighted(self, on):
        self._highlighted = on
        self.update()

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()

        if self.is_src:
            bg = QColor("#e8f5eb")
            accent = C_SRC_ACCENT
        elif self.is_dst:
            bg = QColor("#f5e8ee")
            accent = C_DST_ACCENT
        else:
            bg = C_SURFACE if self._highlighted else C_CONTAINER1
            accent = C_SECONDARY if self._highlighted else C_OUTLINE

        painter.setPen(QPen(accent, 2.0))
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 6, 6)

        # Left accent bar for src/dst
        if self.is_src or self.is_dst:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(accent))
            painter.drawRoundedRect(
                QRectF(rect.x() + 1, rect.y() + 6, 4, rect.height() - 12),
                2, 2,
            )

        # ASN label
        font_asn = QFont("SF Mono", 11, QFont.Weight.Bold)
        painter.setFont(font_asn)
        painter.setPen(QPen(C_ON_SURFACE))
        painter.drawText(
            QRectF(rect.x() + 14, rect.y() + 6, rect.width() - 20, 22),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"AS{self.asn}",
        )

        # Name label
        if self.asn_name:
            font_name = QFont("Roboto", 9)
            painter.setFont(font_name)
            painter.setPen(QPen(C_SECONDARY))
            fm = QFontMetrics(font_name)
            elided = fm.elidedText(
                self.asn_name, Qt.TextElideMode.ElideRight, int(rect.width()) - 20
            )
            painter.drawText(
                QRectF(rect.x() + 14, rect.y() + 26, rect.width() - 20, 20),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                elided,
            )

    def hoverEnterEvent(self, event):
        self._highlighted = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._highlighted = False
        self.update()
        super().hoverLeaveEvent(event)


class PathEdgeItem(QGraphicsPathItem):
    """Curved edge between two ASN nodes with arrowhead."""

    def __init__(self, src_node, dst_node, weight=1, power=0,
                 thickness=1.5, path_indices=None, is_reverse=False):
        super().__init__()
        self.src_node = src_node
        self.dst_node = dst_node
        self.weight = weight
        self.power = power
        self.thickness = thickness
        self.path_indices = path_indices or []
        self.is_reverse = is_reverse
        self._highlighted = False

        self.setAcceptHoverEvents(True)
        direction = "←" if is_reverse else "→"
        tip = f"AS{src_node.asn} {direction} AS{dst_node.asn}"
        tip += f"\nPaths: {weight}"
        if power:
            tip += f" | Power: {power}"
        tip += f"\n{'Reverse' if is_reverse else 'Forward'}"
        self.setToolTip(tip)

        self._rebuild()

    def _rebuild(self):
        """Compute the bezier path and arrowhead."""
        if self.is_reverse:
            # Reverse: draw right → left
            # src_node is at a higher layer (right), dst_node at lower (left)
            # We draw from src's left port to dst's right port
            p1 = self.src_node.left_port
            p2 = self.dst_node.right_port
            # Offset vertically to separate from forward edges
            p1 = QPointF(p1.x(), p1.y() + 10)
            p2 = QPointF(p2.x(), p2.y() + 10)
            dx = abs(p1.x() - p2.x())
            cp_offset = max(dx * 0.4, 40)
            path = QPainterPath()
            path.moveTo(p1)
            path.cubicTo(
                QPointF(p1.x() - cp_offset, p1.y()),
                QPointF(p2.x() + cp_offset, p2.y()),
                p2,
            )
            # Arrowhead at destination (p2, which is on the left)
            arrow_size = 8
            line = QLineF(QPointF(p2.x() + cp_offset, p2.y()), p2)
        else:
            # Forward: draw left → right
            p1 = self.src_node.right_port
            p2 = self.dst_node.left_port
            dx = abs(p2.x() - p1.x())
            cp_offset = max(dx * 0.4, 40)
            path = QPainterPath()
            path.moveTo(p1)
            path.cubicTo(
                QPointF(p1.x() + cp_offset, p1.y()),
                QPointF(p2.x() - cp_offset, p2.y()),
                p2,
            )
            arrow_size = 8
            line = QLineF(QPointF(p2.x() - cp_offset, p2.y()), p2)

        # Arrowhead
        angle = math.atan2(-line.dy(), line.dx())
        a1 = QPointF(
            p2.x() - arrow_size * math.cos(angle - math.pi / 7),
            p2.y() + arrow_size * math.sin(angle - math.pi / 7),
        )
        a2 = QPointF(
            p2.x() - arrow_size * math.cos(angle + math.pi / 7),
            p2.y() + arrow_size * math.sin(angle + math.pi / 7),
        )
        path.moveTo(p2)
        path.lineTo(a1)
        path.moveTo(p2)
        path.lineTo(a2)

        self.setPath(path)
        self._apply_style()

    def set_highlighted(self, on):
        self._highlighted = on
        self._apply_style()
        self.update()

    def _apply_style(self):
        if self._highlighted:
            color = C_EDGE_REV if self.is_reverse else C_EDGE_FWD
            pen = QPen(color, self.thickness)
        else:
            color = C_EDGE_REV_DIM if self.is_reverse else C_EDGE_FWD_DIM
            pen = QPen(color, max(self.thickness * 0.6, 1.0))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.setPen(pen)

    def shape(self):
        """Widen the hit area so thin edges are easier to click."""
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self.thickness + 8, 12))
        return stroker.createStroke(self.path())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            scene = self.scene()
            if isinstance(scene, PathGraphScene):
                scene.edge_clicked.emit(self)
        super().mousePressEvent(event)


# ─── Scene ────────────────────────────────────────────────────────────────────

class PathGraphScene(QGraphicsScene):
    """Manages ASN nodes, forward edges, and reverse edges."""
    edge_clicked = pyqtSignal(object)  # emits PathEdgeItem

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBackgroundBrush(QBrush(C_BACKGROUND))
        self.node_items = {}
        self.fwd_edge_items = []
        self.rev_edge_items = []

    def build(self, nodes, fwd_edges, rev_edges):
        """Populate scene from graph data."""
        self.clear()
        self.node_items = {}
        self.fwd_edge_items = []
        self.rev_edge_items = []

        # Create nodes
        for asn, info in nodes.items():
            item = AsnNodeItem(
                asn=info["asn"], name=info["name"],
                is_src=info["is_src"], is_dst=info["is_dst"],
                path_count=info["path_count"],
            )
            item.setPos(info["x"], info["y"])
            self.addItem(item)
            self.node_items[asn] = item

        # Create forward edges
        for edge in fwd_edges:
            src_item = self.node_items.get(edge["src"])
            dst_item = self.node_items.get(edge["dst"])
            if src_item and dst_item:
                e = PathEdgeItem(
                    src_item, dst_item,
                    weight=edge["weight"], power=edge["power"],
                    thickness=edge["thickness"],
                    path_indices=edge["path_indices"],
                    is_reverse=False,
                )
                e.setZValue(-1)
                self.addItem(e)
                self.fwd_edge_items.append(e)

        # Create reverse edges
        for edge in rev_edges:
            # For reverse edges, src is at a higher layer, dst at lower
            src_item = self.node_items.get(edge["src"])
            dst_item = self.node_items.get(edge["dst"])
            if src_item and dst_item:
                e = PathEdgeItem(
                    src_item, dst_item,
                    weight=edge["weight"], power=edge["power"],
                    thickness=edge["thickness"],
                    path_indices=edge["path_indices"],
                    is_reverse=True,
                )
                e.setZValue(-2)  # behind forward edges
                self.addItem(e)
                self.rev_edge_items.append(e)

    @property
    def all_edges(self):
        return self.fwd_edge_items + self.rev_edge_items

    def highlight_path(self, path_index, is_reverse=False):
        """Highlight a single path (forward or reverse)."""
        # Dim everything
        for e in self.all_edges:
            e.set_highlighted(False)
        for n in self.node_items.values():
            n.set_highlighted(False)

        if path_index is None:
            # Show all
            for e in self.all_edges:
                e.set_highlighted(True)
            return

        edge_list = self.rev_edge_items if is_reverse else self.fwd_edge_items
        active_asns = set()
        for e in edge_list:
            if path_index in e.path_indices:
                e.set_highlighted(True)
                active_asns.add(e.src_node.asn)
                active_asns.add(e.dst_node.asn)

        for asn, node in self.node_items.items():
            if asn in active_asns:
                node.set_highlighted(True)

    def set_direction_visibility(self, show_fwd, show_rev):
        """Toggle visibility of forward / reverse edges."""
        for e in self.fwd_edge_items:
            e.setVisible(show_fwd)
        for e in self.rev_edge_items:
            e.setVisible(show_rev)


class PathGraphView(QGraphicsView):
    """Zoomable / pannable view for the path graph."""

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("border: none; background: #fefcf8;")
        self._zoom = 0

    def wheelEvent(self, event: QWheelEvent):
        factor = 1.15
        if event.angleDelta().y() > 0:
            if self._zoom < 10:
                self.scale(factor, factor)
                self._zoom += 1
        else:
            if self._zoom > -10:
                self.scale(1 / factor, 1 / factor)
                self._zoom -= 1

    def fit_all(self):
        self.fitInView(
            self.scene().itemsBoundingRect().adjusted(-40, -40, 40, 40),
            Qt.AspectRatioMode.KeepAspectRatio,
        )
        self._zoom = 0


# ─── Main Window ──────────────────────────────────────────────────────────────

class PathVisualizationWindow(QMainWindow):
    """Window for AS-path visualization between two IPs."""

    def __init__(self, parent=None, src_ip="", dst_ip=""):
        super().__init__(parent)
        self.setWindowTitle("🗺 AS-Path Visualization")
        self.setMinimumSize(1100, 700)
        self._workers = []
        self._result = None

        self._build_ui()

        if src_ip:
            self._src_input.setText(src_ip)
        if dst_ip:
            self._dst_input.setText(dst_ip)

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        toolbar = QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        logo = QLabel("  🗺 AS-Path Visualization  ")
        logo.setStyleSheet(
            "font-size:15px; font-weight:bold; color:#752d46; padding:4px;"
        )
        toolbar.addWidget(logo)
        toolbar.addSeparator()

        toolbar.addWidget(QLabel(" Source IP: "))
        self._src_input = QLineEdit()
        self._src_input.setPlaceholderText("e.g. 8.8.8.8")
        self._src_input.setMinimumWidth(160)
        self._src_input.returnPressed.connect(self._do_trace)
        toolbar.addWidget(self._src_input)

        toolbar.addWidget(QLabel("  →  Dest IP: "))
        self._dst_input = QLineEdit()
        self._dst_input.setPlaceholderText("e.g. 1.1.1.1")
        self._dst_input.setMinimumWidth(160)
        self._dst_input.returnPressed.connect(self._do_trace)
        toolbar.addWidget(self._dst_input)

        self._trace_btn = QPushButton("Trace Path")
        self._trace_btn.clicked.connect(self._do_trace)
        toolbar.addWidget(self._trace_btn)

        toolbar.addSeparator()

        fit_btn = QPushButton("Fit")
        fit_btn.setToolTip("Fit graph to view")
        fit_btn.clicked.connect(lambda: self._view.fit_all())
        toolbar.addWidget(fit_btn)

        zoom_in = QPushButton("+")
        zoom_in.setStyleSheet("padding: 4px 0px; font-size: 16px; min-width: 32px;")
        zoom_in.setFixedWidth(32)
        zoom_in.clicked.connect(lambda: self._view.scale(1.2, 1.2))
        toolbar.addWidget(zoom_in)

        zoom_out = QPushButton("−")
        zoom_out.setStyleSheet("padding: 4px 0px; font-size: 16px; min-width: 32px;")
        zoom_out.setFixedWidth(32)
        zoom_out.clicked.connect(lambda: self._view.scale(1/1.2, 1/1.2))
        toolbar.addWidget(zoom_out)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        help_btn = QPushButton("?")
        help_btn.setStyleSheet("padding: 4px 0px; font-size: 16px; min-width: 32px;")
        help_btn.setToolTip("Help")
        help_btn.clicked.connect(self._open_help)
        toolbar.addWidget(help_btn)

        # Main content: splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        # Left: graph view
        self._scene = PathGraphScene()
        self._scene.edge_clicked.connect(self._on_edge_clicked)
        self._view = PathGraphView(self._scene)
        splitter.addWidget(self._view)

        # Right: sidebar
        sidebar = QWidget()
        sidebar.setMaximumWidth(320)
        sidebar.setMinimumWidth(240)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(8, 8, 8, 8)

        # Summary
        summary_box = QGroupBox("Summary")
        summary_form = QFormLayout(summary_box)
        self._lbl_src = QLabel("—")
        self._lbl_dst = QLabel("—")
        self._lbl_fwd = QLabel("—")
        self._lbl_rev = QLabel("—")
        self._lbl_hops = QLabel("—")
        summary_form.addRow("Source:", self._lbl_src)
        summary_form.addRow("Destination:", self._lbl_dst)
        summary_form.addRow("Forward paths:", self._lbl_fwd)
        summary_form.addRow("Reverse paths:", self._lbl_rev)
        summary_form.addRow("Hop range:", self._lbl_hops)
        side_layout.addWidget(summary_box)

        # Visibility toggles
        vis_box = QGroupBox("Visibility")
        vis_layout = QVBoxLayout(vis_box)
        self._chk_fwd = QCheckBox("Forward paths (→)")
        self._chk_fwd.setChecked(True)
        self._chk_fwd.stateChanged.connect(self._on_visibility_changed)
        self._chk_rev = QCheckBox("Reverse paths (←)")
        self._chk_rev.setChecked(True)
        self._chk_rev.stateChanged.connect(self._on_visibility_changed)
        vis_layout.addWidget(self._chk_fwd)
        vis_layout.addWidget(self._chk_rev)
        side_layout.addWidget(vis_box)

        # Path list
        paths_box = QGroupBox("Discovered Paths")
        paths_layout = QVBoxLayout(paths_box)
        self._path_list = QListWidget()
        self._path_list.currentRowChanged.connect(self._on_path_selected)
        paths_layout.addWidget(self._path_list)

        show_all_btn = QPushButton("Show All Paths")
        show_all_btn.clicked.connect(lambda: (
            self._path_list.clearSelection(),
            self._scene.highlight_path(None),
        ))
        paths_layout.addWidget(show_all_btn)
        side_layout.addWidget(paths_box)

        # Legend
        legend_box = QGroupBox("Legend")
        legend_layout = QVBoxLayout(legend_box)
        for color, label in [
            ("#1a873a", "● Source ASN"),
            ("#752d46", "● Destination ASN"),
            ("#d4b896", "● Transit ASN"),
        ]:
            lbl = QLabel(
                f'<span style="color:{color}; font-size:16px;">●</span> {label}'
            )
            legend_layout.addWidget(lbl)

        legend_layout.addWidget(QLabel(
            '<span style="font-size:11px; color:#3d2914;">'
            '<b style="color:#752d46;">━━</b> Forward path (src → dst)<br>'
            '<b style="color:#2d6b5a;">━━</b> Reverse path (dst → src)</span>'
        ))
        legend_layout.addWidget(QLabel(
            '<span style="font-size:11px; color:#5c3e2a;">'
            'Edge thickness = power score (neighbour strength).<br>'
            'Click a path in the list to highlight it.</span>'
        ))
        side_layout.addWidget(legend_box)

        side_layout.addStretch()
        splitter.addWidget(sidebar)
        splitter.setSizes([800, 280])

        # Status bar
        self._progress = QProgressBar()
        self._progress.setMaximumWidth(200)
        self._progress.setMaximum(0)
        self._progress.setVisible(False)
        self.statusBar().addPermanentWidget(self._progress)

    # ── Actions ───────────────────────────────────────────────────────────

    def _do_trace(self):
        src = self._src_input.text().strip()
        dst = self._dst_input.text().strip()
        if not src or not dst:
            self.statusBar().showMessage("Enter both a source and destination IP.")
            return

        self._trace_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._path_list.clear()
        self._scene.clear()
        self._scene.node_items = {}
        self._scene.fwd_edge_items = []
        self._scene.rev_edge_items = []
        self.statusBar().showMessage("Tracing…")

        worker = PathTraceWorker(src, dst)
        worker.finished.connect(self._on_trace_result)
        worker.error.connect(self._on_trace_error)
        worker.progress.connect(lambda msg: self.statusBar().showMessage(msg))
        self._workers.append(worker)
        worker.start()

    def _on_trace_error(self, err):
        self._trace_btn.setEnabled(True)
        self._progress.setVisible(False)
        self.statusBar().showMessage(f"Error: {err}")
        for lbl in (self._lbl_src, self._lbl_dst, self._lbl_fwd,
                     self._lbl_rev, self._lbl_hops):
            lbl.setText("—")

    def _on_trace_result(self, data):
        self._trace_btn.setEnabled(True)
        self._progress.setVisible(False)
        self._result = data

        src_asn = data.get("src_asn", "?")
        dst_asn = data.get("dst_asn", "?")
        fwd_paths = data.get("forward_paths", [])
        rev_paths = data.get("reverse_paths", [])
        power_scores = data.get("power_scores", {})

        src_name = ASN_CACHE.get(src_asn) or ""
        dst_name = ASN_CACHE.get(dst_asn) or ""

        # Update summary
        self._lbl_src.setText(
            f"AS{src_asn} ({src_name})" if src_name else f"AS{src_asn}"
        )
        self._lbl_dst.setText(
            f"AS{dst_asn} ({dst_name})" if dst_name else f"AS{dst_asn}"
        )
        self._lbl_fwd.setText(
            f'{len(fwd_paths)} ({data.get("fwd_path_type", "—")})'
        )
        self._lbl_rev.setText(
            f'{len(rev_paths)} ({data.get("rev_path_type", "—")})'
        )

        all_p = fwd_paths + rev_paths
        if all_p:
            lengths = [len(p) for p in all_p]
            lo, hi = min(lengths), max(lengths)
            self._lbl_hops.setText(
                f"{lo} hop{'s' if lo != 1 else ''}"
                if lo == hi else f"{lo}–{hi} hops"
            )
        else:
            self._lbl_hops.setText("—")

        # Same-ASN case
        if data.get("same_asn"):
            self.statusBar().showMessage(
                f"Source and destination are both in AS{src_asn}."
            )
            nodes = {
                src_asn: {
                    "asn": src_asn, "name": src_name, "layer": 0,
                    "x": 0, "y": 0, "is_src": True, "is_dst": True,
                    "path_count": 1,
                },
            }
            self._scene.build(nodes, [], [])
            self._view.fit_all()
            return

        # Build and render graph
        nodes, fwd_edges, rev_edges, layers = build_graph(
            fwd_paths, rev_paths, src_asn, dst_asn, power_scores,
        )
        self._scene.build(nodes, fwd_edges, rev_edges)

        # Populate path list
        self._path_list.clear()
        for i, path in enumerate(fwd_paths):
            label = self._fmt_path_label(path)
            item = QListWidgetItem(f"→ Fwd {i+1}: {label}")
            item.setForeground(QColor("#752d46"))
            item.setData(Qt.ItemDataRole.UserRole, ("fwd", i))
            self._path_list.addItem(item)

        for i, path in enumerate(rev_paths):
            label = self._fmt_path_label(path)
            item = QListWidgetItem(f"← Rev {i+1}: {label}")
            item.setForeground(QColor("#2d6b5a"))
            item.setData(Qt.ItemDataRole.UserRole, ("rev", i))
            self._path_list.addItem(item)

        # Highlight all
        self._scene.highlight_path(None)

        QTimer.singleShot(100, self._view.fit_all)

        n_power = sum(1 for e in fwd_edges + rev_edges if e["power"])
        self.statusBar().showMessage(
            f"AS{src_asn} → AS{dst_asn}: "
            f"{len(fwd_paths)} forward, {len(rev_paths)} reverse paths "
            f"({n_power} edges with power scores)"
        )

    def _fmt_path_label(self, path):
        parts = []
        for asn in path:
            name = ASN_CACHE.get(asn)
            short = name[:12] + "…" if name and len(name) > 12 else (name or "")
            parts.append(f"{asn}" + (f" ({short})" if short else ""))
        return " → ".join(parts)

    def _on_path_selected(self, row):
        if row < 0:
            return
        item = self._path_list.item(row)
        if item:
            direction, idx = item.data(Qt.ItemDataRole.UserRole)
            self._scene.highlight_path(idx, is_reverse=(direction == "rev"))

    def _on_visibility_changed(self):
        self._scene.set_direction_visibility(
            self._chk_fwd.isChecked(),
            self._chk_rev.isChecked(),
        )

    # ── Edge click → Link Details ─────────────────────────────────────────

    def _open_help(self):
        """Open the Path Viz help dialog."""
        from .helpview import PathVizHelpDialog, STYLESHEET as _
        dlg = PathVizHelpDialog(parent=self)
        dlg.show()

    def _on_edge_clicked(self, edge_item):
        """Open a detail dialog for the clicked edge."""
        dlg = LinkDetailDialog(edge_item, parent=self)
        dlg.setStyleSheet(STYLESHEET)
        dlg.show()