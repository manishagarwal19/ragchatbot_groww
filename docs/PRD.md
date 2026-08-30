# PRD: HDFC Mutual Fund FAQ Assistant (RAG Prototype)

**Product:** Facts-only RAG chatbot for 5 HDFC Direct Growth funds on Groww  
**Status:** Prototype / hobby  
**Owner:** PM  
**Source of truth:** [problem statement.txt](./problem%20statement.txt)

---

## 1. Problem

Investors looking at HDFC funds on Groww still bounce between fund pages, factsheets, and FAQs to answer simple questions (expense ratio, SIP minimum, exit load, lock-in). There is no single, citeable, facts-only assistant limited to official public pages.

This prototype tests whether a small RAG stack can answer those questions reliably **only** from five Groww fund URLs—without advice, PII, or extra sources.

---

## 2. Goal

Ship a working Streamlit FAQ assistant that:

1. Ingests **only** the five Groww pages listed below.
2. Answers **factual** questions with **one citation URL** per answer.
3. Refuses advice / portfolio / “should I buy” questions politely.
4. Makes the RAG pipeline visible enough to evaluate chunking, retrieval, and Mistral answers.

**Non-goal:** A production chatbot, personalization, account login, or coverage of any fund/page beyond the corpus.

---

## 3. Users

| Who | Need |
| --- | --- |
| Curious investor (demo user) | Fast, cited facts from Groww fund pages |
| Builder / PM | Validate RAG quality, refusals, and UI constraints |

No authenticated users. No stored identity.

---

## 4. Corpus (hard scope)

**Site:** [groww.in](https://groww.in/) · **AMC:** HDFC  
**Allowed sources:** these five URLs only. Nothing else (no other Groww pages, no blogs, no app-backend screenshots).

| Category | Fund | URL |
| --- | --- | --- |
| Large-cap | HDFC Large Cap Fund Direct Growth | https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth |
| Flexi-cap | HDFC Flexi Cap Fund Direct Growth (Groww slug still uses legacy “equity fund” name) | https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth |
| ELSS | HDFC ELSS Tax Saver Fund Direct Plan Growth | https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth |
| Small-cap | HDFC Small Cap Fund Direct Growth | https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth |
| Hybrid | HDFC Balanced Advantage Fund Direct Growth | https://groww.in/mutual-funds/hdfc-balanced-advantage-fund-direct-growth |

---

## 5. User experience

**Surface:** Streamlit, Groww-inspired colors, tiny UI.

**On load:**

- One welcome line
- Three example questions
- Persistent note: **“Facts-only. No investment advice.”**

**Each answer must:**

- Be **≤ 3 sentences**
- Include **exactly one** citation link (the Groww page used)
- Include **“Last updated from sources: &lt;date/time of last ingest&gt;”**
- Stay factual; no buy/sell, ranking, or “best fund” language

**Suggested example questions (UI):**

1. What is the expense ratio of HDFC Large Cap Fund Direct Growth?
2. What is the ELSS lock-in for HDFC ELSS Tax Saver?
3. What is the minimum SIP and exit load for HDFC Small Cap Fund?

---

## 6. Functional requirements

### 6.1 In-scope questions (answer from corpus)

Examples: expense ratio, ELSS lock-in, minimum SIP, exit load, riskometer, benchmark, how to download a capital-gains statement **if that text exists on the allowed pages**.

### 6.2 Out-of-scope questions (refuse)

| Type | Behaviour |
| --- | --- |
| Advice / portfolio (“Should I buy/sell?”, “Which is better?”) | Polite facts-only refusal + one relevant **educational** link from the allowed corpus (e.g. the fund page the user named, or a generic Groww fund page in corpus) |
| Returns / performance comparison | Do **not** compute or compare returns. Direct user to the official factsheet **if linked from the allowed page**; otherwise refuse and cite the fund page |
| PII (PAN, Aadhaar, account numbers, OTP, email, phone) | Do not accept or store. Tell the user not to share PII and continue with facts-only help |
| Anything not in the 5 URLs | “I can only answer from the five listed HDFC fund pages on Groww.” + citation to the closest matching fund page if the user named one |

### 6.3 RAG pipeline (build as specified)

| Stage | Spec |
| --- | --- |
| Ingest | Fetch/upload content from the 5 URLs only |
| Chunk | Split page text into retrieval chunks |
| Embed | `sentence-transformers/all-MiniLM-L6-v2` (Hugging Face), free/lightweight |
| Store | ChromaDB |
| Retrieve | Embed the question with the same model; return relevant chunks |
| Generate | Mistral API; prompt = retrieved chunks + user question + system rules (facts-only, ≤3 sentences, one citation, last-updated line, refuse advice/PII/returns math) |
| UI | Streamlit |

### 6.4 Edge cases (must test)

- Ambiguous fund (“expense ratio?” with no fund name)
- Wrong AMC / fund not in corpus
- Advice phrased as a fact (“Is this a good time to invest?”)
- User pastes PAN / phone
- “Which fund has higher returns?”
- Stale vs missing field on the page
- Empty retrieval (no useful chunks)
- Multiple funds in one question

---

## 7. Non-functional / constraints

- **Public sources only**
- **No PII** stored or logged in identifiable form
- **No performance claims** (no DIY return math)
- **Transparency:** citations + last-updated from ingest
- Prototype quality is enough; no SLA, auth, or multi-user persistence required

---

## 8. Success criteria (prototype)

| Criterion | Pass |
| --- | --- |
| Ingest | All 5 URLs chunked, embedded, in ChromaDB |
| Factual Q | Correct fact + 1 Groww citation + last-updated, ≤3 sentences |
| Advice Q | Refusal, no recommendation, educational/corpus link |
| Returns Q | No computed comparison; factsheet or fund-page pointer |
| PII | Rejected; not stored |
| UI | Welcome + 3 examples + facts-only disclaimer |
| RAG demo | Can show retrieve → generate path for evaluation |

---

## 9. Out of scope (explicit)

- Other AMCs, other HDFC funds, Groww blog/help beyond the 5 URLs
- Transaction, KYC, login, statements generation
- Screenshots of Groww app backend
- Fine-tuned models, paid embeddings, production hosting
- Multi-turn “advisor” personality

---

## 10. Open questions (for build)

1. Ingest: live scrape of the 5 URLs vs one-time saved HTML/markdown dumps?
2. How often is the corpus refreshed (drives “Last updated from sources”)?
3. If capital-gains download steps are **not** on these five pages, refuse or stay silent?
4. Mistral model name / token limits for the prompt?

**Default if unspecified:** dump/scrape once at demo time; refresh is manual; missing page content → refuse with citation; document the Mistral model in the repo README.
