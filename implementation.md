# Phase-wise implementation

This plan follows [architecture.md](./architecture.md) and keeps the prototype small: local Streamlit UI, five approved source pages, Sentence Transformers, ChromaDB, and a configurable LLM.

## Phase 1 — Create the project directories

### Set up

Create the project and data directories:

```text
app.py
config.yaml
.env.example
.gitignore
requirements.txt
data/
  01_raw/
  02_chunks/
  03_embeddings/
  04_vector_db/
tests/
```

- Add source URLs, chunk size, embedding model, ChromaDB path/collection, retrieval threshold, and LLM provider/model settings to `config.yaml`.
- Default embedding model: `sentence-transformers/all-MiniLM-L6-v2`.
- Default vector database: ChromaDB.
- Configure Groq as the primary LLM provider, with the requested model read from `GROQ_MODEL`; support Gemini, OpenAI, Anthropic, and Mistral as alternatives.
- Keep `GROQ_API_KEY` and model selection in local environment settings. Ignore `.env`, `.venv/`, generated `data/`, and caches in `.gitignore`.

### Check

- The app can read its configuration.
- No real API key is in source control.
- Invalid provider or backend configuration produces a clear error.

## Phase 2 — Scrape the approved pages

### Implement

- Fetch only the five URLs in `config.yaml`; do not follow links or crawl other pages.
- Check HTTP status, content type, response size, and timeout. Reject redirects to unapproved URLs.
- Extract visible page text while preserving headings and relevant table text.
- Record each page’s source ID, title, URL, fetch date, status, and extracted text in `data/01_raw/pages.json`.
- Report fetch errors per URL. Do not mark a partial scrape as a successful refresh.

### Check

- Only allowlisted URLs are requested.
- Internal page links are never fetched.
- A failed page is reported, not silently saved as empty content.
- Raw records contain the original URL and fetch date.

## Phase 3 — Load and validate scraped documents

### Implement

- Read only the saved `data/01_raw/pages.json`; this phase performs no network requests.
- Validate the required fields, source allowlist, fetch status, non-empty text, and fetch date for every document.
- Normalize valid page records into a consistent in-memory `Document` structure for chunking.
- Reject duplicate source IDs/URLs and stop the pipeline if a required page is missing or invalid.
- Save normalized documents to `data/01_raw/loaded_documents.json`.
- Write a load manifest to `data/01_raw/load_manifest.json` with loaded document IDs, validation status, and content hashes.

### Check

- Loading a valid raw snapshot produces five normalized documents.
- Missing, failed, malformed, or unapproved documents produce a clear error.
- This phase never fetches a URL or follows a page link.

## Phase 4 — Chunk the documents

### Implement

- Use section-aware chunks that keep scheme facts and their labels together (for example, expense ratio/value or exit load/condition).
- Keep chunks for different schemes separate; attach source ID, scheme, section, source URL, and fetch date.
- Set a configurable maximum chunk size and split at section or paragraph boundaries.
- Exclude returns, performance, ranking, and return-calculator content from the answerable chunks.
- Save chunks with stable IDs to `data/02_chunks/chunks.json`.

### Check

- Fact labels remain with their values.
- Chunks never mix scheme sources.
- Performance and ranking content is excluded.
- Re-running on unchanged input produces stable chunk IDs.

## Phase 5 — Create embeddings

### Implement

- Load the configured Sentence Transformers model once for ingestion.
- Embed every chunk and save chunk ID, model name, and vector in `data/03_embeddings/embeddings.json`.
- Validate that each chunk has one finite vector and all vectors have the same dimension.
- Use the exact same configured model for question embeddings during retrieval.
- Store the model name/fingerprint in the ingestion manifest; require re-ingestion if it changes.

### Check

- Embedding count equals chunk count.
- Vectors are non-empty, finite, and consistently sized.
- A model mismatch blocks retrieval instead of mixing incompatible vectors.

## Phase 6 — Store data in ChromaDB

### Implement

- Create the ChromaDB collection using the configured path and collection name.
- Store chunk text, embedding, stable ID, and source metadata.
- Save a manifest with fetch dates, chunk/vector counts, embedding model, collection, and ingestion status under `data/04_vector_db/`.
- Validate the new index before making it active; preserve the last successful index if refresh fails.

### Check

- Stored record count matches chunk/vector counts.
- A test query returns text and the expected source metadata.
- The collection persists after app restart.
- A failed refresh does not replace a valid collection.

## Phase 7 — Retrieval logic and UI

### Retrieval and answer flow

1. Check the user’s question for PII and unsafe intent before embedding or sending it to a model.
2. Resolve a named scheme to a source filter when possible.
3. Embed the question with the configured ingestion model.
4. Query the configured ChromaDB collection using `top_k` and a distance threshold.
5. If evidence is weak or missing, return an unsupported response without calling the LLM.
6. For supported questions, send only the safe query and retrieved excerpts to the selected provider.
7. Validate the response; the app, not the LLM, selects one source URL and its fetch date.
8. Show the answer (maximum three sentences), one source link, and `Last updated from sources: YYYY-MM-DD`.

Groq is the primary provider; read `GROQ_API_KEY` and `GROQ_MODEL` from local environment settings. Verify the requested model ID `qwen/qwen3.8-27b` before release. Gemini, OpenAI, Anthropic, and Mistral are configurable alternatives. Surface provider errors instead of inventing an answer.

### UI

- Show a welcome message, three example questions, and the disclaimer: **“Facts-only. No investment advice.”**
- Provide an explicit **Run ingestion** action and show progress/errors for scraping, document loading, chunking, embedding, and indexing.
- Show artifact counts and source metadata; do not persist question/answer history.
- Keep any retrieval debug panel limited to corpus excerpts and metadata.

### Check

- A named-scheme question retrieves evidence from that scheme.
- A valid answer’s citation and date come from its supporting result.
- Weak retrieval does not call the LLM.
- The UI displays the required citation and update date for answers and refusals.

## Phase 8 — Edge cases and guardrail tests

Test each case and confirm the expected behavior before handoff:

| Input or failure | Expected behavior |
|---|---|
| PAN, Aadhaar, account number, OTP, email, or phone-like input | Reject before embedding/LLM; do not log or persist |
| “Should I buy/sell?” or a portfolio recommendation request | Polite refusal; no recommendation |
| Return, performance, or ranking question | No performance claim; link to an approved official factsheet/disclosure |
| Statement-download question not supported by sources | Say the steps are not in the corpus; do not infer them |
| Unknown fact or low retrieval confidence | Unsupported response; no LLM-generated guess |
| Question names one scheme but retrieved evidence is another | Reject or retrieve again with the correct scheme filter |
| Source timeout, HTTP error, or redirect outside allowlist | Report the source failure; do not mark ingestion complete |
| Embedding or ChromaDB error | Report the failed phase; preserve the last successful index |
| Missing API key, invalid model, timeout, or provider error | Show a clear error; do not return a fabricated answer |
| Model gives too many sentences, unsupported content, or a URL | Reject/replace with a safe fallback; citation remains application-owned |
| Source fetch date is old or missing | Show the recorded date or decline; never substitute today’s date |

### Guardrail acceptance checks

- No unsafe query reaches the embedding model or external LLM.
- Questions and answers are not written to persistent storage or logs.
- Every user-facing answer/refusal is at most three sentences, has one relevant source link, and includes the required update line.
- Provider, ingestion, and retrieval failures are visible and never produce success-shaped fallbacks.

## Handoff checklist

- Run the focused tests for each phase and the end-to-end guardrail cases.
- Confirm only approved pages were fetched and all stage artifacts are inspectable.
- Confirm retrieval uses the same embedding model and vector database configuration as ingestion.
- Provide setup instructions, a source list, 5–10 sample Q&A items, and the UI disclaimer.
- Provide a hosted link or a demo video of no more than three minutes; otherwise document local run steps.

## Open decisions

- The requirement asks for 15–25 source URLs but currently limits scraping to five pages. Decide whether to list additional non-indexed official references or approve more pages for ingestion.
- Confirm whether the specified Groww pages meet the institutional-source requirement for AMC/SEBI/AMFI citations.
- Approve official educational and factsheet links for refusals.
- Verify availability of Groq model `qwen/qwen3.8-27b`.
