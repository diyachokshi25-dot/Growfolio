# Vercel implementation plan

This plan follows [architecture.md](./architecture.md). The deployed app uses FastAPI on Vercel, a static browser UI, OpenAI embeddings, and Chroma Cloud. Corpus ingestion is a separate local command; Vercel Functions never write to a local vector database.

## 1. Project structure and configuration

```text
app.py                    # FastAPI entrypoint; exports app
public/index.html         # Static FAQ interface
ingest_cloud.py           # Manual allowlisted ingestion
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

`ingest_cloud.py` requests exactly the five URLs in `config.yaml`. It disables redirects, enforces response size and timeout limits, checks HTML content type, strips non-visible elements, and never fetches discovered links.

### Check

- All five sources succeed or ingestion stops with an explicit error.
- A redirect, non-HTML result, timeout, HTTP error, or oversized response cannot be marked successful.

## 3. Loading and validation

The script writes raw pages to `data/01_raw/pages.json`, validates the exact source IDs and URLs, fetch status, HTML type, text, hashes, uniqueness, and fetch dates, then writes `loaded_documents.json` and `load_manifest.json`.

### Check

- Exactly five unique approved records are loaded.
- Missing, malformed, duplicate, or unapproved data stops ingestion.

## 4. Chunking

The section-aware chunker preserves short fact labels with their values, keeps scheme chunks separate, and excludes performance/ranking sections. It saves stable chunk IDs and metadata to `data/02_chunks/chunks.json`.

### Check

- Each chunk has a source ID, URL, section, and fetch date.
- Chunks remain attributable to one approved page.

## 5. Embedding

Ingestion and query retrieval both call OpenAI `text-embedding-3-small`. The script validates vector count, dimension, numeric values, and finite values, then saves the embedding stage artifact to `data/03_embeddings/embeddings.json`.

### Check

- Vector count equals chunk count.
- A model change requires re-ingestion before retrieval.

## 6. Chroma Cloud storage

Ingestion uses `CHROMA_API_KEY`, `CHROMA_TENANT`, `CHROMA_DATABASE`, and optional `CHROMA_HOST`. It upserts stable chunk IDs into the configured collection, removes stale IDs, checks the stored count, performs a sample query, and writes the local vector manifest.

### Check

- Chroma Cloud contains the complete current set of chunks.
- A sample query returns the expected source metadata.
- Vercel uses the same collection and the same embedding model as ingestion.

## 7. Retrieval, API, and UI

1. `POST /api/answer` validates a question (1–500 characters) and selected provider.
2. The API blocks likely PII, advice, performance, and unsupported statement-download questions before embeddings or LLM calls.
3. It generates an OpenAI query embedding, filters by named scheme, and requests configured top-k results from Chroma Cloud.
4. It validates metadata, source allowlist, fetch date, distance, and the maximum-distance threshold.
5. It sends excerpts from only the cited source to the selected LLM.
6. It rejects overlong, URL-bearing, or performance-related generated text.
7. The API returns answer text, one application-owned source URL, and the source fetch date.

The static browser UI renders the result and disclaimer. It must not persist query history or expose provider credentials.

### Check

- A named scheme is filtered to its approved page.
- Weak retrieval does not call an LLM.
- Each answer includes one source and `Last updated from sources:`.
- Provider, embedding, and Chroma Cloud errors remain visible.

### UI design and interaction

`public/index.html` adapts the `growfolio_dolce_vita_edition` Stitch export supplied in `stitch_growfolio.zip`. Preserve its Italian garden / vintage stationery direction with a white canvas, pale-blue cabana stripes, butter-yellow accents, Bodoni Moda display headings, readable body/control type, and subtle botanical and postal details. Keep decorative art secondary to facts, controls, citations, and large corpus figures.

The page summarizes five approved source pages, four HDFC scheme pages, and five pipeline steps (load, chunk, embed, store, retrieve and cite). It lists the allowlisted sources, provides example-question chips, and sends only the question and selected answer provider to `POST /api/answer`. It renders answer text safely, displays the returned source link and `Last updated from sources:` date, and shows request errors visibly. Do not copy the generated Stitch mock answer, mock source metadata, or unverified financial metrics into the live UI.

### Check

- The question form works with mouse and keyboard on mobile and desktop.
- Example chips populate the question field but do not submit a request.
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
| Missing API key or Chroma Cloud configuration | Clear configuration error |
| Provider/embedding/Chroma Cloud outage | Visible failure, not a fabricated answer |
| Too many sentences, generated URL, or performance claim | Replace with safe fallback |

### Deployment checklist

- Add `OPENAI_API_KEY`, `CHROMA_API_KEY`, `CHROMA_TENANT`, and `CHROMA_DATABASE` as Vercel Secret variables. Add `CHROMA_HOST` only for a non-default region.
- Select Production and any desired Preview environments.
- Deploy, run `python ingest_cloud.py` locally with the same keys and collection, and verify the ingestion manifest.
- Configure Vercel Firewall rate limits before sharing the public URL; requests can incur API costs.
- Never commit `.env` or paste secrets into chat or source code.
