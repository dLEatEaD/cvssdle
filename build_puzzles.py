#!/usr/bin/env python3
"""Build puzzles.json for CVSSdle from the NVD API (KEV-listed CVEs only).

Usage:  python3 build_puzzles.py [--api-key KEY]

No API key is required, but one raises the NVD rate limit from
5 requests / 30s to 50 requests / 30s. Get one free at:
https://nvd.nist.gov/developers/request-an-api-key
"""

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

NVD = "https://services.nvd.nist.gov/rest/json/cves/2.0"
KEV = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
PAGE = 2000
OUT = Path(__file__).parent / "puzzles.json"

# Shapes enforced on fields that the game interpolates into innerHTML.
CVE_RE = re.compile(r"CVE-\d{4}-\d{4,7}")
VECTOR_RE = re.compile(r"CVSS:3\.[01]/[A-Za-z:/]+")
VALID_SEVERITIES = {"Critical", "High", "Medium", "Low", "None"}

# Desktop, mobile and server operating systems are excluded: they dominate KEV
# (313 of 1233 entries, 139 of them just "Microsoft Windows") and the records
# are repetitive, which makes for a monotonous game. Network and security
# appliance firmware that happens to be named an OS - Cisco IOS, PAN-OS,
# FortiOS, Junos - is deliberately kept, since those are the interesting ones.
OS_VENDORS = {"Apple", "Android", "Samsung"}
OS_PRODUCTS = {
    ("Microsoft", "Windows"),
    ("Microsoft", "Win32k"),
    ("Microsoft", "Windows Kernel"),
}


def is_operating_system(vendor: str, product: str) -> bool:
    if vendor in OS_VENDORS:
        return True
    if (vendor, product) in OS_PRODUCTS:
        return True
    if vendor == "Microsoft" and product.startswith("Windows"):
        return True
    if vendor == "Linux" and "kernel" in product.lower():
        return True
    if vendor == "Google" and "android" in product.lower():
        return True
    return False

# Only keep vulns from vendors a security team will actually recognize.
KNOWN_VENDORS = {
    "Microsoft", "Apache", "Cisco", "Citrix", "Fortinet", "VMware", "Oracle",
    "Adobe", "Google", "Apple", "Atlassian", "Ivanti", "Progress", "Zoho",
    "SolarWinds", "F5", "Palo Alto Networks", "PaperCut", "MOVEit",
    "Zimbra", "Confluence", "Pulse Secure", "Sophos", "Zyxel", "SonicWall",
    "Linux", "Samba", "Mozilla", "PHP", "WordPress", "Jenkins", "Docker",
    "GitLab", "Veeam", "Barracuda Networks", "Check Point", "Juniper",
    "Trend Micro", "Qualcomm", "Samsung", "Android", "Roundcube", "Chamilo",
    "ownCloud", "CrushFTP", "ScreenConnect", "ConnectWise", "Array Networks",
    "Netgear", "D-Link", "TP-Link", "QNAP", "Synology", "Elasticsearch",
    "Splunk", "Nagios", "Grafana", "Kubernetes", "OpenSSL", "Red Hat",
    "IBM", "SAP", "Dell", "HP", "Hewlett Packard Enterprise", "Broadcom",
}


def fetch(url: str, key: str | None, tries: int = 5) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "cvssdle-builder"})
    if key:
        req.add_header("apiKey", key)
    delay = 6 if key else 20
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode())
        except Exception as exc:  # noqa: BLE001 - NVD throttles aggressively
            if attempt == tries - 1:
                raise
            wait = delay * (attempt + 1)
            print(f"  retry in {wait}s ({exc})")
            time.sleep(wait)
    raise RuntimeError("unreachable")


def clean(text: str) -> str:
    """Trim NVD descriptions to one readable sentence or two."""
    text = re.sub(r"\s+", " ", text).strip()
    # Drop the trailing "This issue affects..." / advisory boilerplate.
    text = re.split(r"\s+(?:This issue affects|Supported versions that)", text)[0]
    if len(text) > 340:
        cut = text[:340].rsplit(". ", 1)[0]
        text = (cut + ".") if len(cut) > 120 else text[:337].rstrip() + "..."
    return text


def redact(text: str, cve_id: str) -> str:
    """Remove giveaways: the CVE id and explicit severity words."""
    text = re.sub(r"CVE-\d{4}-\d{4,7}", "this vulnerability", text)
    text = re.sub(
        r"\b(critical|high|medium|low)[- ]severity\b", "a", text, flags=re.I
    )
    return text


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--limit", type=int, default=0,
                    help="max puzzles to keep (0 = no cap, use everything eligible)")
    args = ap.parse_args()

    print("Fetching CISA KEV catalog...")
    kev = fetch(KEV, None)
    kev_meta = {v["cveID"]: v for v in kev["vulnerabilities"]}
    print(f"  {len(kev_meta)} KEV entries (catalog {kev['catalogVersion']})")

    print("Fetching KEV CVEs from NVD (this takes a minute)...")
    records, start = [], 0
    while True:
        qs = urllib.parse.urlencode(
            {"hasKev": "", "resultsPerPage": PAGE, "startIndex": start}
        ).replace("hasKev=", "hasKev")
        data = fetch(f"{NVD}?{qs}", args.api_key)
        batch = data.get("vulnerabilities", [])
        records.extend(batch)
        total = data.get("totalResults", 0)
        start += PAGE
        print(f"  {len(records)}/{total}")
        if start >= total or not batch:
            break
        time.sleep(6 if args.api_key else 20)

    puzzles = []
    for item in records:
        cve = item["cve"]
        cid = cve["id"]
        metrics = cve.get("metrics", {}).get("cvssMetricV31") or []
        primary = next(
            (m for m in metrics if m.get("type") == "Primary"), metrics[0] if metrics else None
        )
        if not primary:
            continue
        cvss = primary["cvssData"]
        meta = kev_meta.get(cid)
        if not meta or meta["vendorProject"] not in KNOWN_VENDORS:
            continue
        if is_operating_system(meta["vendorProject"], meta["product"]):
            continue
        desc = next(
            (d["value"] for d in cve.get("descriptions", []) if d["lang"] == "en"), ""
        )
        if len(desc) < 60:
            continue

        # The renderer interpolates id, vector and severity into innerHTML
        # (including an href), so enforce their shape here rather than trusting
        # upstream. Anything unexpected is dropped instead of shipped.
        severity = cvss["baseSeverity"].title()
        vector = cvss["vectorString"]
        if not CVE_RE.fullmatch(cid):
            continue
        if not VECTOR_RE.fullmatch(vector):
            continue
        if severity not in VALID_SEVERITIES:
            continue

        puzzles.append(
            {
                "id": cid,
                "vendor": meta["vendorProject"],
                "product": meta["product"],
                "name": meta["vulnerabilityName"],
                "desc": redact(clean(desc), cid),
                "score": round(float(cvss["baseScore"]), 1),
                "severity": severity,
                "vector": vector,
                "published": cve.get("published", "")[:10],
                "ransomware": meta.get("knownRansomwareCampaignUse") == "Known",
                "url": f"https://nvd.nist.gov/vuln/detail/{cid}",
            }
        )

    # Spread the answer scores out so the game isn't all 9.8s.
    by_score: dict[float, list] = {}
    for p in puzzles:
        by_score.setdefault(p["score"], []).append(p)
    for group in by_score.values():
        group.sort(key=lambda p: p["published"], reverse=True)

    # Interleave across score bands so the pool isn't front-loaded with 9.8s.
    # This ordering is what split_pool.py relies on to keep both pools balanced.
    cap = args.limit or len(puzzles)
    balanced, round_robin = [], True
    while round_robin and len(balanced) < cap:
        round_robin = False
        for score in sorted(by_score, reverse=True):
            if by_score[score]:
                balanced.append(by_score[score].pop(0))
                round_robin = True
            if len(balanced) >= cap:
                break

    OUT.write_text(json.dumps(balanced, indent=1))
    dist: dict[str, int] = {}
    for p in balanced:
        dist[p["severity"]] = dist.get(p["severity"], 0) + 1
    print(f"\nWrote {len(balanced)} puzzles to {OUT.name}")
    print("Severity mix:", dist)
    print("Unique scores:", len({p['score'] for p in balanced}))
    print(f"Enough for {len(balanced) / 365:.1f} years of dailies.")


if __name__ == "__main__":
    main()
