# Product Requirements Document

## Product

**Name:** HDFC Mutual Fund FAQ Assistant  
**Status:** Draft  
**Date:** 2026-11-13  
**Primary experience:** Small web-based retrieval-augmented FAQ assistant for factual mutual fund scheme questions.

## 1. Problem statement

Retail investors and support/content teams repeatedly need basic, verifiable facts about mutual fund schemes, including expense ratio, exit load, minimum SIP, ELSS lock-in, riskometer, benchmark, and statement-download guidance. Finding these details across scheme pages takes time, and answers without clear citations can be difficult to verify.

The assistant should retrieve concise answers from approved public sources, cite the source used, and decline to give advice or unsupported information. It is a facts-only support tool, not an investment adviser.

## 2. Users and needs

### Primary users

- Retail users looking up or factually comparing the selected HDFC schemes.
- Support and content teams responding to repetitive mutual fund questions.

### User needs

- Ask a plain-language question about a supported scheme.
- Receive a short answer grounded in the approved corpus.
- Open the source page to verify the fact.
- Understand when the corpus does not support an answer.
- Avoid sharing personal or account information.

## 3. Goals and non-goals

### Goals

1. Answer factual questions about the selected HDFC Mutual Fund overview and four schemes.
2. Provide one clear source link and a “Last updated from sources:” date with every answer.
3. Keep answers to no more than three sentences.
4. Make each RAG phase inspectable through separately stored outputs.
5. Keep embedding, vector-store, and LLM settings configurable.
6. Refuse advice, unsupported questions, and performance claims safely.

### Non-goals

- Recommending, ranking, or selecting funds for a user.
- Calculating, predicting, or comparing returns or other performance claims.
- Collecting or storing investor identity, contact, or account information.
- Authenticated account support, transactions, portfolio analysis, or tax/legal advice.
- Production-grade availability, monitoring, or multi-user administration.

## 4. Initial source scope

The initial fetch allowlist contains exactly these five user-specified pages. The loader must not follow or fetch links found inside them.

| Scope | Page | URL |
|---|---|---|
| AMC overview | HDFC Mutual Fund | https://groww.in/mutual-funds/amc/hdfc-mutual-funds |
| Large Cap | HDFC Large Cap Fund Direct Growth | https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth |
| Flexi Cap | HDFC Flexi Cap Direct Plan Growth | https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth |
| ELSS | HDFC ELSS Tax Saver Fund Direct Plan Growth | https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth |
| Mid Cap | HDFC Mid Cap Fund Direct Growth | https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth |

Only public pages may be used. No screenshots of app backends and no third-party blogs may be used. Each answer must be traceable to an approved source. The specified pages are Groww pages; if institutional AMC, SEBI, or AMFI sources are required for citations, they must be explicitly approved and added to the allowlist before ingestion.

## 5. Supported question categories

- Expense ratio.
- Exit load and applicable conditions.
- Minimum SIP.
- ELSS lock-in.
- Riskometer.
- Scheme benchmark.
- Statement-download or capital-gains-statement guidance, only when supported by an approved public source.
- General scheme facts present in the approved pages.

If a requested fact is missing, stale, ambiguous, or outside the approved corpus, the assistant must say it cannot confirm the answer rather than infer one.

## 6. User experience

### Main screen

- Short welcome line explaining the assistant’s HDFC scheme scope.
- Facts-only disclaimer: **“Facts-only. No investment advice.”**
- Three example questions, such as “What is the minimum SIP?”, “What is the ELSS lock-in?”, and “What is the exit load?”
- One question input and a submit action.
- Answer area with no more than three sentences, one clear source link, and the source-update date.
- Clear message when information is unavailable or a question is declined.

### Response format

Every response must include:

1. A direct factual answer or a brief refusal/unsupported-answer message.
2. One clear citation link relevant to that response.
3. **“Last updated from sources: YYYY-MM-DD”** using the latest successful fetch date for the cited source.

Opinionated or portfolio questions (for example, “Should I buy or sell?”) receive a polite refusal and a relevant educational link from an approved official public source. No advice is generated.

## 7. Functional requirements

### FR-1: Source loading

- Fetch only the five configured URLs.
- Do not crawl, follow, or fetch internal links or other discovered URLs.
- Store source URL, title, fetch timestamp, and extracted page content.
- Surface fetch errors; do not silently treat failed pages as successfully loaded.

### FR-2: Chunking

- Use a section-aware strategy appropriate to scheme facts, keeping related labels and values together.
- Preserve scheme, section, source URL, and fetch date as chunk metadata.
- Exclude performance/return material from the answerable index.
- Persist the resulting chunks for review.

### FR-3: Embeddings

- Default embedding model: `sentence-transformers/all-MiniLM-L6-v2`.
- Make the embedding provider/model configurable.
- Use the exact same configured embedding model for ingestion and query-time retrieval.
- Persist embeddings and their chunk identifiers for inspection.

### FR-4: Vector database and retrieval

- Use ChromaDB for the initial prototype.
- Configure vector-store provider, persistence location, and collection name centrally.
- Retrieve the most relevant chunks from the same configured vector store used during ingestion.
- Keep source metadata attached to each retrieved result and use it to create citations.
- If retrieval is weak or no relevant evidence is found, return an unsupported response.

### FR-5: LLM configuration

- Use Google Gemini 3.5 Flash-Lite (`gemini-3.5-flash-lite`) as the only answer-generation model.
- Read `GEMINI_API_KEY` from environment configuration (for example, `.env` or Vercel Secret variables); never commit secrets.
- Keep the Gemini model identifier in central configuration and surface API/configuration errors to the user.
- OpenAI remains the embedding provider; it is separate from answer generation and may incur separate costs.
- Document that Gemini free-tier quotas apply and that free-tier content may be used to improve Google products.
- Do not persist prompts, questions, answers, or provider credentials.

### FR-6: Answer generation and citations

- Answer only from retrieved approved excerpts.
- Use concise, neutral language and a maximum of three sentences.
- Include one source link for every answer, including safe refusals.
- Include the source’s latest successful fetch date in the required “Last updated” line.
- Do not invent missing facts, citations, or source URLs.

### FR-7: Safety and privacy

- Do not accept for processing or store PAN, Aadhaar, account numbers, OTPs, emails, or phone numbers.
- Detect likely sensitive identifiers before sending a query to the embedding model or LLM; reject such queries with a brief privacy message.
- Do not log or persist user questions or answers.
- Never provide investment recommendations or personalized portfolio guidance.
- Never compute, compare, predict, or state performance claims.
- If asked about performance, decline and link to an official factsheet/disclosure source when one is approved.

## 8. RAG pipeline and visible artifacts

The prototype must make each stage inspectable:

1. **Data loading:** `data/01_raw/` — fetched text and source metadata.
2. **Chunking:** `data/02_chunks/` — chunks with source, scheme, section, and date metadata.
3. **Embedding:** `data/03_embeddings/` — embedding model identifier and vectors keyed by chunk ID.
4. **Vector database:** `data/04_vector_db/` — persistent ChromaDB collection and ingestion manifest.
5. **Retrieval:** show retrieved excerpts and their source metadata in a demo/debug view without exposing secrets or user PII.

Re-ingestion must refresh the artifacts from the allowlisted pages and use the same model/backend configuration for later retrieval.

## 9. Configuration and privacy requirements

- Central configuration must hold the source allowlist, chunking options, embedding provider/model, vector DB provider/path/collection, retrieval parameters, and Gemini answer model.
- API keys must be read from the local environment and excluded from source control and generated data artifacts.
- No question or answer history is required for the prototype.
- Any debug display must contain corpus passages only, not secrets or personal query content.

## 10. Deliverables

- Working prototype link, or a demo video of no more than three minutes if hosting is unavailable.
- CSV or Markdown source list documenting 15–25 URLs used.
- README with setup steps, supported AMC/schemes, and known limitations.
- Sample Q&A file with 5–10 queries, answers, and links.
- Disclaimer snippet used in the UI.
- Stored artifacts for each RAG pipeline stage.

## 11. Acceptance criteria

1. The loader makes requests only to the five initial allowlisted pages and never follows page links.
2. Loading, chunking, embedding, and ChromaDB outputs are separately persisted and inspectable.
3. The embedding model identifier used at query time matches the ingestion model.
4. The UI displays a welcome message, three example questions, and the facts-only disclaimer.
5. A supported factual answer is at most three sentences and contains one relevant source link and the required update line.
6. Unsupported questions receive a clear non-inventive response with a source link and update line.
7. Advice and portfolio-selection requests are politely declined and linked to an approved educational source.
8. Performance questions do not result in a performance claim and instead point to an approved official factsheet/disclosure source.
9. Queries containing likely PII are rejected before embedding or LLM submission and are not persisted.
10. Provider/API errors are shown explicitly; they do not produce a fabricated answer.
11. The sample Q&A contains between five and ten entries and follows the same citation, date, and sentence-length rules.

## 12. Delivery phases

1. **Data loading:** implement allowlisted fetch and raw data persistence.
2. **Data chunking:** select and document section-aware chunk boundaries; persist chunks and metadata.
3. **Data embedding:** embed chunks with the configured model and persist vectors.
4. **Vector database:** write vectors and metadata to configured ChromaDB collection.
5. **Retrieval and answer:** retrieve relevant chunks, classify/refuse unsafe or unsupported requests, and generate cited factual responses.
6. **UI and handoff:** add examples, disclaimer, sample Q&A, README, source list, and a short demo or local run instructions.

## 13. Risks, limitations, and open decisions

- **Source-count conflict:** the loader is restricted to five pages, while the deliverable asks for 15–25 URLs. Decide whether the additional URLs may be official references that are listed but not fetched, or whether the crawl/index scope can be expanded.
- **Official-source conflict:** the five specified sources are Groww pages, while the skills requirement calls for citations from AMC/SEBI/AMFI pages. Confirm whether the five specified pages are sufficient or approve additional institutional sources.
- **Statement guidance:** the five scheme/AMC pages may not contain statement-download steps. Add an approved official source or keep these questions explicitly unsupported.
- **Factsheet link:** an approved official AMC factsheet/disclosure URL is needed for performance-question refusals.
- **Gemini free tier:** quotas, model availability, and data-use terms may change; verify Google's current terms before release.
- **Source freshness:** scheme values can change. Fetch dates must be visible, and the prototype must not imply that a past fetch is current.
- **Prototype security:** local environment keys and in-memory query processing are suitable only for a demo; public deployment requires a separate privacy/security review.
