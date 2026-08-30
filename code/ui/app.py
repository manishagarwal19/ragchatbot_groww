"""Streamlit UI — query the Phase 5 retrieval backend (architecture Phase 6 "retrieve" path).

Run from repo root:
    streamlit run code/ui/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# `streamlit run` is a console script, so sys.path[0] is the venv bin dir and
# bare `import code.*` would resolve to the stdlib `code` module. Put the repo
# root back on the path so the `code` package is found in any launch mode.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st

from code.bootstrap import ensure_corpus
from code.embedding.embed import embed_query, load_model, model_dimension
from code.ingest.allowlist import FUNDS, fund_keys
from code.retrieval.retrieve import RetrievalResult, retrieve
from code.vector_store.store import get_collection

# Groww-inspired palette (tight, PRD §5: "tiny UI").
_BLUE = "#2447F9"
_GREEN = "#00B386"
_INK = "#1B2530"

st.set_page_config(page_title="HDFC Fund FAQ Assistant", page_icon="📈", layout="centered")

st.markdown(
    f"""
<style>
    html, body, [data-testid="stAppViewContainer"] {{ color: {_INK}; }}
    .app-title {{ color: {_BLUE}; font-size: 1.6rem; font-weight: 700; }}
    .app-sub {{ color: {_INK}; font-size: 1rem; margin-top: 0.2rem; }}
    .disclaimer {{
        color: #5B6770; font-size: 0.85rem; border-top: 1px solid #E4E7EB;
        padding-top: 0.5rem; margin-top: 2rem;
    }}
    .citation {{ color: {_GREEN}; }}
    .chunk-caption {{ color: #5B6770; font-size: 0.8rem; }}
</style>
""",
    unsafe_allow_html=True,
)

EXAMPLES = [
    (
        "What is the expense ratio of HDFC Large Cap Fund Direct Growth?",
        "Expense ratio · Large Cap",
    ),
    ("What is the ELSS lock-in for HDFC ELSS Tax Saver?", "ELSS lock-in"),
    ("What is the minimum SIP and exit load for HDFC Small Cap Fund?", "SIP / exit load"),
]

_REFUSAL_TEXT = {
    "refused_pii": (
        "Please don't share personal information (PAN, Aadhaar, account numbers, "
        "OTP, email or phone). I only answer facts from the five HDFC fund pages."
    ),
    "refused_advice": (
        "I'm a facts-only assistant and can't give investment or buy/sell advice. "
        "Ask me a factual question instead."
    ),
    "refused_returns": (
        "I don't compute or compare returns. Let me point you to the official "
        "factsheet for the fund if it's linked on the page."
    ),
    "out_of_corpus": (
        "I can only answer from these five HDFC fund pages on Groww."
    ),
}


@st.cache_resource(show_spinner="Loading embedding model…")
def _model():
    return load_model()


@st.cache_resource(show_spinner="Connecting to vector store…")
def _collection():
    return get_collection()


def _ask(question: str) -> RetrievalResult:
    return retrieve(
        question,
        embed_fn=lambda q: embed_query(q, model=_model()),
        collection=_collection(),
    )


def _render(result: RetrievalResult) -> None:
    if result.status == "ok":
        chunk = result.chunks[0]
        st.markdown(
            f'<div class="app-sub">Facts found on the fund page — '
            f'<a class="citation" href="{chunk.url}" target="_blank">'
            f"{chunk.url}</a>.</div>",
            unsafe_allow_html=True,
        )
        st.caption(f"Last updated from sources: {result.last_updated}")
        st.markdown("**Matched chunks:**")
        for i, c in enumerate(result.chunks, start=1):
            with st.expander(
                f"{i}. {c.chunk_id}  ·  `{c.fund_key}`  ·  distance {c.distance:.3f}"
            ):
                st.text(c.text)
        return

    if result.status in _REFUSAL_TEXT:
        st.info(_REFUSAL_TEXT[result.status])
        if result.status == "out_of_corpus" and result.reason:
            st.caption(f"(matched hint: {result.reason})")
        st.markdown("**I can answer about:**")
        for key in fund_keys():
            entry = FUNDS[key]
            st.markdown(f"- {entry['fund_name']} — [fund page]({entry['url']})")
        return

    if result.status == "needs_clarification":
        st.info(
            "I couldn't tell which fund you mean. Please name one of the five "
            "HDFC funds so I can point you to the right page."
        )
        st.markdown("**I can answer about:**")
        for key in fund_keys():
            st.markdown(f"- {FUNDS[key]['fund_name']}")
        return

    if result.status == "empty":
        st.info(
            "I couldn't find a useful match for that on the five HDFC fund pages. "
            "Try rephrasing or naming the fund."
        )
        if result.citation_url:
            st.markdown(f"Closest fund page: [{result.citation_url}]({result.citation_url})")
        return

    if result.status == "empty_question":
        st.info("Type a question above to search the corpus.")
        return

    st.warning(f"Unexpected status: {result.status} ({result.reason})")


def main() -> None:
    with st.spinner("Preparing the corpus (first boot builds it)…"):
        try:
            ensure_corpus()
        except Exception as exc:  # noqa: BLE001
            st.error(
                "Could not build the retrieval corpus. "
                f"Cause: {exc}\n\nIf this is a fresh clone, commit "
                "`data/raw/extracted/*.json` (Phase 1) before deploying."
            )
            st.stop()

    try:
        dim = model_dimension(_model())
    except Exception as exc:  # noqa: BLE001
        st.error(f"Embedding model unavailable: {exc}")
        st.stop()
    try:
        _collection().count()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Vector store unavailable: {exc}")
        st.stop()

    st.markdown('<div class="app-title">HDFC Fund FAQ Assistant</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="app-sub">Weekly questions about the five HDFC direct-growth funds, '
        "answered straight from their Groww pages.</div>",
        unsafe_allow_html=True,
    )

    st.markdown("**Try an example:**")
    cols = st.columns(len(EXAMPLES))
    for col, (question, label) in zip(cols, EXAMPLES):
        if col.button(label, use_container_width=True):
            st.session_state["question"] = question
            st.rerun()

    default = st.session_state.get("question", "")
    with st.form("ask"):
        question = st.text_input(
            "Ask a factual question",
            value=default,
            placeholder="e.g. What is the ELSS lock-in for HDFC ELSS Tax Saver?",
        )
        submitted = st.form_submit_button("Ask", type="primary")

    if submitted and question.strip():
        with st.spinner("Searching the corpus…"):
            result = _ask(question.strip())
        _render(result)

    st.markdown(
        '<div class="disclaimer">Facts-only. No investment advice. '
        f"Corpus: the {len(FUNDS)} HDFC fund pages listed above · "
        f"embedding model dim {dim}</div>",
        unsafe_allow_html=True,
    )


main()