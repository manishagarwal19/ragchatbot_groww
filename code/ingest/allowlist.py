"""Hard-coded corpus allowlist (architecture Phase 1 / PRD §4)."""

from __future__ import annotations

from typing import Dict, FrozenSet, List

# fund_key -> public Groww URL. Nothing else may be fetched or persisted as a source.
FUNDS: Dict[str, Dict[str, str]] = {
    "large_cap": {
        "fund_name": "HDFC Large Cap Fund Direct Growth",
        "url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
    },
    "flexi_cap": {
        "fund_name": "HDFC Flexi Cap Fund Direct Growth",
        "url": "https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth",
    },
    "elss": {
        "fund_name": "HDFC ELSS Tax Saver Fund Direct Plan Growth",
        "url": "https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth",
    },
    "small_cap": {
        "fund_name": "HDFC Small Cap Fund Direct Growth",
        "url": "https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth",
    },
    "hybrid": {
        "fund_name": "HDFC Balanced Advantage Fund Direct Growth",
        "url": "https://groww.in/mutual-funds/hdfc-balanced-advantage-fund-direct-growth",
    },
}

ALLOWED_URLS: FrozenSet[str] = frozenset(entry["url"] for entry in FUNDS.values())
ALLOWED_FUND_KEYS: FrozenSet[str] = frozenset(FUNDS)


def assert_allowed_url(url: str) -> str:
    if url not in ALLOWED_URLS:
        raise ValueError(f"URL is not on the corpus allowlist: {url}")
    return url


def fund_keys() -> List[str]:
    return list(FUNDS.keys())
