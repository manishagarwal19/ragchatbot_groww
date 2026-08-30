"""Split one Phase 1 document into per-URL retrieval chunks (architecture Phase 2)."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from code.ingest.allowlist import FUNDS, assert_allowed_url

# Retrieval units the architecture calls out by name.
_TOPIC_SPECS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (
        "identity",
        (
            "Scheme name on page:",
            "Category:",
            "Sub-category:",
            "Super category:",
            "Plan type:",
            "Scheme type:",
            "Description:",
            "Fund manager:",
            "Launch date:",
            "AUM:",
        ),
    ),
    ("expense", ("Expense ratio:",)),
    ("exit_load", ("Exit load:", "Stamp duty:")),
    (
        "sip",
        (
            "Minimum SIP:",
            "Maximum SIP:",
            "Minimum lumpsum:",
            "Minimum additional investment:",
            "SIP allowed:",
            "Lumpsum allowed:",
        ),
    ),
    ("lock_in", ("Lock-in:",)),
    ("riskometer", ("Riskometer:", "Risk (as stated on page):")),
    ("benchmark", ("Benchmark:", "Benchmark name:")),
    (
        "tax",
        (
            "Tax impact",
            "Category info:",
            "Category helper:",
            "Category definition:",
            "Category description:",
        ),
    ),
)

_FACTS_HEADER = re.compile(r"Facts extracted from the fund page[^\n]*")
_VISIBLE_HEADER = "Visible page text:"

# Site chrome / other-product lists — not fund facts.
_BOILERPLATE_LINE = re.compile(
    r"(?i)^(stocks|intraday|ipo|mtfs?|f&o|etf screener|demat account|"
    r"share market|indices|terminal|option chain|pledge|commodities|"
    r"api trading|nfo.?s?|blog|credit|pricing|contact us|"
    r"download the app|groww|products|mutual funds screener|"
    r"sip calculator|brokerage calculator|margin calculator|"
    r"compare similar funds|top gainers|top losers|most traded|"
    r"see all|understand terms|return calculator|monthly sip|"
    r"one time|over the past|would've become|historic returns|"
    r"home|version:|© )",
)

_HOLDINGS_BLOCK = re.compile(
    r"Holdings\s*\(\s*\d+\s*\).*?(?=Minimum investments|Understand terms|About\s|$)",
    re.DOTALL | re.IGNORECASE,
)
_FOOTER_CUT = re.compile(
    r"(Vaishnavi Tech Park|Download the App\nGROWW|© 2016-)",
    re.IGNORECASE,
)
_CAPITAL_GAINS = re.compile(
    r"capital[\s-]?gains?(?:\s+statement)?",
    re.IGNORECASE,
)

_MIN_BODY_CHARS = 24
_VISIBLE_WINDOW = 900
_VISIBLE_OVERLAP = 120


def _header(fund_name: str, url: str) -> str:
    return f"Fund: {fund_name}\nSource URL: {url}"


def _split_facts_and_visible(text: str) -> Tuple[str, str]:
    visible = ""
    facts = text
    if _VISIBLE_HEADER in text:
        facts, visible = text.split(_VISIBLE_HEADER, 1)
    facts = _FACTS_HEADER.sub("", facts, count=1)
    facts = facts.lstrip(":\n ")
    return facts.strip(), visible.strip()


def _fact_lines(facts_block: str) -> List[str]:
    lines = [ln.strip() for ln in facts_block.splitlines() if ln.strip()]
    return [ln for ln in lines if ln.lower() not in {"fund:", "source url:"}]


def _lines_for_prefixes(lines: Sequence[str], prefixes: Sequence[str]) -> List[str]:
    matched: List[str] = []
    for line in lines:
        if any(line.startswith(p) for p in prefixes):
            matched.append(line)
    return matched


def _content_start(lines: Sequence[str], hero: str) -> int:
    """First line of the fund content, skipping the site-nav / title block."""
    hero_lower = hero.lower()
    for i, line in enumerate(lines):
        if line.strip().lower() == hero_lower:
            return i
    for i, line in enumerate(lines):
        lowered = line.lower()
        if hero_lower in lowered and "mutual fund performance" not in lowered:
            return i
    return 0


def _strip_visible_chrome(visible: str, hero: str) -> str:
    if not visible:
        return ""
    lines = visible.splitlines()
    body = "\n".join(lines[_content_start(lines, hero):])
    foot = _FOOTER_CUT.search(body)
    if foot:
        body = body[: foot.start()]
    body = _HOLDINGS_BLOCK.sub("\n", body)
    kept: List[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line or _BOILERPLATE_LINE.match(line):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def _is_boilerplate_chunk(body: str, fund_name: str) -> bool:
    compact = " ".join(body.split())
    if len(compact) < _MIN_BODY_CHARS:
        return True
    # Chrome-only: no fund name and no FAQ terms.
    lowered = compact.lower()
    faq_hits = (
        "expense",
        "sip",
        "exit load",
        "lock-in",
        "lock in",
        "riskometer",
        "benchmark",
        "capital gain",
        "factsheet",
        "minimum",
        "lumpsum",
        "stamp duty",
    )
    if fund_name.lower() not in lowered and not any(t in lowered for t in faq_hits):
        return True
    return False


def _windows(text: str, size: int, overlap: int) -> List[str]:
    if not text:
        return []
    if len(text) <= size:
        return [text]
    step = max(size - overlap, 1)
    out: List[str] = []
    i = 0
    while i < len(text):
        out.append(text[i : i + size].strip())
        if i + size >= len(text):
            break
        i += step
    return [w for w in out if w]


def _record(
    fund_key: str,
    fund_name: str,
    url: str,
    ingested_at: str,
    chunk_id: str,
    body: str,
    *,
    curated: bool = False,
) -> Optional[Dict[str, str]]:
    body = body.strip()
    if not body:
        return None
    # Curated chunks are labeled facts pulled from the page JSON (topics,
    # leftover facts, factsheet links, capital-gains text) — keep them even
    # when short. Only free-form visible-text windows need the boilerplate
    # filter so chrome isn't stored.
    if not curated and _is_boilerplate_chunk(body, fund_name):
        return None
    text = f"{_header(fund_name, url)}\n\n{body}"
    return {
        "chunk_id": chunk_id,
        "text": text,
        "url": url,
        "fund_key": fund_key,
        "ingested_at": ingested_at,
    }


def chunk_document(doc: Dict) -> List[Dict[str, str]]:
    fund_key = doc["fund_key"]
    if fund_key not in FUNDS:
        raise ValueError(f"Unknown fund_key: {fund_key}")
    url = assert_allowed_url(doc["url"])
    if url != FUNDS[fund_key]["url"]:
        raise ValueError(f"Document URL does not match allowlist for {fund_key}")
    fund_name = doc.get("fund_name") or FUNDS[fund_key]["fund_name"]
    ingested_at = doc["ingested_at"]

    facts_block, visible_raw = _split_facts_and_visible(doc.get("text") or "")
    lines = _fact_lines(facts_block)
    scheme_line = next((ln for ln in lines if ln.startswith("Scheme name on page:")), None)
    hero = scheme_line.split(":", 1)[1].strip() if scheme_line else fund_name
    chunks: List[Dict[str, str]] = []
    used_lines: set = set()

    for topic, prefixes in _TOPIC_SPECS:
        picked = _lines_for_prefixes(lines, prefixes)
        if not picked:
            continue
        for ln in picked:
            used_lines.add(ln)
        rec = _record(
            fund_key,
            fund_name,
            url,
            ingested_at,
            f"{fund_key}__{topic}",
            "\n".join(picked),
            curated=True,
        )
        if rec:
            chunks.append(rec)

    leftover = [ln for ln in lines if ln not in used_lines]
    if leftover:
        rec = _record(
            fund_key,
            fund_name,
            url,
            ingested_at,
            f"{fund_key}__other_facts",
            "\n".join(leftover),
            curated=True,
        )
        if rec:
            chunks.append(rec)

    links: Iterable[str] = doc.get("factsheet_links") or []
    link_lines = [ln for ln in links if isinstance(ln, str) and ln.strip()]
    if link_lines:
        rec = _record(
            fund_key,
            fund_name,
            url,
            ingested_at,
            f"{fund_key}__factsheet",
            "Factsheet or scheme document links that appear on this page:\n"
            + "\n".join(link_lines),
            curated=True,
        )
        if rec:
            chunks.append(rec)

    visible = _strip_visible_chrome(visible_raw, hero)
    if visible:
        cg_matches = list(_CAPITAL_GAINS.finditer(visible))
        if cg_matches:
            start = max(cg_matches[0].start() - 200, 0)
            end = min(cg_matches[-1].end() + 400, len(visible))
            rec = _record(
                fund_key,
                fund_name,
                url,
                ingested_at,
                f"{fund_key}__capital_gains",
                visible[start:end],
                curated=True,
            )
            if rec:
                chunks.append(rec)
        for i, window in enumerate(_windows(visible, _VISIBLE_WINDOW, _VISIBLE_OVERLAP)):
            rec = _record(
                fund_key,
                fund_name,
                url,
                ingested_at,
                f"{fund_key}__visible_{i:02d}",
                window,
            )
            if rec:
                chunks.append(rec)

    if not chunks:
        raise ValueError(f"No chunks produced for {fund_key}")
    return chunks
