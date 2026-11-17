# Architecture — HDFC Mutual Fund FAQ Assistant

## 1. Purpose and deployment

This document describes the deployed prototype architecture. The public application is a Vercel-hosted FastAPI endpoint and static browser UI. The ingestion script runs manually from a trusted local machine and writes to Neon Postgres with pgvector.

- **Initial corpus:** Five explicitly allowlisted Groww pages; no link crawling.
- **Runtime:** Vercel Python Functions (FastAPI) and static CDN assets.
- **Vector store:** Neon Postgres with pgvector.
**Embedding model:** OpenAI `text-embedding-3-small` for both ingestion and retrieval.

## 2. Architectural principles

1. **Allowlisted sources only:** ingestion requests the five configured URLs directly and never follows discovered links or redirects.
2. **Evidence before generation:** the LLM receives retrieved excerpts, not unrestricted web content.
3. **Citations are application-owned:** the application chooses the source URL and fetch date from retrieved metadata.
4. **Fail closed:** unsupported, low-confidence, unsafe, or untraceable questions receive a concise refusal.
5. **Explicit pipeline artifacts:** ingestion writes inspectable raw, loaded, chunk, embedding, and index manifests under ignored `data/`.
6. **Same embedding model end to end:** ingestion and query-time embeddings use the configured OpenAI model.
7. **No app-side query history:** questions and answers are not written to the corpus or local artifacts. API keys stay in environment secrets.

## 3. System context

```mermaid
flowchart LR
    U[User] --> UI[Static browser UI on Vercel CDN]
    UI --> API[FastAPI on Vercel]
    API --> Guard[PII and intent guard]
    Guard --> Embed[OpenAI embeddings]
    Embed --> Search[Neon pgvector retrieval]
    Search -->|source excerpts and metadata| Answer[Answer orchestrator]
    Answer --> LLM[Groq GPT-OSS 20B]
    LLM -->|draft| Answer
    Answer -->|answer, one source, fetch date| UI
    Ingest[Local ingest_neon.py] --> Fetch[Five-page allowlist scraper]
    Fetch --> Raw[Raw and loaded artifacts]
    Raw --> Chunk[Section-aware chunker]
    Chunk --> Embeddings[OpenAI text-embedding-3-small]
    Embeddings --> Artifacts[Inspectable local artifacts]
    Embeddings -->|vectors, chunks, metadata| Search
```

### Trust boundaries

- **Browser to API:** input is untrusted and checked before any embedding or LLM call.
- **Ingestion to public sites:** only exact configured source URLs are fetched; redirects are rejected.
- **API to Groq:** only safe questions and retrieved excerpts are sent to Groq.
- **Vercel to Neon:** the vector database is external and durable; the pooled connection string is a server-side environment secret.
- **Local ingestion machine:** contains temporary public-source artifacts, not saved Q&A history or API keys in the repository.

## 4. Components

### 4.1 Browser UI

`public/index.html` is the static, responsive FAQ experience served by Vercel. Its visual direction adapts the `growfolio_dolce_vita_edition` Stitch export supplied in `stitch_growfolio.zip`: white stationery-like surfaces, pale-blue cabana stripes, butter-yellow accents, Bodoni Moda display type, readable Epilogue controls, and restrained botanical/postal motifs. The generated mock answer and mock metrics are not used; corpus counts and answers reflect the configured source set and live API response.

The page provides:

- A prominent question form, fixed Groq GPT-OSS 20B label, and example-question chips that only fill the question field.
- Corpus summaries for five approved pages, four scheme pages, and five pipeline steps.
- A directory of the five allowlisted public source pages and a visual load/chunk/embed/store/retrieve flow.
- A response card that renders the API answer as text and displays exactly the API-provided source URL and fetch date.
- Facts-only and privacy notices, responsive layouts, visible keyboard focus, and reduced-motion support.

The browser sends the question and the fixed `groq` provider to `POST /api/answer`; it does not persist question history or receive provider credentials. Network and API errors are shown in the response card rather than replaced with a sample answer.

### 4.2 FastAPI application

`app.py` exports the top-level FastAPI `app` expected by Vercel’s Python runtime. It validates request length and accepts only the Groq answer provider, runs guardrails, creates query embeddings, searches Neon using pgvector cosine distance, calls Groq, validates the answer, and returns a small JSON response. `/api/health` is a basic health endpoint.

The app does not load or embed the local Sentence Transformers model. This keeps local ML model weights out of the serverless function bundle.

### 4.3 Ingestion pipeline

`ingest_neon.py` is run manually from a trusted local machine after setting `OPENAI_API_KEY` and the Neon pooled connection string in `DATABASE_URL`.

| Phase | Component | Output |
|---|---|---|
| 1. Scrape | Fixed allowlist fetcher and HTML extractor | `data/neon/01_raw/pages.json` |
| 2. Load | Required-source, metadata, hash, and date validation | `data/neon/01_raw/loaded_documents.json`, `load_manifest.json` |
| 3. Chunk | Section-aware chunker | `data/neon/02_chunks/chunks.json` |
| 4. Embed | OpenAI `text-embedding-3-small` | `data/neon/03_embeddings/embeddings.json` |
| 5. Index | Neon Postgres / pgvector | Remote `hdfc_chunks` table and `data/neon/04_vector_db/manifest.json` |

The script rejects failed responses, redirects, non-HTML pages, oversized responses, invalid page records, and partial source sets. It writes stage artifacts under `data/neon/` so it does not overwrite the legacy Streamlit artifacts, then verifies the stored count and a sample retrieval after indexing. Re-ingestion replaces the corpus in one database transaction, so a failed refresh does not leave a partial index.

### 4.4 Vector database and retrieval

Neon stores chunk text, supplied embedding vectors, embedding-model identifiers, and source metadata in the `hdfc_chunks` table. The `vector` column uses the configured embedding dimension and an HNSW cosine index. Vercel queries it using the same configured OpenAI model used by ingestion. Scheme mentions add a `source_id` filter. Retrieval validates source URLs, dates, distances, model identifiers, and result shape before generating an answer. The older Streamlit prototype retains a separate local ChromaDB index.

The configured distance threshold blocks LLM calls when evidence is weak. Only results from the selected citation URL are passed to the model.

### 4.5 Guardrails and answer orchestration

Before any external model call, the API:

1. Rejects likely PAN, Aadhaar, account number, OTP, email, and phone-number content.
2. Refuses recommendations, advice, and performance/return requests.
3. Declines statement-download questions because steps are absent from this five-page corpus.
4. Retrieves evidence for remaining factual questions.
5. Declines unsupported or low-confidence questions without calling the LLM.
6. Uses an LLM prompt that treats retrieved text as untrusted and limits the response to two short sentences.
7. Rejects URL-bearing, overlong, or performance-related generated text.
8. Adds exactly one source link and `Last updated from sources:` outside the model-generated text.

### 4.6 LLM provider adapter

Groq `openai/gpt-oss-20b` is the only answer model. Its model ID is in `config.yaml`; `GROQ_API_KEY` authenticates answer-generation requests. Groq Free plan availability and limits are organization-specific. Daily request exhaustion is distinguished from short-term request/token limits using Groq's rate-limit headers. OpenAI remains required for embeddings and may incur separate costs.

## 5. Configuration and secrets

Non-secret settings live in `config.yaml`: source allowlist, scraper limits, chunk size, retrieval `top_k` and distance threshold, Groq answer model, OpenAI embedding model, Neon pgvector provider, and embedding dimension.

Vercel environment variables:

- Required: `GROQ_API_KEY`, `OPENAI_API_KEY`, `DATABASE_URL`.

Use Vercel’s secret environment variable type; do not use a `NEXT_PUBLIC_` prefix. `DATABASE_URL` should be Neon’s pooled connection string and must be the same database populated by ingestion. `.env` is ignored and must never be committed. `.env.example` contains names only.

## 6. Data contracts

### Chunk record

```json
{
  "id": "hdfc_large_cap-0001",
  "text": "Expense ratio ...",
  "metadata": {
    "source_id": "hdfc_large_cap",
    "source_title": "HDFC Large Cap Fund Direct Growth",
    "source_url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
    "section": "Scheme facts",
    "fetched_at": "YYYY-MM-DD"
  }
}
```

The same metadata is stored with each Neon record. The answer date comes from the cited retrieval result, not the current date or the LLM.

### API response

```json
{
  "answer": "Factual response or safe refusal.",
  "source_url": "https://groww.in/mutual-funds/...",
  "last_updated": "YYYY-MM-DD"
}
```

## 7. Failures and operations

- Missing environment variables return a configuration error; provider or database failures are surfaced rather than converted to fabricated answers.
- Missing or empty Neon tables return a clear message to configure `DATABASE_URL` and run `ingest_neon.py`.
- Refreshes should be run from a trusted machine; verify the generated count and sample retrieval.
- Do not expose a public endpoint without Vercel Firewall rate limits or equivalent controls; requests can incur embedding and LLM costs.
- Review source freshness, privacy, provider terms, and deployment logs before sharing the app publicly.

## 8. Known limits

- The corpus is limited to five Groww pages and does not provide statement-download instructions.
- The requested 15–25 URL bibliography conflicts with the exact five-page fetch limit.
- Groww pages may be stale or incomplete; AMC/SEBI/AMFI institutional sources are not indexed.
- The reference link used for performance refusals is not part of the indexed corpus.
- This prototype is not a production financial-support service.
