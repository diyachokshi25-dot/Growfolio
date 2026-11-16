# HDFC mutual fund FAQ assistant

A facts-only FAQ prototype for five HDFC mutual-fund pages. The Vercel deployment uses a FastAPI API, a static browser UI, Gemini 3.5 Flash-Lite for answer generation, OpenAI embeddings, and Chroma Cloud. It does not provide investment advice or save questions and answers.

## Deploy on Vercel

1. Create a [Chroma Cloud](https://trychroma.com/) database. In its **Connect** panel, copy the API key, tenant ID, database name, and (if shown) regional host.
2. In Vercel, import `diyachokshi25-dot/Growfolio` from GitHub. Use the repository root and keep the detected Python runtime/default build settings. The root `app.py` exports the FastAPI `app`; `public/index.html` is the browser UI.
3. In **Project Settings → Environment Variables**, add these as **Secret** values for Production (and Preview if you use preview deployments):

   | Name | Value |
   | --- | --- |
   | `GEMINI_API_KEY` | Google AI Studio API key. Required for Gemini 3.5 Flash-Lite answer generation. |
   | `OPENAI_API_KEY` | OpenAI API key. Required for ingestion and query-time embeddings; this remains a separate API cost even when Gemini answers are on the free tier. |
   | `CHROMA_API_KEY` | Chroma Cloud API key |
   | `CHROMA_TENANT` | Chroma Cloud tenant ID |
   | `CHROMA_DATABASE` | Chroma Cloud database name |
   | `CHROMA_HOST` | Optional regional host; leave unset for the default AWS US East region. |

   Do not add a `NEXT_PUBLIC_` prefix, paste keys into source files, or commit `.env`.
   Create a Gemini key in [Google AI Studio](https://aistudio.google.com/apikey). Gemini's free tier has usage quotas and may use submitted content to improve Google products; never submit personal information.
4. Deploy. Vercel's Python runtime detects the FastAPI `app` in `app.py`; static files are served from `public/`.
5. Before asking questions, populate Chroma Cloud once from a trusted local machine:

   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   if (!(Test-Path .env)) { Copy-Item .env.example .env }
   # Fill the required keys in .env, then run:
   python ingest_cloud.py
   ```

   Ingestion fetches only the five allowlisted Groww pages, embeds them with the same configured OpenAI model used at query time, and stores chunks in the configured Chroma Cloud collection. It also writes inspectable stage artifacts under ignored `data/`.
6. Visit the Vercel deployment URL and ask a factual question. Gemini 3.5 Flash-Lite is the only answer model.

The API health check is `/api/health`. If Vercel environment variables change, redeploy so the new values are available to the deployment.

## Local options

- Run the Vercel-compatible API locally with `uvicorn app:app --reload`; it serves the API. Open `public/index.html` separately or use `vercel dev` to test the Vercel routing and static UI together.
- The previous Streamlit prototype remains in `streamlit_app.py`. To run it locally, install `requirements-streamlit.txt`, set its configured local embedding model and `GEMINI_API_KEY`, then run `streamlit run streamlit_app.py`. Its local ChromaDB index is separate from the Vercel Chroma Cloud collection.

## Scope and limits

- Only the five URLs in `config.yaml` are scraped; links found on those pages are not followed.
- OpenAI `text-embedding-3-small` and cosine distance are used for both ingestion and query retrieval. Switching the model requires a new Chroma collection and a fresh ingestion.
- Gemini 3.5 Flash-Lite is the sole answer model. Free-tier quotas and Google's free-tier data-use terms apply; OpenAI embeddings and Chroma Cloud have separate quotas or costs.
- Chroma Cloud is required for Vercel because serverless local files are not a durable vector database.
- The source corpus does not explain statement downloads; the assistant declines to invent steps.
- This is a demo, not a production financial-support service. Review source freshness, security, cost, rate limits, privacy, and provider terms before public use.
- Configure Vercel Firewall rate limits before sharing the public URL; otherwise visitors can incur embedding and LLM API costs.

**Disclaimer:** Facts only. This assistant does not provide investment, legal, or tax advice, make recommendations, or compare performance. Do not enter PAN, Aadhaar, account numbers, OTPs, phone numbers, or email addresses.
