"""Query guard — decide whether this question may run retrieval (architecture Phase 5).

Refusals applied before retrieve when the question type is clear:
PII, advice/portfolio, returns-math, out-of-corpus. Also detects which of the
five corpus funds the question names (optional retrieval constraint).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

from code.ingest.allowlist import FUNDS
from code.ingest.extract import redact_pii

# Case-insensitive aliases: fund_key -> phrases that name that fund.
_FUND_ALIASES = {
    "large_cap": (
        "hdfc large cap",
        "hdfc large-cap",
        "large cap fund direct growth",
    ),
    "flexi_cap": (
        "hdfc flexi cap",
        "hdfc flexi-cap",
        "hdfc equity fund",
        "flexi cap fund direct growth",
    ),
    "elss": (
        "hdfc elss",
        "hdfc tax saver",
        "elss tax saver fund",
    ),
    "small_cap": (
        "hdfc small cap",
        "hdfc small-cap",
        "small cap fund direct growth",
    ),
    "hybrid": (
        "hdfc balanced advantage",
        "balanced advantage fund",
    ),
}

# AMCs that are never in the five-URL corpus. Common misspellings/forms are
# included so a stray typo doesn't fall through to retrieval.
_OTHER_AMCS = (
    "sbi", "axis", "icici", "kotak", "franklin", "templeton", "mirae", "nippon",
    "aditya birla", "birla sun", "uti", "parag parikh", "parag parekh",
    "parekh", "ppfas", "quant", "motilal", "pgim", "dsp", "canara",
    "mahindra", "bandhan", "navi", "edelweiss", "baroda", "lic", "hsbc",
    "jupiter", "360 one", "invezta", "whiteoak", "union mutual",
)

# HDFC funds that are NOT part of the five-URL corpus.
_HDFC_NON_CORPUS = (
    "hdfc mid cap", "hdfc multi cap", "hdfc focused", "hdfc index",
    "hdfc banking", "hdfc infrastructure", "hdfc pharma", "hdfc healthcare",
    "hdfc defence", "hdfc technology", "hdfc consumption", "hdfc dividend yield",
    "hdfc value", "hdfc retirement", "hdfc children", "hdfc arbitrage",
    "hdfc liquid", "hdfc money market", "hdfc short term", "hdfc ultra short",
    "hdfc corporate bond", "hdfc credit risk", "hdfc gilt", "hdfc floater",
    "hdfc dynamic", "hdfc equity savings", "hdfc multi asset", "hdfc multiple yield",
    "hdfc capital builder", "hdfc balanced fund", "hdfc hybrid equity", "hdfc step one",
)

_PII_EXTRA = (
    re.compile(r"\botp\b", re.I),
    re.compile(r"\b\d{9,18}\b"),  # account-number-like run of digits
)

_ADVICE = (
    re.compile(r"\b(should|shall) i (buy|sell|invest|switch|redeem|start|put|allocate)\b", re.I),
    re.compile(r"\b(is|was) (this|it) a good time\b", re.I),
    re.compile(r"\bwhich( \w+)?( one)? (is|are|would be) (better|best)\b", re.I),
    re.compile(r"\bbest (mutual |equity |debt )?fund\b", re.I),
    re.compile(r"\brecommend\w*\b", re.I),
    re.compile(r"\badvice\b|\bportfolio\b|\basset allocation\b", re.I),
    re.compile(r"\b(i want|i plan|i am planning|i am thinking|i m thinking) (to )?(invest|buy|sell|switch)\b", re.I),
    re.compile(r"\bworth (it|investing|buying|selling)\b", re.I),
    re.compile(r"\bgood time to (invest|buy|sell)\b", re.I),
    re.compile(r"\bwhere (should )?i (invest|put) money\b", re.I),
    re.compile(r"\bwhat should i do\b", re.I),
)

_RETURNS = (
    re.compile(r"higher returns", re.I),
    re.compile(r"better returns", re.I),
    re.compile(r"best returns", re.I),
    re.compile(r"returns (vs|versus|compared to|comparison)", re.I),
    re.compile(r"(compare|comparing|comparison).{0,20}returns", re.I),
    re.compile(r"\bxirr\b|\bcagr\b", re.I),
    re.compile(r"annual(ised|ized)\s+returns", re.I),
    re.compile(r"(over the )?(past|last|trailing|historic|historical|previous)\s*\d*\s*(year|yr|years).{0,10}returns", re.I),
    re.compile(r"how much (would|will|did|does) .{0,40} (earn|return|make|grow)", re.I),
    re.compile(r"\d+\s*%? returns", re.I),
    re.compile(r"(grew|growth|appreciated) by \d", re.I),
    re.compile(r"(which|what) fund (has|gave|gives|generated|made) \w+ returns", re.I),
)


@dataclass
class GuardResult:
    status: str  # ok | refused_pii | refused_advice | refused_returns | out_of_corpus
    reason: str = ""
    named_funds: List[str] = field(default_factory=list)
    out_of_corpus_hint: str = ""


def _named_funds(question: str) -> List[str]:
    lowered = question.lower()
    found: List[str] = []
    for fund_key, aliases in _FUND_ALIASES.items():
        if any(alias in lowered for alias in aliases):
            found.append(fund_key)
    return found


def _fund_order(fund_key: str) -> int:
    return list(FUNDS).index(fund_key)


def classify_question(question: str) -> GuardResult:
    if not question or not question.strip():
        return GuardResult(status="empty", reason="empty question")

    if redact_pii(question) != question or any(p.search(question) for p in _PII_EXTRA):
        return GuardResult(status="refused_pii", reason="PII detected; not stored or embedded")

    if any(p.search(question) for p in _ADVICE):
        return GuardResult(
            status="refused_advice",
            reason="advice/portfolio question; facts-only assistant",
        )

    if any(p.search(question) for p in _RETURNS):
        return GuardResult(
            status="refused_returns",
            reason="returns computation is out of scope",
        )

    # Out-of-corpus detection runs before alias matching so that an explicit
    # mention of a non-corpus fund is never captured by a loose alias such as
    # "flexi cap fund direct growth".
    lowered = question.lower()
    for hint in _HDFC_NON_CORPUS:
        if hint in lowered:
            return GuardResult(status="out_of_corpus", out_of_corpus_hint=hint, reason=f"{hint} not in corpus")
    for amc in _OTHER_AMCS:
        if amc in lowered:
            return GuardResult(status="out_of_corpus", out_of_corpus_hint=amc, reason=f"{amc} not in corpus")

    named = _named_funds(question)
    if named:
        return GuardResult(status="ok", named_funds=sorted(set(named), key=_fund_order))

    return GuardResult(status="ok")