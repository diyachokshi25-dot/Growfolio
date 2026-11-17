# Vercel implementation plan

This plan follows [architecture.md](./architecture.md). The deployed app uses FastAPI on Vercel, a static browser UI, OpenAI embeddings, and Neon Postgres with pgvector. Corpus ingestion is a separate local command; Vercel Functions never write to a local vector database.

## 1. Project structure and configuration

```text
app.py                    # FastAPI entrypoint; exports app
public/index.html         # Static FAQ interface
ingest_neon.py            # Manual allowlisted ingestion
neon_store.py             # Shared Neon connection and pgvector setup
config.yaml               # Sources, chunking, retrieval, model and collection settings
requirements.txt          # Vercel runtime dependencies
requirements-streamlit.txt# Optional legacy local UI dependencies
data/                     # Ignored local ingestion artifacts
tests/
```

Keep `.env`, `.venv/`, generated `data/`, caches, and API keys out of Git. Vercel secrets are set in Project Settings, not committed to the repository.

### Check

- Vercel detects the top-level FastAPI `app` in `app.py`.
- `/api/health` responds with `{"status":"ok"}`.
- `public/index.html` is served as the landing page.

## 2. Scraping documents

`ingest_neon.py` requests exactly the five URLs in `config.yaml`. It disables redirects, enforces response size and timeout limits, checks HTML content type, strips non-visible elements, and never fetches discovered links.

### Check

- All five sources succeed or ingestion stops with an explicit error.
- A redirect, non-HTML result, timeout, HTTP error, or oversized response cannot be marked successful.

## 3. Loading and validation

The script writes raw pages to `data/neon/01_raw/pages.json`, validates the exact source IDs and URLs, fetch status, HTML type, text, hashes, uniqueness, and fetch dates, then writes the loaded documents and manifest under `data/neon/01_raw/`.

### Check

- Exactly five unique approved records are loaded.
- Missing, malformed, duplicate, or unapproved data stops ingestion.

## 4. Chunking

The section-aware chunker preserves short fact labels with their values, keeps scheme chunks separate, and excludes performance/ranking sections. It saves stable chunk IDs and metadata to `data/neon/02_chunks/chunks.json`.

### Check

- Each chunk has a source ID, URL, section, and fetch date.
- Chunks remain attributable to one approved page.

## 5. Embedding

Ingestion and query retrieval both call OpenAI `text-embedding-3-small`. The script validates vector count, dimension, numeric values, and finite values, then saves the embedding stage artifact to `data/neon/03_embeddings/embeddings.json`.

### Check

- Vector count equals chunk count.
- A model change requires re-ingestion before retrieval.

## 6. Neon pgvector storage

Ingestion uses the Neon pooled connection string from `DATABASE_URL`. It enables pgvector, creates the configured-dimension `hdfc_chunks` table and cosine HNSW index, then replaces the indexed corpus inside one transaction. It checks the stored count, performs a sample query, and writes `data/neon/04_vector_db/manifest.json`. These artifacts are kept separate from the legacy Streamlit pipeline.

### Check

- Neon contains the complete current set of chunks and matching embedding-model metadata.
- A sample query returns the expected source metadata.
- Vercel and ingestion use the same Neon database and embedding model.

## 7. Retrieval, API, and UI

1. `POST /api/answer` validates a question (1–500 characters); Groq is the only accepted answer provider.
2. The API blocks likely PII, advice, performance, and unsupported statement-download questions before embeddings or LLM calls.
3. It generates an OpenAI query embedding, filters by named scheme, and requests configured top-k results from Neon using cosine distance.
4. It validates metadata, source allowlist, fetch date, distance, and the maximum-distance threshold.
5. It sends excerpts from only the cited source to Groq `openai/gpt-oss-20b`.
6. It rejects overlong, URL-bearing, or performance-related generated text.
7. The API returns answer text, one application-owned source URL, and the source fetch date.

The static browser UI renders the result and disclaimer. It must not persist query history or expose provider credentials.

### Check

- A named scheme is filtered to its approved page.
- Weak retrieval does not call an LLM.
- Each answer includes one source and `Last updated from sources:`.
- Groq, embedding, and Neon errors remain visible.

### UI design and interaction

`public/index.html` adapts the `growfolio_dolce_vita_edition` Stitch export supplied in `stitch_growfolio.zip`. Preserve its Italian garden / vintage stationery direction with a white canvas, pale-blue cabana stripes, butter-yellow accents, Bodoni Moda display headings, readable body/control type, and subtle botanical and postal details. Keep decorative art secondary to facts, controls, citations, and large corpus figures.

The page summarizes five approved source pages, four HDFC scheme pages, and five pipeline steps (load, chunk, embed, store, retrieve and cite). It lists the allowlisted sources, provides example-question chips, and sends the question with the fixed `groq` provider to `POST /api/answer`. It renders answer text safely, displays the returned source link and `Last updated from sources:` date, and shows request errors visibly. Do not copy the generated Stitch mock answer, mock source metadata, or unverified financial metrics into the live UI.

### Check

- The question form works with mouse and keyboard on mobile and desktop.
- Example chips populate the question field but do not submit a request.
- Groq GPT-OSS 20B is the only model shown or submitted for answer generation.
- The result card displays only the API response, one source link, and the fetch-date label.
- Failed or malformed responses show an error; they never fall back to a sample financial answer.
- Reduced-motion preferences disable decorative animation, and focus states remain visible.

## 8. Guardrails and edge-case checks

| Case | Expected behavior |
|---|---|
| PAN, Aadhaar, account, OTP, email, or phone-like input | Refuse before external model calls |
| Buy/sell or recommendation request | Polite refusal; no recommendation |
| Return, performance, or ranking request | Refuse performance claims |
| Statement-download question | Say the indexed pages do not contain the steps |
| Unknown fact or low retrieval confidence | Unsupported response; no LLM guess |
| Source outside allowlist or invalid date | Reject retrieved result |
| Missing API key or Neon configuration | Clear configuration error |
| Provider/embedding/Neon outage | Visible failure, not a fabricated answer |
| Too many sentences, generated URL, or performance claim | Replace with safe fallback |

### Deployment checklist

- Add `GROQ_API_KEY`, `OPENAI_API_KEY`, and `DATABASE_URL` as Vercel Secret variables. Use Neon’s pooled connection string for `DATABASE_URL`.
- Groq Free plan limits are organization-specific; daily request exhaustion displays “Limit for the day reached. Please try again after the daily quota resets.” Temporary rate limits display a retry-soon message. OpenAI remains required for embeddings and can incur separate API costs.
- Select Production and any desired Preview environments.
- Deploy, run `python ingest_neon.py` locally with the same `DATABASE_URL` and embedding key, and verify the ingestion manifest.
- Configure Vercel Firewall rate limits before sharing the public URL; requests can incur API costs.
- Never commit `.env` or paste secrets into chat or source code.
