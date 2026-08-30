# Architecture: HDFC Mutual Fund FAQ Assistant (RAG Prototype)

**Role:** Senior architect  
**Scope:** [PRD.md](./PRD.md) only. No extra products, sources, models, or services.  
**Type:** Single-process prototype (Streamlit + local ChromaDB + Mistral API). No auth, SLA, or multi-user persistence.

---

## 1. System context (PRD §2, §5, §6.3)

```
Demo user
    │
    ▼
Streamlit UI  (welcome, 3 examples, “Facts-only. No investment advice.”)
    │  question
    ▼
Query guard  (PII / advice / returns-math / out-of-corpus → refuse path)
    │  factual path
    ▼
Retrieval  →  chunks + source URL
    │
    ▼
Mistral  (facts-only, ≤3 sentences, one citation, last-updated)
    │
    ▼
Answer to UI
```

**Allowed corpus:** exactly five Groww URLs (PRD §4). Public pages only.

**Fixed stack (PRD §6.3):**

| Concern | Choice |
| --- | --- |
| Ingest | Fetch or upload those 5 URLs only |
| Embed | `sentence-transformers/all-MiniLM-L6-v2` |
| Vector store | ChromaDB |
| LLM | Mistral API |
| UI | Streamlit, Groww-inspired colors |

**PRD ingest default:** one dump/scrape at demo time; refresh is **manual**. `Last updated from sources` = timestamp of last successful ingest.

Offline pipeline (phases 1–4) is separate from online query (phase 5). Phase 6 tests retrieval **before** LLM polish.

---

## Phase 1 — Data loading

**Purpose:** Get page text for the five URLs into a local corpus the rest of the pipeline can use.

**Inputs:** Hard-coded allowlist (PRD §4):

| Fund key | URL |
| --- | --- |
| large_cap | `https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth` |
| flexi_cap | `https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth` |
| elss | `https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth` |
| small_cap | `https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth` |
| hybrid | `https://groww.in/mutual-funds/hdfc-balanced-advantage-fund-direct-growth` |

**Rules:**

- Reject any URL not on this list.
- No third-party blogs, no other Groww pages, no app-backend screenshots.
- Do not collect or persist PII.

**Process:**

1. For each allowlisted URL: fetch public HTML **or** load a one-time saved dump (PRD §10 default).
2. Extract visible text (and factsheet **links that appear on the page**, for later “point to factsheet” refusals).
3. Write one document record per URL.

**Document record:**

| Field | Use |
| --- | --- |
| `url` | Sole citation for that fund |
| `fund_key` / `fund_name` | Disambiguation in retrieve + refuse |
| `text` | Body for chunking |
| `ingested_at` | Feeds “Last updated from sources” |

**Exit:** Five documents, or fail ingest (PRD success: all 5 URLs ingested).

---

## Phase 2 — Chunking

**Purpose:** Split each page into retrieval units so expense ratio, SIP, exit load, lock-in, riskometer, benchmark, and (if present) capital-gains-statement text can be found independently.

**Inputs:** Phase 1 documents.

**Rules:**

- Chunk **per source URL**. Never merge two funds into one chunk (needed for “exactly one citation” and multi-fund questions).
- Preserve enough surrounding text that a fact stays understandable without the rest of the page.
- Drop empty / boilerplate-only fragments.

**Chunk record:**

| Field | Use |
| --- | --- |
| `chunk_id` | Stable id |
| `text` | Retrieval + prompt context |
| `url` | Citation |
| `fund_key` | Filter / ranking |
| `ingested_at` | Last-updated (same as parent doc) |

**Exit:** Chunk list covering all five pages.

---

## Phase 3 — Embedding

**Purpose:** Map chunk text (and later the user question) into the same vector space.

**Model (PRD only):** Hugging Face `sentence-transformers/all-MiniLM-L6-v2`. No paid or fine-tuned embeddings.

**Process:**

1. Load the model once per ingest job.
2. Embed each chunk’s `text`.
3. Do not embed PII; this phase only sees corpus text.

**Online reuse:** The **same** model embeds the question in Phase 5.

**Exit:** One vector per chunk, same dimensionality as the model.

---

## Phase 4 — Vector store

**Purpose:** Persist chunk vectors + metadata for similarity search.

**Store (PRD only):** ChromaDB, local to the prototype. No extra index, cache, or hosted vector DB.

**Collection:** one collection for this product.

**Stored per item:** embedding, `text`, `url`, `fund_key`, `chunk_id`, `ingested_at`.

**Rebuild:** On manual re-ingest, replace the collection so retrieval never mixes old and new pages. `ingested_at` on remaining items is the last-updated value shown in the UI.

**Exit:** All five URLs represented as chunks in ChromaDB (PRD §8 ingest pass).

---

## Phase 5 — Retrieval logic

**Purpose:** Given a user question, return the chunks the generator is allowed to see—or signal empty retrieval.

This phase is **search only**. Refusals (advice, PII, returns math, out-of-corpus) are applied **before** retrieve when the question type is clear; empty retrieve is still a first-class outcome (PRD §6.4).

**Process:**

1. **PII check** on the raw question. If PAN / Aadhaar / account / OTP / email / phone: do not store; do not embed; return the PII refusal. Retrieval does not run.
2. Embed the question with `all-MiniLM-L6-v2`.
3. Query ChromaDB for nearest chunks (same collection).
4. **Optional fund constraint:** if the question names one of the five funds, restrict or prefer chunks with that `fund_key`.
5. **Empty retrieval:** if scores/chunks are not useful, return no chunks. Downstream: “I can only answer from the five listed HDFC fund pages…” plus citation to the named fund page if any.
6. **Multiple funds in one question:** retrieve per named `fund_key` (or return two ranked groups). Generator still emits **one** citation per answer turn as per PRD; if two funds are required, prefer refuse-or-clarify using corpus pages rather than blending citations.
7. Attach `url` and `ingested_at` from the winning chunk(s) for the single citation and last-updated line.

**Outputs to generator (factual path):**

- Top chunk texts (prompt context)
- Exactly one `citation_url` (Groww page used)
- `last_updated` from ingest

**Not in this phase:** Mistral wording, Streamlit layout. Those consume this output (PRD §6.3 generate/UI).

---

## Phase 6 — Retrieval testing

**Purpose:** Prove chunking + embedding + Chroma retrieve the **right page and fact**, independent of Mistral. Matches PRD §4 corpus, §6.1–6.2 behaviours that depend on retrieve, §6.4 edge cases, and §8 “RAG demo: retrieve → generate”.

**Method:** Fixed question set. For each item: run Phase 5 (or Phase 5 without LLM). Assert on `fund_key` / `url` / presence of an expected phrase in retrieved `text` / empty vs non-empty. No PII written to logs.

| # | Question type (PRD) | Expect from retrieval |
| --- | --- | --- |
| 1 | Expense ratio of HDFC Large Cap Fund Direct Growth | Chunks from large-cap URL; text about expense ratio |
| 2 | ELSS lock-in for HDFC ELSS Tax Saver | ELSS URL; lock-in |
| 3 | Minimum SIP and exit load, HDFC Small Cap | Small-cap URL; SIP and/or exit load |
| 4 | Riskometer / benchmark (named in-corpus fund) | That fund’s URL; those fields if on page |
| 5 | Capital-gains statement download | Hits **only if** that text exists on an allowed page; else empty → refuse-with-citation (PRD §10 default) |
| 6 | Ambiguous: “expense ratio?” no fund | Weak/mixed `fund_key` or empty → treat as need-to-clarify, not a confident single URL |
| 7 | Wrong AMC / fund not in corpus | Empty or no matching `fund_key` |
| 8 | Advice phrased as fact (“good time to invest?”) | Do not require a “best fund” chunk; guard should refuse; retrieval should not be used to justify advice |
| 9 | PAN / phone in question | Retrieval **must not run**; no store |
| 10 | “Which fund has higher returns?” | Do not retrieve in order to **compute** returns; empty or ignored on this path; answerer points at factsheet link **if on page**, else fund page |
| 11 | Missing field on page | Retrieve the right URL; chunk may lack the field → generator refuses with citation (stale vs missing is ingest-time, not retrieve-time) |
| 12 | Empty retrieval | Explicit no-hit path |
| 13 | Two in-corpus funds in one question | Chunks tagged with **both** `fund_key`s, not a third URL |

**Pass (retrieval-only):** gold URL/`fund_key` (or empty) matches expectation; citation candidate is always one of the five URLs; PII never persisted.

**Then (PRD RAG demo):** one traced factual question showing retrieve chunks → Mistral answer (≤3 sentences, one citation, last-updated). That is generate-path evaluation, not a substitute for the table above.

---

## Constraints carried through all phases

- Public allowlist only; no PII in store or logs.
- No return computation in retrieve or later generate.
- One citation URL per user-visible answer; last-updated from Phase 1 `ingested_at`.
- Prototype: local Chroma, manual rebuild, no production hosting.
