# HDFC mutual fund FAQ assistant

A small Streamlit RAG prototype for factual FAQs about the HDFC Mutual Fund overview and four requested schemes. Answers are limited to three sentences, cite a source URL, and show the source fetch date. The assistant does not provide recommendations or performance comparisons.

## Run locally

1. Use Python 3.11 or newer.
2. Create and activate a virtual environment.
3. Install dependencies: `pip install -r requirements.txt`.
4. Add the API key for your chosen provider to `.env` (copy `.env.example` as a starting point). The app loads `.env` at startup; existing environment variables take precedence. Keep `.env` private and never commit it.
5. Start with `streamlit run app.py`.
6. In the sidebar, click **Run all ingestion phases**. This fetches only the five configured URLs and writes each stage under `data/`.
7. Ask a factual scheme question. Set the desired provider in the sidebar.

## Scope and phases

The source allowlist is in `config.yaml`. The ingester makes direct requests to those five Groww URLs and does not follow or fetch linked pages.

1. **Scraping** — fetched page text and source metadata in `data/01_raw/pages.json`; only the five configured URLs are requested.
2. **Document loading** — reads and validates the saved raw pages without network access, then writes `loaded_documents.json` and `load_manifest.json` under `data/01_raw/`.
3. **Chunking** — section-aware text chunks (configured by `chunking.max_chars`) in `data/02_chunks/chunks.json`; common returns/ranking sections are excluded.
4. **Embedding** — embeddings are created with the configured Sentence Transformers model, validated, and persisted with model fingerprint and dimension in `data/03_embeddings/embeddings.json`.
5. **Vector DB** — ChromaDB stores chunks and metadata in a generation-specific collection under `data/04_vector_db/chroma`; the manifest points to the validated active collection.
6. **Retrieval and answer** — query embedding uses the same configured model and the same Chroma collection. Gemini, OpenAI, Anthropic, and Mistral are selectable in the sidebar.

## Privacy and safety

The app does not save questions or answers. Avoid entering PAN, Aadhaar, account numbers, OTPs, email addresses, or phone numbers; likely identifiers are rejected before retrieval. Provider keys are read from environment variables and sent only to the selected model API. Do not expose this demo publicly without adding appropriate secret management, rate limits, privacy review, and deployment controls.

**Disclaimer:** Facts only. This assistant is for general scheme information and does not provide investment, legal, or tax advice, make recommendations, or compare performance. Scheme details can change; verify them on the linked source page. Do not enter PAN, Aadhaar, account numbers, OTPs, email addresses, or phone numbers.

## Known limits

- The corpus is intentionally restricted to the five requested Groww pages. `sources.csv` lists those five plus the HDFC AMC website as an un-fetched reference link used only for the performance-question refusal. The requested 15–25 URL bibliography cannot be truthfully supplied without consulting additional pages; those pages are not fetched or indexed in this prototype.
- Groww pages can change and may contain stale or incomplete facts. Refreshing ingestion overwrites the local corpus.
- “How to download statements” is not covered by the five-page corpus, so the assistant declines to give steps.
- A Groww source URL does not imply the assistant has verified facts with the AMC, SEBI, or AMFI. Apart from the reference-only AMC website link for performance questions, official AMC/SEBI/AMFI sources are not part of this demo corpus.
- The app requires one configured LLM API key for answer generation. Ingestion uses a local embedding model and may download model weights on first use.
- Performance and ranking content is excluded from chunking; the assistant refuses performance questions and does not calculate returns.
- This is a local demonstration, not a production financial-support service.
