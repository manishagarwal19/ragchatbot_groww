"""Extract one document record per allowlisted Groww HTML dump."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from code.ingest.allowlist import ALLOWED_URLS, FUNDS, assert_allowed_url

# Do not persist PII (architecture Phase 1).
_PII_PATTERNS = (
    re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),  # PAN-like
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"\b(?:\+91[\s-]?)?[6-9]\d{9}\b"),
    re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"),  # Aadhaar-like
)

_NEXT_DATA_RE = re.compile(
    r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)

# Public scalar facts on the fund page JSON. Skip return series / holdings / opinion analysis.
_FACT_KEYS: Tuple[Tuple[str, str], ...] = (
    ("scheme_name", "Scheme name on page"),
    ("category", "Category"),
    ("sub_category", "Sub-category"),
    ("super_category", "Super category"),
    ("plan_type", "Plan type"),
    ("scheme_type", "Scheme type"),
    ("expense_ratio", "Expense ratio"),
    ("exit_load", "Exit load"),
    ("min_sip_investment", "Minimum SIP"),
    ("max_sip_investment", "Maximum SIP"),
    ("min_investment_amount", "Minimum lumpsum"),
    ("mini_additional_investment", "Minimum additional investment"),
    ("sip_allowed", "SIP allowed"),
    ("lumpsum_allowed", "Lumpsum allowed"),
    ("benchmark", "Benchmark"),
    ("benchmark_name", "Benchmark name"),
    ("nfo_risk", "Riskometer"),
    ("fund_manager", "Fund manager"),
    ("launch_date", "Launch date"),
    ("aum", "AUM"),
    ("stamp_duty", "Stamp duty"),
    ("description", "Description"),
)

_LINK_FIELD_KEYS = ("brochure_link", "scheme_info_link", "sid_url")
_FACTSHEET_HREF_HINTS = (
    "factsheet",
    "fact-sheet",
    "brochure",
    ".pdf",
    "/sid",
    "sid_",
    "kim",
    "sai",
    "scheme-info",
    "scheme_info",
)


class _VisibleTextParser(HTMLParser):
    _skip_tags = frozenset({"script", "style", "noscript", "svg"})

    def __init__(self) -> None:
        super().__init__()
        self._skip = 0
        self.parts: List[str] = []
        self.hrefs: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag in self._skip_tags:
            self._skip += 1
        href = dict(attrs).get("href")
        if tag == "a" and href:
            self.hrefs.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag in self._skip_tags and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        piece = data.strip()
        if piece:
            self.parts.append(piece)


def redact_pii(text: str) -> str:
    redacted = text
    for pattern in _PII_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def _parse_next_data(html: str) -> Optional[Dict[str, Any]]:
    match = _NEXT_DATA_RE.search(html)
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    page_props = (payload.get("props") or {}).get("pageProps") or {}
    mf = page_props.get("mfServerSideData")
    return mf if isinstance(mf, dict) else None


def _format_lock_in(value: Any) -> Optional[str]:
    if not isinstance(value, dict):
        return str(value) if value not in (None, "") else None
    years, months, days = value.get("years"), value.get("months"), value.get("days")
    if years is None and months is None and days is None:
        return "None stated on this page"
    parts = []
    if years not in (None, 0):
        parts.append(f"{years} year(s)")
    if months not in (None, 0):
        parts.append(f"{months} month(s)")
    if days not in (None, 0):
        parts.append(f"{days} day(s)")
    return ", ".join(parts) if parts else "None stated on this page"


def _format_category_info(info: Any) -> List[str]:
    if not isinstance(info, dict):
        return []
    lines: List[str] = []
    mapping = (
        ("category", "Category info: category"),
        ("sub_type", "Category info: sub-type"),
        ("category_helper_text", "Category helper"),
        ("definition", "Category definition"),
        ("description", "Category description"),
        ("tax_impact", "Tax impact (as stated on page)"),
    )
    for key, label in mapping:
        val = info.get(key)
        if val not in (None, ""):
            lines.append(f"{label}: {val}")
    return lines


def facts_text_from_mf(mf: Dict[str, Any]) -> str:
    lines: List[str] = ["Facts extracted from the fund page (__NEXT_DATA__):"]
    for key, label in _FACT_KEYS:
        val = mf.get(key)
        if val not in (None, ""):
            lines.append(f"{label}: {val}")
    lock_line = _format_lock_in(mf.get("lock_in"))
    if lock_line:
        lines.append(f"Lock-in: {lock_line}")
    risk = None
    stats = mf.get("return_stats")
    if isinstance(stats, list) and stats and isinstance(stats[0], dict):
        risk = stats[0].get("risk")
    if risk:
        lines.append(f"Risk (as stated on page): {risk}")
    lines.extend(_format_category_info(mf.get("category_info")))
    return "\n".join(lines)


def _normalize_link(href: str, page_url: str) -> Optional[str]:
    href = href.strip()
    if not href or href.startswith("#") or href.lower().startswith("javascript:"):
        return None
    absolute = urljoin(page_url, href)
    parsed = urlparse(absolute)
    if parsed.scheme not in ("http", "https"):
        return None
    return absolute


def _looks_like_factsheet(url: str) -> bool:
    lowered = url.lower()
    return any(hint in lowered for hint in _FACTSHEET_HREF_HINTS)


def factsheet_links_from_page(
    mf: Optional[Dict[str, Any]], hrefs: Iterable[str], page_url: str
) -> List[str]:
    """Links that appear on this page; never used as extra corpus URLs."""
    found: List[str] = []
    seen = set()

    def add(url: Optional[str]) -> None:
        if not url or url in seen:
            return
        # Other Groww HTML pages are out of corpus; keep PDFs / AMC docs only.
        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()
        if host.endswith("groww.in") and not _looks_like_factsheet(url):
            return
        seen.add(url)
        found.append(url)

    if mf:
        for key in _LINK_FIELD_KEYS:
            raw = mf.get(key)
            if isinstance(raw, str) and raw.startswith("http"):
                add(raw)

    for href in hrefs:
        absolute = _normalize_link(href, page_url)
        if absolute and _looks_like_factsheet(absolute):
            add(absolute)

    return found


def visible_text(html: str) -> Tuple[str, List[str]]:
    parser = _VisibleTextParser()
    parser.feed(html)
    parser.close()
    return "\n".join(parser.parts), parser.hrefs


def extract_document(html: str, fund_key: str, ingested_at: str) -> Dict[str, Any]:
    if fund_key not in FUNDS:
        raise ValueError(f"Unknown fund_key: {fund_key}")
    url = assert_allowed_url(FUNDS[fund_key]["url"])
    fund_name = FUNDS[fund_key]["fund_name"]

    visible, hrefs = visible_text(html)
    mf = _parse_next_data(html)
    facts = facts_text_from_mf(mf) if mf else ""
    links = factsheet_links_from_page(mf, hrefs, url)

    body_parts = [
        f"Fund: {fund_name}",
        f"Source URL: {url}",
        facts,
        "Visible page text:",
        visible,
    ]
    text = redact_pii("\n\n".join(part for part in body_parts if part).strip())
    if not text or len(text) < 80:
        raise ValueError(f"Extracted text too short for {fund_key}")
    if not mf and "expense" not in visible.lower():
        # Page payload missing and chrome-only text — treat as failed extract.
        raise ValueError(f"No fund payload in HTML for {fund_key}")

    return {
        "url": url,
        "fund_key": fund_key,
        "fund_name": fund_name,
        "text": text,
        "ingested_at": ingested_at,
        "factsheet_links": links,
    }
